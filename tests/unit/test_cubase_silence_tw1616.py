"""TW-1616: Cubase exports the silence between events as -166 dBFS residue, not exact zeros."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from trackwright.analysis import measure
from trackwright.analysis.speech import detect_speech

RATE = 48000


def episode(path: Path, *, filler: float) -> Path:
    """Room noise with speech-band bursts at 2-8 s and 20-26 s; 10-18 s is ``filler`` (0, or Cubase's residue)."""
    rng = np.random.default_rng(16)
    t = np.arange(30 * RATE) / RATE
    signal = 0.002 * rng.standard_normal(t.size)  # room noise, about -54 dBFS
    for start, end in ((2.0, 8.0), (20.0, 26.0)):
        inside = (t >= start) & (t < end)
        signal[inside] += 0.3 * np.sin(2 * np.pi * 300 * t[inside])
    gap = (t >= 10.0) & (t < 18.0)
    signal[gap] = filler * rng.choice([-1.0, 1.0], gap.sum())
    sf.write(path, np.column_stack([signal, signal]), RATE, subtype="FLOAT")
    return path


def test_residue_is_silence_for_the_speech_detector(tmp_path: Path) -> None:
    residue = detect_speech(episode(tmp_path / "residue.wav", filler=5e-9))
    zeros = detect_speech(episode(tmp_path / "zeros.wav", filler=0.0))
    for found in (residue, zeros):
        spans = [(round(r.start), round(r.end)) for r in found.regions]
        assert spans == [(2, 8), (20, 26)], spans
        assert found.noise_floor_db is not None
        assert found.noise_floor_db > -100  # the room noise, not the residue (it was -1082 dB before)


def test_residue_is_digital_silence_for_the_levels(tmp_path: Path) -> None:
    levels = measure(episode(tmp_path / "residue.wav", filler=5e-9))
    gap = slice(round(10.0 / levels.window), round(18.0 / levels.window))
    assert levels.digital_silence[gap].all()
    assert not levels.digital_silence[round(4.0 / levels.window)]
