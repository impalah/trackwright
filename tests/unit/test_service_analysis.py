"""TW-1504: cubase_analyze_audio at the service level (an exported file, project seconds, the policy)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.core.timefmt import format_seconds
from trackwright.errors import NotFoundError, PolicyError, PreconditionFailedError
from trackwright.fake import FakeCubase

RATE = 8_000


def export(path: Path, parts: list[tuple[str, float]]) -> Path:
    """An 'export': stereo float, exact zeros, -60 dBFS noise, and a -12 dBFS tone over the noise."""
    rng = np.random.default_rng(7)
    chunks = []
    for kind, seconds in parts:
        count = int(seconds * RATE)
        if kind == "zero":
            chunks.append(np.zeros(count))
            continue
        chunk = rng.normal(0.0, 10 ** (-60 / 20), count)
        if kind == "tone":
            chunk = chunk + np.sqrt(2) * 10 ** (-12 / 20) * np.sin(2 * np.pi * 440 * np.arange(count) / RATE)
        chunks.append(chunk)
    mono = np.concatenate(chunks)
    sf.write(str(path), np.stack([mono, mono], axis=1), RATE, subtype="FLOAT")
    return path


def analyzer(fake: FakeCubase, **policy: object) -> CubaseService:
    return CubaseService(fake, WritePolicy(analysis=True, **policy))  # type: ignore[arg-type]


def test_silences_in_project_seconds(fake: FakeCubase, tmp_path: Path) -> None:
    """Like TW-1501: the export starts at 2 s, so file time 0 is project time 2."""
    file = export(tmp_path / "x.wav", [("zero", 2), ("quiet", 2), ("tone", 4), ("quiet", 4), ("tone", 2), ("zero", 2)])
    out = analyzer(fake).analyze_audio(str(file), start="2", min_seconds=3.0)
    assert (out.sample_rate, out.channels, out.seconds, out.subtype) == (RATE, 2, 16.0, "FLOAT")
    assert out.start == "0:00:02.000"
    assert out.noise_floor_db == pytest.approx(-60.0, abs=1.5)
    assert out.threshold_db == pytest.approx(out.noise_floor_db + 10, abs=0.01)  # type: ignore[operator]
    assert out.quiet_sound_db == pytest.approx(-12.0, abs=1.0)  # only the tone is above the threshold
    assert out.sound_db == pytest.approx(-12.0, abs=1.0)
    assert [(s.start, s.end) for s in out.silences] == [
        ("0:00:02.000", "0:00:05.750"),  # zeros + noise before the tone; no padding at the file's start
        ("0:00:10.250", "0:00:13.750"),
    ]
    assert out.silences[1].start_seconds == pytest.approx(10.25)
    assert out.silences[1].level_db == pytest.approx(-60.0, abs=1.5)
    assert out.total == 2
    assert out.total_seconds == pytest.approx(3.75 + 3.5)
    assert out.criteria["min_seconds"] == 3.0
    assert any("levels are those of the export" in n for n in out.notes)
    assert fake.fired == []  # nothing was sent to Cubase


def test_digital_silence_is_reported_as_such(fake: FakeCubase, tmp_path: Path) -> None:
    file = export(tmp_path / "d.wav", [("tone", 2), ("zero", 4), ("tone", 2)])
    silence = analyzer(fake).analyze_audio(str(file), min_seconds=3.0).silences[0]
    assert silence.digital is True
    assert silence.level_db is None
    assert (silence.start_seconds, silence.end_seconds) == (2.25, 5.75)


def test_no_contrast_says_so(fake: FakeCubase, tmp_path: Path) -> None:
    out = analyzer(fake).analyze_audio(str(export(tmp_path / "t.wav", [("tone", 5)])))
    assert out.silences == []
    assert out.threshold_db is None
    assert "no contrast" in out.notes[0]
    assert (out.quiet_sound_db, out.sound_db) == (None, None)


def test_absolute_threshold_and_paging(fake: FakeCubase, tmp_path: Path) -> None:
    parts: list[tuple[str, float]] = [("tone", 1.0), ("quiet", 2.0)] * 5 + [("tone", 1.0)]
    file = export(tmp_path / "p.wav", parts)
    out = analyzer(fake).analyze_audio(str(file), threshold_db=-40.0, min_seconds=1.5, offset=1, limit=2)
    assert out.threshold_db == -40.0
    assert out.total == 5
    assert [s.start_seconds for s in out.silences] == [4.25, 7.25]


def test_refused_while_disabled(fake: FakeCubase, tmp_path: Path) -> None:
    file = export(tmp_path / "a.wav", [("tone", 1)])
    with pytest.raises(PolicyError) as exc:
        CubaseService(fake, WritePolicy(enabled=True)).analyze_audio(str(file))
    assert exc.value.code == "ANALYSIS_DISABLED"


def test_too_long_is_refused_before_reading(fake: FakeCubase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file = export(tmp_path / "long.wav", [("tone", 3)])

    def must_not_read(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("samples were read")

    monkeypatch.setattr("trackwright.core.analyzing.measure", must_not_read)
    with pytest.raises(PreconditionFailedError) as exc:
        analyzer(fake, analysis_max_seconds=2.0).analyze_audio(str(file))
    assert exc.value.code == "TOO_LONG"


def test_bad_requests(fake: FakeCubase, tmp_path: Path) -> None:
    service = analyzer(fake)
    with pytest.raises(PreconditionFailedError) as relative:
        service.analyze_audio("Mixdown/x.wav")
    assert relative.value.code == "BAD_REQUEST"
    with pytest.raises(PreconditionFailedError) as time:
        service.analyze_audio(str(tmp_path / "x.wav"), start="soon")
    assert time.value.code == "BAD_TIME"
    with pytest.raises(PreconditionFailedError) as criteria:
        service.analyze_audio(str(tmp_path / "x.wav"), min_seconds=0)
    assert criteria.value.code == "BAD_REQUEST"
    with pytest.raises(NotFoundError) as missing:
        service.analyze_audio(str(tmp_path / "x.wav"))
    assert missing.value.code == "NOT_FOUND"
    text = tmp_path / "notes.wav"
    text.write_text("hello", encoding="utf-8")
    with pytest.raises(PreconditionFailedError) as bad:
        service.analyze_audio(str(text))
    assert bad.value.code == "BAD_AUDIO"


# ---------------------------------------------------------------- loudness (TW-1603)
def test_measure_loudness(fake: FakeCubase, tmp_path: Path) -> None:
    t = np.arange(RATE * 6) / RATE
    tone = 10 ** (-23 / 20) * np.sin(2 * np.pi * 1000 * t)
    sf.write(str(tmp_path / "st.wav"), np.stack([tone, tone], axis=1), RATE, subtype="FLOAT")
    sf.write(str(tmp_path / "mono.wav"), tone, RATE, subtype="FLOAT")
    service = analyzer(fake)
    out = service.measure_loudness(str(tmp_path / "st.wav"))
    assert out.integrated_lufs == pytest.approx(-23, abs=0.1)
    assert out.true_peak_dbtp == pytest.approx(-23, abs=0.2)
    assert (out.sample_rate, out.channels, out.notes) == (RATE, 2, [])
    mono = service.measure_loudness(str(tmp_path / "mono.wav"))
    assert "mono file" in mono.notes[0]
    assert fake.fired == []


def test_measure_loudness_policy_and_paths(fake: FakeCubase, tmp_path: Path) -> None:
    sf.write(str(tmp_path / "a.wav"), np.zeros(RATE * 3), RATE)
    with pytest.raises(PolicyError) as off:
        CubaseService(fake, WritePolicy(enabled=True)).measure_loudness(str(tmp_path / "a.wav"))
    assert off.value.code == "ANALYSIS_DISABLED"
    with pytest.raises(PreconditionFailedError) as relative:
        analyzer(fake).measure_loudness("a.wav")
    assert relative.value.code == "BAD_REQUEST"
    with pytest.raises(PreconditionFailedError) as long:
        analyzer(fake, analysis_max_seconds=2.0).measure_loudness(str(tmp_path / "a.wav"))
    assert long.value.code == "TOO_LONG"
    silent = analyzer(fake).measure_loudness(str(tmp_path / "a.wav"))
    assert (silent.integrated_lufs, silent.sample_peak_dbfs, silent.true_peak_dbtp) == (None, None, None)


# ---------------------------------------------------------------- speech (TW-1604)
def test_detect_speech_in_project_seconds(fake: FakeCubase, tmp_path: Path) -> None:
    file = export(tmp_path / "voice.wav", [("quiet", 2), ("tone", 3), ("quiet", 2), ("tone", 2), ("quiet", 2)])
    out = analyzer(fake).detect_speech(str(file), start="10", limit=1, offset=1)
    assert out.total == 2
    (region,) = out.regions
    assert region.start_seconds == pytest.approx(17.0, abs=0.02)
    assert region.end_seconds == pytest.approx(19.15, abs=0.05)  # 19.0 + hangover + smoothing
    assert region.start == format_seconds(region.start_seconds)  # h:mm:ss.mmm of the same value
    assert out.speech_seconds == pytest.approx(5.3, abs=0.3)
    assert any("energy detector" in n for n in out.notes)
    assert fake.fired == []


def test_detect_speech_refusals_and_notes(fake: FakeCubase, tmp_path: Path) -> None:
    flat = export(tmp_path / "flat.wav", [("quiet", 4)])
    assert "little contrast" in analyzer(fake).detect_speech(str(flat)).notes[0]
    with pytest.raises(PolicyError) as off:
        CubaseService(fake, WritePolicy(enabled=True)).detect_speech(str(flat))
    assert off.value.code == "ANALYSIS_DISABLED"
    for kwargs, code in (({"start": "soon"}, "BAD_TIME"), ({"on_db": 3.0, "off_db": 6.0}, "BAD_REQUEST")):
        with pytest.raises(PreconditionFailedError) as exc:
            analyzer(fake).detect_speech(str(flat), **kwargs)
        assert exc.value.code == code
    with pytest.raises(PreconditionFailedError) as long:
        analyzer(fake, analysis_max_seconds=1.0).detect_speech(str(flat))
    assert long.value.code == "TOO_LONG"
