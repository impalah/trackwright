"""Guided installation (TW-1301): ``trackwright setup``.

Steps, each one **shown before it is applied and applied only after confirmation** (or ``--yes STEP``):

1. ``script``: install or update the MIDI Remote script in Cubase's user folder;
2. ``config``: create the configuration file when it does not exist (writes and save default to off;
   an existing file is never modified);
3. ``claude``: register the MCP server in Claude Code (``claude mcp add --scope user``) when ``claude``
   is on the PATH and the server is not registered yet; otherwise show the command;
4. a final, read-only ``doctor``.

It never uses sudo, never touches Cubase settings, IAC or Accessibility, and never replaces an existing
Claude Code registration.
"""

from __future__ import annotations

import hashlib
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, TextIO

from loguru import logger

import trackwright
from trackwright.config import Settings, load_settings
from trackwright.cubase import SCRIPT_PATH, install_script, script_status
from trackwright.errors import TrackwrightError

JsonObject = dict[str, Any]
STEPS = ("script", "config", "claude")
SERVER_NAME = "trackwright"
YES = frozenset({"y", "yes", "s", "si", "sí"})
NO = frozenset({"n", "no"})
StepStatus = Literal["done", "skipped", "declined", "manual", "failed"]
Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]

CONFIG_TEMPLATE = """\
# Trackwright configuration, created by 'trackwright setup' (see docs/manual/03-configuracion.md)

[writes]
# Allow tools to modify the open Cubase project. Dry runs and navigation work regardless.
enabled = {writes}
# Allow cubase_save_project to save the project file on disk (needs enabled = true). Only on explicit request.
save = {save}
# allowed_tracks = ["My test track"]   # optional: restrict writes to these track names (empty = all tracks)
"""


class Prompter(Protocol):
    def say(self, text: str) -> None: ...

    def confirm(self, question: str, *, default: bool = False) -> bool: ...


class ConsolePrompter:
    """Questions on stderr, answers from stdin (stdout stays for the JSON summary). End of input means the default."""

    def __init__(self, stream: TextIO | None = None, readline: Callable[[], str] | None = None) -> None:
        self._stream = stream or sys.stderr
        self._readline = readline or sys.stdin.readline

    def say(self, text: str) -> None:
        self._stream.write(text + "\n")
        self._stream.flush()

    def confirm(self, question: str, *, default: bool = False) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        for _ in range(3):
            self._stream.write(f"{question} {suffix} ")
            self._stream.flush()
            line = self._readline()
            if not line:  # end of input
                self.say("")
                return default
            answer = line.strip().lower()
            if not answer:
                return default
            if answer in YES:
                return True
            if answer in NO:
                return False
            self.say("Please answer y or n.")
        return default


def run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(command), capture_output=True, text=True, timeout=60, check=False)  # noqa: S603


def source_checkout() -> Path | None:
    """The repository root when Trackwright runs from its source tree (``uv run``), else ``None``."""
    root = Path(trackwright.__file__).resolve().parents[2]
    pyproject = root / "pyproject.toml"
    if pyproject.is_file() and 'name = "trackwright-mcp"' in pyproject.read_text(encoding="utf-8"):
        return root
    return None


def server_command(which: Callable[[str], str | None] = shutil.which) -> list[str] | None:
    """The command Claude Code must run to start the MCP server, or ``None`` if there is no stable one.

    From a source checkout: ``uv --directory <repo> run trackwright serve``. Installed as a tool
    (``uv tool install``): the absolute path of the ``trackwright`` executable. A temporary ``uvx`` run has
    neither.
    """
    root = source_checkout()
    if root is not None:
        return ["uv", "--directory", str(root), "run", "trackwright", "serve"]
    executable = which("trackwright")
    return [str(Path(executable).absolute()), "serve"] if executable else None


@dataclass
class StepResult:
    step: str
    status: StepStatus
    detail: JsonObject = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return {"step": self.step, "status": self.status, **self.detail}


class Setup:
    def __init__(
        self,
        settings: Settings,
        config_file: Path,
        prompter: Prompter,
        *,
        assume_yes: Sequence[str] = (),
        writes: bool | None = None,
        save: bool | None = None,
        runner: Runner | None = None,
        which: Callable[[str], str | None] | None = None,
        doctor: Callable[[Settings], JsonObject] | None = None,
    ) -> None:
        self.settings = settings
        self.config_file = config_file
        self.prompter = prompter
        self.assume_yes = frozenset(assume_yes)
        self.writes = writes
        self.save = save
        self.runner = runner or run_command
        self.which = which or shutil.which
        self._doctor = doctor
        self.next_steps: list[str] = []

    # ------------------------------------------------------------------ flow
    def run(self) -> JsonObject:
        steps = [self.step_script(), self.step_config(), self.step_claude()]
        doctor = self.run_doctor()
        failed = any(s.status == "failed" for s in steps)
        self.prompter.say(f"\nSetup {'finished with errors' if failed else 'finished'}.")
        for item in self.next_steps:
            self.prompter.say(f"  - {item}")
        return {
            "ok": not failed,
            "steps": [s.to_dict() for s in steps],
            "doctor": doctor,
            "next_steps": self.next_steps,
        }

    def ask(self, step: str, question: str) -> bool:
        if step in self.assume_yes:
            self.prompter.say(f"{question} yes (--yes {step})")
            return True
        return self.prompter.confirm(question)

    def answer(self, step: str, given: bool | None, question: str) -> bool:
        """A setting chosen with a flag, or asked (default no); with ``--yes STEP`` and no flag, no."""
        if given is not None:
            return given
        if step in self.assume_yes:
            return False
        return self.prompter.confirm(question)

    # ------------------------------------------------------------------ 1. script
    def step_script(self) -> StepResult:
        self.prompter.say("\n[1/3] Cubase MIDI Remote script")
        try:
            status = script_status(self.settings.script.install_dir)
        except OSError as exc:
            return self.failed("script", exc)
        self.prompter.say(f"  destination: {status.destination}")
        if status.state == "up_to_date":
            self.prompter.say(f"  already installed, version {status.installed_version}: nothing to do")
            return StepResult("script", "skipped", {"reason": "up_to_date", **status.to_dict()})
        data = SCRIPT_PATH.read_bytes()
        self.prompter.say(
            f"  file: {SCRIPT_PATH.name}, version {status.packaged_version} "
            f"({len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()[:16]}…)"
        )
        self.prompter.say(f"  content: {SCRIPT_PATH}")
        if status.state == "different":
            self.prompter.say(f"  replaces the installed file, version {status.installed_version}")
        else:
            self.prompter.say("  creates the file (nothing is replaced)")
        if not self.ask("script", "Install the script?"):
            self.next_steps.append("install the script later with 'trackwright script install --apply'")
            return StepResult("script", "declined", status.to_dict())
        try:
            after, written = install_script(self.settings.script.install_dir, apply=True)
        except (TrackwrightError, OSError) as exc:
            return self.failed("script", exc)
        self.next_steps.append("restart Cubase: it does not reload a changed script by itself")
        return StepResult(
            "script", "done", {"written": written, "replaced": status.installed_version, **after.to_dict()}
        )

    # ------------------------------------------------------------------ 2. config
    def step_config(self) -> StepResult:
        self.prompter.say("\n[2/3] Configuration")
        self.prompter.say(f"  file: {self.config_file}")
        if self.config_file.exists():
            self.prompter.say("  already exists: kept as it is (edit it by hand to change it)")
            return StepResult("config", "skipped", {"reason": "exists", "path": str(self.config_file)})
        writes = self.answer("config", self.writes, "Allow Trackwright to modify the open Cubase project (writes)?")
        save = writes and self.answer("config", self.save, "Allow it to save the project file when asked (save)?")
        content = CONFIG_TEMPLATE.format(writes=str(writes).lower(), save=str(save).lower())
        self.prompter.say("  content:")
        for line in content.splitlines():
            self.prompter.say(f"    {line}")
        if not self.ask("config", f"Create {self.config_file}?"):
            self.next_steps.append("without a configuration file Trackwright runs read-only (built-in defaults)")
            return StepResult("config", "declined", {"path": str(self.config_file)})
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with self.config_file.open("x", encoding="utf-8") as handle:  # never overwrite
                handle.write(content)
            self.config_file.chmod(0o600)
            self.settings = load_settings(self.config_file)
        except (TrackwrightError, OSError) as exc:
            return self.failed("config", exc)
        logger.info("created {}", self.config_file)
        return StepResult("config", "done", {"path": str(self.config_file), "writes": writes, "save": save})

    # ------------------------------------------------------------------ 3. claude
    def step_claude(self) -> StepResult:
        self.prompter.say("\n[3/3] Claude Code")
        command = server_command(self.which)
        if command is None:
            self.prompter.say("  no stable 'trackwright' executable: install it with 'uv tool install' first")
            self.next_steps.append("install Trackwright with 'uv tool install' and run 'trackwright setup' again")
            return StepResult("claude", "manual", {"reason": "no_executable"})
        add = ["mcp", "add", "--scope", "user", SERVER_NAME, "--", *command]
        claude = self.which("claude")
        if claude is None:
            shown = shlex.join(["claude", *add])
            self.prompter.say(f"  'claude' is not on the PATH. Register the server by hand:\n    {shown}")
            self.next_steps.append(f"register the MCP server: {shown}")
            return StepResult("claude", "manual", {"reason": "claude_not_found", "command": shown})
        existing = self.run_safely([claude, "mcp", "get", SERVER_NAME])
        if existing.returncode == 0:
            self.prompter.say(f"  the server '{SERVER_NAME}' is already registered: kept as it is")
            self.prompter.say(f"  to replace it: claude mcp remove {SERVER_NAME} -s user, then run setup again")
            return StepResult("claude", "skipped", {"reason": "registered", "registration": existing.stdout.strip()})
        shown = shlex.join([claude, *add])
        self.prompter.say(f"  command: {shown}")
        if not self.ask("claude", "Register the MCP server in Claude Code (user scope)?"):
            self.next_steps.append(f"register the MCP server: {shown}")
            return StepResult("claude", "declined", {"command": shown})
        done = self.run_safely([claude, *add])
        if done.returncode != 0:
            error = (done.stderr or done.stdout).strip()
            self.prompter.say(f"  failed: {error}")
            return StepResult("claude", "failed", {"command": shown, "error": {"message": error}})
        self.next_steps.append("restart Claude Code (or open /mcp) so it starts the Trackwright server")
        return StepResult("claude", "done", {"command": shown})

    def run_safely(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        """Run ``command``; a launch failure or timeout becomes a failed result (return code -1)."""
        try:
            return self.runner(command)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("{} failed: {}", command[0], exc)
            return subprocess.CompletedProcess(list(command), -1, "", str(exc))

    # ------------------------------------------------------------------ 4. doctor
    def run_doctor(self) -> JsonObject:
        self.prompter.say("\nChecking the installation (doctor)…")
        if self._doctor is None:
            from trackwright.doctor import run_doctor  # noqa: PLC0415

            self._doctor = run_doctor
        report = self._doctor(self.settings)
        for check in report["checks"]:
            mark = "ok" if check["ok"] else "FAIL"
            self.prompter.say(f"  {mark:4} {check['check']}" + (f": {check['fix']}" if "fix" in check else ""))
        return report

    def failed(self, step: str, exc: Exception) -> StepResult:
        logger.error("setup step {} failed: {}", step, exc)
        error = exc.to_dict() if isinstance(exc, TrackwrightError) else {"message": str(exc)}
        self.prompter.say(f"  failed: {error.get('message', exc)}")
        return StepResult(step, "failed", {"error": error})
