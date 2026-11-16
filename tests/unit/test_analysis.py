"""TW-1503: the audio analyzer, against synthetic signals whose silences are known."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
import soundfile as sf
from hypothesis import given, settings
from hypothesis import strategies as st

from trackwright.analysis import (
    AudioInfo,
    Levels,
    SilenceCriteria,
    find_silences,
    measure,
    noise_floor,
    probe,
    sound_levels,
)
from trackwright.analysis.detect import threshold
from trackwright.analysis.reader import BLOCK_WINDOWS, SILENT_DB
from trackwright.errors import NotFoundError, PreconditionFailedError

Signal = npt.NDArray[np.float64]
WINDOW = 0.02


def noise(seconds: float, rate: int, dbfs: float = -60.0, seed: int = 1) -> Signal:
    return np.random.default_rng(seed).normal(0.0, 10 ** (dbfs / 20), int(seconds * rate))


def tone(seconds: float, rate: int, dbfs: float = -12.0) -> Signal:
    t = np.arange(int(seconds * rate)) / rate
    return np.asarray(np.sqrt(2) * 10 ** (dbfs / 20) * np.sin(2 * np.pi * 440.0 * t), dtype=np.float64)


def write(path: Path, data: Signal, rate: int, subtype: str = "FLOAT") -> Path:
    sf.write(str(path), data, rate, subtype=subtype)
    return path


def layout(rate: int, parts: list[tuple[str, float]], floor: float = -60.0) -> Signal:
    """Concatenate ("tone" | "quiet" | "zero", seconds) parts; noise under everything but "zero"."""
    chunks = []
    for index, (kind, seconds) in enumerate(parts):
        if kind == "zero":
            chunks.append(np.zeros(int(seconds * rate)))
            continue
        base = noise(seconds, rate, floor, seed=index)
        chunks.append(base + tone(seconds, rate) if kind == "tone" else base)
    return np.concatenate(chunks)


def spans(silences: list) -> list[tuple[float, float]]:  # type: ignore[type-arg]
    return [(round(s.start, 2), round(s.end, 2)) for s in silences]


def test_the_tw1501_signal(tmp_path: Path) -> None:
    """The layout of experiments/tw1501: three silences of 3 s or more, the 1 s one ignored."""
    rate = 48_000
    data = layout(rate, [("quiet", 2), ("tone", 4), ("quiet", 4), ("tone", 2), ("quiet", 1), ("tone", 4),
                         ("quiet", 5), ("tone", 3), ("quiet", 5)])  # fmt: skip
    levels = measure(write(tmp_path / "a.wav", data, rate))
    assert levels.info.rate == rate
    assert levels.info.channels == 1
    assert levels.seconds == pytest.approx(30.0)
    assert noise_floor(levels) == pytest.approx(-60.0, abs=1.0)
    assert levels.rms_total_db == pytest.approx(-12 + 10 * np.log10(13 / 30), abs=0.3)  # tone 13 of 30 s
    found = find_silences(levels, SilenceCriteria(min_seconds=3.0))
    assert spans(found) == [(6.25, 9.75), (17.25, 21.75), (25.25, 30.0)]  # padding inside, not at the end
    assert all(not s.digital and s.level_db == pytest.approx(-60.0, abs=1.0) for s in found)
    assert spans(find_silences(levels, SilenceCriteria(min_seconds=0.9)))[:2] == [(0.0, 1.75), (6.25, 9.75)]


def test_digital_silence_is_left_out_of_the_floor(tmp_path: Path) -> None:
    """TW-1501: an export holds exact zeros before and after the event."""
    rate = 8_000
    data = layout(rate, [("zero", 3), ("tone", 2), ("quiet", 3), ("tone", 2), ("zero", 3)])
    levels = measure(write(tmp_path / "z.wav", data, rate))
    assert noise_floor(levels) == pytest.approx(-60.0, abs=1.5)  # not -240
    found = find_silences(levels, SilenceCriteria(min_seconds=2.0))
    assert spans(found) == [(0.0, 2.75), (5.25, 7.75), (10.25, 13.0)]
    assert [s.digital for s in found] == [True, False, True]
    assert found[0].level_db == SILENT_DB


def test_all_zero_file_has_no_floor(tmp_path: Path) -> None:
    levels = measure(write(tmp_path / "zero.wav", np.zeros(8_000 * 4), 8_000))
    assert noise_floor(levels) is None
    assert threshold(levels, SilenceCriteria()) is None
    assert levels.peak_db == SILENT_DB
    assert levels.rms_total_db == SILENT_DB
    assert spans(find_silences(levels)) == [(0.0, 4.0)]  # still digital silence


def test_no_silence(tmp_path: Path) -> None:
    rate = 8_000
    levels = measure(write(tmp_path / "t.wav", tone(6, rate) + noise(6, rate), rate))
    assert find_silences(levels, SilenceCriteria(min_seconds=0.5)) == []
    assert threshold(levels, SilenceCriteria()) is None  # no contrast: nothing to call silence


def test_noise_only_needs_an_absolute_threshold(tmp_path: Path) -> None:
    levels = measure(write(tmp_path / "flat.wav", noise(5, 8_000), 8_000))
    assert find_silences(levels, SilenceCriteria(min_seconds=0.5)) == []  # relative: no contrast


def test_a_file_that_is_only_noise_is_one_silence(tmp_path: Path) -> None:
    levels = measure(write(tmp_path / "n.wav", noise(5, 8_000), 8_000))
    assert spans(find_silences(levels, SilenceCriteria(threshold_db=-50.0))) == [(0.0, 5.0)]


def test_absolute_threshold(tmp_path: Path) -> None:
    rate = 8_000
    data = layout(rate, [("tone", 1), ("quiet", 3), ("tone", 1)], floor=-45.0)
    levels = measure(write(tmp_path / "abs.wav", data, rate))
    assert find_silences(levels, SilenceCriteria(threshold_db=-50.0)) == []  # the noise is above -50
    assert spans(find_silences(levels, SilenceCriteria(threshold_db=-40.0))) == [(1.25, 3.75)]


def test_stereo_counts_every_channel(tmp_path: Path) -> None:
    """Sound on one channel only, or out of phase, is not silence (a mono sum would cancel the latter)."""
    rate = 8_000
    quiet = noise(4, rate)
    one_side = np.stack([quiet, quiet + tone(4, rate)], axis=1)
    opposite = np.stack([quiet + tone(4, rate), quiet - tone(4, rate)], axis=1)
    for name, data in (("one.wav", one_side), ("phase.wav", opposite)):
        levels = measure(write(tmp_path / name, data, rate))
        assert levels.info.channels == 2
        assert find_silences(levels, SilenceCriteria(threshold_db=-40.0, min_seconds=0.5)) == []


def test_short_blips_do_not_break_a_silence(tmp_path: Path) -> None:
    rate = 8_000
    blip = layout(rate, [("tone", 1), ("quiet", 2), ("tone", 0.1), ("quiet", 2), ("tone", 1)])
    levels = measure(write(tmp_path / "blip.wav", blip, rate))
    assert spans(find_silences(levels, SilenceCriteria(min_seconds=3.0, merge_gap_seconds=0.3))) == [(1.25, 4.85)]
    split = find_silences(levels, SilenceCriteria(min_seconds=1.5, merge_gap_seconds=0.0))
    assert spans(split) == [(1.25, 2.75), (3.35, 4.85)]


def test_last_window_may_be_shorter(tmp_path: Path) -> None:
    levels = measure(write(tmp_path / "odd.wav", noise(1.1, 8_000)[:8_039], 8_000))  # 50 windows + 39 samples
    assert levels.rms_db.size == 51
    assert levels.window_end(50) == pytest.approx(8_039 / 8_000)
    assert levels.window_end(49) == pytest.approx(1.0)


def test_silence_across_block_boundaries(tmp_path: Path) -> None:
    rate = 8_000
    block = BLOCK_WINDOWS * WINDOW  # 10 s
    data = layout(rate, [("tone", block - 1), ("quiet", 3), ("tone", block), ("quiet", 2.5), ("tone", 2)])
    levels = measure(write(tmp_path / "long.wav", data, rate, subtype="PCM_16"))
    assert levels.rms_db.size == round(levels.seconds / WINDOW)
    found = find_silences(levels, SilenceCriteria(min_seconds=2.0))
    assert spans(found) == [(9.25, 11.75), (22.25, 24.25)]


def test_probe_reads_only_the_header(tmp_path: Path) -> None:
    info = probe(write(tmp_path / "h.wav", noise(2, 8_000), 8_000, subtype="PCM_24"))
    assert (info.format, info.subtype, info.rate, info.channels, info.frames) == ("WAV", "PCM_24", 8_000, 1, 16_000)
    assert info.seconds == 2.0


def test_errors(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError) as missing:
        probe(tmp_path / "nope.wav")
    assert missing.value.code == "NOT_FOUND"
    text = tmp_path / "notes.wav"
    text.write_text("not audio", encoding="utf-8")
    with pytest.raises(PreconditionFailedError) as bad:
        measure(text)
    assert bad.value.code == "BAD_AUDIO"
    with pytest.raises(PreconditionFailedError) as window:
        measure(text, window=2.0)
    assert window.value.code == "BAD_REQUEST"
    levels = measure(write(tmp_path / "ok.wav", noise(1, 8_000), 8_000))
    for criteria in (
        SilenceCriteria(min_seconds=0),
        SilenceCriteria(padding_seconds=-1),
        SilenceCriteria(merge_gap_seconds=-0.1),
        SilenceCriteria(above_floor_db=-3),
    ):
        with pytest.raises(PreconditionFailedError) as exc:
            find_silences(levels, criteria)
        assert exc.value.code == "BAD_REQUEST"


def test_a_read_error_mid_file_is_bad_audio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = write(tmp_path / "cut.wav", noise(1, 8_000), 8_000)

    def broken(*_args: object, **_kwargs: object) -> object:
        yield np.zeros((160, 1))
        raise RuntimeError("Error : unexpected end of file")

    monkeypatch.setattr("trackwright.analysis.reader.sf.blocks", broken)
    with pytest.raises(PreconditionFailedError) as exc:
        measure(path)
    assert exc.value.code == "BAD_AUDIO"
    assert "unexpected end of file" in str(exc.value.details["reason"])


def test_empty_file(tmp_path: Path) -> None:
    levels = measure(write(tmp_path / "empty.wav", np.zeros(0), 8_000))
    assert levels.rms_db.size == 0
    assert find_silences(levels) == []
    assert noise_floor(levels) is None


# ---------------------------------------------------------------- properties over any levels
def make_levels(values: list[float], zeros: list[bool]) -> Levels:
    count = len(values)
    hop = 160  # 20 ms at 8 kHz
    return Levels(
        info=AudioInfo(format="WAV", subtype="FLOAT", rate=8_000, channels=1, frames=count * hop),
        window=WINDOW,
        rms_db=np.array(values, dtype=np.float64),
        digital_silence=np.array(zeros[:count], dtype=np.bool_),
        peak_db=0.0,
        rms_total_db=0.0,
    )


@given(
    data=st.lists(st.tuples(st.floats(-90, 0), st.booleans()), min_size=1, max_size=600),
    min_seconds=st.floats(0.02, 3.0),
    padding=st.floats(0.0, 0.5),
    gap=st.floats(0.0, 0.5),
    above=st.floats(0.0, 30.0),
)
@settings(max_examples=300, deadline=None)
def test_silences_are_ordered_inside_and_long_enough(
    data: list[tuple[float, bool]], min_seconds: float, padding: float, gap: float, above: float
) -> None:
    levels = make_levels([v for v, _ in data], [z for _, z in data])
    criteria = SilenceCriteria(min_seconds=min_seconds, padding_seconds=padding, merge_gap_seconds=gap,
                               above_floor_db=above)  # fmt: skip
    found = find_silences(levels, criteria)
    previous_end = -1.0
    for silence in found:
        assert 0.0 <= silence.start < silence.end <= levels.seconds + 1e-9
        assert silence.start >= previous_end
        assert silence.seconds >= min_seconds - 2 * padding - 1e-4  # start and end are rounded to 0.1 ms
        previous_end = silence.end


def test_quiet_and_typical_sound_levels(tmp_path: Path) -> None:
    """TW-1507: a gate threshold must stay below the soft phrase; the quiet level finds it."""
    rate = 8_000
    rng = np.random.default_rng(5)
    floor = rng.normal(0.0, 10 ** (-55 / 20), rate * 20)
    t = np.arange(rate * 4) / rate
    loud = np.sqrt(2) * 10 ** (-16 / 20) * np.sin(2 * np.pi * 220 * t)
    soft = np.sqrt(2) * 10 ** (-36 / 20) * np.sin(2 * np.pi * 220 * t)
    data = floor.copy()
    data[rate * 2 : rate * 6] += loud
    data[rate * 8 : rate * 12] += soft
    data[rate * 14 : rate * 18] += loud
    levels = measure(write(tmp_path / "gate.wav", data, rate))
    limit = threshold(levels, SilenceCriteria())
    assert noise_floor(levels) == pytest.approx(-55.0, abs=1.0)
    quiet, typical = sound_levels(levels, limit)
    assert quiet == pytest.approx(-36.0, abs=1.0)  # the soft phrase, not the noise and not the loud parts
    assert typical == pytest.approx(-16.0, abs=1.0)
    assert sound_levels(levels, None) == (None, None)
    assert sound_levels(levels, 10.0) == (None, None)  # nothing above the limit


def test_syllables_are_not_blips(tmp_path: Path) -> None:
    """TW-1507: speech is 250 ms syllables with 100 ms gaps; the default merge gap must not join the pauses
    around a phrase into one silence (0.3 s did: the whole file became a silence)."""
    rate = 8_000
    t = np.arange(rate * 4) / rate
    envelope = ((t % 0.35) < 0.25).astype(np.float64)
    phrase = np.sqrt(2) * 10 ** (-16 / 20) * np.sin(2 * np.pi * 220 * t) * envelope
    data = np.concatenate([noise(3, rate, -55.0, 1), phrase + noise(4, rate, -55.0, 2), noise(3, rate, -55.0, 3)])
    levels = measure(write(tmp_path / "speech.wav", data, rate))
    assert spans(find_silences(levels, SilenceCriteria(min_seconds=1.0))) == [(0.0, 2.75), (7.25, 10.0)]


def test_padding_that_leaves_nothing_after_rounding() -> None:
    """Found by Hypothesis: a silence a hair longer than twice the padding became a 0.18-0.18 span."""
    levels = make_levels([0.0] * 9 + [-90.0] * 10 + [0.0] * 9, [False] * 28)
    criteria = SilenceCriteria(min_seconds=0.02, padding_seconds=0.09999999, merge_gap_seconds=0.0, threshold_db=-50)
    assert all(s.end > s.start for s in find_silences(levels, criteria))
