"""TW-1621: sound effects: what an effect lands on, its level against the voice, overlaps; the credits."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from trackwright.analysis.transitions import active_level_db, overlaps
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import NotFoundError, PolicyError, PreconditionFailedError
from trackwright.fake import FakeCubase
from trackwright.workspace import FOLDER, OwnedItem, State, Workspace, credits_markdown, credits_of, now

RATE = 48000


def test_overlaps_and_level() -> None:
    assert overlaps([(1.0, 3.0), (5.0, 8.0), (9.0, 10.0)], 2.0, 6.0) == [(2.0, 3.0), (5.0, 6.0)]
    assert overlaps([(1.0, 2.0)], 2.0, 3.0) == []
    tone = 0.5 * np.sin(2 * np.pi * 440 * np.arange(RATE) / RATE)
    padded = np.concatenate([tone, np.zeros(3 * RATE)])  # 1 s of sound, 3 s of silence
    level = active_level_db(np.column_stack([padded, padded]), RATE)
    assert level == pytest.approx(20 * np.log10(0.5 / np.sqrt(2)), abs=0.1)  # the silence does not dilute it
    assert active_level_db(np.zeros((RATE, 2)), RATE) is None
    assert active_level_db(np.zeros((10, 2)), RATE) is None


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


def sound(path: Path, seconds: float, spans: list[tuple[float, float]], amp: float = 0.3) -> Path:
    t = np.arange(round(seconds * RATE)) / RATE
    x = 0.0005 * np.random.default_rng(5).standard_normal(len(t))
    for a, b in spans:
        inside = (t >= a) & (t < b)
        x[inside] += amp * np.sin(2 * np.pi * 300 * t[inside])
    sf.write(path, np.column_stack([x, x]), RATE, subtype="FLOAT")
    return path


def make(fake: FakeCubase, project: Path | None, *, analysis: bool = True, workspace: bool = True) -> CubaseService:
    policy = WritePolicy(enabled=True, analysis=analysis, workspace=workspace)
    folders = [str(project)] if project else []
    return CubaseService(fake, policy, launcher=Launcher(folders))  # type: ignore[arg-type]


def test_an_effect_under_speech_and_in_a_pause(fake: FakeCubase, project: Path) -> None:
    voice = sound(project / "Mixdown" / "voices.wav", 30.0, [(2.0, 10.0), (14.0, 25.0)])
    door = sound(project / "door.wav", 2.0, [(0.0, 1.0)], amp=0.9)  # louder than the voice
    svc = make(fake, project)
    under = svc.effect_plan(str(door), "5", voice_file=str(voice))
    assert under.start == 5.0
    assert under.audible_seconds == pytest.approx(1.0, abs=0.02)
    assert under.under_speech_seconds == pytest.approx(1.0, abs=0.02)
    assert under.relative_db == -12.0
    assert under.speech_level_db is not None
    expected = under.speech_level_db - 12.0 - under.effect_level_db
    assert under.suggested_gain_db == pytest.approx(expected, abs=0.06)  # rounded to 0.1 dB
    assert under.suggested_gain_db is not None
    assert under.suggested_gain_db < -12  # 0.9 against 0.3: well down
    assert any("lands on" in n for n in under.notes)
    assert any("its sound ends at" in n for n in under.notes)
    pause = svc.effect_plan(str(door), "11.5", voice_file=str(voice), voice_start=0.0)
    assert (pause.under_speech, pause.relative_db) == ([], -3.0)
    assert any("pause" in n for n in pause.notes)
    chosen = svc.effect_plan(str(door), "11.5", voice_file=str(voice), relative_db=0.0)
    assert chosen.relative_db == 0.0
    alone = svc.effect_plan(str(door), "0:05")
    assert (alone.suggested_gain_db, alone.speech_level_db) == (None, None)
    assert any("no voice export" in n for n in alone.notes)
    assert alone.preview == [2.0, pytest.approx(9.0, abs=0.02)]


def test_overlapping_an_earlier_effect(fake: FakeCubase, project: Path) -> None:
    door = sound(project / "door.wav", 2.0, [(0.0, 1.0)])
    svc = make(fake, project)
    first = svc.render(file=str(door), process="clip", start="5", name="door", skill="podcast-sound-effects",
                       dry_run=False)  # fmt: skip
    assert first.render is not None
    key = f"renders/{Path(first.render.file).name}"
    svc.workspace("record", kind="render", key=key, skill="podcast-sound-effects", run="r1",
                  details={"track_uid": "FX1", "position": 5.0}, dry_run=False)  # fmt: skip
    hit = svc.effect_plan(str(door), "6.5")  # the provenance says 2.0 s: 5.0..7.0
    assert [(o.start, o.end, o.track_uid) for o in hit.overlaps] == [(5.0, 7.0, "FX1")]
    assert any("overlaps 1 earlier" in n for n in hit.notes)
    svc.workspace(
        "record",
        kind="render",
        key=key,
        skill="podcast-sound-effects",
        run="r1",
        details={"audible_seconds": 1.0},
        dry_run=False,
    )  # merged: now its sound is 5.0..6.0
    assert svc.effect_plan(str(door), "6.5").overlaps == []
    state = json.loads((project / FOLDER / "state.json").read_text())
    state["items"].append({"kind": "render", "key": "renders/gone.wav", "skill": "podcast-sound-effects",
                           "run": "r", "updated": "2026-11-16T00:00:00Z", "details": {"position": 6}})  # fmt: skip
    (project / FOLDER / "state.json").write_text(json.dumps(state))
    assert svc.effect_plan(str(door), "6.5").overlaps == []  # a render that is gone is skipped
    assert make(fake, None).effect_plan(str(door), "6.5").overlaps == []  # no project folder known
    bare = project.parent / "bare"
    bare.mkdir()
    assert make(fake, bare).effect_plan(str(door), "6.5").overlaps == []  # no workspace


def test_effect_refusals(fake: FakeCubase, project: Path) -> None:
    svc = make(fake, project)
    silent = project / "silent.wav"
    sf.write(silent, np.zeros((RATE, 2)), RATE)
    with pytest.raises(PreconditionFailedError) as quiet:
        svc.effect_plan(str(silent), "1")
    assert quiet.value.code == "SILENT_SOURCE"
    with pytest.raises(PreconditionFailedError):
        svc.effect_plan(str(silent), "later")
    with pytest.raises(NotFoundError):
        svc.effect_plan(str(project / "none.wav"), "1")
    with pytest.raises(PolicyError):
        make(fake, project, analysis=False).effect_plan(str(silent), "1")


def item(key: str, skill: str, **details: str | float) -> OwnedItem:
    return OwnedItem(kind="render", key=key, skill=skill, run="r", updated=now(), details=details)


def test_credits_gather_every_licence_once() -> None:
    state = State(items=[
        item("renders/a.wav", "podcast-section-transitions", title="Whoosh", license="Storyblocks",
             source="Storyblocks", at=21.48, track_uid="T"),
        item("renders/b.wav", "podcast-sound-effects", title="Door | close", license="CC-BY-4.0",
             attribution="Door by Someone (CC BY 4.0)", position=65.5),
        item("renders/c.wav", "podcast-sound-effects", title="Whoosh", license="Storyblocks", position=90.0),
        item("renders/d.wav", "podcast-music-bed", position=0),  # no licence: not a credit
        item("renders/e.wav", "x", license=""),
    ])  # fmt: skip
    found = credits_of(state)
    assert [c.title for c in found] == ["Door | close", "Whoosh"]
    whoosh = found[1]
    assert (whoosh.at, whoosh.skills) == ([21.48, 90.0], ["podcast-section-transitions", "podcast-sound-effects"])
    text = credits_markdown(found, "E0004")
    assert text.startswith("# Credits: E0004")
    assert "- Door by Someone (CC BY 4.0)" in text
    assert "Door \\| close" in text
    assert "| Whoosh | Storyblocks | Storyblocks | none asked | 0:21.480, 1:30.000 |" in text
    assert "No sound used asks" in credits_markdown([found[1]], "E")


def test_the_credits_action(fake: FakeCubase, project: Path) -> None:
    svc = make(fake, project)
    empty = svc.workspace("credits")
    assert (empty.status, empty.credits) == ("planned", [])
    assert any("nothing to credit" in n for n in empty.notes)
    svc.workspace("record", kind="render", key="renders/a.wav", skill="s", run="r",
                  details={"title": "Whoosh", "license": "Storyblocks", "at": 3.0}, dry_run=False)  # fmt: skip
    plan = svc.workspace("credits")
    assert plan.credits[0]["title"] == "Whoosh"
    assert plan.credits_file is not None
    assert not Path(plan.credits_file).exists()
    done = svc.workspace("credits", dry_run=False)
    assert done.status == "written"
    assert "| Whoosh | Storyblocks |" in Path(plan.credits_file).read_text()
    with pytest.raises(PolicyError):
        make(fake, project, workspace=False).workspace("credits")
    with pytest.raises(PreconditionFailedError) as unknown:
        make(fake, None).workspace("credits")
    assert unknown.value.code == "NO_PROJECT_FOLDER"
    bare = project.parent / "bare"
    bare.mkdir()
    with pytest.raises(PreconditionFailedError) as missing:
        make(fake, bare).workspace("credits", dry_run=False)
    assert missing.value.code == "NO_WORKSPACE"
