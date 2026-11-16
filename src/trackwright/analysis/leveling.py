"""Dialogue leveling (TW-1622): consistent voices without flattening the performance.

Pure functions. Each voice is an export of one voice track alone, with its speech regions (project seconds):

- the **voice's loudness** is BS.1770 K-weighted power measured over its speech only (pauses never count);
- its phrases are joined into **segments** (speech separated by less than ``join_gap``): an intervention, the
  nearest thing to a take that can be told from the audio;
- **between people:** each voice gets the gain that brings it to the target (by default the median voice);
- **between segments of a voice:** a segment that strays more than ``tolerance_db`` from its voice is brought
  back by the excess only, never all the way: a quieter answer stays a little quieter;
- **within a segment** nothing changes, so whispers, laughter and emphasis keep their shape; a segment shorter
  than ``min_segment`` gets only its voice's gain;
- every total gain is bounded by ``max_gain_db``, and gains change in the pauses between segments (``ramp``),
  never inside a phrase.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf
from scipy import signal

from trackwright.analysis.ducking import merge
from trackwright.analysis.loudness import k_weighting

Span = tuple[float, float]


@dataclass(frozen=True, slots=True)
class LevelingParams:
    target_lufs: float | None = None
    """Speech loudness to bring every voice to; None: the median of the voices."""
    max_gain_db: float = 6.0
    tolerance_db: float = 2.0
    join_gap: float = 1.5
    min_segment: float = 3.0
    ramp: float = 0.2


@dataclass(frozen=True, slots=True)
class Gain:
    """A gain over a span of project time (between spans the gain ramps in the pause)."""

    start: float
    end: float
    gain_db: float


@dataclass(slots=True)
class SegmentLevel:
    start: float
    end: float
    speech_seconds: float
    loudness_lufs: float | None
    deviation_db: float | None
    """Against its voice's loudness."""
    segment_gain_db: float
    gain_db: float
    """Total: the voice's gain plus the segment's, bounded."""
    reason: str


@dataclass(slots=True)
class VoiceLevel:
    name: str
    loudness_lufs: float | None
    voice_gain_db: float
    segments: list[SegmentLevel] = field(default_factory=list)

    @property
    def gains(self) -> list[Gain]:
        return [Gain(s.start, s.end, s.gain_db) for s in self.segments]


BINS_PER_SECOND = 100  # the power is kept in 10 ms bins: an hour of voice is 360 000 numbers


def k_power_bins(path: Path) -> npt.NDArray[np.float64]:
    """Mean K-weighted power (channels summed, BS.1770 weights for mono and stereo) of every 10 ms of the
    file, read in blocks; the last partial bin is dropped."""
    info = sf.info(str(path))
    rate, channels = info.samplerate, info.channels
    size = rate // BINS_PER_SECOND
    (b1, a1), (b2, a2) = k_weighting(rate)
    z1, z2 = np.zeros((2, channels)), np.zeros((2, channels))
    pending = np.zeros(0)
    bins: list[npt.NDArray[np.float64]] = []
    for chunk in sf.blocks(str(path), blocksize=size * 600, dtype="float64", always_2d=True):
        filtered, z1 = signal.lfilter(b1, a1, chunk, axis=0, zi=z1)
        filtered, z2 = signal.lfilter(b2, a2, filtered, axis=0, zi=z2)
        joined = np.concatenate([pending, (filtered * filtered).sum(axis=1)])
        whole = len(joined) // size * size
        bins.append(joined[:whole].reshape(-1, size).mean(axis=1))
        pending = joined[whole:]
    return np.concatenate(bins) if bins else np.zeros(0)


def lufs(power: float) -> float | None:
    return round(-0.691 + 10 * float(np.log10(power)), 2) if power > 0 else None


def span_power(power: npt.NDArray[np.float64], rate: int, origin: float, spans: Sequence[Span]) -> tuple[float, int]:
    """Total K-weighted power and number of values inside ``spans`` (project seconds; the file starts at
    ``origin``); ``power`` has ``rate`` values per second (samples, or 10 ms bins)."""
    total, count = 0.0, 0
    for a, b in spans:
        i, j = max(0, round((a - origin) * rate)), min(len(power), round((b - origin) * rate))
        if j > i:
            total += float(power[i:j].sum())
            count += j - i
    return total, count


def _bounded(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def level_voice(  # noqa: PLR0917  (the voice's measurements, all needed)
    power: npt.NDArray[np.float64],
    rate: int,
    origin: float,
    regions: Sequence[Span],
    voice_gain_db: float,
    params: LevelingParams,
) -> list[SegmentLevel]:
    """The segments of one voice, each with its gain (the voice's already chosen)."""
    total, count = span_power(power, rate, origin, regions)
    voice_lufs = lufs(total / count) if count else None
    segments: list[SegmentLevel] = []
    for start, end in merge(regions, params.join_gap):
        inside = [(max(a, start), min(b, end)) for a, b in regions if a < end and b > start]
        seg_total, seg_count = span_power(power, rate, origin, inside)
        loud = lufs(seg_total / seg_count) if seg_count else None
        deviation = round(loud - voice_lufs, 2) if loud is not None and voice_lufs is not None else None
        speech = round(sum(b - a for a, b in inside), 3)
        own, reason = 0.0, "within the tolerance"
        if deviation is None:
            reason = "not measurable"
        elif end - start < params.min_segment:
            reason = "short: only the voice's gain (whispers, laughs, interjections keep their level)"
        elif abs(deviation) > params.tolerance_db:
            own = -(deviation - params.tolerance_db * (1 if deviation > 0 else -1))
            reason = f"{'louder' if deviation > 0 else 'quieter'} than the voice by {abs(deviation):.1f} dB"
        wanted = voice_gain_db + own
        bounded = _bounded(wanted, params.max_gain_db)
        if bounded != wanted:
            reason += f"; bounded to {bounded:+.1f} dB (wanted {wanted:+.1f})"
        segments.append(SegmentLevel(round(start, 3), round(end, 3), speech, loud, deviation, round(own, 2),
                                     round(bounded, 2), reason))  # fmt: skip
    return segments


def plan_leveling(
    voices: Sequence[tuple[str, npt.NDArray[np.float64], int, float, Sequence[Span]]],
    params: LevelingParams,
) -> tuple[float | None, list[VoiceLevel]]:
    """The target and each voice's gains. ``voices``: (name, K-weighted power per sample, rate, origin, regions)."""
    loudness: list[float | None] = []
    for _, power, rate, origin, regions in voices:
        total, count = span_power(power, rate, origin, regions)
        loudness.append(lufs(total / count) if count else None)
    measured = [v for v in loudness if v is not None]
    target = params.target_lufs if params.target_lufs is not None else (
        round(statistics.median(measured), 2) if measured else None
    )  # fmt: skip
    planned: list[VoiceLevel] = []
    for (name, power, rate, origin, regions), loud in zip(voices, loudness, strict=True):
        gain = _bounded(target - loud, params.max_gain_db) if target is not None and loud is not None else 0.0
        level = VoiceLevel(name, loud, round(gain, 2))
        level.segments = level_voice(power, rate, origin, regions, gain, params)
        planned.append(level)
    return target, planned


def gain_points(gains: Sequence[Gain], ramp: float) -> list[tuple[float, float]]:
    """(seconds, dB) points: each gain held over its span, ramps of up to ``ramp`` in the middle of the pause
    between spans; the first and last gains extend before and after."""
    spans = sorted(gains, key=lambda g: g.start)
    points: list[tuple[float, float]] = []
    for i, g in enumerate(spans):
        if i == 0:
            points.append((g.start, g.gain_db))
        else:
            prev = spans[i - 1]
            gap = max(0.0, g.start - prev.end)
            middle, half = prev.end + gap / 2, min(ramp, gap) / 2
            if g.gain_db != prev.gain_db:
                points += [(middle - half, prev.gain_db), (middle + half, g.gain_db)]
        points.append((g.end, g.gain_db))
    ordered: list[tuple[float, float]] = []
    for t, db in points:  # equal times (touching spans): nudge so interpolation stays defined
        ordered.append((ordered[-1][0] + 1e-6 if ordered and t <= ordered[-1][0] else t, db))
    return ordered


def gain_curve(gains: Sequence[Gain], ramp: float) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    points = gain_points(gains, ramp)
    return np.array([p[0] for p in points]), np.array([p[1] for p in points])


def curve_db(
    xs: npt.NDArray[np.float64], ys: npt.NDArray[np.float64], times: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """The gain at ``times``: held at the first and last values outside the points (0 dB with none)."""
    if len(xs) == 0:
        return np.zeros_like(times)
    return np.asarray(np.interp(times, xs, ys), dtype=np.float64)
