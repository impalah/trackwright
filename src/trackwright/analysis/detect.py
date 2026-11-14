"""Noise floor and silences from window levels (pure functions, no file access)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from trackwright.analysis.reader import SILENT_DB, Levels
from trackwright.errors import PreconditionFailedError

FLOOR_PERCENTILE = 10.0
SOUND_PERCENTILE = 90.0


def noise_floor(levels: Levels, percentile: float = FLOOR_PERCENTILE) -> float | None:
    """A low percentile of the window levels, leaving out digital silence; None if there is no sound at all.

    TW-1501: an export holds exact zeros before and after the events; counting them would give -240 dBFS.
    """
    sound = levels.rms_db[~levels.digital_silence]
    if sound.size == 0:
        return None
    return float(np.percentile(sound, percentile))


@dataclass(frozen=True, slots=True)
class SilenceCriteria:
    """How quiet and how long a span must be to count as a silence.

    ``threshold_db`` is absolute (dBFS); when it is None the threshold is ``noise_floor + above_floor_db``,
    which does not depend on faders or pan law (TW-1501: a centered mono track exports 3 dB lower).
    """

    min_seconds: float = 2.0
    above_floor_db: float = 10.0
    threshold_db: float | None = None
    padding_seconds: float = 0.25
    """Kept before and after each silence so the edges of words are not cut (not at the file's ends)."""
    merge_gap_seconds: float = 0.3
    """Louder blips shorter than this inside a silence (a click, a breath) do not break it."""

    def check(self) -> None:
        if self.min_seconds <= 0:
            raise PreconditionFailedError("min_seconds must be greater than 0", code="BAD_REQUEST")
        if self.padding_seconds < 0 or self.merge_gap_seconds < 0:
            raise PreconditionFailedError("padding and merge gap cannot be negative", code="BAD_REQUEST")
        if self.threshold_db is None and self.above_floor_db < 0:
            raise PreconditionFailedError("above_floor_db cannot be negative", code="BAD_REQUEST")


@dataclass(frozen=True, slots=True)
class Silence:
    """A span to remove, in seconds from the start of the file, padding already applied."""

    start: float
    end: float
    level_db: float
    """Mean level of the span (SILENT_DB when it is digital silence only)."""
    digital: bool
    """Every window of the span is exact digital silence."""

    @property
    def seconds(self) -> float:
        return self.end - self.start


def threshold(levels: Levels, criteria: SilenceCriteria) -> float | None:
    """The threshold the criteria give for these levels, or None when only digital silence can count.

    A relative threshold needs contrast: when ``noise_floor + above_floor_db`` reaches the level of the
    sound itself (90th percentile), the file has no quieter part to call silence (a continuous tone, a file
    that is all noise) and None is returned instead of marking everything as silence.
    """
    if criteria.threshold_db is not None:
        return criteria.threshold_db
    floor = noise_floor(levels)
    if floor is None:
        return None
    limit = floor + criteria.above_floor_db
    sound = float(np.percentile(levels.rms_db[~levels.digital_silence], SOUND_PERCENTILE))
    return limit if limit < sound else None


def _runs(mask: list[bool]) -> list[tuple[int, int]]:
    """[start, end) index ranges where ``mask`` is True."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate([*mask, False]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            runs.append((start, index))
            start = None
    return runs


def find_silences(levels: Levels, criteria: SilenceCriteria | None = None) -> list[Silence]:
    """Silences of at least ``min_seconds`` (before padding), ordered and not overlapping."""
    criteria = criteria or SilenceCriteria()
    criteria.check()
    count = levels.rms_db.size
    if count == 0:
        return []
    limit = threshold(levels, criteria)
    quiet = levels.digital_silence.copy() if limit is None else (levels.rms_db < limit) | levels.digital_silence
    runs = _runs([bool(q) for q in quiet])
    merged: list[tuple[int, int]] = []
    for start, end in runs:
        gap = levels.window_start(start) - levels.window_end(merged[-1][1] - 1) if merged else None
        if gap is not None and gap < criteria.merge_gap_seconds:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    total = levels.seconds
    silences: list[Silence] = []
    for start, end in merged:
        begin, finish = levels.window_start(start), levels.window_end(end - 1)
        if finish - begin < criteria.min_seconds:
            continue
        cut_begin = begin if start == 0 else begin + criteria.padding_seconds
        cut_end = finish if end == count else finish - criteria.padding_seconds
        if cut_end - cut_begin <= 0:
            continue
        span = levels.rms_db[start:end]
        digital = bool(levels.digital_silence[start:end].all())
        power = float(np.mean(np.power(10.0, span / 10.0)))
        level = SILENT_DB if digital or power <= 0 else float(10.0 * np.log10(power))
        silences.append(
            Silence(
                start=round(cut_begin, 4), end=round(min(cut_end, total), 4), level_db=round(level, 2), digital=digital
            )
        )
    return silences
