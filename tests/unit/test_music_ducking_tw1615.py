"""TW-1615: previews (a short mix of exports) and the spans an edit of the ducking plan changes."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import NotFoundError, PolicyError, PreconditionFailedError
from trackwright.fake import FakeCubase
from trackwright.workspace import Workspace

RATE = 48000


class Launcher:
    def __init__(self, folders: list[str]) -> None:
        self.folders = folders

    def project_folders(self) -> list[str]:
        return self.folders


@pytest.fixture
def project(tmp_path: Path) -> Path:
    folder = tmp_path / "E0001"
    (folder / "Mixdown").mkdir(parents=True)
    Workspace(folder).create()
    return folder


def write(path: Path, signal: np.ndarray, channels: int = 2) -> Path:
    sf.write(path, np.column_stack([signal] * channels), RATE, subtype="FLOAT")
    return path


@pytest.fixture
def voice(project: Path) -> Path:
    rng = np.random.default_rng(7)
    signal = 0.001 * rng.standard_normal(30 * RATE)
    t = np.arange(30 * RATE) / RATE
    for start, end in ((5.0, 9.0), (20.0, 24.0)):
        inside = (t >= start) & (t < end)
        signal[inside] += 0.3 * np.sin(2 * np.pi * 300 * t[inside])
    return write(project / "Mixdown" / "voices.wav", signal)


def make(fake: FakeCubase, project: Path, **policy: bool) -> CubaseService:
    flags = {"enabled": True, "analysis": True, "workspace": True, **policy}
    return CubaseService(fake, WritePolicy(**flags), launcher=Launcher([str(project)]))  # type: ignore[arg-type]


def test_a_preview_mixes_exports_in_project_time(fake: FakeCubase, project: Path) -> None:
    ones = write(project / "Mixdown" / "a.wav", np.full(4 * RATE, 0.25))  # project 10..14 s
    mono = write(project / "Mixdown" / "b.wav", np.full(2 * RATE, 0.5), channels=1)  # project 12..14 s
    svc = make(fake, project)
    sources = [{"file": str(ones), "start": 10.0}, {"file": str(mono), "start": 12.0, "gain_db": -6.0206}]
    plan = svc.preview(sources, start="9", end="15", name="check")
    assert (plan.status, plan.seconds) == ("planned", 6.0)
    assert not Path(plan.file).exists()
    out = svc.preview(sources, start="9", end="15", name="check", dry_run=False)
    data, rate = sf.read(out.file, always_2d=True)
    assert (rate, data.shape) == (RATE, (6 * RATE, 2))
    assert data[RATE // 2, 0] == 0.0  # 9.5 s: before the first file
    assert data[2 * RATE, 0] == pytest.approx(0.25)  # 11 s: the first file alone
    assert data[4 * RATE, 1] == pytest.approx(0.5, abs=1e-4)  # 13 s: both, the mono one on both channels
    assert data[-RATE // 2, 0] == 0.0  # 14.5 s: after both
    again = svc.preview(sources, start="9", end="15", name="check", dry_run=False)
    assert again.file.endswith("check-2.wav")  # never overwritten


def test_preview_refusals(fake: FakeCubase, project: Path) -> None:
    clip = write(project / "Mixdown" / "c.wav", np.zeros(RATE))
    other = project / "Mixdown" / "d.wav"
    sf.write(other, np.zeros((44100, 2)), 44100)
    svc = make(fake, project)
    for sources, start, end in (
        ([], "0", "1"),
        ([{"file": str(clip), "volume": 1}], "0", "1"),
        ([{"file": str(clip)}], "5", "1"),
        ([{"file": str(clip)}], "0", "500"),
        ([{"file": str(clip)}], "soon", "1"),
    ):
        with pytest.raises(PreconditionFailedError):
            svc.preview(sources, start=start, end=end)
    with pytest.raises(NotFoundError):
        svc.preview([{"file": str(clip.with_name("nope.wav"))}], start="0", end="1")
    with pytest.raises(PreconditionFailedError) as rates:
        svc.preview([{"file": str(clip)}, {"file": str(other)}], start="0", end="1", dry_run=False)
    assert rates.value.code == "BAD_AUDIO"
    with pytest.raises(PolicyError):
        make(fake, project, workspace=False).preview([{"file": str(clip)}], start="0", end="1")


def test_an_edit_lists_what_it_changes(fake: FakeCubase, project: Path, voice: Path) -> None:
    svc = make(fake, project)
    before = {"voice_file": str(voice)}
    plan = svc.ducking_plan(before)
    assert plan.changed is None
    assert [m.why for m in plan.moments[:2]] == [
        "the music goes down for the first word",
        "the music comes back up after the last word",
    ]
    edited = {**before, "overrides": [{"start": 19.0, "end": 26.0, "mode": "depth", "depth_db": -18.0}]}
    out = svc.ducking_plan(edited, previous=before, music_seconds=30.0)
    assert out.changed is not None
    assert len(out.changed) == 1  # only the second phrase
    assert 19.0 <= out.changed[0][0] <= 20.0
    assert svc.ducking_plan(before, previous=before).changed == []


def test_silent_sources_and_moments_are_pointed_out(fake: FakeCubase, project: Path, voice: Path) -> None:
    """Live, two previews fell in a gap of the music track and showed only the voice."""
    music = np.zeros(30 * RATE)
    music[: 12 * RATE] = 0.1  # music only for the first 12 s: the second phrase (20-24 s) has none
    music_file = write(project / "Mixdown" / "music.wav", music)
    svc = make(fake, project)
    plan = svc.ducking_plan({"voice_file": str(voice)}, music_seconds=30.0, music_file=str(music_file))
    # the first phrase's fall and recovery have music around them; the second phrase's do not
    assert [m.at for m in plan.moments] == [pytest.approx(4.75, abs=0.05), pytest.approx(10.0, abs=0.05)]
    assert plan.moments[0].music_db == pytest.approx(-20.0, abs=0.1)
    assert any("left out" in n for n in plan.notes)
    out = svc.preview(
        [{"file": str(voice)}, {"file": str(music_file)}], start="18", end="26", name="gap", dry_run=False
    )
    assert out.levels_db[1] is None
    assert any("music.wav (+0 dB) is silent" in n for n in out.notes)
    with pytest.raises(NotFoundError):
        svc.ducking_plan({"voice_file": str(voice)}, music_file=str(project / "missing.wav"))
