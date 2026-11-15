"""Analyze an exported audio file (TW-1504): noise floor, levels and silences in project seconds.

The Cubase API cannot read track contents, so the analysis works on a file: an export between the locators,
which TW-1501 showed is aligned with the project to the sample (project time = left locator + file time).
Read-only and outside Cubase: nothing is sent to the script. Needs ``[analysis] enabled`` (TW-1502).
"""

from __future__ import annotations

from pathlib import Path

from trackwright.analysis import (
    SilenceCriteria,
    decoded,
    find_silences,
    measure,
    measure_loudness,
    noise_floor,
    probe,
    sound_levels,
)
from trackwright.analysis.detect import threshold
from trackwright.analysis.reader import SILENT_DB
from trackwright.analysis.speech import SpeechCriteria, detect_speech
from trackwright.core.base import ServiceBase
from trackwright.core.models import AnalysisOut, LoudnessOut, SilenceOut, SpeechOut, SpeechRegionOut
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
        path = self._audio_path(file)
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
        with decoded(path) as readable:
            info = probe(readable)
            self.policy.check_analysis(info.seconds)  # TOO_LONG before reading any sample
            levels = measure(readable)
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

    def measure_loudness(self, file: str) -> LoudnessOut:
        """BS.1770 loudness, loudness range and true peak of a file (TW-1603)."""
        self.policy.check_analysis()
        path = self._audio_path(file)
        with decoded(path) as readable:
            self.policy.check_analysis(probe(readable).seconds)
            result = measure_loudness(readable)
        info = result.info
        notes = []
        if info.channels == 1:
            notes.append("mono file: measured as one channel (3 dB lower than the same signal on two channels)")
        if readable_note := ("decoded with afconvert" if path.suffix.lower() in {".m4a", ".aac", ".mp4"} else ""):
            notes.append(readable_note)
        return LoudnessOut(
            file=str(path),
            format=info.format,
            subtype=info.subtype,
            sample_rate=info.rate,
            channels=info.channels,
            seconds=round(info.seconds, 4),
            integrated_lufs=result.integrated_lufs,
            momentary_max_lufs=result.momentary_max_lufs,
            short_term_max_lufs=result.short_term_max_lufs,
            loudness_range_lu=result.loudness_range_lu,
            sample_peak_dbfs=_db(result.sample_peak_dbfs),
            true_peak_dbtp=_db(result.true_peak_dbtp),
            notes=notes,
        )

    def _audio_path(self, file: str) -> Path:
        path = Path(file).expanduser()
        if not path.is_absolute():
            raise PreconditionFailedError("file must be an absolute path", code="BAD_REQUEST", details={"file": file})
        return path

    def detect_speech(
        self,
        file: str,
        *,
        start: str = "0",
        on_db: float = 12.0,
        off_db: float = 6.0,
        hangover: float = 0.15,
        merge_gap: float = 0.2,
        min_region: float = 0.08,
        offset: int = 0,
        limit: int = 100,
    ) -> SpeechOut:
        """Speech regions of a voice track's export, in project seconds (TW-1604)."""
        self.policy.check_analysis()
        path = self._audio_path(file)
        origin = parse_seconds(start)
        if origin is None:
            raise PreconditionFailedError("start looks like '2.5', '1:30' or '0:01:30.000'", code="BAD_TIME")
        criteria = SpeechCriteria(
            on_db=on_db, off_db=off_db, hangover=hangover, merge_gap=merge_gap, min_region=min_region
        )
        criteria.check()
        with decoded(path) as readable:
            self.policy.check_analysis(probe(readable).seconds)
            result = detect_speech(readable, criteria)
        info = result.info
        notes = []
        if result.contrast_db is not None and result.contrast_db < on_db:
            notes.append(
                f"little contrast ({result.contrast_db:.1f} dB) between the noise and the loudest parts: "
                "is this a voice track exported alone?"
            )
        notes.append("energy detector: loud non-speech sounds in the voice band (laughs, coughs) count as activity")
        limit = max(1, min(limit, MAX_SILENCES))
        return SpeechOut(
            file=str(path),
            sample_rate=info.rate,
            channels=info.channels,
            seconds=round(info.seconds, 4),
            start=format_seconds(origin),
            start_seconds=origin,
            noise_floor_db=result.noise_floor_db,
            on_threshold_db=result.on_threshold_db,
            off_threshold_db=result.off_threshold_db,
            contrast_db=result.contrast_db,
            criteria={
                "on_db": on_db,
                "off_db": off_db,
                "hangover": hangover,
                "merge_gap": merge_gap,
                "min_region": min_region,
            },
            total=len(result.regions),
            speech_seconds=round(result.speech_seconds, 3),
            regions=[
                SpeechRegionOut(
                    start=format_seconds(origin + r.start),
                    end=format_seconds(origin + r.end),
                    start_seconds=round(origin + r.start, 4),
                    end_seconds=round(origin + r.end, 4),
                    seconds=round(r.seconds, 4),
                    level_db=r.level_db,
                    confidence=r.confidence,
                )
                for r in result.regions[offset : offset + limit]
            ],
            notes=notes,
        )
