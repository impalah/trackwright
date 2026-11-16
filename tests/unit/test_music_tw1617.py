"""TW-1617: tempo, loop candidates, the ending, and a bed of a given length, on synthetic music."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
import soundfile as sf

from trackwright.analysis.music import (
    Loop,
    analyze,
    estimate_tempo,
    nearest_zero,
    plan_bed,
    render_bed,
)
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import PreconditionFailedError
from trackwright.fake import FakeCubase
from trackwright.workspace import Workspace

RATE = 48000
CHORDS = ((220, 277, 330), (196, 247, 294), (175, 220, 262), (196, 247, 294))


def pattern(bpm: float) -> npt.NDArray[np.float64]:
    """Four bars: a chord per bar and a kick on every beat."""
    beat = 60 / bpm
    t = np.arange(int(16 * beat * RATE)) / RATE
    x = np.zeros_like(t)
    for bar, chord in enumerate(CHORDS):
        inside = (t >= 4 * beat * bar) & (t < 4 * beat * (bar + 1))
        for f in chord:
            x[inside] += 0.05 * np.sin(2 * np.pi * f * t[inside])
    kick = int(0.05 * RATE)
    for b in np.arange(0, 16 * beat - 1e-9, beat):
        i = round(b * RATE)
        x[i : i + kick] += 0.4 * np.exp(-np.arange(kick) / 400) * np.sin(2 * np.pi * 60 * np.arange(kick) / RATE)
    return x


def song(bpm: float, repeats: int = 4) -> npt.NDArray[np.float64]:
    """The pattern ``repeats`` times, then 6 s of it fading out from the second second."""
    t = np.arange(6 * RATE) / RATE
    ending = pattern(bpm)[: len(t)] * np.clip(1 - (t - 2) / 4, 0, 1)
    return np.concatenate([*([pattern(bpm)] * repeats), ending])


@pytest.mark.parametrize("bpm", [75.0, 97.0, 120.0, 140.0])
def test_tempo_beats_and_whole_pattern_loops(bpm: float) -> None:
    result = analyze(song(bpm), RATE)
    beat, bar = 60 / bpm, 240 / bpm
    assert result.tempo.bpm == pytest.approx(bpm, abs=0.1)
    assert all(abs(b - round(b / beat) * beat) < 0.01 for b in result.tempo.beats)  # on the kicks, within 10 ms
    best = result.loops[0]
    # the chords change every bar: only whole patterns (4 bars) seam without a harmonic jump
    assert best.seconds / bar == pytest.approx(4.0, abs=0.02)
    assert best.score > 0.95
    assert result.ending is not None
    assert all(loop.end <= result.ending.start for loop in result.loops)


def test_no_beat_and_no_audio() -> None:
    rng = np.random.default_rng(1)
    noise = 0.1 * rng.standard_normal(10 * RATE)  # no periodic onsets
    tempo = estimate_tempo(noise, RATE)
    assert tempo.beats == []
    assert estimate_tempo(np.zeros(RATE), RATE).bpm is None
    silent = analyze(np.zeros(5 * RATE), RATE)
    assert (silent.ending, silent.loops) == (None, [])


def test_zero_crossings() -> None:
    x = np.sin(2 * np.pi * 100 * np.arange(RATE) / RATE)  # zero every 5 ms
    moved = nearest_zero(x, RATE, 0.0123)
    assert abs(x[round(moved * RATE)]) < 0.02  # one sample from the crossing: at most one step of the sine
    assert abs(moved - 0.0123) <= 0.005
    assert nearest_zero(np.ones(RATE), RATE, 0.5) == 0.5  # none nearby: kept


def test_a_bed_never_goes_over_and_ends_naturally() -> None:
    loop = Loop(2.0, 10.0, 1.0, 0.01)
    plan = plan_bed(loop, 38.0, target=60.0)
    # to the loop's end, back to its start, and on the last pass on to the end of the file
    assert plan.pieces[0] == (0.0, 10.0)
    assert plan.pieces[-1] == (2.0, 38.0)
    assert plan.repeats == 2  # 38 + 2 x 8 - 2 x 0.01 = 53.98; three would be 61.97
    assert plan.seconds == pytest.approx(53.98)
    assert plan_bed(loop, 38.0, target=1.0).pieces == [(0.0, 38.0)]  # shorter than the music: the music as it is
    jump = plan_bed(loop, 38.0, target=60.0, ending_start=34.0)
    assert jump.pieces[0] == (0.0, 2.0)
    assert jump.pieces[-1] == (34.0, 38.0)
    assert jump.seconds <= 60.0
    with pytest.raises(ValueError, match="inside the loop"):
        plan_bed(loop, 38.0, target=60.0, ending_start=5.0)
    x = song(120.0)
    rendered = render_bed(x, RATE, plan)
    assert len(rendered) / RATE == pytest.approx(53.98, abs=0.001)
    fade = round(0.01 * RATE)  # after its crossfade the last pass is the original, sample for sample
    assert np.allclose(rendered[-28 * RATE :, 0], x[10 * RATE : 38 * RATE], atol=1e-9)
    assert rendered.shape[0] > fade
    assert np.max(np.abs(np.diff(rendered[:, 0]))) <= np.max(np.abs(np.diff(x))) * 1.5  # no clicks at the seams


def test_the_loop_end_is_lined_up_with_its_start() -> None:
    from trackwright.analysis.music import refine_end

    x = song(120.0)
    # 8 s is exactly one pattern; ask for an end 30 ms late: the correlation brings it back
    assert refine_end(x, RATE, 4.0, 12.03) == pytest.approx(12.0, abs=0.001)


# ---------------------------------------------------------------- the tools
class Launcher:
    def __init__(self, folders: list[str]) -> None:
        self.folders = folders

    def project_folders(self) -> list[str]:
        return self.folders


def test_the_analysis_and_the_bed_render(fake: FakeCubase, tmp_path: Path) -> None:
    project = tmp_path / "E0001"
    project.mkdir()
    Workspace(project).create()
    music = project / "bed.wav"
    x = song(120.0)
    sf.write(music, np.column_stack([x, x]), RATE, subtype="FLOAT")
    svc = CubaseService(fake, WritePolicy(enabled=True, analysis=True, workspace=True),
                        launcher=Launcher([str(project)]))  # type: ignore[arg-type]  # fmt: skip
    out = svc.music_analysis(str(music))
    assert out.bpm == pytest.approx(120.0, abs=0.1)
    assert out.loops[0].bars == 4
    assert out.ending is not None
    assert out.cache == "stored"
    bed = {"loop_start": out.loops[0].start, "loop_end": out.loops[0].end, "target_seconds": 90.0}
    plan = svc.render(file=str(music), process="bed", bed=bed, name="bed-90")
    assert plan.render is not None
    assert plan.render.seconds <= 90.0
    done = svc.render(file=str(music), process="bed", bed=bed, name="bed-90", dry_run=False)
    assert done.render is not None
    written = sf.info(done.render.file)
    assert written.frames / written.samplerate == pytest.approx(plan.render.seconds, abs=0.001)
    assert done.render.parameters["repeats"] >= 1
    assert any("short of the target" in n for n in done.notes)
    for bad in (
        {**bed, "loop_end": bed["loop_start"]},
        {**bed, "ending_start": 1.0},  # inside the loop
        {**bed, "loop_end": bed["loop_start"] + 1.0, "crossfade": 0.6},
        {**bed, "colour": 1},
    ):
        with pytest.raises(PreconditionFailedError):
            svc.render(file=str(music), process="bed", bed=bad)
    with pytest.raises(PreconditionFailedError):
        svc.render(file=str(music), process="bed")
    with pytest.raises(PreconditionFailedError):
        svc.render(file=str(music), process="bed", bed={**bed, "ending_start": 500.0})
    jumped = svc.render(file=str(music), process="bed", bed={**bed, "ending_start": out.ending.start})
    assert jumped.render is not None
    assert jumped.render.seconds <= 90.0
