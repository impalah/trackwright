"""TW-1619: a stinger between sections: the pause, never the last phrase, the tail, the options; clip renders."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from trackwright.analysis.transitions import audible_seconds, find_gap, plan_transition, render_clip
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import NotFoundError, PreconditionFailedError
from trackwright.fake import FakeCubase
from trackwright.workspace import Workspace

RATE = 48000
SPEECH = [(1.0, 10.0), (10.2, 20.0), (22.5, 40.0), (40.5, 50.0)]  # a section change at 20.0 -> 22.5


def test_the_nearest_pause() -> None:
    assert (find_gap(SPEECH, 21.0).start, find_gap(SPEECH, 21.0).end) == (20.0, 22.5)  # inside it
    assert find_gap(SPEECH, 18.0).start == 20.0  # in speech: the nearest pause
    assert find_gap(SPEECH, 15.0).start == 20.0  # 10.0-10.2 is too short to be a pause
    assert find_gap(SPEECH, 0.2) == find_gap(SPEECH, 0.0)
    assert find_gap(SPEECH, 0.0).end == 1.0  # before the first phrase
    assert find_gap(SPEECH, 60.0).end is None  # after the last
    assert find_gap([], 5.0).end is None


def test_a_stinger_that_fits_never_covers_the_last_phrase() -> None:
    place = plan_transition(SPEECH, 21.0, 1.5)
    assert (place.start, place.end, place.fits, place.overlap) == (20.3, 21.8, True, 0.0)
    assert place.options == []


def test_a_stinger_that_does_not_fit_says_by_how_much_and_what_to_do() -> None:
    place = plan_transition(SPEECH, 21.0, 3.0)
    assert place.start == 20.3  # still after the phrase: nothing moves it earlier
    assert not place.fits
    assert place.overlap == pytest.approx(1.1)  # 20.3 + 3.0 + 0.3 - 22.5
    assert any("insert silence at 22.50" in o for o in place.options)
    assert any("at most 1.90 s" in o for o in place.options)
    with pytest.raises(ValueError, match="audible"):
        plan_transition(SPEECH, 21.0, 0.0)


def test_at_the_ends() -> None:
    first = plan_transition(SPEECH, 0.0, 0.5)
    assert (first.start, first.fits) == (0.0, True)  # no phrase to protect before the first one
    last = plan_transition(SPEECH, 55.0, 8.0)
    assert (last.start, last.fits) == (50.3, True)


def test_audible_length_and_clip() -> None:
    t = np.arange(3 * RATE) / RATE
    tone = np.where(t < 1.2, 0.5 * np.sin(2 * np.pi * 440 * t), 0.0)
    data = np.column_stack([tone, tone])
    assert audible_seconds(data, RATE) == pytest.approx(1.2, abs=0.011)
    assert audible_seconds(np.zeros((RATE, 2)), RATE) == 0.0
    assert audible_seconds(np.zeros((10, 2)), RATE) == 0.0
    out = render_clip(data, RATE, gain_db=-6.0206, trim_end=1.0, fade_in=0.1, fade_out=0.5)
    assert len(out) == RATE
    assert out[0, 0] == 0.0  # faded at both ends
    assert out[-1, 0] == 0.0
    middle = np.abs(out[int(0.2 * RATE) : int(0.5 * RATE), 0]).max()
    assert middle == pytest.approx(0.25, abs=0.001)  # -6 dB


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


def tone(path: Path, seconds: float, spans: list[tuple[float, float]], rate: int = RATE) -> Path:
    t = np.arange(round(seconds * rate)) / rate
    x = 0.0005 * np.random.default_rng(3).standard_normal(len(t))
    for a, b in spans:
        inside = (t >= a) & (t < b)
        x[inside] += 0.3 * np.sin(2 * np.pi * 300 * t[inside])
    sf.write(path, np.column_stack([x, x]), rate, subtype="FLOAT")
    return path


def make(fake: FakeCubase, project: Path) -> CubaseService:
    policy = WritePolicy(enabled=True, analysis=True, workspace=True)
    return CubaseService(fake, policy, launcher=Launcher([str(project)]))  # type: ignore[arg-type]


def test_the_tool(fake: FakeCubase, project: Path) -> None:
    voice = tone(project / "Mixdown" / "voices.wav", 30.0, [(2.0, 10.0), (14.0, 25.0)])
    stinger = tone(project / "sting.wav", 4.0, [(0.0, 1.5)])  # 1.5 s of sound, then silence
    long = tone(project / "long.wav", 6.0, [(0.0, 6.0)], rate=44100)
    svc = make(fake, project)
    plan = svc.transition_plan(str(voice), "0:12", str(stinger))
    assert plan.fits
    assert plan.pause_start == pytest.approx(10.0, abs=0.3)  # the detector's hangover
    assert plan.pause_end == pytest.approx(14.0, abs=0.3)
    assert plan.start == pytest.approx(plan.pause_start + 0.3)
    assert plan.audible_seconds == pytest.approx(1.5, abs=0.02)
    assert any("silence after it" in n for n in plan.notes)
    assert plan.preview[0] < plan.pause_start
    assert plan.pause_end is not None
    assert plan.preview[1] > plan.pause_end
    late = svc.transition_plan(str(voice), "12", str(long), voice_start=100.0)  # the voice at 100 s
    assert (late.pause_start, late.start) == (0.0, 0.0)  # the nearest pause: before its first phrase
    assert any("opens the episode" in n for n in late.notes)
    tight = svc.transition_plan(str(voice), "12", str(long))
    assert (tight.fits, tight.sample_rate) == (False, 44100)
    assert tight.overlap > 2.0
    assert any("does not fit" in n for n in tight.notes)
    far = svc.transition_plan(str(voice), "40", str(stinger))
    assert far.pause_end is None
    assert any("from 40" in n for n in far.notes)  # 15 s after the last phrase
    with pytest.raises(PreconditionFailedError):
        svc.transition_plan(str(voice), "soon", str(stinger))
    with pytest.raises(NotFoundError):
        svc.transition_plan(str(voice), "12", str(project / "none.wav"))
    silent = project / "silent.wav"
    sf.write(silent, np.zeros((RATE, 2)), RATE)
    with pytest.raises(PreconditionFailedError) as quiet:
        svc.transition_plan(str(voice), "12", str(silent))
    assert quiet.value.code == "SILENT_SOURCE"


def test_a_clip_render(fake: FakeCubase, project: Path) -> None:
    stinger = tone(project / "sting.wav", 4.0, [(0.0, 4.0)], rate=44100)
    svc = make(fake, project)
    clip = {"trim_end": 2.0, "fade_out": 0.5, "sample_rate": RATE}
    plan = svc.render(file=str(stinger), process="clip", clip=clip, gain_db=-3.0, start="10.3", name="sting")
    assert plan.render is not None
    assert (plan.render.seconds, plan.render.sample_rate) == (2.0, RATE)
    assert plan.render.parameters["gain_db"] == -3.0
    done = svc.render(file=str(stinger), process="clip", clip=clip, gain_db=-3.0, start="10.3", name="sting",
                      dry_run=False)  # fmt: skip
    assert done.render is not None
    info = sf.info(done.render.file)
    assert (info.samplerate, info.frames) == (RATE, 2 * RATE)
    with pytest.raises(PreconditionFailedError):
        svc.render(file=str(stinger), process="clip", clip={"trim_end": 1.0, "fade_out": 2.0})
    with pytest.raises(PreconditionFailedError):
        svc.render(file=str(stinger), process="clip", clip={"loop": 1})
