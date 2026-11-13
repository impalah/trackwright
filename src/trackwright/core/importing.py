"""Import an audio file, with the user (TW-1203).

Verified in Cubase Elements 15.0.30 (experiments/tw1203): ``File / Import Audio File`` opens the macOS file
selector, the file goes to the **selected track at the cursor**, and Cubase copies it to
``<project>/Audio``. While the selector is open **Cubase does not answer the script**, so the start phase
makes no call after opening it. The confirm phase probes the track's event edges.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

from trackwright.core.base import operation
from trackwright.core.exporting import ExportMixin
from trackwright.core.models import ImportOut
from trackwright.core.project import SECONDS_TOLERANCE, format_seconds
from trackwright.core.ranges import TAG_RECORD, TAG_START
from trackwright.core.refs import TrackSelector
from trackwright.errors import PreconditionFailedError, RequestTimeoutError, TrackwrightError
from trackwright.exports import AUDIO_SUFFIXES

EDGE_TOLERANCE = 0.01


class ImportMixin(ExportMixin):
    @operation
    def import_audio(
        self,
        phase: Literal["start", "confirm"],
        track: str,
        position: str,
        *,
        unit: str = "seconds",
        file: str | None = None,
        since: float | None = None,
        dry_run: bool = True,
    ) -> ImportOut:
        path = Path(file).expanduser() if file else None
        expected = None
        if path is not None:
            if not path.is_file() or path.suffix.lower() not in AUDIO_SUFFIXES:
                raise PreconditionFailedError(f"not an audio file: {path}", code="NOT_FOUND")
            expected = self.exports.duration(path)
        if phase == "confirm":
            return self._confirm_import(track, position, unit, path=path, expected=expected, since=since)
        item = self.resolve_track(TrackSelector.parse(track))
        transport = self._transport_id()
        cursor = self._cursor_seconds(transport)
        at = self._seconds_of(transport, position, unit)
        self._move_cursor_seconds(transport, cursor)
        out = ImportOut(phase="start", status="planned", dry_run=dry_run, track=self.track_info(item).name,
                        position=format_seconds(at), file=str(path) if path else None, expected_seconds=expected,
                        since=None)  # fmt: skip
        out.notes.append("the audio goes to this track at this position; Cubase copies the file into the project")
        if dry_run:
            return out
        self.policy.check_track(out.track)
        if self._transport_flag(transport, TAG_START) or self._transport_flag(transport, TAG_RECORD):
            raise PreconditionFailedError("stop the transport before importing", code="TRANSPORT_RUNNING")
        if not self._performable("file.import_audio"):
            raise TrackwrightError("Cubase cannot open the import dialog now (is another dialog open?)",
                                   code="CANNOT_PERFORM")  # fmt: skip
        self._select_channel(int(item["id"]))
        self._move_cursor_seconds(transport, at)
        out.since = time.time()
        self._range_cmd("file.import_audio")  # from here Cubase is blocked until the user closes the selector
        out.status = "awaiting_user"
        pick = f"press Cmd+Shift+G, paste {path} and open it" if path else "choose the audio file and open it"
        out.instructions = (
            f"Cubase shows the file selector: {pick}. Accept the import options (Cubase copies the file into "
            "the project). Cubase does not answer until the selector is closed. Then call this tool with phase "
            "'confirm', the same track, position and file, and 'since'."
        )
        return out

    def _confirm_import(
        self,
        track: str,
        position: str,
        unit: str,
        *,
        path: Path | None,
        expected: float | None,
        since: float | None,
    ) -> ImportOut:
        if since is None:
            raise PreconditionFailedError("give 'since' from the start phase", code="BAD_REQUEST")
        out = ImportOut(phase="confirm", status="not_found", dry_run=False, track=track, position=position,
                        file=str(path) if path else None, expected_seconds=expected, since=since)  # fmt: skip
        try:
            item = self.resolve_track(TrackSelector.parse(track))
            transport = self._transport_id()
        except RequestTimeoutError:
            out.status = "awaiting_user"
            out.instructions = "Cubase does not answer yet: the file selector is probably still open"
            return out
        cursor = self._cursor_seconds(transport)
        at = self._seconds_of(transport, position, unit)
        out.track, out.position = self.track_info(item).name, format_seconds(at)
        selected = self.call("da.base").get("base")
        self._select_channel(int(item["id"]))
        edges, _ = self.probe_edges(transport, max(at - 1.0, 0.0), until=at + (expected or 0.0) + 1.0)
        self._restore(transport, {}, cursor, selected)
        wanted = [at] + ([at + expected] if expected is not None else [])
        found = [e for e in edges if any(abs(e - w) <= EDGE_TOLERANCE + SECONDS_TOLERANCE for w in wanted)]
        out.edges_found = [format_seconds(e) for e in found]
        project = self._project_folder_for_import()
        if project is not None:
            out.copied_to_project = [Path(f.path).name for f in self.exports.find(project / "Audio", since)]
        if len(found) == len(wanted):
            out.status, out.verified = "done", True
        else:
            out.instructions = (
                "the expected event edges are not on that track: the import was cancelled, went elsewhere, or "
                "the file has another duration"
            )
            out.verified = False
        if expected is None:
            out.notes.append("only the start was checked: give 'file' to check the end too")
        out.notes.append("Undo in Cubase removes the event, not the copy in the project's Audio folder")
        return out

    def _project_folder_for_import(self) -> Path | None:
        folders = self.launcher.project_folders() if self.launcher is not None else []
        return Path(folders[0]) if folders else None
