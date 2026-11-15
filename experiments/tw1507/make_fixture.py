"""TW-1507: a speech-like test signal for setting a noise gate.

Mono, 48 kHz, 24-bit PCM, 30 s. Room noise at -55 dBFS RMS everywhere. "Phrases" made of 250 ms syllables
(220 + 660 Hz, raised-cosine edges) with 100 ms gaps: loud at -16 dBFS RMS (2-8 s and 20-26 s) and soft at
-36 dBFS RMS (11-17 s). Pauses with only the noise: 0-2, 8-11, 17-20 and 26-30 s.

A well-set gate removes the noise in the pauses and keeps both the loud and the soft phrases.
Usage: uv run python experiments/tw1507/make_fixture.py [output.wav]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

RATE = 48_000
SECONDS = 30.0
NOISE_DBFS = -55.0
PHRASES = ((2.0, 8.0, -16.0), (11.0, 17.0, -36.0), (20.0, 26.0, -16.0))
SYLLABLE, GAP, EDGE = 0.25, 0.10, 0.02


def syllables(seconds: float) -> np.ndarray:
    """Envelope 0..1 of syllables and gaps, with raised-cosine edges."""
    t = np.arange(int(seconds * RATE)) / RATE
    phase = t % (SYLLABLE + GAP)
    envelope = (phase < SYLLABLE).astype(np.float64)
    ramp = np.clip(np.minimum(phase, SYLLABLE - phase) / EDGE, 0.0, 1.0)
    return envelope * (0.5 - 0.5 * np.cos(np.pi * ramp))


def main(out: Path) -> None:
    rng = np.random.default_rng(1507)
    data = rng.normal(0.0, 10 ** (NOISE_DBFS / 20), int(SECONDS * RATE))
    for start, end, dbfs in PHRASES:
        first, last = int(start * RATE), int(end * RATE)
        t = np.arange(last - first) / RATE
        voice = np.sin(2 * np.pi * 220 * t) + 0.5 * np.sin(2 * np.pi * 660 * t)
        voice *= 10 ** (dbfs / 20) / np.sqrt(np.mean(voice**2))  # RMS = dbfs while a syllable sounds
        data[first:last] += voice * syllables(end - start)
    sf.write(str(out), data, RATE, subtype="PCM_24")
    print(out)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("tw1507-fixture.wav"))
