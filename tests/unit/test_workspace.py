"""TW-1602: the Trackwright/ folder inside a project folder, its models and the cubase_workspace tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import PolicyError, PreconditionFailedError
from trackwright.fake import FakeCubase
from trackwright.workspace import (
    FOLDER,
    SUBFOLDERS,
    EpisodeProfile,
    OwnedItem,
    ProtectedRange,
    State,
    Workspace,
    now,
)


class Launcher:
    def __init__(self, folders: list[str]) -> None:
        self.folders = folders

    def project_folders(self) -> list[str]:
        return self.folders


def service(fake: FakeCubase, folders: list[str], *, enabled: bool = True) -> CubaseService:
    return CubaseService(fake, WritePolicy(workspace=enabled), launcher=Launcher(folders))  # type: ignore[arg-type]


def item(kind: str = "render", key: str = "renders/a.wav", skill: str = "podcast-music-ducking") -> OwnedItem:
    return OwnedItem(kind=kind, key=key, skill=skill, run="r1", updated=now())  # type: ignore[arg-type]


# ---------------------------------------------------------------- the folder
def test_create_only_the_workspace(tmp_path: Path) -> None:
    (tmp_path / "Audio").mkdir()
    space = Workspace(tmp_path)
    assert not space.exists
    assert space.missing() == [FOLDER, *(f"{FOLDER}/{s}" for s in SUBFOLDERS)]
    assert space.create() == space.missing() or space.missing() == []
    assert space.exists
    assert space.missing() == []
    assert space.create() == []  # idempotent
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Audio", FOLDER]
    assert sorted(p.name for p in space.path.iterdir()) == sorted(SUBFOLDERS)


def test_paths_stay_inside(tmp_path: Path) -> None:
    space = Workspace(tmp_path)
    space.create()
    assert space.file("renders/x.wav") == space.path / "renders" / "x.wav"
    (tmp_path / "outside").mkdir()
    (space.path / "renders" / "link").symlink_to(tmp_path / "outside")
    for bad in ("../Audio/x.wav", "/etc/passwd", "", "renders/link/x.wav", "renders/../../x"):
        with pytest.raises(PreconditionFailedError) as exc:
            space.file(bad)
        assert exc.value.code == "BAD_REQUEST"


def test_a_symlinked_or_file_workspace_is_refused(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    (project / FOLDER).symlink_to(elsewhere)
    with pytest.raises(PreconditionFailedError) as link:
        Workspace(project).create()
    assert link.value.code == "BAD_WORKSPACE"
    assert not Workspace(project).exists
    other = tmp_path / "other"
    other.mkdir()
    (other / FOLDER).write_text("not a folder", encoding="utf-8")
    with pytest.raises(PreconditionFailedError) as file:
        Workspace(other).create()
    assert file.value.code == "BAD_WORKSPACE"


def test_missing_project_folder(tmp_path: Path) -> None:
    with pytest.raises(PreconditionFailedError) as exc:
        Workspace(tmp_path / "gone")
    assert exc.value.code == "NOT_FOUND"


# ---------------------------------------------------------------- state.json
def test_state_round_trip_and_ownership(tmp_path: Path) -> None:
    space = Workspace(tmp_path)
    with pytest.raises(PreconditionFailedError) as missing:
        space.save_state(State())
    assert missing.value.code == "NO_WORKSPACE"
    space.create()
    assert space.load_state() == State()  # no file yet: empty
    state = State()
    state.record(item())
    state.record(item(kind="track", key="uid:ABC"))
    state.record(item(key="renders/a.wav", skill="podcast-music-bed"))  # same kind and key: replaced
    space.save_state(state)
    loaded = space.load_state()
    assert [(i.kind, i.key, i.skill) for i in loaded.items] == [
        ("track", "uid:ABC", "podcast-music-ducking"),
        ("render", "renders/a.wav", "podcast-music-bed"),
    ]
    assert [i.key for i in loaded.owned_by("podcast-music-ducking")] == ["uid:ABC"]
    assert loaded.owned_by("podcast-music-ducking", "render") == []
    assert loaded.find("track", "uid:ABC") is not None
    assert loaded.forget("track", "uid:ABC") is True
    assert loaded.forget("track", "uid:ABC") is False
    assert json.loads((space.path / "state.json").read_text())["version"] == 1
    assert [p.name for p in space.path.iterdir() if p.name.startswith(".")] == []  # no temporary file left


def test_a_broken_state_file_is_reported(tmp_path: Path) -> None:
    space = Workspace(tmp_path)
    space.create()
    (space.path / "state.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(PreconditionFailedError) as exc:
        space.load_state()
    assert exc.value.code == "BAD_WORKSPACE"


def test_a_failed_write_leaves_the_old_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    space = Workspace(tmp_path)
    space.create()
    state = State()
    state.record(item())
    space.save_state(state)

    def broken(self: Path, target: Path) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", broken)
    with pytest.raises(OSError, match="disk full"):
        space.save_state(State())
    assert len(space.load_state().items) == 1
    assert [p.name for p in space.path.iterdir() if p.name.startswith(".")] == []


# ---------------------------------------------------------------- profile.toml
def test_profile_round_trip(tmp_path: Path) -> None:
    space = Workspace(tmp_path)
    space.create()
    assert space.load_profile() is None
    profile = EpisodeProfile(
        show="my-show",
        track_roles={"Host": "voice", "uid:123": "music"},
        protected=[ProtectedRange(start=10, end=12.5, note="sponsor read")],
        notes="first take",
    )
    path = space.save_profile(profile)
    assert 'show = "my-show"' in path.read_text()
    assert space.load_profile() == profile
    path.write_text('[track_roles]\nHost = "singer"\n', encoding="utf-8")
    with pytest.raises(PreconditionFailedError) as exc:
        space.load_profile()
    assert exc.value.code == "BAD_WORKSPACE"
    with pytest.raises(ValueError, match="end must be after start"):
        ProtectedRange(start=5, end=5)


# ---------------------------------------------------------------- the tool
def test_status_without_a_known_project(fake: FakeCubase) -> None:
    out = service(fake, []).workspace()
    assert out.status == "unknown_project"
    assert "unknown" in out.notes[0]
    with pytest.raises(PreconditionFailedError) as exc:
        service(fake, ["/a", "/b"]).workspace("init", dry_run=False)
    assert exc.value.code == "NO_PROJECT_FOLDER"
    assert "ambiguous" in exc.value.message


def test_init_needs_the_permission(fake: FakeCubase, tmp_path: Path) -> None:
    with pytest.raises(PolicyError) as exc:
        service(fake, [str(tmp_path)], enabled=False).workspace("init")
    assert exc.value.code == "WORKSPACE_DISABLED"
    status = service(fake, [str(tmp_path)], enabled=False).workspace()  # reporting is always allowed
    assert status.status == "absent"
    assert "writing is disabled" in status.notes[0]
    assert not (tmp_path / FOLDER).exists()


def test_init_dry_run_then_create(fake: FakeCubase, tmp_path: Path) -> None:
    tool = service(fake, [str(tmp_path)])
    plan = tool.workspace("init")
    assert (plan.status, plan.dry_run) == ("planned", True)
    assert plan.missing[0] == FOLDER
    assert not (tmp_path / FOLDER).exists()
    done = tool.workspace("init", dry_run=False)
    assert done.status == "created"
    assert done.created == plan.missing
    assert done.missing == []
    assert tool.workspace("init").status == "exists"
    assert tool.workspace("init", dry_run=False).created == []


def test_status_reports_state_and_profile(fake: FakeCubase, tmp_path: Path) -> None:
    space = Workspace(tmp_path)
    space.create()
    state = State()
    state.record(item())
    state.record(item(kind="track", key="uid:1"))
    space.save_state(state)
    space.save_profile(EpisodeProfile(show="s", track_roles={"Host": "voice"}))
    out = service(fake, [str(tmp_path)]).workspace()
    assert out.status == "exists"
    assert (out.has_state, out.has_profile) == (True, True)
    assert out.owned == {"podcast-music-ducking:render": 1, "podcast-music-ducking:track": 1}
    assert out.profile == {"show": "s", "track_roles": 1, "protected_ranges": 0}


def test_bad_action(fake: FakeCubase) -> None:
    with pytest.raises(PreconditionFailedError) as exc:
        service(fake, []).workspace("delete")  # type: ignore[arg-type]
    assert exc.value.code == "BAD_REQUEST"


# ---------------------------------------------------------------- record and forget (TW-1609)
def test_record_and_forget(fake: FakeCubase, tmp_path: Path) -> None:
    Workspace(tmp_path).create()
    tool = service(fake, [str(tmp_path)])
    args: dict[str, Any] = {"kind": "plugin", "key": "UID1/slot:1", "skill": "noise-gate", "run": "r1"}
    plan = tool.workspace("record", **args, details={"plugin": "Gate"})
    assert (plan.status, plan.before, plan.after is not None) == ("planned", None, True)
    assert not (tmp_path / FOLDER / "state.json").exists()
    done = tool.workspace("record", **args, details={"plugin": "Gate"}, dry_run=False)
    assert done.status == "recorded"
    assert done.owned == {"noise-gate:plugin": 1}  # the state after the change
    assert done.items[0]["key"] == "UID1/slot:1"
    status = tool.workspace()
    assert status.owned == {"noise-gate:plugin": 1}
    assert status.items[0]["details"] == {"plugin": "Gate"}
    taken = tool.workspace("record", **{**args, "skill": "other"}, dry_run=False)
    assert taken.before is not None
    assert any("the newest creator owns it" in n for n in taken.notes)
    gone = tool.workspace("forget", kind="plugin", key="UID1/slot:1", dry_run=False)
    assert (gone.status, gone.after) == ("forgotten", None)
    assert tool.workspace().owned == {}
    assert "nothing recorded" in tool.workspace("forget", kind="plugin", key="UID1/slot:1").notes[0]


def test_record_refusals(fake: FakeCubase, tmp_path: Path) -> None:
    with pytest.raises(PolicyError):
        service(fake, [str(tmp_path)], enabled=False).workspace("record", kind="track", key="k", skill="s", run="r")
    tool = service(fake, [str(tmp_path)])
    for kwargs in (
        {"kind": "song", "key": "k"},
        {"kind": "track", "key": ""},
        {"kind": "track", "key": "k"},  # no skill and run
        {"kind": "track", "key": "k", "skill": "s", "run": "r", "details": {"x": object()}},
    ):
        with pytest.raises(PreconditionFailedError) as exc:
            tool.workspace("record", **kwargs)
        assert exc.value.code == "BAD_REQUEST", kwargs
    with pytest.raises(PreconditionFailedError) as unknown:
        service(fake, []).workspace("forget", kind="track", key="k")
    assert unknown.value.code == "NO_PROJECT_FOLDER"
    with pytest.raises(PreconditionFailedError) as missing:
        tool.workspace("record", kind="track", key="k", skill="s", run="r", dry_run=False)
    assert missing.value.code == "NO_WORKSPACE"
