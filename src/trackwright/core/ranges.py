"""Range editing in seconds (TW-1211), for podcast-style editing where the time signature does not matter.

Verified in Cubase Elements 15.0.30 (experiments/tw1211):

* the locators cannot be set through the seconds display, but the cursor can; ``Set Left/Right Locator``
  then puts a locator at the cursor;
* with the Range tool, ``Select in Loop`` selects the range between the locators **on every track**;
* ``Delete``, ``Delete Time``, ``Cut Time``, ``Insert Silence`` and ``Crop Range`` act on it without a
  dialog, and ``Undo`` reverts each exactly;
* ``Locate Next Event`` walks the event edges (starts and ends, unlabelled) of the selected tracks. The
  API cannot read events, so this probe is what verifies the edit.
"""

from __future__ import annotations

import contextlib
import math
from typing import Literal

from trackwright.core.base import MIXER, TAG_SELECTED, operation
from trackwright.core.models import RangeEditOut
from trackwright.core.project import SECONDS_TOLERANCE, ProjectMixin, format_seconds, parse_seconds
from trackwright.core.refs import TrackSelector
from trackwright.core.writing import bars_tuple, format_bars
from trackwright.errors import PreconditionFailedError, TrackwrightError

RangeAction = Literal["delete", "delete_time", "cut_time", "insert_silence", "crop"]
ACTION_KEYS: dict[str, str] = {
    "delete": "edit.delete",
    "delete_time": "edit.delete_time",
    "cut_time": "edit.cut_time",
    "insert_silence": "edit.insert_silence",
    "crop": "edit.crop_range",
}
EFFECTS: dict[str, str] = {
    "delete": "removes the audio in the range and leaves a gap; nothing moves",
    "delete_time": "removes the range and moves everything after it earlier, closing the gap",
    "cut_time": "like delete_time, and copies the range to the clipboard",
    "insert_silence": "inserts silence as long as the range at its start, moving everything after it later",
    "crop": "keeps only the range and removes everything outside it",
}
TAG_START, TAG_RECORD = 4015, 4019
MAX_EDGES = 48
PROBE_MARGIN = 1.0  # seconds before the range where the probe starts


class RangeMixin(ProjectMixin):
    # ------------------------------------------------------------------ helpers
    def _seconds_of(self, transport: int, value: str, unit: str) -> float:
        if unit == "seconds":
            seconds = parse_seconds(value)
            if seconds is None:
                raise PreconditionFailedError(f"bad time {value!r}: use '2.5', '1:30' or '0:01:30.000'",
                                              code="BAD_TIME")  # fmt: skip
            return seconds
        if unit == "bars":
            position = bars_tuple(value)
            if position is None:
                raise PreconditionFailedError(f"bad position {value!r}: use '9. 1. 1. 0'", code="BAD_TIME")
            self.call("transport.setTime", {"which": "locator", "display": "primary", "time": format_bars(position)})
            self.wait_until(self._cursor_bars, lambda now: bars_tuple(now) == position)
            return self._cursor_seconds(transport)
        raise PreconditionFailedError("unit must be 'seconds' or 'bars'", code="BAD_REQUEST")

    def _transport_flag(self, transport: int, tag: int) -> bool:
        return float(self.call("da.param.get", {"id": transport, "tag": tag, **MIXER}).get("process") or 0) >= 0.5

    def _select_channel(self, channel_id: int) -> None:
        self.call("da.param.set", {"id": channel_id, "tag": TAG_SELECTED, "value": 1, "scope": "mixer"})
        self.wait_until(lambda: self.call("da.base"), lambda base: base.get("base") == channel_id)

    def _range_cmd(self, key: str) -> None:
        self.call("cmd.run", {"key": key})

    def _performable(self, key: str) -> bool:
        return self.call("cmd.canPerform", {"key": key}).get("canPerform", {}).get(key) is True

    def probe_edges(self, transport: int, start: float) -> tuple[list[float], bool]:
        """Event edges after ``start`` on the selected tracks, and whether the walk reached the last one."""
        self._move_cursor_seconds(transport, start)
        edges: list[float] = []
        previous = self._cursor_seconds(transport)
        for _ in range(MAX_EDGES):
            self._range_cmd("transport.locate_next_event")
            last = previous

            def moved(value: float, last: float = last) -> bool:
                return value != last

            now = self.wait_until(lambda: self._cursor_seconds(transport), moved)
            if abs(now - previous) <= SECONDS_TOLERANCE / 2:
                return edges, True
            edges.append(now)
            previous = now
        return edges, False

    # ------------------------------------------------------------------ tool
    @operation
    def edit_range(
        self,
        start: str,
        end: str,
        action: RangeAction,
        *,
        unit: str = "seconds",
        verify_track: str | None = None,
        dry_run: bool = True,
    ) -> RangeEditOut:
        if action not in ACTION_KEYS:
            raise PreconditionFailedError(f"action must be one of {sorted(ACTION_KEYS)}", code="BAD_REQUEST")
        transport = self._transport_id()
        cursor_before = self._cursor_seconds(transport)
        start_s, end_s = self._seconds_of(transport, start, unit), self._seconds_of(transport, end, unit)
        if unit == "bars":
            self._move_cursor_seconds(transport, cursor_before)
        if not 0 <= start_s < end_s:
            raise PreconditionFailedError("the range must have 0 <= start < end", code="BAD_TIME")
        probe_item = self.resolve_track(TrackSelector.parse(verify_track)) if verify_track else None
        out = RangeEditOut(
            dry_run=dry_run,
            action=action,
            start=format_seconds(start_s),
            end=format_seconds(end_s),
            length_seconds=round(end_s - start_s, 3),
            effect=EFFECTS[action],
            scope="every track with events in the range (Cubase's Select in Loop selects all tracks)",
            verify_track=self.track_info(probe_item).name if probe_item else None,
            notes=["Edit > Undo in Cubase reverts it", "the project is not saved"],
        )
        if dry_run:
            return out
        self.policy.check_project_write()
        if self._transport_flag(transport, TAG_START) or self._transport_flag(transport, TAG_RECORD):
            raise PreconditionFailedError("stop the transport before editing", code="TRANSPORT_RUNNING")
        self._apply_range(out, transport, (start_s, end_s), probe_item=probe_item, cursor_before=cursor_before)
        return out

    def _apply_range(
        self,
        out: RangeEditOut,
        transport: int,
        span: tuple[float, float],
        *,
        probe_item: dict[str, object] | None,
        cursor_before: float,
    ) -> None:
        start, end = span
        primary = self.call("transport.get").get("primary") or {}
        locators = {k: str((primary.get(k) or {}).get("time", "")) for k in ("cycleLeft", "cycleRight")}
        selected = self.call("da.base").get("base")
        probe_from = max(start - PROBE_MARGIN, 0.0)
        before: tuple[list[float], bool] | None = None
        try:
            if probe_item is not None:
                self._select_channel(int(str(probe_item["id"])))
                before = self.probe_edges(transport, probe_from)
            left = self._set_locator_seconds(transport, "left", start)
            right = self._set_locator_seconds(transport, "right", end)
            out.locators = [left, right]
            self._range_cmd("tool.range")
            self._range_cmd("edit.select_in_loop")
            key = ACTION_KEYS[out.action]
            if not self._performable(key):
                raise PreconditionFailedError(
                    "Cubase did not create the range selection (is the project window in front?)",
                    code="NO_RANGE_SELECTION",
                )
            self._range_cmd(key)
            out.applied = True
            if not self._performable("edit.undo"):
                out.notes.append("Undo is not available: Cubase may be showing a dialog; answer it")
        finally:
            self._range_cmd("tool.select")
            out.notes.append("the Object Selection tool is active again")
            self._restore(transport, locators, cursor_before, selected)
        if probe_item is not None and before is not None and out.applied:
            self._select_channel(int(str(probe_item["id"])))
            after = self.probe_edges(transport, probe_from)
            self._restore(transport, locators, cursor_before, selected)
            out.edges_before = [format_seconds(e) for e in before[0]]
            out.edges_after = [format_seconds(e) for e in after[0]]
            out.mismatches = compare_edges(out.action, start, end, before, after)
            out.verified = not out.mismatches
        else:
            out.notes.append("not verified: give verify_track (a track with audio) to check the result")

    def _restore(self, transport: int, locators: dict[str, str], cursor: float, selected: object) -> None:
        for field, time in locators.items():
            if bars_tuple(time) is not None:
                self.call("transport.setTime", {"which": field, "display": "primary", "time": time})
        with contextlib.suppress(TrackwrightError):  # the project may now be shorter than the old cursor
            self._move_cursor_seconds(transport, cursor)
        if isinstance(selected, int) and selected >= 0:
            with contextlib.suppress(TrackwrightError):
                self._select_channel(selected)


def expected_edge(action: str, start: float, end: float, edge: float) -> float | None:
    """Where an edge should be after the action (``None`` = removed)."""
    gap = end - start
    inside = start + SECONDS_TOLERANCE < edge < end - SECONDS_TOLERANCE
    if action == "crop":
        return edge if start - SECONDS_TOLERANCE <= edge <= end + SECONDS_TOLERANCE else None
    if action == "insert_silence":
        return edge if edge < start - SECONDS_TOLERANCE else edge + gap
    if inside:
        return None
    if action == "delete" or edge <= start + SECONDS_TOLERANCE:
        return edge
    return edge - gap  # delete_time / cut_time


def compare_edges(
    action: str, start: float, end: float, before: tuple[list[float], bool], after: tuple[list[float], bool]
) -> list[str]:
    """Differences between the probed edges after the edit and what the action should leave."""
    gap = end - start
    mapped = [m for m in (expected_edge(action, start, end, e) for e in before[0]) if m is not None]
    new_edges = {"delete": [start, end], "crop": [start, end], "insert_silence": [start, start + gap]}.get(
        action, [start]
    )
    horizon = math.inf
    if not before[1] and before[0]:
        last = expected_edge(action, start, end, before[0][-1])
        horizon = min(horizon, last if last is not None else start)
    if not after[1] and after[0]:
        horizon = min(horizon, after[0][-1])

    def near(value: float, pool: list[float]) -> bool:
        return any(abs(value - other) <= SECONDS_TOLERANCE * 2 for other in pool)

    problems = [
        f"unexpected edge at {format_seconds(e)}"
        for e in after[0]
        if e <= horizon + SECONDS_TOLERANCE and not near(e, mapped + new_edges)
    ]
    problems += [
        f"missing edge at {format_seconds(m)}"
        for m in mapped
        if m <= horizon + SECONDS_TOLERANCE and not near(m, after[0])
    ]
    return problems
