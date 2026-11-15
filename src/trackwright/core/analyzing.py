"""Analyze an exported audio file (TW-1504): noise floor, levels and silences in project seconds.

The Cubase API cannot read track contents, so the analysis works on a file: an export between the locators,
which TW-1501 showed is aligned with the project to the sample (project time = left locator + file time).
Read-only and outside Cubase: nothing is sent to the script. Needs ``[analysis] enabled`` (TW-1502).
"""

from __future__ import annotations

from pathlib import Path

from trackwright.analysis import SilenceCriteria, find_silences, measure, noise_floor, probe, sound_levels
from trackwright.analysis.detect import threshold
from trackwright.analysis.reader import SILENT_DB
from trackwright.core.base import ServiceBase
from trackwright.core.models import AnalysisOut, SilenceOut
from trackwright.core.timefmt import format_seconds, parse_seconds
from trackwright.errors import PreconditionFailedError

MAX_SILENCES = 500


def _db(value: float | None) -> float | None:
    return None if value is None or value <= SILENT_DB else round(value, 2)


class AnalyzingMixin(ServiceBase):
    def analyze_audio(
        self,
        file: str,
        *,
        start: str = "0",
        min_seconds: float = 2.0,
        above_floor_db: float = 10.0,
        threshold_db: float | None = None,
        padding_seconds: float = 0.25,
        merge_gap_seconds: float = 0.05,
        offset: int = 0,
        limit: int = 100,
    ) -> AnalysisOut:
        self.policy.check_analysis()
        path = Path(file).expanduser()
        if not path.is_absolute():
            raise PreconditionFailedError("file must be an absolute path", code="BAD_REQUEST", details={"file": file})
        origin = parse_seconds(start)
        if origin is None:
            raise PreconditionFailedError("start looks like '2.5', '1:30' or '0:01:30.000'", code="BAD_TIME")
        criteria = SilenceCriteria(
            min_seconds=min_seconds,
            above_floor_db=above_floor_db,
            threshold_db=threshold_db,
            padding_seconds=padding_seconds,
            merge_gap_seconds=merge_gap_seconds,
        )
        criteria.check()
        info = probe(path)
        self.policy.check_analysis(info.seconds)  # TOO_LONG before reading any sample
        levels = measure(path)
        silences = find_silences(levels, criteria)
        limit = max(1, min(limit, MAX_SILENCES))
        page = silences[offset : offset + limit]
        used = threshold(levels, criteria)
        quiet, typical = sound_levels(levels, used)
        notes = []
        if used is None:
            notes.append(
                "no contrast between the quietest and loudest parts: only digital silence (exact zeros) was "
                "counted; give threshold_db to use an absolute threshold"
            )
        notes.append("levels are those of the export (pan law, faders and inserts included), not of the source file")
        return AnalysisOut(
            file=str(path),
            format=info.format,
            subtype=info.subtype,
            sample_rate=info.rate,
            channels=info.channels,
            seconds=round(info.seconds, 4),
            start=format_seconds(origin),
            start_seconds=origin,
            noise_floor_db=_db(noise_floor(levels)),
            threshold_db=_db(used),
            quiet_sound_db=_db(quiet),
            sound_db=_db(typical),
            peak_db=_db(levels.peak_db),
            rms_db=_db(levels.rms_total_db),
            criteria={
                "min_seconds": criteria.min_seconds,
                "above_floor_db": criteria.above_floor_db,
                "threshold_db": criteria.threshold_db,
                "padding_seconds": criteria.padding_seconds,
                "merge_gap_seconds": criteria.merge_gap_seconds,
                "window_seconds": round(levels.window, 4),
            },
            total=len(silences),
            total_seconds=round(sum(s.seconds for s in silences), 3),
            silences=[
                SilenceOut(
                    start=format_seconds(origin + s.start),
                    end=format_seconds(origin + s.end),
                    start_seconds=round(origin + s.start, 4),
                    end_seconds=round(origin + s.end, 4),
                    seconds=round(s.seconds, 4),
                    level_db=_db(s.level_db),
                    digital=s.digital,
                )
                for s in page
            ],
            notes=notes,
        )
