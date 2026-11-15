"""Pure helpers of the final quality control (TW-1611): level changes between sections, codec and bit rate.

**Level changes between sections.** The short-term loudness (3 s windows every 100 ms) is placed at the
middle of its window and grouped in sections (10 s by default). Pauses do not count: windows quieter than
the integrated loudness minus 20 LU, or digital silence, are left out, and a section with less than a third
of its windows left is "mostly pause" and has no level. A change is reported where two consecutive sections
with a level differ by ``jump_lu`` or more: a new voice much louder or quieter, music that comes in hot, a
segment recorded at another level. A slow drift over many sections is not a change between sections.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

STEP = 0.1  # seconds between short-term values
WINDOW = 3.0  # short-term window
PAUSE_BELOW_LU = 20.0  # windows this far under the integrated loudness are pauses
MIN_SPEECH_SHARE = 1 / 3

CODECS = {
    ".wav": "wav",
    ".wave": "wav",
    ".mp3": "mp3",
    ".m4a": "aac",
    ".aac": "aac",
    ".mp4": "aac",
    ".flac": "flac",
    ".aif": "aiff",
    ".aiff": "aiff",
    ".ogg": "ogg",
    ".opus": "opus",
}
PCM = frozenset({"wav", "aiff", "flac"})


@dataclass(frozen=True, slots=True)
class LevelChange:
    at: float
    """Seconds from the start of the file: the boundary between the two sections."""
    before_lufs: float
    after_lufs: float

    @property
    def change_lu(self) -> float:
        return self.after_lufs - self.before_lufs


def section_levels(
    short_term: npt.NDArray[np.float64], integrated: float | None, section: float = 10.0
) -> list[float | None]:
    """Median short-term loudness of each section (None for a section that is mostly pause)."""
    if short_term.size == 0 or integrated is None:
        return []
    centers = np.arange(short_term.size) * STEP + WINDOW / 2
    floor = integrated - PAUSE_BELOW_LU
    count = int(np.ceil((centers[-1] + 1e-9) / section)) or 1
    levels: list[float | None] = []
    for index in range(count):
        inside = (centers >= index * section) & (centers < (index + 1) * section)
        values = short_term[inside]
        kept = values[np.isfinite(values) & (values >= floor)]
        levels.append(float(np.median(kept)) if values.size and kept.size >= values.size * MIN_SPEECH_SHARE else None)
    return levels


def level_changes(
    short_term: npt.NDArray[np.float64], integrated: float | None, *, section: float = 10.0, jump_lu: float = 6.0
) -> list[LevelChange]:
    """Boundaries where consecutive sections (both with a level) differ by ``jump_lu`` or more."""
    levels = section_levels(short_term, integrated, section)
    changes = []
    for index in range(1, len(levels)):
        before, after = levels[index - 1], levels[index]
        if before is not None and after is not None and abs(after - before) >= jump_lu:
            changes.append(LevelChange(at=index * section, before_lufs=round(before, 2), after_lufs=round(after, 2)))
    return changes


def loudest_moment(short_term: npt.NDArray[np.float64]) -> float | None:
    """Middle of the loudest 3 s window, in seconds from the start of the file."""
    finite = np.where(np.isfinite(short_term), short_term, -np.inf)
    if finite.size == 0 or not np.isfinite(finite.max()):
        return None
    return float(np.argmax(finite)) * STEP + WINDOW / 2


def codec_of(path: Path) -> str | None:
    """The codec a delivery profile names, from the file's extension (``.m4a`` is taken as AAC)."""
    return CODECS.get(path.suffix.lower())


def bitrate_kbps(size_bytes: int, seconds: float, codec: str | None) -> float | None:
    """Average bit rate of a compressed file (size over duration); None for PCM or an unknown codec."""
    if codec is None or codec in PCM or seconds <= 0:
        return None
    return round(size_bytes * 8 / seconds / 1000, 1)
