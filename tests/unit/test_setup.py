"""TW-1301: guided installation (``trackwright setup``) with temporary destinations and scripted answers."""

from __future__ import annotations

import io
import json
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from trackwright import installer
from trackwright.cli import main
from trackwright.config import Settings, load_settings
from trackwright.cubase import SCRIPT_NAME, install_script
from trackwright.installer import ConsolePrompter, Setup, server_command, source_checkout

JsonObject = dict[str, Any]
REPO = Path(__file__).resolve().parents[2]


class Prompter:
    """Scripted answers, in order; asking more questions than scripted fails the test."""

    def __init__(self, *answers: bool) -> None:
        self.answers = list(answers)
        self.questions: list[str] = []
        self.lines: list[str] = []

    def say(self, text: str) -> None:
        self.lines.append(text)

    def confirm(self, question: str, *, default: bool = False) -> bool:
        assert default is False
        self.questions.append(question)
        assert self.answers, f"unexpected question: {question}"
        return self.answers.pop(0)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


class Runner:
    def __init__(self, *, registered: bool = False, add_code: int = 0, fail: bool = False) -> None:
        self.registered, self.add_code, self.fail = registered, add_code, fail
        self.calls: list[list[str]] = []

    def __call__(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(command))
        if self.fail:
            raise OSError("cannot run")
        if command[1:3] == ["mcp", "get"]:
            return subprocess.CompletedProcess(list(command), 0 if self.registered else 1, "trackwright:\n  ok", "")
        return subprocess.CompletedProcess(list(command), self.add_code, "", "add failed" if self.add_code else "")


def which(found: dict[str, str]) -> Any:
    return found.get


def green_doctor(settings: Settings) -> JsonObject:
    return {"ok": True, "checks": [{"check": "writes", "ok": True, "detail": settings.writes.enabled}]}


def make(
    tmp_path: Path,
    prompter: Prompter,
    *,
    runner: Runner | None = None,
    found: dict[str, str] | None = None,
    **options: Any,
) -> tuple[Setup, Path, Runner]:
    script_dir = tmp_path / "scripts"
    settings = Settings.model_validate({"script": {"install_dir": script_dir}})
    runner = runner or Runner()
    setup = Setup(
        settings,
        tmp_path / "cfg" / "config.toml",
        prompter,
        runner=runner,
        which=which({"claude": "/bin/claude"} if found is None else found),
        doctor=green_doctor,
        **options,
    )
    return setup, script_dir, runner


def statuses(result: JsonObject) -> dict[str, str]:
    return {s["step"]: s["status"] for s in result["steps"]}


def test_interactive_yes_to_everything(tmp_path: Path) -> None:
    prompter = Prompter(True, True, False, True, True)  # script; writes, save; create config; register
    setup, script_dir, runner = make(tmp_path, prompter)
    result = setup.run()

    assert result["ok"] is True
    assert statuses(result) == {"script": "done", "config": "done", "claude": "done"}
    assert (script_dir / SCRIPT_NAME).is_file()
    assert "creates the file (nothing is replaced)" in prompter.text
    config = tmp_path / "cfg" / "config.toml"
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    loaded = load_settings(config)
    assert loaded.writes.enabled is True
    assert loaded.writes.save is False
    assert "enabled = true" in prompter.text  # the content is shown before asking
    assert runner.calls[-1][:6] == ["/bin/claude", "mcp", "add", "--scope", "user", "trackwright"]
    assert runner.calls[-1][6] == "--"
    assert runner.calls[-1][-1] == "serve"
    assert any("restart Cubase" in s for s in result["next_steps"])
    assert any("restart Claude Code" in s for s in result["next_steps"])
    assert result["doctor"]["checks"][0]["detail"] is True  # doctor sees the new configuration


def test_declining_changes_nothing(tmp_path: Path) -> None:
    prompter = Prompter(False, False, False, False)  # script; writes; create config; register
    setup, script_dir, runner = make(tmp_path, prompter)
    result = setup.run()

    assert statuses(result) == {"script": "declined", "config": "declined", "claude": "declined"}
    assert not (script_dir / SCRIPT_NAME).exists()
    assert not (tmp_path / "cfg").exists()
    assert [c[1:3] for c in runner.calls] == [["mcp", "get"]]
    assert len(prompter.questions) == 4  # save is not asked when writes are off
    assert any("register the MCP server" in s for s in result["next_steps"])


def test_existing_installation_is_kept(tmp_path: Path) -> None:
    prompter = Prompter()
    setup, script_dir, _ = make(tmp_path, prompter, runner=Runner(registered=True))
    install_script(script_dir, apply=True)
    config = tmp_path / "cfg" / "config.toml"
    config.parent.mkdir()
    config.write_text("[writes]\nenabled = true\n", encoding="utf-8")

    result = setup.run()
    assert statuses(result) == {"script": "skipped", "config": "skipped", "claude": "skipped"}
    assert config.read_text(encoding="utf-8") == "[writes]\nenabled = true\n"
    assert prompter.questions == []
    assert "claude mcp remove trackwright -s user" in prompter.text


def test_different_script_shows_the_replaced_version(tmp_path: Path) -> None:
    setup, script_dir, _ = make(tmp_path, Prompter(True), found={})
    script_dir.mkdir()
    (script_dir / SCRIPT_NAME).write_text("var SCRIPT_VERSION = '0.0.1';\n", encoding="utf-8")
    result = setup.step_script()
    assert result.status == "done"
    assert result.detail["replaced"] == "0.0.1"
    assert "replaces the installed file, version 0.0.1" in setup.prompter.text  # type: ignore[attr-defined]


def test_yes_flags_apply_without_asking(tmp_path: Path) -> None:
    prompter = Prompter()
    setup, _, _ = make(tmp_path, prompter, assume_yes=["script", "config", "claude"])
    result = setup.run()
    assert statuses(result) == {"script": "done", "config": "done", "claude": "done"}
    assert prompter.questions == []
    loaded = load_settings(tmp_path / "cfg" / "config.toml")
    assert (loaded.writes.enabled, loaded.writes.save) == (False, False)  # --yes never enables writes
    assert "(--yes config)" in prompter.text


def test_writes_and_save_flags(tmp_path: Path) -> None:
    setup, _, _ = make(tmp_path, Prompter(), assume_yes=["config"], writes=True, save=True)
    assert setup.step_config().detail == {"path": str(tmp_path / "cfg" / "config.toml"), "writes": True, "save": True}


def test_save_needs_writes(tmp_path: Path) -> None:
    setup, _, _ = make(tmp_path, Prompter(), assume_yes=["config"], writes=False, save=True)
    assert setup.step_config().detail["save"] is False


def test_claude_not_on_path_shows_the_command(tmp_path: Path) -> None:
    setup, _, runner = make(tmp_path, Prompter(), found={})
    result = setup.step_claude()
    assert result.status == "manual"
    assert result.detail["command"].startswith("claude mcp add --scope user trackwright -- ")
    assert runner.calls == []


def test_registration_failure(tmp_path: Path) -> None:
    setup, _, _ = make(tmp_path, Prompter(True, False, False, True), runner=Runner(add_code=1))
    result = setup.run()
    assert result["ok"] is False
    claude = next(s for s in result["steps"] if s["step"] == "claude")
    assert claude["error"] == {"message": "add failed"}


def test_claude_cannot_run(tmp_path: Path) -> None:
    setup, _, _ = make(tmp_path, Prompter(True), runner=Runner(fail=True))
    result = setup.step_claude()
    assert result.status == "failed"
    assert result.detail["error"] == {"message": "cannot run"}


def test_script_install_failure(tmp_path: Path) -> None:
    setup, script_dir, _ = make(tmp_path, Prompter(True))
    script_dir.mkdir()
    (script_dir / SCRIPT_NAME).symlink_to(tmp_path / "elsewhere.js")
    result = setup.step_script()
    assert result.status == "failed"
    assert "symbolic link" in result.detail["error"]["message"]


def test_script_status_failure(tmp_path: Path) -> None:
    setup, script_dir, _ = make(tmp_path, Prompter())
    script_dir.mkdir()
    (script_dir / SCRIPT_NAME).mkdir()  # a directory where the file should be
    assert setup.step_script().status == "failed"


def test_config_write_failure(tmp_path: Path) -> None:
    setup, _, _ = make(tmp_path, Prompter(), assume_yes=["config"])
    (tmp_path / "cfg").write_text("not a directory", encoding="utf-8")
    result = setup.step_config()
    assert result.status == "failed"


def test_server_command_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    assert source_checkout() == REPO
    assert server_command(lambda _n: None) == ["uv", "--directory", str(REPO), "run", "trackwright", "serve"]
    monkeypatch.setattr(installer, "source_checkout", lambda: None)
    assert server_command(lambda _n: "/opt/bin/trackwright") == ["/opt/bin/trackwright", "serve"]
    uvx = ["uvx", "--from", f"trackwright=={installer.trackwright.__version__}", "trackwright", "serve"]
    assert server_command(lambda _n: None) == uvx
    cached = "/Users/x/.cache/uv/archive-v0/abc/bin/trackwright"
    assert server_command(lambda _n: cached) == uvx


def test_source_checkout_outside_the_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "site" / "lib" / "trackwright"
    package.mkdir(parents=True)
    monkeypatch.setattr(installer.trackwright, "__file__", str(package / "__init__.py"))
    assert source_checkout() is None


@pytest.mark.parametrize(
    ("typed", "default", "expected"),
    [
        ("y\n", False, True),
        ("sí\n", False, True),
        ("no\n", True, False),
        ("\n", True, True),
        ("", False, False),  # end of input
        ("maybe\n?\nok\n", True, True),  # three invalid answers: the default
        ("maybe\nn\n", True, False),
    ],
)
def test_console_prompter(typed: str, default: bool, expected: bool) -> None:
    out = io.StringIO()
    prompter = ConsolePrompter(out, io.StringIO(typed).readline)
    assert prompter.confirm("Go?", default=default) is expected
    assert out.getvalue().startswith(f"Go? {'[Y/n]' if default else '[y/N]'} ")


def test_cli_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))  # default script folder under the temporary home
    short = tempfile.mkdtemp(dir="/tmp", prefix="tw-")  # AF_UNIX paths are short
    monkeypatch.setenv("TMPDIR", short)  # no bridge there
    monkeypatch.setattr("trackwright.installer.shutil.which", lambda _n: None)
    monkeypatch.setattr("sys.stdin", io.StringIO("y\n"))  # the script; then end of input
    config = tmp_path / "new" / "config.toml"

    assert main(["--config", str(config), "setup", "--yes", "config", "--writes"]) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert statuses(result) == {"script": "done", "config": "done", "claude": "manual"}
    assert (tmp_path / "Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/trackwright/bridge").is_dir()
    assert load_settings(config).writes.enabled is True
    assert result["doctor"]["ok"] is False  # no bridge in the temporary TMPDIR
    assert "[1/3] Cubase MIDI Remote script" in captured.err
    shutil.rmtree(short)


def test_cli_setup_rejects_unknown_steps() -> None:
    with pytest.raises(SystemExit):
        main(["setup", "--yes", "everything"])


def test_a_registration_pinned_to_another_version_is_reported(tmp_path: Path) -> None:
    """0.4.0: a uvx registration of 0.3.0 would keep running the old server after an upgrade."""

    class Pinned(Runner):
        def __call__(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
            self.calls.append(list(command))
            out = "trackwright:\n  Command: uvx\n  Args: --from trackwright==0.3.0 trackwright serve"
            return subprocess.CompletedProcess(list(command), 0, out, "")

    setup, _, _ = make(tmp_path, Prompter(), runner=Pinned())
    result = setup.step_claude()
    assert (result.status, result.detail["reason"]) == ("skipped", "registered_other_version")
    assert any("0.3.0" in step and "claude mcp remove" in step for step in setup.next_steps)


def test_a_registration_of_this_version_is_fine(tmp_path: Path) -> None:
    class Current(Runner):
        def __call__(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
            out = f"Args: --from trackwright=={installer.trackwright.__version__} trackwright serve"
            return subprocess.CompletedProcess(list(command), 0, out, "")

    setup, _, _ = make(tmp_path, Prompter(), runner=Current())
    assert setup.step_claude().detail["reason"] == "registered"
    assert setup.next_steps == []
