"""TW-1501: a test signal with known silences and an alignment click.

Mono, 48 kHz, 24-bit PCM, 30 s. Background noise at -60 dBFS everywhere; a 1 ms full-scale click at 1.000 s;
a 440 Hz tone at -12 dBFS at 2-6, 10-12, 13-17 and 22-25 s. Only the noise in between:
6-10 (4 s), 12-13 (1 s), 17-22 (5 s), 25-30 (5 s). Standard library only.

Usage: uv run python experiments/tw1501/make_fixture.py [output.wav]
"""

from __future__ import annotations

import math
import random
import sys
import wave
from pathlib import Path

RATE = 48_000
SECONDS = 30.0
CLICK_AT = 1.0
TONES = ((2.0, 6.0), (10.0, 12.0), (13.0, 17.0), (22.0, 25.0))
TONE_DBFS = -12.0
NOISE_DBFS = -60.0  # RMS of the noise
FULL_SCALE = 2**23 - 1


def sample(t: float, rng: random.Random) -> float:
    value = rng.gauss(0.0, 10 ** (NOISE_DBFS / 20))
    if any(start <= t < end for start, end in TONES):
        value += math.sqrt(2) * 10 ** (TONE_DBFS / 20) * math.sin(2 * math.pi * 440.0 * t)  # RMS = TONE_DBFS
    if CLICK_AT <= t < CLICK_AT + 0.001:
        value = 0.99
    return max(-1.0, min(1.0, value))


def main(out: Path) -> None:
    rng = random.Random(1501)
    frames = bytearray()
    for n in range(int(RATE * SECONDS)):
        frames += int(sample(n / RATE, rng) * FULL_SCALE).to_bytes(3, "little", signed=True)
    with wave.open(str(out), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(3)
        wav.setframerate(RATE)
        wav.writeframes(bytes(frames))
    print(out)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("tw1501-fixture.wav"))
