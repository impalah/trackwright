"""Loudness and true peak (TW-1603): ITU-R BS.1770-4 as used by EBU R128 (Tech 3341 and 3342).

- **K-weighting:** a high-shelf pre-filter and a high-pass (the "RLB" curve), designed for any sample rate
  with the formulas of the reference implementations; at 48 kHz they give the coefficients of BS.1770.
- **Integrated loudness:** 400 ms blocks with 75 % overlap, absolute gate at -70 LUFS, relative gate 10 LU
  below the ungated mean of the blocks above it.
- **Momentary / short-term:** the loudest 400 ms block and the loudest 3 s window (hop 100 ms).
- **Loudness range (LRA, EBU Tech 3342):** short-term values gated at -70 LUFS and 20 LU below their mean;
  the spread between their 10th and 95th percentiles.
- **True peak:** the signal oversampled 4x (polyphase FIR) and its largest absolute value, in dBTP.

The file is read in blocks: memory grows with the number of 100 ms steps, not with the samples. Channel
weights: 1.0 for the front channels, 0 for LFE and 1.41 for the surround channels in the usual 5.1 order;
a mono file is measured as one channel (it reads 3 dB lower than the same signal on two channels).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf
from scipy import signal

from trackwright.analysis.reader import SILENT_DB, AudioInfo, probe
from trackwright.errors import PreconditionFailedError

STEP = 0.1  # seconds between measurements
BLOCK_STEPS = 4  # 400 ms momentary block
SHORT_STEPS = 30  # 3 s short-term window
ABSOLUTE_GATE = -70.0
RELATIVE_GATE = -10.0
LRA_RELATIVE_GATE = -20.0
OVERSAMPLE = 4
READ_SECONDS = 10.0
SURROUND_WEIGHTS = (1.0, 1.0, 1.0, 0.0, 1.41, 1.41)  # L R C LFE Ls Rs

Coefficients = tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]


@dataclass(frozen=True, slots=True)
class Loudness:
    info: AudioInfo
    integrated_lufs: float | None
    """None when every block is below the absolute gate (silence) or the file is shorter than 400 ms."""
    momentary_max_lufs: float | None
    short_term_max_lufs: float | None
    loudness_range_lu: float | None
    """None with fewer than two gated short-term values (a file shorter than about 3 s)."""
    sample_peak_dbfs: float
    true_peak_dbtp: float


def k_weighting(rate: int) -> tuple[Coefficients, Coefficients]:
    """The two biquads of BS.1770 for ``rate``: (high shelf), (high pass)."""
    f0, gain_db, q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    k = math.tan(math.pi * f0 / rate)
    vh = 10 ** (gain_db / 20)
    vb = vh**0.4996667741545416
    a0 = 1 + k / q + k * k
    shelf = (
        np.array([(vh + vb * k / q + k * k) / a0, 2 * (k * k - vh) / a0, (vh - vb * k / q + k * k) / a0]),
        np.array([1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0]),
    )
    f0, q = 38.13547087602444, 0.5003270373238773
    k = math.tan(math.pi * f0 / rate)
    a0 = 1 + k / q + k * k
    highpass = (np.array([1.0, -2.0, 1.0]), np.array([1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0]))
    return shelf, highpass


def channel_weights(channels: int) -> npt.NDArray[np.float64]:
    if channels <= 2:
        return np.ones(channels)
    return np.array([SURROUND_WEIGHTS[c] if c < len(SURROUND_WEIGHTS) else 1.0 for c in range(channels)])


def _lufs(power: float) -> float:
    return -0.691 + 10 * math.log10(power) if power > 0 else -math.inf


def _windows(steps: npt.NDArray[np.float64], weights: npt.NDArray[np.float64], size: int) -> npt.NDArray[np.float64]:
    """Weighted mean power of every window of ``size`` consecutive 100 ms steps (one per step)."""
    if len(steps) < size:
        return np.zeros(0)
    power = steps @ weights  # per step, channels weighted and summed
    sums = np.convolve(power, np.ones(size), mode="valid")
    return np.asarray(sums / size, dtype=np.float64)


def _gated_mean(blocks: npt.NDArray[np.float64], relative: float) -> tuple[float | None, npt.NDArray[np.float64]]:
    """Mean power of the blocks that pass the absolute and the relative gate, and those blocks' loudness."""
    loud = np.array([_lufs(p) for p in blocks])
    kept = blocks[loud > ABSOLUTE_GATE]
    if kept.size == 0:
        return None, np.zeros(0)
    threshold = _lufs(float(kept.mean())) + relative
    final = blocks[(loud > ABSOLUTE_GATE) & (loud > threshold)]
    if final.size == 0:
        return None, np.zeros(0)
    return float(final.mean()), np.array([_lufs(p) for p in final])


def _db(value: float) -> float:
    return 20 * math.log10(value) if value > 0 else SILENT_DB


def measure_loudness(path: Path) -> Loudness:
    """Every measurement of the module for the audio file at ``path`` (read in blocks)."""
    info = probe(path)
    rate, channels = info.rate, info.channels
    step = round(rate * STEP)
    (b1, a1), (b2, a2) = k_weighting(rate)
    state1 = np.zeros((2, channels))
    state2 = np.zeros((2, channels))
    pending = np.zeros((0, channels))
    steps: list[npt.NDArray[np.float64]] = []
    sample_peak = 0.0
    true_peak = 0.0
    overlap = 64  # input samples carried over so the oversampling filter has history at block edges
    history = np.zeros((0, channels))
    block = max(step, round(rate * READ_SECONDS) // step * step)
    try:
        for chunk in sf.blocks(str(path), blocksize=block, dtype="float64", always_2d=True):
            data = np.asarray(chunk, dtype=np.float64)
            sample_peak = max(sample_peak, float(np.abs(data).max(initial=0.0)))
            joined = np.concatenate([history, data])
            up = signal.resample_poly(joined, OVERSAMPLE, 1, axis=0)
            fresh = up[len(history) * OVERSAMPLE :]
            true_peak = max(true_peak, float(np.abs(fresh).max(initial=0.0)))
            history = joined[-overlap:]
            filtered, state1 = signal.lfilter(b1, a1, data, axis=0, zi=state1)
            filtered, state2 = signal.lfilter(b2, a2, filtered, axis=0, zi=state2)
            squared = np.concatenate([pending, filtered * filtered])
            full = len(squared) // step * step
            if full:
                steps.append(squared[:full].reshape(-1, step, channels).mean(axis=1))
            pending = squared[full:]
    except RuntimeError as exc:  # soundfile reports read errors as RuntimeError (LibsndfileError)
        raise PreconditionFailedError(
            f"could not read {path.name} to the end", code="BAD_AUDIO", details={"path": str(path), "reason": str(exc)}
        ) from exc
    per_step = np.concatenate(steps) if steps else np.zeros((0, channels))
    weights = channel_weights(channels)
    blocks = _windows(per_step, weights, BLOCK_STEPS)
    shorts = _windows(per_step, weights, SHORT_STEPS)
    integrated, _ = _gated_mean(blocks, RELATIVE_GATE)
    _, short_gated = _gated_mean(shorts, LRA_RELATIVE_GATE)
    lra = None
    if short_gated.size >= 2:
        low, high = np.percentile(short_gated, [10, 95])
        lra = round(float(high - low), 2)
    momentary = _lufs(float(blocks.max())) if blocks.size else -math.inf
    short = _lufs(float(shorts.max())) if shorts.size else -math.inf
    return Loudness(
        info=info,
        integrated_lufs=round(_lufs(integrated), 2) if integrated else None,
        momentary_max_lufs=round(momentary, 2) if momentary > ABSOLUTE_GATE else None,
        short_term_max_lufs=round(short, 2) if short > ABSOLUTE_GATE else None,
        loudness_range_lu=lra,
        sample_peak_dbfs=round(_db(sample_peak), 2),
        true_peak_dbtp=round(_db(max(true_peak, sample_peak)), 2),
    )
