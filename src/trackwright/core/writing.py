"""Write and navigation tools (epic E06).

Every project modification follows the same rules:
- the write policy is checked (dry runs are always allowed);
- ``dry_run`` defaults to true and returns the plan without touching Cubase;
- writes are **never retried**: after a timeout the outcome is unknown, so the value is read back
  and reported with the error;
- the result is verified by reading the state back.

Navigation (selecting a track, moving the cursor) changes no project data and is always allowed.
"""

from __future__ import annotations

import re

from trackwright.core.base import (
    MIXER,
    TAG_INPUT,
    TAG_MUTE,
    TAG_NAME,
    TAG_OUTPUT,
    TAG_RECORD,
    TAG_SELECTED,
    TAG_SOLO,
    TAG_VOLUME,
    JsonObject,
    converted_value,
    operation,
)
from trackwright.core.models import (
    Change,
    InsertPluginOut,
    PositionOut,
    SelectOut,
    TempoOut,
    TimePosition,
    Value,
    WriteOut,
)
from trackwright.core.project import SECONDS_TOLERANCE, ProjectMixin, format_seconds, parse_seconds
from trackwright.core.refs import TrackSelector
from trackwright.errors import NotFoundError, PreconditionFailedError, RequestTimeoutError, TrackwrightError

BARS_RE = re.compile(r"^\s*(\d+)\s*\.\s*(\d+)\s*\.\s*(\d+)\s*\.\s*(\d+)\s*$")
TEMPO_TOLERANCE = 0.01


def bars_tuple(text: str) -> tuple[int, int, int, int] | None:
    match = BARS_RE.match(text)
    if not match:
        return None
    bar, beat, sixteenth, ticks = (int(g) for g in match.groups())
    return bar, beat, sixteenth, ticks


def format_bars(position: tuple[int, int, int, int]) -> str:
    """Cubase's own rendering, e.g. ``"3. 1. 1.  0"`` (ticks right-aligned on three characters)."""
    bar, beat, sixteenth, ticks = position
    return f"{bar}. {beat}. {sixteenth}.{ticks:>3}"


# Channel parameters that set_parameter refuses (TW-1401): writing the routing disconnects the track
# ("Sin bus" in the simulator's record of the POC); name and selection have their own verified tools.
PROTECTED_CHANNEL_TAGS = {
    TAG_INPUT: "input routing",
    TAG_OUTPUT: "output routing",
    TAG_NAME: "track name",
    TAG_SELECTED: "selection",
}
PROTECTED_TAG_TOOLS = {TAG_NAME: "cubase_rename_track", TAG_SELECTED: "cubase_select_track"}


class WritingMixin(ProjectMixin):
    # ------------------------------------------------------------------ helpers
    def _value(self, raw: JsonObject | None) -> Value | None:
        return None if raw is None else Value(process=raw.get("process"), display=raw.get("display"))

    def _change(self, before: JsonObject, requested: float | str, after: JsonObject | None, ok: bool | None) -> Change:
        before_value = self._value(before)
        assert before_value is not None
        return Change(
            tag=int(before["tag"]),
            title=str(before.get("title", "")),
            before=before_value,
            requested=requested,
            after=self._value(after),
            verified=ok,
        )

    # ------------------------------------------------------------------ parameters
    @operation
    def set_parameter(
        self,
        track: str,
        target: str,
        tag: int,
        value: float,
        *,
        unit: str = "process",
        dry_run: bool = True,
        tolerance: float = 1e-3,
        expect_title: str | None = None,
    ) -> WriteOut:
        item = self.resolve_track(TrackSelector.parse(track))
        obj = self.resolve_target(item, target)
        if obj is item and tag in PROTECTED_CHANNEL_TAGS:
            raise PreconditionFailedError(
                f"channel parameter {tag} ({PROTECTED_CHANNEL_TAGS[tag]}) cannot be written with this tool",
                code="READ_ONLY_PARAM",
                details={
                    "use": "cubase_rename_track / cubase_select_track" if tag in (TAG_NAME, TAG_SELECTED) else None
                },
            )
        before = self.read_parameter(int(obj["id"]), tag)
        if before.get("editLock"):
            raise PreconditionFailedError("the parameter is edit-locked in Cubase", code="PARAM_LOCKED")
        if expect_title is not None and before.get("title") != expect_title:
            raise PreconditionFailedError(
                f"parameter {tag} is {before.get('title')!r}, expected {expect_title!r}", code="PRECONDITION_FAILED"
            )
        if unit == "plain":
            converted = self.call("da.convert", {"id": obj["id"], "tag": tag, "plain": value, **MIXER})
            process = converted_value(converted)
        elif unit == "process":
            process = value
        else:
            raise PreconditionFailedError("unit must be 'process' or 'plain'", code="BAD_REQUEST")
        if not 0.0 <= process <= 1.0:
            raise PreconditionFailedError(
                f"process value {process:.6g} is outside [0, 1]", code="OUT_OF_RANGE", details={"unit": unit}
            )
        name = self.track_info(item).name
        if dry_run:
            return WriteOut(
                track_uid=f"uid:{item['uid']}",
                dry_run=True,
                target=f"{name} / {target}",
                changes=[self._change(before, process, None, None)],
                verified=None,
            )
        self.policy.check_track(name)
        params = {"id": obj["id"], "tag": tag, "value": process, **MIXER}
        if expect_title is not None:
            params["expectTitle"] = expect_title  # re-checked by the script in the same tick as the write
        result = self.write_parameter("da.param.set", params, int(obj["id"]), tag)
        after = result.get("after") or self.read_parameter(int(obj["id"]), tag)
        ok = after.get("process") is not None and abs(float(after["process"]) - process) <= tolerance
        return WriteOut(
            track_uid=f"uid:{item['uid']}",
            dry_run=False,
            target=f"{name} / {target}",
            changes=[self._change(before, process, after, ok)],
            verified=ok,
            note=None if ok else "the value read back differs from the request",
        )

    @operation
    def set_track_mix(
        self,
        track: str,
        *,
        volume: float | None = None,
        mute: bool | None = None,
        solo: bool | None = None,
        record_arm: bool | None = None,
        dry_run: bool = True,
    ) -> WriteOut:
        wanted: list[tuple[int, float]] = []
        if volume is not None:
            if not 0.0 <= volume <= 1.0:
                raise PreconditionFailedError("volume is a normalized value in [0, 1]", code="OUT_OF_RANGE")
            wanted.append((TAG_VOLUME, volume))
        wanted += [
            (tag, 1.0 if flag else 0.0)
            for tag, flag in ((TAG_MUTE, mute), (TAG_SOLO, solo), (TAG_RECORD, record_arm))
            if flag is not None
        ]
        if not wanted:
            raise PreconditionFailedError("give at least one of volume, mute, solo, record_arm", code="BAD_REQUEST")
        item = self.resolve_track(TrackSelector.parse(track))
        name = self.track_info(item).name
        oid = int(item["id"])
        befores = [(self.read_parameter(oid, tag), value) for tag, value in wanted]
        if dry_run:
            return WriteOut(
                track_uid=f"uid:{item['uid']}",
                dry_run=True,
                target=name,
                verified=None,
                changes=[self._change(b, v, None, None) for b, v in befores],
            )
        self.policy.check_track(name)
        changes: list[Change] = []
        for before, value in befores:
            tag = int(before["tag"])
            try:
                result = self.write_parameter(
                    "da.param.set", {"id": oid, "tag": tag, "value": value, **MIXER}, oid, tag
                )
            except TrackwrightError as exc:
                # Earlier changes did happen: say so, so that nobody assumes the track is untouched.
                exc.details["applied"] = [c.model_dump() for c in changes]
                raise
            after = result.get("after") or self.read_parameter(oid, tag)
            ok = after.get("process") is not None and abs(float(after["process"]) - value) <= 1e-3
            changes.append(self._change(before, value, after, ok))
        return WriteOut(
            track_uid=f"uid:{item['uid']}",
            dry_run=False,
            target=name,
            changes=changes,
            verified=all(c.verified for c in changes),
        )

    @operation
    def rename_track(self, track: str, new_name: str, *, dry_run: bool = True) -> WriteOut:
        new_name = new_name.strip()
        if not 1 <= len(new_name) <= 64:
            raise PreconditionFailedError("the new name must have 1 to 64 characters", code="BAD_REQUEST")
        item = self.resolve_track(TrackSelector.parse(track))
        current = self.track_info(item).name
        others = [self.track_info(c).name for c in self.channels() if c["id"] != item["id"]]
        if new_name in others:
            raise PreconditionFailedError(f"another track is already called {new_name!r}", code="NAME_CONFLICT")
        oid = int(item["id"])
        before = self.read_parameter(oid, TAG_NAME)
        if dry_run:
            return WriteOut(
                track_uid=f"uid:{item['uid']}",
                dry_run=True,
                target=current,
                verified=None,
                changes=[self._change(before, new_name, None, None)],
            )
        self.policy.check_track(current)
        result = self.write_parameter(
            "da.param.setDisplay", {"id": oid, "tag": TAG_NAME, "value": new_name, **MIXER}, oid, TAG_NAME
        )
        after = result.get("after") or self.read_parameter(oid, TAG_NAME)
        title = self.call("da.object", {"id": oid, **MIXER}).get("title")
        ok = after.get("display") == new_name and title == new_name
        return WriteOut(
            track_uid=f"uid:{item['uid']}",
            dry_run=False,
            target=current,
            changes=[self._change(before, new_name, after, ok)],
            verified=ok,
            note=f"use the selector 'uid:{item['uid']}': name selectors change with the name",
        )

    # ------------------------------------------------------------------ plugins
    @operation
    def insert_plugin(self, track: str, slot: int, plugin_uid: str, *, dry_run: bool = True) -> InsertPluginOut:
        item = self.resolve_track(TrackSelector.parse(track))
        name = self.track_info(item).name
        slot_obj = self.insert_slot(item, slot)
        if slot_obj.get("children"):
            raise PreconditionFailedError(f"insert slot {slot} is occupied", code="SLOT_OCCUPIED")
        entry = self._find_plugin(int(slot_obj["id"]), plugin_uid)
        plugin_name = str(entry["name"])
        if dry_run:
            return InsertPluginOut(
                track_uid=f"uid:{item['uid']}",
                dry_run=True,
                track=name,
                slot=slot,
                plugin_uid=plugin_uid,
                plugin_name=plugin_name,
                inserted=None,
                verified=None,
                plugin_ref=None,
            )
        self.policy.check_track(name)
        try:
            result = self.call("pm.set", {"slot": slot_obj["id"], "uid": plugin_uid, **MIXER})
        except RequestTimeoutError as exc:
            try:
                exc.details["read_back"] = self.call("da.object", {"id": slot_obj["id"], **MIXER})
            except TrackwrightError as read_error:
                exc.details["read_back_error"] = str(read_error)
            raise
        children = self.children(int(slot_obj["id"])) if result.get("result") else []
        plugin = children[0] if children else None
        ok = plugin is not None and self.plugin_uid(str(plugin.get("uniqueName"))) == plugin_uid
        return InsertPluginOut(
            track_uid=f"uid:{item['uid']}",
            dry_run=False,
            inserted=bool(result.get("result")),
            verified=ok,
            plugin_ref=self.ref_for(plugin) if plugin else None,
            track=name,
            slot=slot,
            plugin_uid=plugin_uid,
            plugin_name=plugin_name,
        )

    def _find_plugin(self, slot_id: int, plugin_uid: str) -> JsonObject:
        collections = self.call("pm.collections", {"slot": slot_id, **MIXER})
        index = int(collections.get("activeIndex", -1))
        offset = 0
        while index >= 0:
            page = self.call(
                "pm.entries", {"slot": slot_id, "collection": index, "offset": offset, "limit": 40, **MIXER}
            )
            for entry in page.get("items", []):
                if entry.get("uid") == plugin_uid:
                    return dict(entry)
            offset += len(page.get("items", []))
            if not page.get("items") or offset >= int(page.get("matched", 0)):
                break
        raise NotFoundError(f"plugin {plugin_uid} is not in the catalog of this slot", code="PLUGIN_NOT_FOUND")

    # ------------------------------------------------------------------ navigation
    def _selected_name(self) -> tuple[int, str | None]:
        base = int(self.call("da.base").get("base", -1))
        if base < 0:
            return base, None
        match = [c for c in self.channels() if c["id"] == base]
        return base, self.track_info(match[0]).name if match else None

    @operation
    def select_track(self, track: str | None = None, step: str | None = None) -> SelectOut:
        if (track is None) == (step is None):
            raise PreconditionFailedError("give exactly one of track or step", code="BAD_REQUEST")
        before_id, before_name = self._selected_name()

        def base() -> JsonObject:
            return self.call("da.base")

        if step is not None:
            if step not in ("next", "prev"):
                raise PreconditionFailedError("step must be 'next' or 'prev'", code="BAD_REQUEST")
            self.call("sel.step", {"direction": step})
            self.wait_until(base, lambda b: int(b.get("base", -1)) != before_id)
            after_id, after_name = self._selected_name()
            # C-14: at the first or last track the selection does not move, and that is not a success
            return SelectOut(
                selected_before=before_name, selected_after=after_name, verified=0 <= after_id != before_id
            )
        item = self.resolve_track(TrackSelector.parse(track))
        self.call("da.param.set", {"id": item["id"], "tag": TAG_SELECTED, "value": 1, **MIXER})
        self.wait_until(base, lambda b: b.get("base") == item["id"])
        after_id, after_name = self._selected_name()
        return SelectOut(selected_before=before_name, selected_after=after_name, verified=after_id == item["id"])

    @operation
    def set_position(self, which: str, time: str, *, unit: str = "bars", dry_run: bool = False) -> PositionOut:
        field = {"cursor": "locator", "cycle_left": "cycleLeft", "cycle_right": "cycleRight"}.get(which)
        if field is None:
            raise PreconditionFailedError("which must be cursor, cycle_left or cycle_right", code="BAD_REQUEST")
        seconds: float | None = None
        if unit == "bars":
            position = bars_tuple(time)
            if position is None:
                raise PreconditionFailedError("bars look like '3. 1. 1. 0' (bar. beat. 16th. tick)", code="BAD_TIME")
            text = format_bars(position)
        elif unit == "seconds":
            seconds = parse_seconds(time)
            if seconds is None:
                raise PreconditionFailedError("seconds look like '2.5', '1:30' or '0:01:30.000'", code="BAD_TIME")
            text = format_seconds(seconds)
        else:
            raise PreconditionFailedError("unit must be 'bars' or 'seconds'", code="BAD_REQUEST")
        transport = self.call("transport.get")
        before_raw = (transport.get("primary") or {}).get(field)
        before = TimePosition(time=before_raw["time"], format=before_raw.get("format")) if before_raw else None
        if dry_run:
            return PositionOut(dry_run=True, which=which, requested=text, before=before, after=None, verified=None)
        if which != "cursor":
            # The cycle locators are saved with the project (TW-1401); moving the cursor is navigation.
            self.policy.check_project_write()
        if seconds is not None:
            return self._set_position_seconds(which, field, text, seconds, before)
        self.call("transport.setTime", {"which": field, "display": "primary", "time": text})
        expected = bars_tuple(text)

        def read() -> JsonObject:
            raw = (self.call("transport.get").get("primary") or {}).get(field) or {}
            return dict(raw)

        after_raw = self.wait_until(read, lambda raw: bars_tuple(str(raw.get("time", ""))) == expected)
        after = TimePosition(time=str(after_raw.get("time", "")), format=after_raw.get("format"))
        return PositionOut(
            dry_run=False, which=which, requested=text, before=before, after=after,
            verified=bars_tuple(after.time) == expected,
        )  # fmt: skip

    def _set_position_seconds(
        self, which: str, field: str, text: str, seconds: float, before: TimePosition | None
    ) -> PositionOut:
        """Seconds, verified with the Transport's own seconds display (TW-1211): no tempo or meter assumed."""
        transport = self._transport_id()
        if which == "cursor":
            landed = self._move_cursor_seconds(transport, seconds)
            after = TimePosition(time=self._cursor_bars(), format="Compases+Tiempos")
            return PositionOut(dry_run=False, which=which, requested=text, before=before, after=after,
                               verified=abs(landed - seconds) <= SECONDS_TOLERANCE,
                               note=f"cursor at {format_seconds(landed)} (read back in seconds)")  # fmt: skip
        cursor = self._cursor_seconds(transport)
        try:
            locator = self._set_locator_seconds(transport, "left" if which == "cycle_left" else "right", seconds)
        finally:
            self._move_cursor_seconds(transport, cursor)  # the cursor was only a means: put it back
        expected = bars_tuple(locator)
        raw = (self.call("transport.get").get("primary") or {}).get(field) or {}
        after = TimePosition(time=str(raw.get("time", "")), format=raw.get("format"))
        return PositionOut(
            dry_run=False, which=which, requested=text, before=before, after=after,
            verified=expected is not None and bars_tuple(after.time) == expected,
            note="set at the cursor with Set Left/Right Locator (the seconds display cannot move the locators)",
        )  # fmt: skip

    @operation
    def set_tempo(self, bpm: float, *, dry_run: bool = True) -> TempoOut:
        if not 20 <= bpm <= 300:
            raise PreconditionFailedError("tempo must be within 20..300 BPM", code="OUT_OF_RANGE")
        before = self.call("transport.get").get("tempoBPM")
        if dry_run:
            return TempoOut(dry_run=True, before=before, requested=bpm, after=None, verified=None)
        self.policy.check_project_write()
        self.call("transport.setTempo", {"bpm": bpm})
        after = self.wait_until(
            lambda: self.call("transport.get"),
            lambda data: abs(float(data.get("tempoBPM") or 0) - bpm) < TEMPO_TOLERANCE,
        ).get("tempoBPM")
        ok = after is not None and abs(float(after) - bpm) < TEMPO_TOLERANCE
        return TempoOut(dry_run=False, before=before, requested=bpm, after=after, verified=ok)
