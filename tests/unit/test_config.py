from __future__ import annotations

import os
from pathlib import Path

import pytest

from trackwright.config import Settings, default_socket_dir, load_settings
from trackwright.errors import ConfigError


def test_defaults_are_read_only(tmp_path: Path) -> None:
    settings = load_settings(environ={})
    assert settings.writes.enabled is False
    assert settings.writes.allowed_tracks == ()
    assert settings.source is None
    assert settings.bridge.to_cubase_port == "Trackwright To Cubase"
    assert settings.bridge.socket_path.name == "bridge.sock"


def test_default_socket_dir_uses_tmpdir_and_uid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    assert default_socket_dir() == tmp_path / f"trackwright-{os.getuid()}"


def test_load_from_file(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[bridge]
request_timeout = 2.5
socket_dir = "~/sockets"

[writes]
enabled = true
allowed_tracks = ["POC-TEST"]

[logging]
level = "debug"
file = "~/logs/tw.log"
""",
        encoding="utf-8",
    )
    settings = load_settings(cfg)
    assert settings.source == cfg
    assert settings.bridge.request_timeout == 2.5
    assert settings.writes.enabled is True
    assert settings.writes.allowed_tracks == ("POC-TEST",)
    assert settings.logging.level == "DEBUG"
    assert settings.bridge.socket_dir == Path("~/sockets").expanduser()
    assert settings.logging.file == Path("~/logs/tw.log").expanduser()


def test_env_variable_points_to_file(tmp_path: Path) -> None:
    cfg = tmp_path / "x.toml"
    cfg.write_text("[writes]\nenabled = true\n", encoding="utf-8")
    assert load_settings(environ={"TRACKWRIGHT_CONFIG": str(cfg)}).writes.enabled is True


def test_explicit_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_settings(tmp_path / "missing.toml")


def test_default_location_is_used_when_present() -> None:
    default = Path("~/.config/trackwright/config.toml").expanduser()
    default.parent.mkdir(parents=True)
    default.write_text("[logging]\nlevel = 'WARNING'\n", encoding="utf-8")
    assert load_settings(environ={}).logging.level == "WARNING"


@pytest.mark.parametrize(
    "content",
    [
        "[bridge]\nrequest_timeout = 99\n",
        "[bridge]\nunknown = 1\n",
        "[surprise]\nx = 1\n",
        "[logging]\nlevel = 'LOUD'\n",
        "source = '/etc/passwd'\n",
        "not toml = = =",
    ],
)
def test_invalid_files_are_rejected(tmp_path: Path, content: str) -> None:
    cfg = tmp_path / "bad.toml"
    cfg.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(cfg)


def test_settings_are_immutable() -> None:
    settings = Settings()
    with pytest.raises(ValueError, match="frozen"):
        settings.writes.enabled = True  # type: ignore[misc]
