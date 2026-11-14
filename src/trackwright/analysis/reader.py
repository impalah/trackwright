"""Reading audio files in blocks into per-window levels (soundfile + numpy)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf

from trackwright.errors import NotFoundError, PreconditionFailedError

DEFAULT_WINDOW = 0.020  # seconds; short enough for the gaps of speech, long enough to smooth a waveform
SILENT_DB = -240.0  # level reported for exact digital silence (log of zero)
BLOCK_WINDOWS = 500  # windows read per block (10 s at the default window)


@dataclass(frozen=True, slots=True)
class AudioInfo:
    """What the file header says; nothing has been read beyond it."""

    format: str
    subtype: str
    rate: int
    channels: int
    frames: int

    @property
    def seconds(self) -> float:
        return self.frames / self.rate if self.rate else 0.0


@dataclass(frozen=True, slots=True)
class Levels:
    """One level per window of the whole file, all channels together.

    The level of a window is the RMS over its samples **and** its channels (power average): content on one
    channel counts, and out-of-phase channels do not cancel as they would in a mono sum.
    """

    info: AudioInfo
    window: float
    rms_db: npt.NDArray[np.float64]
    digital_silence: npt.NDArray[np.bool_]
    """True where every sample of the window is exactly zero (before or after an event, TW-1501)."""
    peak_db: float
    rms_total_db: float

    @property
    def seconds(self) -> float:
        return self.info.seconds

    def window_start(self, index: int) -> float:
        return index * self.window

    def window_end(self, index: int) -> float:
        return min((index + 1) * self.window, self.seconds)


def _db(value: float) -> float:
    return 20.0 * math.log10(value) if value > 0 else SILENT_DB


def _open_error(path: Path, exc: Exception) -> PreconditionFailedError:
    return PreconditionFailedError(
        f"not an audio file soundfile can read (WAV, AIFF, FLAC, Ogg): {path.name}",
        code="BAD_AUDIO",
        details={"path": str(path), "reason": str(exc)},
    )


def probe(path: Path) -> AudioInfo:
    """The header of ``path``: NOT_FOUND if it is not a file, BAD_AUDIO if it is not readable audio."""
    if not path.is_file():
        raise NotFoundError(f"audio file not found: {path}", code="NOT_FOUND", details={"path": str(path)})
    try:
        info = sf.info(str(path))
    except (RuntimeError, sf.LibsndfileError) as exc:  # LibsndfileError is a RuntimeError in soundfile
        raise _open_error(path, exc) from exc
    return AudioInfo(
        format=str(info.format),
        subtype=str(info.subtype),
        rate=int(info.samplerate),
        channels=int(info.channels),
        frames=int(info.frames),
    )


def measure(path: Path, *, window: float = DEFAULT_WINDOW) -> Levels:
    """Read ``path`` in blocks and return the level of every window (the last one may be shorter)."""
    if not 0.001 <= window <= 1.0:
        raise PreconditionFailedError("the analysis window must be between 1 ms and 1 s", code="BAD_REQUEST")
    info = probe(path)
    hop = max(1, round(info.rate * window))
    levels: list[npt.NDArray[np.float64]] = []
    zeros: list[npt.NDArray[np.bool_]] = []
    peak = 0.0
    energy = 0.0
    count = 0
    try:
        for block in sf.blocks(str(path), blocksize=hop * BLOCK_WINDOWS, dtype="float64", always_2d=True):
            samples = np.asarray(block, dtype=np.float64)
            squares = samples * samples
            peak = max(peak, float(np.abs(samples).max()))
            energy += float(squares.sum())
            count += samples.size
            full = samples.shape[0] // hop * hop
            parts = [squares[:full].reshape(-1, hop * samples.shape[1])]
            if full < samples.shape[0]:  # only in the last block: a shorter last window
                parts.append(squares[full:].reshape(1, -1))
            for part in parts:
                mean = part.mean(axis=1)
                with np.errstate(divide="ignore"):
                    levels.append(np.where(mean > 0, 10.0 * np.log10(mean), SILENT_DB))
                zeros.append(mean == 0)
    except (RuntimeError, sf.LibsndfileError) as exc:
        raise _open_error(path, exc) from exc
    rms_db = np.concatenate(levels) if levels else np.zeros(0, dtype=np.float64)
    silent = np.concatenate(zeros) if zeros else np.zeros(0, dtype=np.bool_)
    return Levels(
        info=info,
        window=hop / info.rate,
        rms_db=rms_db,
        digital_silence=silent,
        peak_db=_db(peak),
        rms_total_db=_db(math.sqrt(energy / count)) if count else SILENT_DB,
    )
