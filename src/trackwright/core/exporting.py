"""Export the mix (TW-1204), with the user: Trackwright sets the range and opens Cubase's dialog, the user
chooses the format and exports, and the confirm phase finds the file and checks its duration.

Verified in Cubase Elements 15.0.30 (experiments/tw1204): the dialog has no range field and exports between
the locators; Select All + Locators to Selection put them around all the audio; it proposes
``<project folder>/Mixdown`` and the project name.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

from trackwright.core.base import operation
from trackwright.core.models import ExportedFileOut, ExportOut
from trackwright.core.project import format_seconds
from trackwright.core.ranges import TAG_RECORD, TAG_START, RangeMixin
from trackwright.errors import PreconditionFailedError, TrackwrightError

DURATION_TOLERANCE = 0.15
INSTRUCTIONS = (
    "Cubase shows 'Export Audio Mixdown'. Check the channel (Stereo Out), the name, the folder and the format "
    "(WAV for archiving, MP3 for publishing), then click 'Export Audio'. Afterwards call this tool with "
    "phase 'confirm' and the same 'since' and 'expected_seconds'."
)


class ExportMixin(RangeMixin):
    def _locators_around_all_audio(self, transport: int) -> tuple[float, float]:
        """Select All + Locators to Selection (verified), then read both locators in seconds."""
        self._range_cmd("tool.select")
        self._range_cmd("edit.select_all")
        self._range_cmd("transport.locators_to_selection")
        self._clear_selection()
        cursor = self._cursor_seconds(transport)
        primary = self.call("transport.get").get("primary") or {}
        bounds = []
        for field in ("cycleLeft", "cycleRight"):
            bars = str((primary.get(field) or {}).get("time", ""))
            self.call("transport.setTime", {"which": "locator", "display": "primary", "time": bars})
            self.wait_until(self._cursor_bars, bars.__eq__)
            bounds.append(self._cursor_seconds(transport))
        self._move_cursor_seconds(transport, cursor)
        return bounds[0], bounds[1]

    def _export_folder(self) -> Path | None:
        folders = self.launcher.project_folders() if self.launcher is not None else []
        return Path(folders[0]) / "Mixdown" if folders else None

    @operation
    def export_mix(
        self,
        phase: Literal["start", "confirm"],
        *,
        start: str | None = None,
        end: str | None = None,
        unit: str = "seconds",
        since: float | None = None,
        expected_seconds: float | None = None,
        folder: str | None = None,
        dry_run: bool = True,
    ) -> ExportOut:
        if phase == "confirm":
            return self._confirm_export(since, expected_seconds, folder)
        if (start is None) != (end is None):
            raise PreconditionFailedError("give both start and end, or neither for the whole project",
                                          code="BAD_REQUEST")  # fmt: skip
        transport = self._transport_id()
        guess = self._export_folder()
        out = ExportOut(phase="start", status="planned", dry_run=dry_run, start=None, end=None,
                        expected_seconds=None, folder=str(guess) if guess else None, since=None)  # fmt: skip
        if start is not None and end is not None:
            cursor = self._cursor_seconds(transport)
            span = (self._seconds_of(transport, start, unit), self._seconds_of(transport, end, unit))
            self._move_cursor_seconds(transport, cursor)
            if not 0 <= span[0] < span[1]:
                raise PreconditionFailedError("the range must have 0 <= start < end", code="BAD_TIME")
            out.start, out.end = format_seconds(span[0]), format_seconds(span[1])
            out.expected_seconds = round(span[1] - span[0], 3)
        else:
            out.notes.append("whole project: the locators will go around all the audio")
        if dry_run:
            return out
        self.policy.check_project_write()
        if self._transport_flag(transport, TAG_START) or self._transport_flag(transport, TAG_RECORD):
            raise PreconditionFailedError("stop the transport before exporting", code="TRANSPORT_RUNNING")
        if out.expected_seconds is None:
            span = self._locators_around_all_audio(transport)
            out.start, out.end = format_seconds(span[0]), format_seconds(span[1])
            out.expected_seconds = round(span[1] - span[0], 3)
        else:
            cursor = self._cursor_seconds(transport)
            self._set_locator_seconds(transport, "left", self._seconds_of(transport, str(start), unit))
            self._set_locator_seconds(transport, "right", self._seconds_of(transport, str(end), unit))
            self._move_cursor_seconds(transport, cursor)
        if not self._performable("file.export_audio_mixdown"):
            raise TrackwrightError("Cubase cannot open the export dialog now (is another dialog open?)",
                                   code="CANNOT_PERFORM")  # fmt: skip
        out.since = time.time()
        self._range_cmd("file.export_audio_mixdown")
        out.status = "awaiting_user"
        out.instructions = INSTRUCTIONS
        out.notes.append("the locators stay on the exported range")
        return out

    def _confirm_export(self, since: float | None, expected: float | None, folder: str | None) -> ExportOut:
        if since is None:
            raise PreconditionFailedError("give 'since' from the start phase", code="BAD_REQUEST")
        where = Path(folder).expanduser() if folder else self._export_folder()
        out = ExportOut(phase="confirm", status="not_found", dry_run=False, start=None, end=None,
                        expected_seconds=expected, folder=str(where) if where else None, since=since)  # fmt: skip
        if where is None:
            out.instructions = "the export folder is unknown: give 'folder' (the path shown in Cubase's dialog)"
            return out
        for found in self.exports.find(where, since):
            matches = None
            if expected is not None and found.duration_seconds is not None:
                matches = abs(found.duration_seconds - expected) <= DURATION_TOLERANCE
            out.files.append(ExportedFileOut(path=found.path, size_bytes=found.size_bytes,
                                             duration_seconds=found.duration_seconds,
                                             duration_matches=matches))  # fmt: skip
        if out.files:
            out.status = "done"
            out.verified = out.files[0].duration_matches
        else:
            out.instructions = (
                "no audio file newer than the start phase in that folder: finish the export in Cubase, or give "
                "'folder' if you chose another one"
            )
        return out
