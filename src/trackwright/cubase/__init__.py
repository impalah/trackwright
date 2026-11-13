"""The Trackwright MIDI Remote script shipped inside the package, and its installer.

Cubase loads user scripts from
``~/Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/<vendor>/<device>/<Vendor>_<Device>.js``.
Cubase does **not** reload a changed script by itself: restart Cubase (or use "Reload Scripts")
after installing a new version.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from loguru import logger

from trackwright.errors import PreconditionFailedError

SCRIPT_NAME = "Trackwright_Bridge.js"
SCRIPT_PATH = Path(__file__).with_name(SCRIPT_NAME)

InstallState = Literal["missing", "up_to_date", "different"]


def _version_of(path: Path) -> str | None:
    match = re.search(r"var SCRIPT_VERSION = '([^']+)'", path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


SCRIPT_VERSION = _version_of(SCRIPT_PATH)


@dataclass(frozen=True)
class ScriptStatus:
    destination: Path
    state: InstallState
    packaged_version: str | None
    installed_version: str | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "destination": str(self.destination),
            "state": self.state,
            "packaged_version": self.packaged_version,
            "installed_version": self.installed_version,
        }


def script_status(install_dir: Path, source: Path = SCRIPT_PATH) -> ScriptStatus:
    """Compare the installed script with ``source`` (the packaged script by default)."""
    destination = install_dir / SCRIPT_NAME
    if not destination.exists():
        return ScriptStatus(destination, "missing", _version_of(source), None)
    state: InstallState = "up_to_date" if _digest(destination) == _digest(source) else "different"
    return ScriptStatus(destination, state, _version_of(source), _version_of(destination))


def install_script(install_dir: Path, *, apply: bool, source: Path = SCRIPT_PATH) -> tuple[ScriptStatus, bool]:
    """Copy ``source`` (the packaged script by default) to ``install_dir``. Without ``apply`` only report.

    ``source`` lets developers install an experiment build (for example ``experiments/tw1101``).
    Returns the status *after* the call and whether a file was written.
    """
    if not install_dir.is_absolute():
        raise PreconditionFailedError(f"the install directory must be an absolute path: {install_dir}")
    if not source.is_file() or _version_of(source) is None:
        raise PreconditionFailedError(f"{source} is not a Trackwright MIDI Remote script")
    status = script_status(install_dir, source)
    if not apply or status.state == "up_to_date":
        return status, False
    if status.destination.is_symlink():
        raise PreconditionFailedError(f"refusing to overwrite a symbolic link: {status.destination}")
    install_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, status.destination)
    logger.info("installed {} {} at {}", SCRIPT_NAME, _version_of(source), status.destination)
    return script_status(install_dir, source), True
