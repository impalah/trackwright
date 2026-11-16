"""TW-1618: a loop the user marks (aligned, scored), a prepared loop, and where the seams fall in the bed."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from trackwright.analysis.music import BedPlan, Loop, estimate_tempo, plan_bed, seam_score, seam_times
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.fake import FakeCubase
from trackwright.workspace import Workspace

from .test_music_tw1617 import RATE, pattern, song


def test_a_marked_loop_is_scored_like_a_found_one() -> None:
    x = song(120.0)
    tempo = estimate_tempo(x, RATE)
    whole = seam_score(x, RATE, tempo, 4.0, 12.0)  # the whole 4-bar pattern
    cut = seam_score(x, RATE, tempo, 2.0, 6.0)  # bar 2 to bar 4: equal chords, the rest of the progression lost
    assert whole is not None
    assert cut is not None
    assert whole > 0.95
    assert cut < whole - 0.05  # ranked lower; one bar of four differs, so not by much
    assert seam_score(x, RATE, tempo, 0.0, len(x) / RATE) is None  # a whole file looped on itself


def test_seam_times_in_the_bed() -> None:
    plan = BedPlan(pieces=[(0.0, 10.0), (2.0, 10.0), (2.0, 38.0)], seconds=0.0, repeats=2, crossfade=0.5)
    assert seam_times(plan) == [9.5, 17.0]  # each seam where its crossfade begins
    assert seam_times(plan_bed(Loop(2.0, 10.0, 1.0, 0.0), 38.0, target=1.0)) == []


class Launcher:
    def __init__(self, folders: list[str]) -> None:
        self.folders = folders

    def project_folders(self) -> list[str]:
        return self.folders


@pytest.fixture
def svc(fake: FakeCubase, tmp_path: Path) -> CubaseService:
    project = tmp_path / "E0001"
    project.mkdir()
    Workspace(project).create()
    return CubaseService(fake, WritePolicy(enabled=True, analysis=True, workspace=True),
                         launcher=Launcher([str(project)]))  # type: ignore[arg-type]  # fmt: skip


def write(path: Path, x: np.ndarray) -> Path:
    sf.write(path, np.column_stack([x, x]), RATE, subtype="FLOAT")
    return path


def test_a_marked_region_is_aligned_and_doubtful_seams_noted(svc: CubaseService, tmp_path: Path) -> None:
    music = write(tmp_path / "song.wav", song(120.0))
    bed = {"loop_start": 4.0, "loop_end": 12.03, "target_seconds": 60.0, "align": True}
    out = svc.render(file=str(music), process="bed", bed=bed, name="bed")
    assert out.render is not None
    params = out.render.parameters
    assert params["loop_end_used"] == pytest.approx(12.0, abs=0.001)  # 30 ms late, lined up by correlation
    assert params["seam_score"] > 0.95
    assert params["seams"]
    assert any("lined up" in n for n in out.notes)
    # a jump into music of another character: the pattern, then 10 s of noise
    rng = np.random.default_rng(3)
    mixed = write(tmp_path / "mixed.wav", np.concatenate([pattern(120.0), 0.1 * rng.standard_normal(10 * RATE)]))
    doubtful = svc.render(file=str(mixed), process="bed", name="bed",
                          bed={"loop_start": 1.0, "loop_end": 9.0, "target_seconds": 40.0})  # fmt: skip
    assert any("listen to the seams" in n for n in doubtful.notes)


def test_a_prepared_loop_repeats_the_whole_file(svc: CubaseService, tmp_path: Path) -> None:
    loop = write(tmp_path / "loop.wav", pattern(120.0))  # 8 s, made to loop
    out = svc.render(file=str(loop), process="bed", name="bed", dry_run=False,
                     bed={"loop_start": 0.0, "loop_end": 8.0, "target_seconds": 30.0, "crossfade": 0.0})  # fmt: skip
    assert out.render is not None
    assert out.render.parameters["seam_score"] is None
    assert out.render.parameters["seams"] == [8.0, 16.0]
    data, _ = sf.read(out.render.file, always_2d=True)
    assert len(data) == 24 * RATE  # three passes, no crossfade: the file as it is, three times
    assert np.allclose(data[8 * RATE : 16 * RATE, 0], data[: 8 * RATE, 0], atol=1e-7)
