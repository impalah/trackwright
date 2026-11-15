"""TW-1606: renders in Trackwright/renders/ with their provenance, imported back and owned."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import NotFoundError, PolicyError, PreconditionFailedError
from trackwright.fake import FakeCubase, FakeExports
from trackwright.renders import (
    gain,
    is_render,
    load_provenance,
    next_name,
    problems,
    provenance_path,
    render_file,
    slug,
)
from trackwright.workspace import Workspace

RATE = 48000


class Launcher:
    def __init__(self, folders: list[str]) -> None:
        self.folders = folders

    def project_folders(self) -> list[str]:
        return self.folders


@pytest.fixture
def project(tmp_path: Path) -> Path:
    folder = tmp_path / "X0001.test"
    (folder / "Mixdown").mkdir(parents=True)
    Workspace(folder).create()
    return folder


@pytest.fixture
def export(project: Path) -> Path:
    """Two seconds of a stereo 1 kHz tone at -12 dBFS: the export of a track alone."""
    t = np.arange(2 * RATE) / RATE
    tone = 0.25 * np.sin(2 * np.pi * 1000 * t)
    path = project / "Mixdown" / "voice.wav"
    sf.write(path, np.column_stack([tone, tone]), RATE, subtype="FLOAT")
    return path


@pytest.fixture
def exports() -> FakeExports:
    return FakeExports()


def make(
    fake: FakeCubase,
    project: Path | None,
    exports: FakeExports | None = None,
    *,
    workspace: bool = True,
    **policy: bool,
) -> CubaseService:
    folders = [str(project)] if project is not None else []
    return CubaseService(
        fake,
        WritePolicy(enabled=True, analysis=policy.get("analysis", True), workspace=workspace),
        sleep=lambda _s: None,
        settle_timeout=0.0,
        launcher=Launcher(folders),  # type: ignore[arg-type]
        exports=exports,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------- the renders module
def test_names_are_safe_and_never_reused(tmp_path: Path) -> None:
    assert slug("Pod Mic / gain") == "Pod-Mic-gain"
    assert slug("../..") == "render"
    assert slug("x" * 100) == "x" * 64
    assert next_name(tmp_path, "voice-gain") == "voice-gain.wav"
    (tmp_path / "voice-gain.wav").write_bytes(b"")
    assert next_name(tmp_path, "voice-gain") == "voice-gain-2.wav"
    (tmp_path / "voice-gain-2.json").write_text("{}")
    assert next_name(tmp_path, "voice-gain") == "voice-gain-3.wav"


def test_gain_is_exact_and_float(export: Path, tmp_path: Path) -> None:
    target = tmp_path / "half.wav"
    info, peak = render_file(export, target, gain(-20 * np.log10(2)))
    data, rate = sf.read(target, dtype="float64", always_2d=True)
    source, _ = sf.read(export, dtype="float64", always_2d=True)
    assert (rate, data.shape, sf.info(str(target)).subtype) == (RATE, source.shape, "FLOAT")
    assert np.max(np.abs(data - source / 2)) < 1e-7
    assert peak == pytest.approx(0.125, abs=1e-6)
    assert (info.rate, info.channels) == (RATE, 2)


def test_a_failed_render_leaves_nothing(export: Path, tmp_path: Path) -> None:
    def broken(_block: np.ndarray) -> np.ndarray:
        raise ValueError("boom")

    folder = tmp_path / "out"
    folder.mkdir()
    with pytest.raises(ValueError, match="boom"):
        render_file(export, folder / "x.wav", broken)
    assert list(folder.iterdir()) == []


def test_unreadable_source(export: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("Internal psf_fseek() failed")

    monkeypatch.setattr(sf, "blocks", failing)
    target = tmp_path / "out.wav"
    with pytest.raises(PreconditionFailedError) as exc:
        render_file(export, target, gain(0))
    assert exc.value.code == "BAD_AUDIO"
    assert not target.exists()


# ---------------------------------------------------------------- the tool: render
def test_dry_run_writes_nothing(fake: FakeCubase, project: Path, export: Path) -> None:
    out = make(fake, project).render(file=str(export), start="40", gain_db=-6, track="POC-TEST")
    assert (out.status, out.dry_run) == ("planned", True)
    assert out.render is not None
    assert out.render.file.endswith("Trackwright/renders/POC-TEST-gain.wav")
    assert (out.render.position, out.render.replaces, out.render.seconds) == ("0:00:40.000", "POC-TEST", 2.0)
    assert list((project / "Trackwright" / "renders").iterdir()) == []


def test_render_with_provenance(fake: FakeCubase, project: Path, export: Path) -> None:
    svc = make(fake, project)
    out = svc.render(file=str(export), start="40", gain_db=-6, track="POC-TEST", skill="test", run="r1", dry_run=False)
    assert out.status == "done"
    assert out.render is not None
    render = Path(out.render.file)
    assert is_render(render)
    provenance = load_provenance(render)
    uid = fake.channel_by_title("POC-TEST").uid
    assert (provenance.skill, provenance.run, provenance.process) == ("test", "r1", "gain")
    assert (provenance.position, provenance.track, provenance.track_uid) == (40.0, "POC-TEST", uid)
    assert provenance.parameters == {"gain_db": -6}
    assert provenance.source.path == str(export)
    assert (provenance.rate, provenance.channels, provenance.seconds) == (RATE, 2, 2.0)
    assert provenance.peak_dbfs == pytest.approx(-18.04, abs=0.01)
    assert problems(render, provenance) == []
    assert out.instructions is not None
    assert "untick 'Copy file to project folder'" in out.instructions
    assert "mute 'POC-TEST'" in out.instructions
    again = svc.render(file=str(export), start="40", track="POC-TEST", skill="test", dry_run=False)
    assert again.render is not None
    assert again.render.file.endswith("POC-TEST-gain-2.wav")
    assert render.is_file()  # the first one is untouched


def test_loud_render_is_noted(fake: FakeCubase, project: Path, export: Path) -> None:
    out = make(fake, project).render(file=str(export), gain_db=20, name="hot.wav", dry_run=False)
    assert out.render is not None
    assert out.render.file.endswith("renders/hot.wav")
    assert any("peaks at" in n for n in out.notes)


def test_problems_are_found(fake: FakeCubase, project: Path, export: Path) -> None:
    out = make(fake, project).render(file=str(export), dry_run=False)
    assert out.render is not None
    render = Path(out.render.file)
    provenance = load_provenance(render)
    data, _ = sf.read(export, always_2d=True)
    sf.write(export, data * 0.5, RATE, subtype="FLOAT")
    assert problems(render, provenance) == ["the source voice.wav changed after the render was made"]
    export.unlink()
    assert problems(render, provenance) == ["the source voice.wav is gone (the render itself is still usable)"]
    render.write_bytes(render.read_bytes()[:-4] + b"\0\0\0\1")
    assert "voice-gain.wav changed after it was rendered" in problems(render, provenance)
    render.unlink()
    assert problems(render, provenance) == ["the render voice-gain.wav is missing"]
    assert not is_render(render)


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"file": None}, "BAD_REQUEST"),
        ({"process": "reverb"}, "BAD_REQUEST"),
        ({"gain_db": 41}, "BAD_REQUEST"),
        ({"skill": " "}, "BAD_REQUEST"),
        ({"start": "soon"}, "BAD_TIME"),
        ({"file": "relative.wav"}, "BAD_REQUEST"),
    ],
)
def test_bad_requests(fake: FakeCubase, project: Path, export: Path, kwargs: dict[str, object], code: str) -> None:
    args: dict[str, object] = {"file": str(export), **kwargs}
    with pytest.raises(PreconditionFailedError) as exc:
        make(fake, project).render(**args)  # type: ignore[arg-type]
    assert exc.value.code == code


def test_missing_source(fake: FakeCubase, project: Path) -> None:
    with pytest.raises(NotFoundError):
        make(fake, project).render(file=str(project / "nope.wav"))


def test_permissions_and_workspace(fake: FakeCubase, project: Path, export: Path, tmp_path: Path) -> None:
    with pytest.raises(PolicyError) as disabled:
        make(fake, project, workspace=False).render(file=str(export))
    assert disabled.value.code == "WORKSPACE_DISABLED"
    with pytest.raises(PolicyError) as no_analysis:
        make(fake, project, analysis=False).render(file=str(export))
    assert no_analysis.value.code == "ANALYSIS_DISABLED"
    with pytest.raises(PreconditionFailedError) as unknown:
        make(fake, None).render(file=str(export))
    assert unknown.value.code == "NO_PROJECT_FOLDER"
    bare = tmp_path / "bare"
    bare.mkdir()
    with pytest.raises(PreconditionFailedError) as none:
        make(fake, bare).render(file=str(export))
    assert none.value.code == "NO_WORKSPACE"
    (project / "Trackwright" / "renders").rmdir()
    assert make(fake, project).render(file=str(export)).status == "planned"
    with pytest.raises(PreconditionFailedError) as no_renders:
        make(fake, project).render(file=str(export), dry_run=False)
    assert no_renders.value.code == "NO_WORKSPACE"
    with pytest.raises(PreconditionFailedError):
        make(fake, project).render("other")  # type: ignore[arg-type]


# ---------------------------------------------------------------- import and ownership
def new_track(svc: CubaseService, fake: FakeCubase, name: str) -> str:
    svc.add_track_interactive("start", "audio", name)
    fake.complete_dialog(name)
    return f"uid:{fake.channel_by_title(name).uid}"


def rendered(svc: CubaseService, export: Path, exports: FakeExports, **kwargs: object) -> Path:
    out = svc.render(file=str(export), start="40", track="POC-TEST", skill="test", dry_run=False, **kwargs)  # type: ignore[arg-type]
    assert out.render is not None
    exports.durations[out.render.file] = 2.0
    return Path(out.render.file)


def test_import_records_ownership(fake: FakeCubase, project: Path, export: Path, exports: FakeExports) -> None:
    svc = make(fake, project, exports)
    render = rendered(svc, export, exports, run="r1")
    track = new_track(svc, fake, "POC-TEST render")
    plan = svc.import_audio("start", track, "40", file=str(render))
    assert plan.render == str(provenance_path(render))
    started = svc.import_audio("start", track, "40", file=str(render), dry_run=False)
    assert started.instructions is not None
    assert "untick 'Copy file to project folder'" in started.instructions
    fake.finish_import(2.0)
    done = svc.import_audio("confirm", track, "40", file=str(render), since=started.since)
    assert (done.status, done.verified, done.owned) == ("done", True, True)
    assert any("mute 'POC-TEST'" in n for n in done.notes)
    state = json.loads((project / "Trackwright" / "state.json").read_text())
    kinds = {(i["kind"], i["key"]) for i in state["items"]}
    uid = track.removeprefix("uid:")
    assert kinds == {("render", "renders/POC-TEST-gain.wav"), ("track", uid)}
    listed = svc.render("list")
    assert [(r.imported_on, r.track_present, r.problems) for r in listed.renders] == [(uid, True, [])]

    # a re-run: a new render on a new track; the earlier track is pointed out, not removed
    second = rendered(svc, export, exports, run="r2")
    other = new_track(svc, fake, "POC-TEST render 2")
    started = svc.import_audio("start", other, "40", file=str(second), dry_run=False)
    fake.finish_import(2.0)
    done = svc.import_audio("confirm", other, "40", file=str(second), since=started.since)
    assert any("'POC-TEST render'" in n and "earlier render track" in n for n in done.notes)
    assert fake.channel_by_title("POC-TEST render")


def test_import_refuses_a_misplaced_or_changed_render(
    fake: FakeCubase, project: Path, export: Path, exports: FakeExports
) -> None:
    svc = make(fake, project, exports)
    render = rendered(svc, export, exports)
    track = new_track(svc, fake, "R")
    with pytest.raises(PreconditionFailedError) as misplaced:
        svc.import_audio("start", track, "41", file=str(render))
    assert misplaced.value.code == "MISALIGNED"
    with pytest.raises(PreconditionFailedError) as original:
        svc.import_audio("start", "POC-TEST", "40", file=str(render))
    assert original.value.code == "BAD_REQUEST"
    export.unlink()
    plan = svc.import_audio("start", track, "40", file=str(render))
    assert any("is gone" in n for n in plan.notes)
    render.write_bytes(render.read_bytes()[:-4] + b"\0\0\0\1")
    with pytest.raises(PreconditionFailedError) as changed:
        svc.import_audio("start", track, "40", file=str(render))
    assert changed.value.code == "BAD_RENDER"


def test_import_without_workspace_permission_is_not_owned(
    fake: FakeCubase, project: Path, export: Path, exports: FakeExports
) -> None:
    render = rendered(make(fake, project, exports), export, exports)
    svc = make(fake, project, exports, workspace=False)
    track = new_track(svc, fake, "R")
    started = svc.import_audio("start", track, "40", file=str(render), dry_run=False)
    fake.finish_import(2.0)
    done = svc.import_audio("confirm", track, "40", file=str(render), since=started.since)
    assert (done.status, done.owned) == ("done", False)
    assert not (project / "Trackwright" / "state.json").exists()


def test_a_broken_provenance_is_reported(fake: FakeCubase, project: Path, export: Path, exports: FakeExports) -> None:
    svc = make(fake, project, exports)
    render = rendered(svc, export, exports)
    provenance_path(render).write_text("{not json", encoding="utf-8")
    with pytest.raises(PreconditionFailedError) as bad:
        svc.render("list")
    assert bad.value.code == "BAD_RENDER"


def test_list_of_an_empty_workspace(fake: FakeCubase, project: Path) -> None:
    out = make(fake, project).render("list")
    assert (out.status, out.renders) == ("listed", [])
    assert out.notes == ["no renders in the workspace"]
