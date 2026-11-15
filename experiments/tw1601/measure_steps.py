"""TW-1601 item 3 and 6: where recorded volume steps land in an export, and what MP3 encoding changes.

Usage: uv run python experiments/tw1601/measure_steps.py WAV MP3 --start 6.0
Prints, as JSON, the times (project seconds) where the level crosses the middle of each step, from 5 ms
windows, for the WAV and the MP3; the MP3's offset against the WAV (cross-correlation of envelopes), its
format, and sample and true peak (4x oversampled with an FFT) of both.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf

WINDOW = 0.005


def envelope(data: np.ndarray, rate: int) -> np.ndarray:
    mono = data.mean(axis=1)
    hop = int(rate * WINDOW)
    frames = mono[: len(mono) // hop * hop].reshape(-1, hop)
    return 20 * np.log10(np.sqrt((frames**2).mean(axis=1)) + 1e-12)


def crossings(level: np.ndarray, start: float) -> list[float]:
    high, low = np.percentile(level, 90), np.percentile(level, 10)
    middle = (high + low) / 2
    above = level > middle
    edges = np.nonzero(above[1:] != above[:-1])[0] + 1
    return [round(start + i * WINDOW, 4) for i in edges]


def true_peak(data: np.ndarray) -> float:
    n = data.shape[0]
    spectrum = np.fft.rfft(data, axis=0)
    up = np.fft.irfft(spectrum, n * 4, axis=0) * 4
    return round(float(20 * np.log10(np.abs(up).max() + 1e-12)), 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wav", type=Path)
    parser.add_argument("mp3", type=Path)
    parser.add_argument("--start", type=float, default=0.0)
    args = parser.parse_args()
    out: dict[str, object] = {}
    levels = {}
    for name, path in (("wav", args.wav), ("mp3", args.mp3)):
        info = sf.info(str(path))
        data, rate = sf.read(str(path), always_2d=True)
        levels[name] = envelope(data, rate)
        out[name] = {
            "format": f"{info.format}/{info.subtype}",
            "rate": rate,
            "seconds": round(len(data) / rate, 4),
            "crossings": crossings(levels[name], args.start),
            "sample_peak_db": round(float(20 * np.log10(np.abs(data).max())), 2),
            "true_peak_db": true_peak(data),
        }
    a, b = levels["wav"] - levels["wav"].mean(), levels["mp3"] - levels["mp3"].mean()
    n = min(len(a), len(b))
    corr = np.correlate(b[:n], a[:n], mode="full")
    out["mp3_offset_seconds"] = round((int(np.argmax(corr)) - (n - 1)) * WINDOW, 4)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
