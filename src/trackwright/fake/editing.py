"""Range editing, undo, clipboard and transport as seen in Cubase (TW-1211, TW-1212)."""

from __future__ import annotations

from trackwright.fake.core import FakeCore
from trackwright.fake.timeline import (
    _bars,
    _bars_to_beats,
    _beats_to_bars,
    _edit_events,
)


class FakeEditing(FakeCore):
    # ------------------------------------------------------------------ range editing (TW-1211)
    def _bars_at(self, seconds: float) -> str:
        return _beats_to_bars(seconds * self.tempo / 60, self.meter)

    def _apply_selection(self, key: str) -> bool:
        if key in ("tool.range", "tool.select"):
            self.tool = key.split(".")[1]
            self.range = None
        elif key == "edit.select_in_loop":
            start, end = self._seconds(self.transport["cycleLeft"]), self._seconds(self.transport["cycleRight"])
            self.range = (start, end) if self.tool == "range" and start < end else None
        elif key == "edit.select_none":
            self.range = None
            self.selected_events = []
        elif key == "edit.select_all":
            self.selected_events = [(tid, e) for tid, events in self.track_events.items() for e in events]
        elif key == "edit.select_events_under_cursor":  # verified: only the selected tracks
            self.selected_events = self._under_cursor()
        else:
            return False
        return True

    def _apply_edit(self, key: str) -> bool:
        """Tool, selection and range commands; ``False`` lets other edit commands fall through."""
        if self._apply_selection(key):
            return True
        if key == "edit.split_at_cursor" and self.selected_events:
            self._split_selected(self._seconds(self.transport["locator"]))
        elif key == "edit.delete" and self.tool == "select" and self.selected_events:
            self._snapshot()
            for tid, event in self.selected_events:
                self.track_events[tid].remove(event)
            self.selected_events = []
        elif key in self.RANGE_ACTIONS and self.range is not None:
            self.history.append({tid: list(events) for tid, events in self.track_events.items()})
            for tid, events in self.track_events.items():
                self.track_events[tid] = _edit_events(events, key, *self.range)
            if key == "edit.cut_time":
                self.clipboard_seconds = self.range[1] - self.range[0]
        elif key == "edit.undo" and self.history:
            self.track_events = self.history.pop()
            self.selected_events = []
        else:
            return False
        return True

    def _split_selected(self, at: float) -> None:
        self._snapshot()
        for tid, (a, b) in self.selected_events:
            if a + 1e-6 < at < b - 1e-6:
                events = self.track_events[tid]
                events[events.index((a, b))] = (a, at)
                events.append((at, b))
        self.selected_events = []

    def selection_bounds(self) -> tuple[float, float] | None:
        if self.tool == "range":
            return self.range
        if not self.selected_events:
            return None
        return min(e[0] for _, e in self.selected_events), max(e[1] for _, e in self.selected_events)

    def edges(self, track_id: int) -> list[float]:
        return sorted({round(edge, 3) for event in self.track_events.get(track_id, []) for edge in event})

    def _apply_preset(self, key: str) -> bool:
        """Preset Next/Previous: act on the plugin whose editor is open, only when a preset is loaded."""
        if key not in ("preset.next", "preset.previous"):
            return False
        open_slots = [o for o in self.objects.values() if o.type == "Slot" and 4101 in o.params
                      and o.params[4101].value >= 0.5 and o.children]  # fmt: skip
        if len(open_slots) == 1 and self.preset_loaded and self.editor_focused:
            step = 0.1 if key == "preset.next" else -0.1
            for param in self.objects[open_slots[0].children[0]].params.values():
                param.value = round((param.value + step) % 1.0, 6)
        return True

    def _apply_project(self, key: str) -> None:
        if self._apply_preset(key):
            return
        tracks = self.channels[1:]
        if key == "addtrack.marker":
            self.non_mixer_tracks.append("Marker")
            self.selected = -1
        elif key == "marker.insert":
            self.markers.append(self.transport["locator"])
        elif key in ("project.select_track_next", "project.select_track_prev") and self.selected in tracks:
            i = tracks.index(self.selected) + (1 if key.endswith("next") else -1)
            if 0 <= i < len(tracks):
                self._select(tracks[i])
        elif key == "project.remove_selected_tracks" and self.selected in tracks:
            if self.objects[self.selected].has_events:
                self.pending_removal = self.selected  # Cubase asks for confirmation
            else:
                self.remove(self.selected)
                self.selected = -1

    def _apply_transport(self, key: str) -> None:
        self._apply_transport_move(key)
        self._cursor_moved()

    def _cursor_moved(self) -> None:
        if self.auto_select_under_cursor and self.tool == "select" and self.track_events:
            self.selected_events = self._under_cursor()

    def _apply_locators(self, key: str) -> bool:
        bounds = self.selection_bounds()
        if key == "transport.locators_to_selection" and bounds:
            self.transport["cycleLeft"], self.transport["cycleRight"] = (self._bars_at(b) for b in bounds)
        elif key in ("transport.set_left_locator", "transport.set_right_locator"):
            self.transport["cycleLeft" if "left" in key else "cycleRight"] = self.transport["locator"]
        else:
            return False
        return True

    def _apply_transport_move(self, key: str) -> None:
        cursor = self.transport["locator"]
        if self._apply_locators(key):
            return
        if key == "transport.locate_next_event":
            here = self._seconds(cursor)
            following = [edge for edge in self.edges(self.selected) if edge > here + 1e-6]
            if following:
                self.transport["locator"] = self._bars_at(following[0])
        elif key in ("transport.locate_selection", "transport.locate_selection_end") and self.selection_bounds():
            bounds = self.selection_bounds()
            assert bounds is not None
            self.transport["locator"] = self._bars_at(bounds[0 if key.endswith("selection") else 1])
        elif key == "transport.start":
            self.playing = True
            self.position = _bars_to_beats(cursor, self.meter)
        elif key == "transport.stop":
            self.playing = False
        elif key == "transport.locate_prev_marker":
            earlier = [m for m in self.markers if _bars(m) < _bars(cursor)]
            self.transport["locator"] = max(earlier, key=_bars) if earlier else "1. 1. 1.  0"
        elif key == "transport.locate_next_marker":
            later = [m for m in self.markers if _bars(m) > _bars(cursor)]
            if later:
                self.transport["locator"] = min(later, key=_bars)
            elif self.last_event_end is not None and _bars(self.last_event_end) > _bars(cursor):
                # Verified on Cubase 15 (2026-11-12): without a next marker the cursor goes to the end of the
                # last event of the project (the POC had seen it stay put).
                self.transport["locator"] = self.last_event_end
