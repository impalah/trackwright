"""TW-1607: show, episode and delivery profiles, resolved built-in < show < episode."""

from __future__ import annotations

import tomllib
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import NotFoundError, PolicyError, PreconditionFailedError
from trackwright.fake import FakeCubase
from trackwright.profiles import (
    BUILTIN,
    DeliveryProfile,
    ShowProfile,
    builtin_delivery,
    check_show_name,
    profile_toml,
    resolve,
)
from trackwright.workspace import EpisodeProfile, Workspace

SOURCE = {"url": "user", "retrieved": date(2026, 11, 15), "covers": ["loudness_lufs", "true_peak_dbtp"]}
HOST: dict[str, Any] = {"title": "My host", "loudness_lufs": -16.0, "true_peak_dbtp": -1.0, "sources": [SOURCE]}
SHOW: dict[str, Any] = {
    "title": "Demo show",
    "track_roles": {"Pod Mic": "voice", "Music": "music"},
    "voices": {"Pod Mic": {"pan": 0}},
    "editing": {"padding_seconds": 0.3},
    "delivery": {"targets": ["myhost"], "profiles": {"myhost": HOST}},
}


class Launcher:
    def __init__(self, folders: list[str]) -> None:
        self.folders = folders

    def project_folders(self) -> list[str]:
        return self.folders


@pytest.fixture
def project(tmp_path: Path) -> Path:
    folder = tmp_path / "E0001"
    folder.mkdir()
    Workspace(folder).create()
    return folder


def make(fake: FakeCubase, tmp_path: Path, project: Path | None, *, workspace: bool = True) -> CubaseService:
    return CubaseService(
        fake,
        WritePolicy(enabled=True, workspace=workspace),
        launcher=Launcher([str(project)] if project else []),  # type: ignore[arg-type]
        shows_dir=tmp_path / "shows",
    )


# ---------------------------------------------------------------- delivery profiles
def test_every_value_needs_a_source() -> None:
    assert DeliveryProfile.model_validate(HOST).loudness_lufs == -16.0
    with pytest.raises(ValidationError, match="values without a source"):
        DeliveryProfile.model_validate({**HOST, "bitrate_kbps": 128})
    with pytest.raises(ValidationError, match="unknown fields in covers"):
        DeliveryProfile.model_validate({**HOST, "sources": [{**SOURCE, "covers": ["loudness"]}]})
    with pytest.raises(ValidationError):
        DeliveryProfile.model_validate({**HOST, "sources": []})


def test_the_builtin_profiles_are_valid_and_cited() -> None:
    for name, profile in builtin_delivery().items():
        assert check_show_name(name) == name
        assert all(s.url.startswith("https://") for s in profile.sources), name


# ---------------------------------------------------------------- resolving the layers
def test_layers_and_origins() -> None:
    show = ShowProfile.model_validate(SHOW)
    episode = EpisodeProfile.model_validate(
        {"show": "demo", "track_roles": {"Music": "effects", "Guest": "voice"}, "delivery": {"targets": []}}
    )
    settings, origins, profiles = resolve(show, episode)
    assert settings.track_roles == {"Pod Mic": "voice", "Music": "effects", "Guest": "voice"}
    assert (settings.editing.min_silence_seconds, settings.editing.padding_seconds) == (2.0, 0.3)
    assert settings.delivery.targets == []  # lists are replaced whole
    assert origins["editing.min_silence_seconds"] == "built-in"
    assert origins["editing.padding_seconds"] == "show"
    assert origins["track_roles.Pod Mic"] == "show"
    assert origins["track_roles.Music"] == "episode"
    assert origins["voices.Pod Mic.pan"] == "show"
    assert origins["delivery.targets"] == "episode"
    assert profiles["myhost"].title == "My host"
    alone, _, _ = resolve(None, None)
    assert alone == BUILTIN


def test_toml_round_trip() -> None:
    show = ShowProfile.model_validate(SHOW)
    text = profile_toml(show)
    assert "[music]" not in text  # empty tables left out
    assert "notes" not in profile_toml(ShowProfile(title="x"))  # and empty texts
    assert ShowProfile.model_validate(tomllib.loads(text)) == show
    assert tomllib.loads(profile_toml(EpisodeProfile()))["version"] == 1


def test_show_names() -> None:
    for bad in ("", "../x", "a b", "x" * 65, ".hidden"):
        with pytest.raises(PreconditionFailedError):
            check_show_name(bad)


# ---------------------------------------------------------------- the tool
def test_write_and_resolve(fake: FakeCubase, tmp_path: Path, project: Path) -> None:
    svc = make(fake, tmp_path, project)
    assert svc.profile("shows").shows == []
    plan = svc.profile("write_show", show="demo", data=SHOW)
    assert (plan.status, plan.before, plan.changed) == ("planned", None, True)
    assert plan.after is not None
    assert 'title = "Demo show"' in plan.after
    assert not (tmp_path / "shows").exists()
    written = svc.profile("write_show", show="demo", data=SHOW, dry_run=False)
    assert written.status == "written"
    assert (tmp_path / "shows" / "demo.toml").read_text() == plan.after
    assert svc.profile("write_show", show="demo", data=SHOW).changed is False
    assert svc.profile("shows").shows == ["demo"]

    episode = {"show": "demo", "track_roles": {"Guest": "voice"}, "protected": [{"start": 10, "end": 20}]}
    assert svc.profile("write_episode", data=episode).after is not None
    assert not (project / "Trackwright" / "profile.toml").exists()
    svc.profile("write_episode", data=episode, dry_run=False)
    out = svc.profile()
    assert (out.show, out.status) == ("demo", "read")
    assert out.settings is not None
    assert out.settings["track_roles"] == {"Pod Mic": "voice", "Music": "music", "Guest": "voice"}
    assert out.origins["track_roles.Guest"] == "episode"
    assert out.protected == [{"start": 10.0, "end": 20.0, "note": ""}]
    assert out.episode is not None
    assert out.episode["track_roles"] == {"Guest": "voice"}  # the episode layer alone, without the show's roles
    assert [(d.name, d.origin, d.loudness_lufs) for d in out.delivery] == [("myhost", "show/episode", -16.0)]
    listed = svc.profile("delivery")
    assert ("myhost", "show/episode") in [(d.name, d.origin) for d in listed.delivery]


def test_resolve_without_episode_or_show(fake: FakeCubase, tmp_path: Path, project: Path) -> None:
    out = make(fake, tmp_path, project).profile()
    assert out.show is None
    assert any("no Trackwright/profile.toml" in n for n in out.notes)
    assert any("no show" in n for n in out.notes)
    assert out.settings is not None
    assert out.settings["editing"] == {"min_silence_seconds": 2.0, "padding_seconds": 0.25}
    none = make(fake, tmp_path, None).profile()
    assert any("no episode profile" in n for n in none.notes)


def test_a_show_given_explicitly_wins_and_unknown_targets_are_noted(
    fake: FakeCubase, tmp_path: Path, project: Path
) -> None:
    svc = make(fake, tmp_path, project)
    svc.profile("write_show", show="other", data={"delivery": {"targets": ["nowhere"]}}, dry_run=False)
    svc.profile("write_episode", data={"show": "demo"}, dry_run=False)
    out = svc.profile(show="other")
    assert out.show == "other"
    assert any("the episode names the show 'demo'" in n for n in out.notes)
    assert any("unknown delivery target 'nowhere'" in n for n in out.notes)
    with pytest.raises(NotFoundError):
        svc.profile()  # the episode's show 'demo' does not exist


def test_refusals(fake: FakeCubase, tmp_path: Path, project: Path) -> None:
    with pytest.raises(PolicyError) as disabled:
        make(fake, tmp_path, project, workspace=False).profile("write_show", show="demo", data=SHOW)
    assert disabled.value.code == "WORKSPACE_DISABLED"
    svc = make(fake, tmp_path, project)
    cases: list[tuple[dict[str, Any], str]] = [
        ({"action": "write_show", "show": "demo"}, "BAD_REQUEST"),
        ({"action": "write_show", "data": SHOW}, "BAD_REQUEST"),
        ({"action": "write_show", "show": "../x", "data": SHOW}, "BAD_REQUEST"),
        ({"action": "write_show", "show": "demo", "data": {"tempo": 120}}, "BAD_PROFILE"),
        ({"action": "write_episode", "data": {"track_roles": {"x": "singer"}}}, "BAD_PROFILE"),
        ({"action": "nothing"}, "BAD_REQUEST"),
    ]
    for kwargs, code in cases:
        action = kwargs.pop("action")
        with pytest.raises(PreconditionFailedError) as exc:
            svc.profile(action, **kwargs)
        assert exc.value.code == code, kwargs
    with pytest.raises(PreconditionFailedError) as unknown:
        make(fake, tmp_path, None).profile("write_episode", data={})
    assert unknown.value.code == "NO_PROJECT_FOLDER"
    bare = tmp_path / "bare"
    bare.mkdir()
    with pytest.raises(PreconditionFailedError) as missing:
        make(fake, tmp_path, bare).profile("write_episode", data={}, dry_run=False)
    assert missing.value.code == "NO_WORKSPACE"


def test_broken_show_files(fake: FakeCubase, tmp_path: Path, project: Path) -> None:
    shows = tmp_path / "shows"
    shows.mkdir()
    (shows / "bad.toml").write_text("title = ", encoding="utf-8")
    (shows / "wrong.toml").write_text("tempo = 120\n", encoding="utf-8")
    svc = make(fake, tmp_path, project)
    for name in ("bad", "wrong"):
        with pytest.raises(PreconditionFailedError) as exc:
            svc.profile(show=name)
        assert exc.value.code == "BAD_PROFILE"


def test_shows_dir_defaults_next_to_the_config(fake: FakeCubase) -> None:
    svc = CubaseService(fake, WritePolicy())
    assert svc.shows_dir() == Path("~/.config/trackwright/shows").expanduser()


def test_the_shipped_numbers() -> None:
    """The values read from the platforms' pages on 2026-11-15 (a change here must cite a new reading)."""
    shipped = builtin_delivery()
    assert sorted(shipped) == ["apple", "ivoox", "spotify", "youtube"]
    apple = shipped["apple"]
    assert (apple.loudness_lufs, apple.loudness_tolerance_lu, apple.true_peak_dbtp) == (-16.0, 1.0, -1.0)
    assert (shipped["spotify"].loudness_lufs, shipped["spotify"].true_peak_dbtp) == (None, None)  # not published
    assert (shipped["youtube"].loudness_lufs, shipped["youtube"].sample_rates) == (None, [48000])
    assert shipped["ivoox"].loudness_lufs is None
