"""TW-1603: BS.1770 / EBU R128 loudness against the EBU test cases and an independent implementation.

Test signals follow EBU Tech 3341 (loudness meters) and Tech 3342 (loudness range), generated here: stereo
1 kHz sines whose peak level in dBFS equals the expected loudness in LUFS, and sequences that exercise the
gates. Tolerances are the documents' (±0.1 LU for integrated loudness, ±1 LU for the range). pyloudnorm
(development dependency only) is an independent implementation for noise-like signals.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pyloudnorm
import pytest
import soundfile as sf

from trackwright.analysis import decoded, measure_loudness
from trackwright.analysis.loudness import READ_SECONDS, k_weighting
from trackwright.analysis.reader import SILENT_DB
from trackwright.errors import PreconditionFailedError

RATE = 48_000
Signal = npt.NDArray[np.float64]


def sine(dbfs: float, seconds: float, rate: int = RATE, freq: float = 1000.0, phase: float = 0.0) -> Signal:
    t = np.arange(int(seconds * rate)) / rate
    return np.asarray(10 ** (dbfs / 20) * np.sin(2 * np.pi * freq * t + phase), dtype=np.float64)


def stereo(mono: Signal) -> Signal:
    return np.stack([mono, mono], axis=1)


def write(tmp_path: Path, name: str, data: Signal, rate: int = RATE, subtype: str = "FLOAT") -> Path:
    path = tmp_path / name
    sf.write(str(path), data, rate, subtype=subtype)
    return path


def test_coefficients_at_48k_match_bs1770() -> None:
    """The coefficient tables of BS.1770-4 for 48 kHz (stage 1 and stage 2)."""
    (b1, a1), (b2, a2) = k_weighting(48_000)
    assert b1 == pytest.approx([1.53512485958697, -2.69169618940638, 1.19839281085285], abs=1e-12)
    assert a1 == pytest.approx([1.0, -1.69065929318241, 0.73248077421585], abs=1e-12)
    assert b2 == pytest.approx([1.0, -2.0, 1.0])
    assert a2 == pytest.approx([1.0, -1.99004745483398, 0.99007225036621], abs=1e-12)


@pytest.mark.parametrize(("dbfs", "seconds"), [(-23.0, 20), (-33.0, 20)])
def test_tech3341_cases_1_and_2(tmp_path: Path, dbfs: float, seconds: float) -> None:
    """Stereo 1 kHz sine: M, S and I equal the sine's peak level (±0.1 LU)."""
    result = measure_loudness(write(tmp_path, "s.wav", stereo(sine(dbfs, seconds))))
    assert result.integrated_lufs == pytest.approx(dbfs, abs=0.1)
    assert result.momentary_max_lufs == pytest.approx(dbfs, abs=0.1)
    assert result.short_term_max_lufs == pytest.approx(dbfs, abs=0.1)
    assert result.sample_peak_dbfs == pytest.approx(dbfs, abs=0.05)


def test_tech3341_case_3_relative_gate(tmp_path: Path) -> None:
    """-36 dBFS 10 s, -23 dBFS 60 s, -36 dBFS 10 s: the quiet parts fall under the relative gate."""
    data = np.concatenate([sine(-36, 10), sine(-23, 60), sine(-36, 10)])
    assert measure_loudness(write(tmp_path, "g.wav", stereo(data))).integrated_lufs == pytest.approx(-23, abs=0.1)


def test_tech3341_case_4_absolute_gate(tmp_path: Path) -> None:
    """-72 / -36 / -23 / -36 / -72 dBFS: the -72 parts fall under the absolute gate too."""
    data = np.concatenate([sine(-72, 10), sine(-36, 10), sine(-23, 60), sine(-36, 10), sine(-72, 10)])
    assert measure_loudness(write(tmp_path, "a.wav", stereo(data))).integrated_lufs == pytest.approx(-23, abs=0.1)


@pytest.mark.parametrize(
    ("first", "second", "lra"),
    [(-20.0, -30.0, 10.0), (-20.0, -15.0, 5.0), (-40.0, -20.0, 20.0)],
)
def test_tech3342_loudness_range(tmp_path: Path, first: float, second: float, lra: float) -> None:
    """Tech 3342 cases 1-3: 20 s at one level, then 20 s at another; LRA is their difference (±1 LU)."""
    data = np.concatenate([sine(first, 20), sine(second, 20)])
    result = measure_loudness(write(tmp_path, "r.wav", stereo(data)))
    assert result.loudness_range_lu == pytest.approx(lra, abs=1.0)


def test_true_peak_between_samples(tmp_path: Path) -> None:
    """A sine at a quarter of the sample rate, 45 degrees out of phase: every sample is at 0.707 of the real
    peak, so the true peak reads about 3 dB above the sample peak."""
    data = sine(-6.0, 2, freq=RATE / 4, phase=np.pi / 4)
    result = measure_loudness(write(tmp_path, "tp.wav", stereo(data)))
    assert result.sample_peak_dbfs == pytest.approx(-9.03, abs=0.05)
    assert result.true_peak_dbtp == pytest.approx(-6.0, abs=0.3)


def test_mono_reads_three_db_lower(tmp_path: Path) -> None:
    result = measure_loudness(write(tmp_path, "m.wav", sine(-23, 10)))
    assert result.info.channels == 1
    assert result.integrated_lufs == pytest.approx(-26.01, abs=0.1)


def test_silence_and_short_files(tmp_path: Path) -> None:
    silent = measure_loudness(write(tmp_path, "z.wav", stereo(np.zeros(RATE * 5))))
    assert (silent.integrated_lufs, silent.momentary_max_lufs, silent.loudness_range_lu) == (None, None, None)
    assert silent.sample_peak_dbfs == SILENT_DB
    short = measure_loudness(write(tmp_path, "short.wav", stereo(sine(-20, 0.3))))
    assert short.integrated_lufs is None
    assert short.short_term_max_lufs is None
    assert short.sample_peak_dbfs == pytest.approx(-20, abs=0.05)


@pytest.mark.parametrize("rate", [44_100, 48_000])
def test_agrees_with_pyloudnorm(tmp_path: Path, rate: int) -> None:
    """Noise with pauses and level changes, longer than one read block, at both common rates."""
    rng = np.random.default_rng(1603)
    seconds = READ_SECONDS * 2.5
    noise = rng.normal(0, 0.05, (int(seconds * rate), 2))
    noise[int(5 * rate) : int(8 * rate)] *= 0.01
    noise[int(15 * rate) :] *= 3
    result = measure_loudness(write(tmp_path, f"n{rate}.wav", noise, rate))
    reference = pyloudnorm.Meter(rate).integrated_loudness(noise)
    assert result.integrated_lufs == pytest.approx(reference, abs=0.1)


def test_mp3_is_measured(tmp_path: Path) -> None:
    try:
        path = write(tmp_path, "s.mp3", stereo(sine(-23, 10)), subtype="MPEG_LAYER_III")
    except RuntimeError, ValueError, TypeError:
        pytest.skip("this libsndfile cannot write MP3")
    assert measure_loudness(path).integrated_lufs == pytest.approx(-23, abs=0.3)


@pytest.mark.skipif(shutil.which("afconvert") is None, reason="macOS afconvert not available")
def test_aac_is_decoded_with_afconvert(tmp_path: Path) -> None:
    wav = write(tmp_path, "s.wav", stereo(sine(-23, 10)), subtype="PCM_24")
    aac = tmp_path / "s.m4a"
    subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", str(wav), str(aac)], check=True, capture_output=True)
    with decoded(aac) as readable:
        assert readable != aac
        assert readable.suffix == ".wav"
        result = measure_loudness(readable)
    assert not readable.exists()  # the temporary file is gone
    assert result.integrated_lufs == pytest.approx(-23, abs=0.3)
    with decoded(wav) as same:
        assert same == wav


@pytest.mark.skipif(shutil.which("afconvert") is None, reason="macOS afconvert not available")
def test_an_undecodable_aac_is_bad_audio(tmp_path: Path) -> None:
    fake = tmp_path / "broken.m4a"
    fake.write_bytes(b"not audio at all")
    with pytest.raises(PreconditionFailedError) as exc, decoded(fake):
        pass
    assert exc.value.code == "BAD_AUDIO"


def test_read_error_mid_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = write(tmp_path, "cut.wav", stereo(sine(-23, 2)))

    def broken(*_args: object, **_kwargs: object) -> object:
        yield np.zeros((4800, 2))
        raise RuntimeError("unexpected end of file")

    monkeypatch.setattr("trackwright.analysis.loudness.sf.blocks", broken)
    with pytest.raises(PreconditionFailedError) as exc:
        measure_loudness(path)
    assert exc.value.code == "BAD_AUDIO"
