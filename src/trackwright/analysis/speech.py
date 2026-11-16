"""Voice activity detection (TW-1604): where a voice track has speech.

Each voice is on its own track (exported alone with solo), so the question is only "speech or not", never
"who". The detector works on the level of the speech band and decides with hysteresis:

1. **Speech band:** the signal (channels averaged) goes through a band-pass filter, 100 Hz to 4 kHz, so a
   mains hum below it or hiss above it does not count as a voice.
2. **Levels:** RMS of that band every 10 ms, lightly smoothed; the noise floor is their 10th percentile,
   leaving out digital silence (frames under -120 dBFS: Cubase exports silence as -166 dBFS residue, TW-1616).
3. **Hysteresis:** speech starts when the level rises ``on_db`` above the floor and lasts while it stays
   ``off_db`` above it, so the dips between syllables do not split a word.
4. **Clean-up:** a hangover after each region (word endings decay slowly), gaps shorter than ``merge_gap``
   joined, regions shorter than ``min_region`` dropped (clicks, bumps), and regions more than ``faint_db``
   below the typical speech level dropped: on a real episode (TW-1604) a 0.37 s noise at -52 dB inside a
   pause, 39 dB below the voice, passed the noise-floor test and split the pause in two.

Every region has its mean level and a confidence (how far above the floor it is). This is an energy
detector: a loud non-speech sound in the voice band (a laugh, a cough, a door) counts as activity, which is
what ducking and leveling need; telling words apart is the transcription's job (TW-1630).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf
from scipy import signal

from trackwright.analysis.reader import DIGITAL_SILENCE_DB, SILENT_DB, AudioInfo, probe
from trackwright.errors import PreconditionFailedError

FRAME = 0.010
SMOOTH_FRAMES = 3
BAND = (100.0, 4000.0)
READ_SECONDS = 10.0
FLOOR_PERCENTILE = 10.0
SOUND_PERCENTILE = 90.0
CONFIDENT_MARGIN_DB = 30.0
DIGITAL_POWER = 10 ** (DIGITAL_SILENCE_DB / 10)  # TW-1616: Cubase's silence is -166 dBFS, not zeros


@dataclass(frozen=True, slots=True)
class SpeechCriteria:
    on_db: float = 12.0
    """Speech starts this far above the noise floor."""
    off_db: float = 6.0
    """And continues while the level stays this far above it."""
    hangover: float = 0.15
    """Seconds added after each region: word endings decay below the threshold before they are inaudible."""
    merge_gap: float = 0.2
    """Gaps shorter than this inside speech are joined (pauses between words)."""
    min_region: float = 0.08
    """Shorter regions are dropped (clicks, bumps)."""
    faint_db: float = 30.0
    """Regions this far below the typical speech level (duration-weighted median) are dropped."""

    def check(self) -> None:
        if self.off_db < 0 or self.on_db < self.off_db:
            raise PreconditionFailedError("need 0 <= off_db <= on_db", code="BAD_REQUEST")
        if min(self.hangover, self.merge_gap, self.min_region, self.faint_db) < 0:
            raise PreconditionFailedError("hangover, merge_gap and min_region cannot be negative", code="BAD_REQUEST")


@dataclass(frozen=True, slots=True)
class SpeechRegion:
    start: float
    end: float
    level_db: float
    """Mean level of the speech band in the region (dBFS)."""
    confidence: float
    """0..1: how far above the noise floor the region is (30 dB or more is 1)."""

    @property
    def seconds(self) -> float:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class SpeechActivity:
    info: AudioInfo
    noise_floor_db: float | None
    """10th percentile of the speech-band levels, digital silence left out; None for a silent file."""
    on_threshold_db: float | None
    off_threshold_db: float | None
    contrast_db: float | None
    """90th minus 10th percentile: under ``on_db`` there is no clear speech to find."""
    regions: list[SpeechRegion]
    speech_level_db: float | None = None
    """Typical speech level: the duration-weighted median of the regions' levels."""
    faint_dropped: int = 0
    """Regions dropped for being ``faint_db`` below the typical speech level."""

    @property
    def speech_seconds(self) -> float:
        return sum(r.seconds for r in self.regions)


def band_levels(path: Path) -> tuple[AudioInfo, npt.NDArray[np.float64], npt.NDArray[np.bool_]]:
    """Level of the speech band every 10 ms (dBFS) and whether each frame is digital silence."""
    info = probe(path)
    rate = info.rate
    frame = max(1, round(rate * FRAME))
    high = min(BAND[1], rate / 2 * 0.9)
    sos = signal.butter(4, [BAND[0], high], btype="bandpass", fs=rate, output="sos")
    state = signal.sosfilt_zi(sos) * 0.0
    pending = np.zeros(0)
    pending_raw = np.zeros(0)
    levels: list[npt.NDArray[np.float64]] = []
    zeros: list[npt.NDArray[np.bool_]] = []
    block = max(frame, round(rate * READ_SECONDS) // frame * frame)
    try:
        for chunk in sf.blocks(str(path), blocksize=block, dtype="float64", always_2d=True):
            mono = np.asarray(chunk, dtype=np.float64).mean(axis=1)
            filtered, state = signal.sosfilt(sos, mono, zi=state)
            data = np.concatenate([pending, filtered])
            raw = np.concatenate([pending_raw, mono])
            full = len(data) // frame * frame
            if full:
                power = (data[:full] ** 2).reshape(-1, frame).mean(axis=1)
                with np.errstate(divide="ignore"):
                    levels.append(np.where(power > 0, 10 * np.log10(power), SILENT_DB))
                zeros.append((raw[:full].reshape(-1, frame) ** 2).mean(axis=1) < DIGITAL_POWER)
            pending, pending_raw = data[full:], raw[full:]
    except RuntimeError as exc:  # soundfile read errors
        raise PreconditionFailedError(
            f"could not read {path.name} to the end", code="BAD_AUDIO", details={"path": str(path), "reason": str(exc)}
        ) from exc
    level = np.concatenate(levels) if levels else np.zeros(0)
    silent = np.concatenate(zeros) if zeros else np.zeros(0, dtype=np.bool_)
    if level.size >= SMOOTH_FRAMES:
        power = 10 ** (level / 10)
        smooth = np.convolve(power, np.ones(SMOOTH_FRAMES) / SMOOTH_FRAMES, mode="same")
        with np.errstate(divide="ignore"):
            level = np.where(smooth > 0, 10 * np.log10(smooth), SILENT_DB)
    return info, level, silent


def _hysteresis(level: npt.NDArray[np.float64], on: float, off: float) -> list[tuple[int, int]]:
    regions: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(level):
        if start is None and value >= on:
            start = index
        elif start is not None and value < off:
            regions.append((start, index))
            start = None
    if start is not None:
        regions.append((start, len(level)))
    return regions


def detect_speech(path: Path, criteria: SpeechCriteria | None = None) -> SpeechActivity:
    """Speech regions of a voice track's export, in seconds from the start of the file."""
    criteria = criteria or SpeechCriteria()
    criteria.check()
    info, level, silent = band_levels(path)
    sound = level[~silent]
    if sound.size == 0:
        return SpeechActivity(info, None, None, None, None, [])
    floor = float(np.percentile(sound, FLOOR_PERCENTILE))
    contrast = float(np.percentile(sound, SOUND_PERCENTILE)) - floor
    on, off = floor + criteria.on_db, floor + criteria.off_db
    total = info.seconds

    def mean_level(start: float, end: float) -> float:
        first, last = round(start / FRAME), round(end / FRAME)
        frames = level[first : max(first + 1, last)]
        return float(10 * np.log10(np.mean(10 ** (frames / 10))))

    # Faint spans are dropped before joining: once joined to a phrase they could no longer be told apart.
    raw = [(a * FRAME, b * FRAME) for a, b in _hysteresis(level, on, off)]
    raw_levels = [mean_level(a, b) for a, b in raw]
    typical = _weighted_median(raw_levels, [b - a for a, b in raw])
    loud = [
        span
        for span, value in zip(raw, raw_levels, strict=True)
        if typical is None or value >= typical - criteria.faint_db
    ]
    faint = len(raw) - len(loud)
    merged: list[tuple[float, float]] = []
    for start, end in ((a, min(b + criteria.hangover, total)) for a, b in loud):
        if merged and start - merged[-1][1] < criteria.merge_gap:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    regions = []
    for start, end in merged:
        if end - start < criteria.min_region + criteria.hangover:
            continue
        mean = mean_level(start, end)
        regions.append(
            SpeechRegion(
                start=round(start, 3),
                end=round(end, 3),
                level_db=round(mean, 2),
                confidence=round(min(1.0, max(0.0, (mean - floor) / CONFIDENT_MARGIN_DB)), 2),
            )
        )
    return SpeechActivity(
        speech_level_db=None if typical is None else round(typical, 2),
        faint_dropped=faint,
        info=info,
        noise_floor_db=round(floor, 2),
        on_threshold_db=round(on, 2),
        off_threshold_db=round(off, 2),
        contrast_db=round(contrast, 2),
        regions=regions,
    )


def _weighted_median(values: list[float], weights: list[float]) -> float | None:
    if not values:
        return None
    order = np.argsort(values)
    cumulative = np.cumsum(np.asarray(weights)[order])
    index = int(np.searchsorted(cumulative, cumulative[-1] / 2))
    return float(np.asarray(values)[order][index])
