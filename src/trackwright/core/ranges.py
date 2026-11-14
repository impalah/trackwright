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
import itertools
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
MAX_ROUNDS = 6  # single-track deletion: events hidden under others only show up after those are deleted
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

    def probe_edges(self, transport: int, start: float, until: float = math.inf) -> tuple[list[float], bool]:
        """Event edges after ``start`` on the selected tracks (up to the first one past ``until``), and
        whether the walk reached the last edge."""
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
            if now > until:
                return edges, False
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
        track: str | None = None,
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
        if track is not None and action != "delete":
            raise PreconditionFailedError(
                "on a single track only 'delete' is possible: closing or opening time on one track would "
                "put it out of sync with the others",
                code="BAD_REQUEST",
            )
        target = self.resolve_track(TrackSelector.parse(track)) if track else None
        probe_item = target or (self.resolve_track(TrackSelector.parse(verify_track)) if verify_track else None)
        out = RangeEditOut(
            dry_run=dry_run,
            action=action,
            start=format_seconds(start_s),
            end=format_seconds(end_s),
            length_seconds=round(end_s - start_s, 3),
            effect=EFFECTS[action],
            scope=(
                f"only the track {self.track_info(target).name}"
                if target
                else "every track with events in the range (Cubase's Select in Loop selects all tracks)"
            ),
            track=self.track_info(target).name if target else None,
            verify_track=self.track_info(probe_item).name if probe_item else None,
            notes=["Edit > Undo in Cubase reverts it", "the project is not saved"],
        )
        if dry_run:
            return out
        if target is not None:
            self.policy.check_track(self.track_info(target).name)
        else:
            self.policy.check_all_tracks("an edit on every track")
        if self._transport_flag(transport, TAG_START) or self._transport_flag(transport, TAG_RECORD):
            raise PreconditionFailedError("stop the transport before editing", code="TRANSPORT_RUNNING")
        if target is not None:
            self._delete_on_track(out, transport, (start_s, end_s), int(target["id"]), cursor_before)
        else:
            self._apply_range(out, transport, (start_s, end_s), probe_item=probe_item, cursor_before=cursor_before)
        return out

    # ------------------------------------------------------------------ one track (TW-1212)
    def _clear_selection(self) -> None:
        if self._performable("edit.select_none"):
            self._range_cmd("edit.select_none")

    def _selection_bounds(self, transport: int) -> tuple[float, float] | None:
        bounds = []
        for key in ("transport.locate_selection", "transport.locate_selection_end"):
            if not self._performable(key):
                return None
            previous = self._cursor_seconds(transport)
            self._range_cmd(key)

            def moved(value: float, last: float = previous) -> bool:
                return value != last

            bounds.append(self.wait_until(lambda: self._cursor_seconds(transport), moved))
        return bounds[0], bounds[1]

    def _delete_on_track(
        self, out: RangeEditOut, transport: int, span: tuple[float, float], channel: int, cursor_before: float
    ) -> None:
        """Verified recipe (experiments/tw1212): split this track's events at both ends, then delete the
        pieces inside one by one with Select Events under Cursor, which only looks at the selected track."""
        start, end = span
        selected = self.call("da.base").get("base")
        probe_from = max(start - PROBE_MARGIN, 0.0)
        steps = 0
        try:
            self._range_cmd("tool.select")
            self._select_channel(channel)
            before = self.probe_edges(transport, probe_from)
            for cut in (start, end):
                self._clear_selection()
                self._move_cursor_seconds(transport, cut)
                if self._performable("edit.select_events_under_cursor"):
                    self._range_cmd("edit.select_events_under_cursor")
                    if self._performable("edit.split_at_cursor"):
                        self._range_cmd("edit.split_at_cursor")
                        steps += 1
            for _ in range(MAX_ROUNDS):
                deleted = self._delete_round(transport, start, end)
                steps += deleted
                if not deleted:
                    break
            out.applied = True
        finally:
            out.undo_steps = steps
            self._clear_selection()
            out.notes.append("the Object Selection tool is active")
            self._restore(transport, {}, cursor_before, selected)
        self._select_channel(channel)
        after = self.probe_edges(transport, probe_from)
        self._restore(transport, {}, cursor_before, selected)
        out.edges_before = [format_seconds(e) for e in before[0]]
        out.edges_after = [format_seconds(e) for e in after[0]]
        out.mismatches = compare_edges("delete", start, end, before, after)
        out.verified = not out.mismatches
        if steps > 1:
            out.notes.append(f"undoing it in Cubase takes {steps} Undo steps")

    def _delete_round(self, transport: int, start: float, end: float) -> int:
        """Delete every event piece found between consecutive edges inside the range; return how many."""
        edges, _ = self.probe_edges(transport, start, until=end)
        points = [start, *(e for e in edges if e < end - SECONDS_TOLERANCE), end]
        deleted = 0
        for a, b in itertools.pairwise(points):
            if b - a <= SECONDS_TOLERANCE:
                continue
            self._clear_selection()
            self._move_cursor_seconds(transport, (a + b) / 2)
            if not self._performable("edit.select_events_under_cursor"):
                continue
            self._range_cmd("edit.select_events_under_cursor")
            bounds = self._selection_bounds(transport)
            if bounds is None or bounds[0] < start - SECONDS_TOLERANCE or bounds[1] > end + SECONDS_TOLERANCE:
                raise PreconditionFailedError(
                    "an event reaches outside the range (the split did not happen); nothing more was deleted",
                    code="SPLIT_FAILED",
                    details={"selection": [format_seconds(x) for x in bounds] if bounds else None},
                )
            # Measuring moved the cursor to the selection end, and with Cubase's "auto-select events under
            # cursor" preference that changes the selection (verified, TW-1212): select the piece again.
            self._clear_selection()
            self._move_cursor_seconds(transport, (a + b) / 2)
            self._range_cmd("edit.select_events_under_cursor")
            if self._performable("edit.delete"):
                self._range_cmd("edit.delete")
                deleted += 1
        return deleted

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
            # A leftover object selection must not be what the edit acts on (TW-1401).
            self._clear_selection()
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
            out.undo_steps = 1
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
