"""TW-1616: how closely real-time automation recording follows a planned ducking envelope.

Compares an export of the music with the recorded PreGain automation against the same music exported without
it, window by window (10 ms RMS ratio, only where the music is audible), and against the planned envelope.

    uv run python experiments/tw1616/measure.py <automated.wav> <original.wav> <points.json>
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

WINDOW = 0.010
AUDIBLE_DB = -60.0


def gain_curve(automated: np.ndarray, original: np.ndarray, rate: int) -> tuple[np.ndarray, np.ndarray]:
    step = round(rate * WINDOW)
    count = min(len(automated), len(original)) // step
    a = automated[: count * step].reshape(count, step, -1)
    o = original[: count * step].reshape(count, step, -1)
    ra = np.sqrt(np.mean(a**2, axis=(1, 2)))
    ro = np.sqrt(np.mean(o**2, axis=(1, 2)))
    times = (np.arange(count) + 0.5) * WINDOW
    with np.errstate(divide="ignore", invalid="ignore"):
        gain = 20 * np.log10(ra / ro)
    audible = 20 * np.log10(np.maximum(ro, 1e-12)) > AUDIBLE_DB
    return times[audible], gain[audible]


def main() -> None:
    automated, rate = sf.read(sys.argv[1], always_2d=True)
    original, rate2 = sf.read(sys.argv[2], always_2d=True)
    assert rate == rate2
    points = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))["seconds"]
    xs, ys = np.array([p[0] for p in points]), np.array([p[1] for p in points])
    times, measured = gain_curve(automated, original, rate)
    planned = np.interp(times, xs, ys, left=0.0, right=0.0)
    error = measured - planned
    print(f"audible windows: {len(times)} of {round(min(len(automated), len(original)) / rate / WINDOW)}")
    print(
        f"error vs plan: mean {error.mean():+.2f} dB, median {np.median(error):+.2f}, "
        f"95th |error| {np.percentile(np.abs(error), 95):.2f} dB, max |error| {np.abs(error).max():.2f} dB"
    )
    flat = np.abs(np.gradient(planned)) < 1e-9
    print(
        f"on the plan's flat parts: max |error| {np.abs(error[flat]).max():.2f} dB, "
        f"median {np.median(error[flat]):+.3f} dB"
    )
    best = None
    for lag in np.arange(-0.5, 0.501, 0.01):  # the shift of the plan that best explains the measurement
        shifted = np.interp(times - lag, xs, ys, left=0.0, right=0.0)
        rms = float(np.sqrt(np.mean((measured - shifted) ** 2)))
        if best is None or rms < best[1]:
            best = (lag, rms)
    print(f"best lag: {best[0]:+.2f} s (rms error {best[1]:.2f} dB; at lag 0: {np.sqrt(np.mean(error**2)):.2f} dB)")
    print("transitions (planned point -> where the measured gain crosses the midpoint):")
    for (t0, g0), (t1, g1) in itertools.pairwise(points):
        if abs(g1 - g0) < 1 or t1 - t0 > 3:
            continue
        mid = (g0 + g1) / 2
        window = (times > t0 - 0.6) & (times < t1 + 0.6)
        seg_t, seg_g = times[window], measured[window]
        crossings = np.flatnonzero(np.diff(np.sign(seg_g - mid)) != 0)
        planned_mid = t0 + (t1 - t0) / 2
        if len(crossings):
            print(
                f"  {t0:7.2f}-{t1:7.2f} s ({g0:+.0f}->{g1:+.0f} dB): planned mid {planned_mid:.3f} s, "
                f"measured {seg_t[crossings[0]]:.3f} s, delay {seg_t[crossings[0]] - planned_mid:+.3f} s"
            )
        else:
            print(f"  {t0:7.2f}-{t1:7.2f} s: no crossing: the gain did not move there (or the music is silent)")


if __name__ == "__main__":
    main()
