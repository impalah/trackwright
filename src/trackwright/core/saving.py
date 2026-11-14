"""Saving the project (TW-1202). Only on an explicit request: separate policy switch, dry run by default.

Verified in Cubase Elements 15.0.30 (experiments/tw1202): ``File / Save`` rewrites the project's .cpr and
``File / Save New Version`` writes ``<name>-01.cpr`` (and Cubase then works on it), both without a dialog
in a project that was saved before. The result is checked by the .cpr files' dates; nothing is opened.
Close, Revert and Quit are not offered.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

from trackwright.core.base import ServiceBase, operation
from trackwright.core.models import ProjectFileOut, SaveOut
from trackwright.exports import PROJECT_SUFFIXES, ExportedFile

SAVE_KEYS = {"save": "file.save", "new_version": "file.save_new_version"}
SAVE_WAIT_SECONDS = 10.0
EFFECTS = {
    "save": "overwrites the project file Cubase has open with the current state",
    "new_version": "writes a new numbered project file (<name>-NN.cpr); Cubase then works on that file",
}


def _file(found: ExportedFile) -> ProjectFileOut:
    return ProjectFileOut(name=Path(found.path).name, size_bytes=found.size_bytes,
                          modified=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(found.modified)))  # fmt: skip


class SavingMixin(ServiceBase):
    def _project_files(self, folder: Path | None, since: float = 0.0) -> list[ExportedFile]:
        return self.exports.find(folder, since, PROJECT_SUFFIXES) if folder else []

    @operation
    def save_project(self, mode: Literal["save", "new_version"] = "save", *, dry_run: bool = True) -> SaveOut:
        folder, unknown = self.project_folder()
        before = self._project_files(folder)
        out = SaveOut(mode=mode, dry_run=dry_run, status="planned", folder=str(folder) if folder else None,
                      files_before=[_file(f) for f in before], notes=[EFFECTS[mode]])  # fmt: skip
        if folder is None:
            out.notes.append(f"{unknown}: the save cannot be verified")
        if dry_run:
            return out
        self.policy.check_save()
        started = time.time()
        self.call("cmd.run", {"key": SAVE_KEYS[mode]})
        if folder is None:
            out.status = "fired"  # C-06: nothing proves a file was written (a new project shows Save As)
            out.instructions = "the save was requested but cannot be verified: check in Cubase that it was saved"
            return out
        names_before = {Path(f.path).name for f in before}
        deadline = time.monotonic() + SAVE_WAIT_SECONDS
        while True:
            written = [f for f in self._project_files(folder, started)
                       if mode == "save" or Path(f.path).name not in names_before]  # fmt: skip
            if written or time.monotonic() >= deadline:
                break
            self._sleep(0.5)
        if written:
            out.status, out.saved, out.verified = "saved", _file(written[0]), True
        else:
            out.status, out.verified = "awaiting_user", False
            out.instructions = (
                "no project file was written: Cubase may be showing a dialog (for example 'Save As' for a "
                "project that was never saved). Answer it in Cubase."
            )
        return out
