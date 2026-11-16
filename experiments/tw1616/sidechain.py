"""TW-1616 (a): what a side-chained compressor did to the music, against the voice and the offline plan.

The music is a steady pink noise, so whatever changes in its level is the compressor. Its output is the mix
minus the voice (both exported by Cubase, aligned to the sample); its gain is that over the original noise, in
10 ms windows. The voice's level is measured in the same windows, and the offline plan for the same voice
(trackwright.analysis.ducking, default values) is set beside it.

    uv run python experiments/tw1616/sidechain.py <mix.wav> <voice.wav> <noise.wav>
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from trackwright.analysis.ducking import plan
from trackwright.analysis.speech import detect_speech

WINDOW = 0.010


def rms_db(x: np.ndarray, step: int) -> np.ndarray:
    count = len(x) // step
    blocks = x[: count * step].reshape(count, step, -1)
    rms = np.sqrt(np.mean(blocks**2, axis=(1, 2)))
    return 20 * np.log10(np.maximum(rms, 1e-12))


def main() -> None:
    mix, rate = sf.read(sys.argv[1], always_2d=True)
    voice, _ = sf.read(sys.argv[2], always_2d=True)
    noise, _ = sf.read(sys.argv[3], always_2d=True)
    n = min(len(mix), len(voice), len(noise))
    step = round(rate * WINDOW)
    compressed = mix[:n] - voice[:n]
    gain = rms_db(compressed, step) - rms_db(noise[:n], step)
    voice_db = rms_db(voice[:n], step)
    times = (np.arange(len(gain)) + 0.5) * WINDOW
    regions = [(r.start, r.end) for r in detect_speech(Path(sys.argv[2])).regions]
    planned = plan(regions, total=n / rate).gain_db(times)
    speaking = np.zeros(len(times), dtype=bool)
    for start, end in regions:
        speaking |= (times >= start) & (times < end)
    print(f"speech regions: {len(regions)}, {speaking.mean() * 100:.0f} % of the time")
    print(
        f"gain while speaking: median {np.median(gain[speaking]):+.1f} dB, "
        f"10-90 % {np.percentile(gain[speaking], 10):+.1f} .. {np.percentile(gain[speaking], 90):+.1f} dB"
    )
    silent = ~speaking & (voice_db < -60)
    if silent.any():
        print(
            f"gain where the voice is silent (< -60 dBFS): median {np.median(gain[silent]):+.1f} dB "
            f"({silent.sum() * WINDOW:.1f} s)"
        )
    # within speech: how much the gain moves from one 100 ms block to the next (pumping)
    blocks = gain[: len(gain) // 10 * 10].reshape(-1, 10).mean(axis=1)
    sp = speaking[: len(speaking) // 10 * 10].reshape(-1, 10).all(axis=1)
    moves = np.abs(np.diff(blocks))[sp[1:] & sp[:-1]]
    print(
        f"inside speech, change between consecutive 100 ms blocks: median {np.median(moves):.1f} dB, "
        f"95th {np.percentile(moves, 95):.1f} dB"
    )
    print(
        f"correlation of the gain with the voice level (speaking): "
        f"{np.corrcoef(gain[speaking], voice_db[speaking])[0, 1]:+.2f}"
    )
    print("per 2 s: voice dBFS | compressor gain | offline plan")
    for s in range(0, int(n / rate), 2):
        m = (times >= s) & (times < s + 2)
        print(f"  {s:4d}s  {np.median(voice_db[m]):7.1f}  {np.median(gain[m]):+6.1f}  {np.median(planned[m]):+6.1f}")


if __name__ == "__main__":
    main()
