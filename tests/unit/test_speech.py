"""TW-1604: voice activity detection on speech-like signals (syllables over room noise)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
import soundfile as sf

from trackwright.analysis.speech import READ_SECONDS, SpeechCriteria, detect_speech
from trackwright.errors import PreconditionFailedError

RATE = 16_000
Signal = npt.NDArray[np.float64]


def syllables(seconds: float, dbfs: float, rate: int = RATE) -> Signal:
    """250 ms syllables (220 + 660 Hz, raised-cosine edges) with 100 ms gaps, RMS ``dbfs`` while sounding."""
    t = np.arange(int(seconds * rate)) / rate
    voice = np.sin(2 * np.pi * 220 * t) + 0.5 * np.sin(2 * np.pi * 660 * t)
    voice *= 10 ** (dbfs / 20) / np.sqrt(np.mean(voice**2))
    phase = t % 0.35
    ramp = np.clip(np.minimum(phase, 0.25 - phase) / 0.02, 0.0, 1.0)
    return np.asarray(voice * (phase < 0.25) * (0.5 - 0.5 * np.cos(np.pi * ramp)), dtype=np.float64)


def episode(parts: list[tuple[float, float | None]], noise_db: float = -55.0, rate: int = RATE) -> Signal:
    """(seconds, phrase level or None for a pause), over noise everywhere."""
    rng = np.random.default_rng(1604)
    chunks = [
        rng.normal(0, 10 ** (noise_db / 20), int(s * rate)) + (syllables(s, level, rate) if level is not None else 0)
        for s, level in parts
    ]
    return np.asarray(np.concatenate(chunks), dtype=np.float64)


def write(tmp_path: Path, data: Signal, rate: int = RATE, name: str = "v.wav") -> Path:
    path = tmp_path / name
    sf.write(str(path), data, rate, subtype="FLOAT")
    return path


def spans(result: object) -> list[tuple[float, float]]:
    return [(round(r.start, 1), round(r.end, 1)) for r in result.regions]  # type: ignore[attr-defined]


def test_phrases_and_pauses(tmp_path: Path) -> None:
    """Loud, soft and loud phrases separated by pauses: one region per phrase (syllable gaps joined)."""
    data = episode([(2, None), (6, -16), (3, None), (6, -36), (3, None), (6, -16), (4, None)])
    result = detect_speech(write(tmp_path, data))
    assert result.noise_floor_db is not None
    assert result.noise_floor_db < -50
    found = spans(result)
    assert len(found) == 3
    for (start, end), (expected_start, expected_end) in zip(found, [(2, 8), (11, 17), (20, 26)], strict=True):
        assert start == pytest.approx(expected_start, abs=0.1)
        assert end == pytest.approx(expected_end, abs=0.4)  # last syllable plus the hangover
    soft = result.regions[1]
    assert soft.level_db < result.regions[0].level_db - 15
    assert 0 < soft.confidence < result.regions[0].confidence <= 1
    assert result.speech_seconds == pytest.approx(18, abs=1.0)


def test_hum_and_hiss_are_not_speech(tmp_path: Path) -> None:
    """A loud 50 Hz hum and broadband hiss throughout: only the phrase is detected."""
    t = np.arange(10 * RATE) / RATE
    hum = 10 ** (-30 / 20) * np.sqrt(2) * np.sin(2 * np.pi * 50 * t)
    data = episode([(3, None), (4, -20), (3, None)], noise_db=-50) + hum
    ((start, end),) = spans(detect_speech(write(tmp_path, data)))
    assert start == 3.0
    assert end == pytest.approx(7.1, abs=0.4)


def test_a_click_is_not_speech(tmp_path: Path) -> None:
    data = episode([(6, None)])
    data[3 * RATE : 3 * RATE + 16] = 0.8  # 1 ms
    assert detect_speech(write(tmp_path, data)).regions == []


def test_syllable_gaps_split_without_merging(tmp_path: Path) -> None:
    data = episode([(1, None), (1.4, -16), (1, None)])
    joined = detect_speech(write(tmp_path, data))
    assert len(joined.regions) == 1
    split = detect_speech(write(tmp_path, data), SpeechCriteria(merge_gap=0.0, hangover=0.0))
    assert len(split.regions) == 4  # four syllables of 250 ms


def test_stereo_and_block_boundaries(tmp_path: Path) -> None:
    """A phrase that crosses the read block boundary is one region; stereo is averaged."""
    seconds_before = READ_SECONDS - 2
    mono = episode([(seconds_before, None), (4, -20), (3, None)], rate=48_000)
    result = detect_speech(write(tmp_path, np.stack([mono, mono], axis=1), rate=48_000))
    assert result.info.channels == 2
    ((start, end),) = spans(result)
    assert start == seconds_before
    assert end == pytest.approx(seconds_before + 4.1, abs=0.4)


def test_no_contrast_and_silence(tmp_path: Path) -> None:
    flat = detect_speech(write(tmp_path, episode([(5, None)]), name="flat.wav"))
    assert flat.regions == []
    assert flat.contrast_db is not None
    assert flat.contrast_db < 12
    silent = detect_speech(write(tmp_path, np.zeros(RATE * 3), name="zero.wav"))
    assert (silent.noise_floor_db, silent.regions) == (None, [])


def test_digital_silence_is_left_out_of_the_floor(tmp_path: Path) -> None:
    data = np.concatenate([np.zeros(RATE * 3), episode([(2, None), (3, -20), (2, None)]), np.zeros(RATE * 3)])
    result = detect_speech(write(tmp_path, data))
    assert result.noise_floor_db is not None
    assert result.noise_floor_db > -100  # the noise, not the zeros
    assert spans(result)[0][0] == pytest.approx(5.0, abs=0.1)


def test_bad_criteria_and_read_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = write(tmp_path, episode([(2, -20)]))
    for criteria in (SpeechCriteria(on_db=3, off_db=6), SpeechCriteria(off_db=-1), SpeechCriteria(hangover=-0.1)):
        with pytest.raises(PreconditionFailedError) as exc:
            detect_speech(path, criteria)
        assert exc.value.code == "BAD_REQUEST"

    def broken(*_args: object, **_kwargs: object) -> object:
        yield np.zeros((1600, 1))
        raise RuntimeError("unexpected end of file")

    monkeypatch.setattr("trackwright.analysis.speech.sf.blocks", broken)
    with pytest.raises(PreconditionFailedError) as read:
        detect_speech(path)
    assert read.value.code == "BAD_AUDIO"
