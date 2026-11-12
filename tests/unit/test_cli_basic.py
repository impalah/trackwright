from __future__ import annotations

import json
from pathlib import Path

import pytest

from trackwright import __version__
from trackwright.cli import main


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0
    assert json.loads(capsys.readouterr().out) == {"trackwright": __version__}


def test_config_shows_defaults(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["config"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["writes"]["enabled"] is False
    assert data["bridge"]["socket_path"].endswith("bridge.sock")


def test_invalid_config_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text("[writes]\nenabled = 'maybe'\n", encoding="utf-8")
    assert main(["--config", str(bad), "config"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "CONFIG_ERROR"


def test_missing_command_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_module_entry_point(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import runpy

    monkeypatch.setattr("sys.argv", ["trackwright", "version"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("trackwright", run_name="__main__")
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out
