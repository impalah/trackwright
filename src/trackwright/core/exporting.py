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

from trackwright.core.base import MIXER, SoloChange, operation
from trackwright.core.models import ExportedFileOut, ExportOut, SoloChangeOut
from trackwright.core.ranges import RangeMixin
from trackwright.core.refs import TrackSelector
from trackwright.core.tags import Channel, Transport
from trackwright.core.timefmt import format_seconds
from trackwright.errors import PreconditionFailedError, TrackwrightError

DURATION_TOLERANCE = 0.15
LOSSY_SUFFIXES = frozenset({".mp3", ".m4a", ".ogg"})


def duration_tolerance(path: str, expected: float) -> float:
    """Lossy files report an *estimated* duration and lose or gain a few frames at the end: an MP3 of a
    139.976 s range measured 139.721 s (verified, TW-1204), a 28 s one 27.991 s."""
    if Path(path).suffix.lower() in LOSSY_SUFFIXES:
        return 0.5 + expected * 0.002
    return DURATION_TOLERANCE


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
            self.wait_until(self.cursor_bars, bars.__eq__)
            bounds.append(self._cursor_seconds(transport))
        self._move_cursor_seconds(transport, cursor)
        return bounds[0], bounds[1]

    def _export_folder(self) -> Path | None:
        folder, _unknown = self.project_folder()
        return folder / "Mixdown" if folder else None

    @operation
    def export_mix(
        self,
        phase: Literal["start", "confirm", "cancel"],
        *,
        solo: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        unit: str = "seconds",
        since: float | None = None,
        expected_seconds: float | None = None,
        folder: str | None = None,
        dry_run: bool = True,
    ) -> ExportOut:
        if phase == "confirm":
            out = self._confirm_export(since, expected_seconds, folder)
            self._restore_solo(out)
            return out
        if phase == "cancel":
            if since is None:
                raise PreconditionFailedError("give 'since' from the start phase", code="BAD_REQUEST")
            out = ExportOut(phase="cancel", status="cancelled", dry_run=False, start=None, end=None,
                            expected_seconds=None, folder=None, since=since)  # fmt: skip
            self._restore_solo(out)
            return out
        return self._start_export(start, end, unit, solo, dry_run=dry_run)

    def _start_export(
        self, start: str | None, end: str | None, unit: str, solo: list[str] | None, *, dry_run: bool
    ) -> ExportOut:
        if (start is None) != (end is None):
            raise PreconditionFailedError("give both start and end, or neither for the whole project",
                                          code="BAD_REQUEST")  # fmt: skip
        transport = self._transport_id()
        guess = self._export_folder()
        out = ExportOut(phase="start", status="planned", dry_run=dry_run, start=None, end=None,
                        expected_seconds=None, folder=str(guess) if guess else None, since=None)  # fmt: skip
        if start is not None and end is not None:
            span = self._span_seconds(transport, start, end, unit)
            if not 0 <= span[0] < span[1]:
                raise PreconditionFailedError("the range must have 0 <= start < end", code="BAD_TIME")
            out.start, out.end = format_seconds(span[0]), format_seconds(span[1])
            out.expected_seconds = round(span[1] - span[0], 3)
        else:
            out.notes.append("whole project: the locators will go around all the audio")
        plan = self._solo_plan(solo) if solo else []
        out.solo = [SoloChangeOut(track_uid=f"uid:{c.uid}", name=c.name, before=c.before, during=not c.before)
                    for c in plan]  # fmt: skip
        if dry_run:
            return out
        self.policy.check_project_write()
        if self._transport_flag(transport, Transport.START) or self._transport_flag(transport, Transport.RECORD):
            raise PreconditionFailedError("stop the transport before exporting", code="TRANSPORT_RUNNING")
        for change in plan:
            self.policy.check_track(change.name)
        applied: list[SoloChange] = []
        try:
            for change in plan:
                self._write_solo(change, not change.before)
                applied.append(change)
            self._open_export_dialog(transport, out, span if out.expected_seconds is not None else None)
        except BaseException:
            for change in reversed(applied):  # nothing was exported: put every solo back before failing
                try:
                    self._write_solo(change, change.before)
                except TrackwrightError:
                    out.notes.append(f"could not restore the solo of {change.name}")
            raise
        if applied:
            self._export_solo[out.since or 0.0] = applied
            out.notes.append("solo changed for the export: confirm or cancel puts it back")
        return out

    def _open_export_dialog(self, transport: int, out: ExportOut, span: tuple[float, float] | None) -> None:
        if span is None:
            span = self._locators_around_all_audio(transport)
            out.start, out.end = format_seconds(span[0]), format_seconds(span[1])
            out.expected_seconds = round(span[1] - span[0], 3)
        else:
            cursor = self._cursor_seconds(transport)
            self._set_locator_seconds(transport, "left", span[0])  # C-27: converted once, in the plan
            self._set_locator_seconds(transport, "right", span[1])
            self._move_cursor_seconds(transport, cursor)
        if not self._performable("file.export_audio_mixdown"):
            raise TrackwrightError("Cubase cannot open the export dialog now (is another dialog open?)",
                                   code="CANNOT_PERFORM")  # fmt: skip
        out.since = time.time()
        self._range_cmd("file.export_audio_mixdown")
        out.status = "awaiting_user"
        out.instructions = INSTRUCTIONS
        out.notes.append("the locators stay on the exported range")

    # ------------------------------------------------------------------ solo (TW-1605)
    def _solo_plan(self, selectors: list[str]) -> list[SoloChange]:
        """The solo flags to change so that exactly the given tracks are soloed (outputs never change)."""
        wanted = {int(self.resolve_track(TrackSelector.parse(s))["id"]) for s in selectors}
        plan = []
        for item in self.channels():
            info = self.track_info(item)
            if info.type == "OutputChannel" or info.solo is None:
                continue
            soloed = bool(info.solo)
            if soloed != (int(item["id"]) in wanted):
                plan.append(SoloChange(int(item["id"]), str(item["uid"]), info.name, soloed))
        return plan

    def _write_solo(self, change: SoloChange, on: bool) -> None:
        value = 1.0 if on else 0.0
        self.write_parameter("da.param.set", {"id": change.channel_id, "tag": Channel.SOLO, "value": value, **MIXER},
                             change.channel_id, Channel.SOLO)  # fmt: skip

    def _restore_solo(self, out: ExportOut) -> None:
        """Put back every solo the start phase changed; try them all, report each one."""
        changes = self._export_solo.pop(out.since or 0.0, [])
        if not changes:
            return
        restored = []
        for change in changes:
            ok: bool | None
            try:
                self._write_solo(change, change.before)
                ok = float(self.read_parameter(change.channel_id, Channel.SOLO).get("process") or 0) >= 0.5
                ok = ok == change.before
            except TrackwrightError as exc:
                ok = False
                out.notes.append(f"could not restore the solo of {change.name}: {exc.code}")
            restored.append(SoloChangeOut(track_uid=f"uid:{change.uid}", name=change.name, before=change.before,
                                          during=not change.before, restored=ok))  # fmt: skip
        out.solo = restored
        out.solo_restored = all(r.restored for r in restored)

    def _confirm_export(self, since: float | None, expected: float | None, folder: str | None) -> ExportOut:
        if since is None:
            raise PreconditionFailedError("give 'since' from the start phase", code="BAD_REQUEST")
        where = Path(folder).expanduser().resolve() if folder else self._export_folder()
        out = ExportOut(phase="confirm", status="not_found", dry_run=False, start=None, end=None,
                        expected_seconds=expected, folder=str(where) if where else None, since=since)  # fmt: skip
        if where is None:
            out.instructions = "the export folder is unknown: give 'folder' (the path shown in Cubase's dialog)"
            return out
        for found in self.exports.find(where, since):
            matches, difference = None, None
            if expected is not None and found.duration_seconds is not None:
                difference = round(found.duration_seconds - expected, 3)
                matches = abs(difference) <= duration_tolerance(found.path, expected)
            out.files.append(ExportedFileOut(path=found.path, size_bytes=found.size_bytes,
                                             duration_seconds=found.duration_seconds,
                                             difference_seconds=difference, duration_matches=matches))  # fmt: skip
        if out.files:
            out.status = "done"
            out.verified = out.files[0].duration_matches
        else:
            out.instructions = (
                "no audio file newer than the start phase in that folder: finish the export in Cubase, or give "
                "'folder' if you chose another one"
            )
        return out
