from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from trackwright.cli import main
from trackwright.cubase import SCRIPT_NAME, SCRIPT_PATH, SCRIPT_VERSION, install_script, script_status
from trackwright.errors import PreconditionFailedError


def test_packaged_script_exists_and_has_version() -> None:
    assert SCRIPT_PATH.is_file()
    assert SCRIPT_VERSION is not None
    assert re.fullmatch(r"\d+\.\d+\.\d+", SCRIPT_VERSION)


def test_status_missing(tmp_path: Path) -> None:
    status = script_status(tmp_path / "bridge")
    assert status.state == "missing"
    assert status.installed_version is None


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    target = tmp_path / "bridge"
    status, written = install_script(target, apply=False)
    assert written is False
    assert status.state == "missing"
    assert not target.exists()


def test_install_then_up_to_date(tmp_path: Path) -> None:
    target = tmp_path / "Local" / "trackwright" / "bridge"
    status, written = install_script(target, apply=True)
    assert written is True
    assert status.state == "up_to_date"
    assert (target / SCRIPT_NAME).read_bytes() == SCRIPT_PATH.read_bytes()
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == [SCRIPT_NAME]
    _, again = install_script(target, apply=True)
    assert again is False


def test_different_version_is_replaced(tmp_path: Path) -> None:
    (tmp_path / SCRIPT_NAME).write_text("var SCRIPT_VERSION = '0.9.0'\n", encoding="utf-8")
    status = script_status(tmp_path)
    assert status.state == "different"
    assert status.installed_version == "0.9.0"
    status, written = install_script(tmp_path, apply=True)
    assert written is True
    assert status.state == "up_to_date"


def test_symlink_is_not_overwritten(tmp_path: Path) -> None:
    other = tmp_path / "elsewhere.js"
    other.write_text("// unrelated\n", encoding="utf-8")
    (tmp_path / SCRIPT_NAME).symlink_to(other)
    with pytest.raises(PreconditionFailedError, match="symbolic link"):
        install_script(tmp_path, apply=True)
    assert other.read_text(encoding="utf-8") == "// unrelated\n"


def test_cli_status_and_install(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "bridge"
    assert main(["script", "status", "--dir", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "missing"

    assert main(["script", "install", "--dir", str(target)]) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["dry_run"] is True
    assert "--apply" in dry["next_step"]

    assert main(["script", "install", "--dir", str(target), "--apply"]) == 0
    done = json.loads(capsys.readouterr().out)
    assert done["written"] is True
    assert "restart Cubase" in done["next_step"]


def test_relative_install_dir_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(PreconditionFailedError, match="absolute"):
        install_script(Path("~/Documents/x"), apply=True)
    assert list(tmp_path.iterdir()) == []


def test_cli_default_destination_is_under_home(capsys: pytest.CaptureFixture[str]) -> None:
    import os

    assert main(["script", "status"]) == 0
    destination = json.loads(capsys.readouterr().out)["destination"]
    assert destination.startswith(os.environ["HOME"])


def test_install_another_source(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    experiment = tmp_path / "exp.js"
    experiment.write_text(
        SCRIPT_PATH.read_text(encoding="utf-8").replace(f"'{SCRIPT_VERSION}'", f"'{SCRIPT_VERSION}+x'"),
        encoding="utf-8",
    )
    target = tmp_path / "bridge"
    status, written = install_script(target, apply=True, source=experiment)
    assert written is True
    assert (status.state, status.installed_version) == ("up_to_date", f"{SCRIPT_VERSION}+x")
    assert script_status(target).state == "different"  # compared with the packaged script
    assert main(["script", "status", "--dir", str(target), "--file", str(experiment)]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "up_to_date"
    status, written = install_script(target, apply=True)  # back to the released script
    assert (written, status.installed_version) == (True, SCRIPT_VERSION)


def test_install_refuses_a_file_that_is_not_a_script(tmp_path: Path) -> None:
    bogus = tmp_path / "notes.txt"
    bogus.write_text("hello", encoding="utf-8")
    with pytest.raises(PreconditionFailedError, match="not a Trackwright"):
        install_script(tmp_path / "bridge", apply=True, source=bogus)
    with pytest.raises(PreconditionFailedError):
        install_script(tmp_path / "bridge", apply=False, source=tmp_path / "missing.js")
