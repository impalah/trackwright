"""Tools built on Cubase commands (epic E07).

Commands give no result back. The tools therefore:
- check ``canPerform`` first (it depends on context);
- report the observed class of the command (``direct``, ``dialog``, ``confirm``, ``ui_selection``,
  ``unknown``) and never report a ``dialog`` command as done;
- verify the effect by reading state when it is observable, or say ``not_observable``.
"""

from __future__ import annotations

from typing import Literal

from trackwright.commands import COMMANDS, CommandSpec
from trackwright.core.base import JsonObject, ServiceBase, operation
from trackwright.core.models import CommandOut, CommandStatus
from trackwright.core.refs import TrackSelector
from trackwright.core.writing import bars_tuple, format_bars
from trackwright.errors import NotFoundError, PreconditionFailedError

TRACK_KINDS = {"audio": "addtrack.audio", "group": "addtrack.group", "folder": "addtrack.folder"}
MARKER_ACTIONS = {
    "add_marker_track": "addtrack.marker",
    "insert_at_cursor": "marker.insert",
    "locate_prev": "transport.locate_prev_marker",
    "locate_next": "transport.locate_next_marker",
}
NAVIGATION_COMMANDS = frozenset(
    {
        "transport.locate_prev_marker",
        "transport.locate_next_marker",
        "project.select_track_next",
        "project.select_track_prev",
    }
)


class CommandingMixin(ServiceBase):
    # ------------------------------------------------------------------ core
    def _spec(self, key: str) -> CommandSpec:
        spec = COMMANDS.get(key)
        if spec is None:
            raise NotFoundError(
                f"unknown command {key!r}", code="COMMAND_NOT_FOUND", details={"known": sorted(COMMANDS)}
            )
        return spec

    def _can_perform(self, key: str) -> bool | None:
        value = self.call("cmd.canPerform", {"key": key}).get("canPerform", {}).get(key)
        return value if isinstance(value, bool) else None

    def _out(
        self,
        spec: CommandSpec,
        *,
        dry_run: bool,
        can: bool | None,
        status: CommandStatus,
        verified: bool | Literal["not_observable"] | None,
        instructions: str | None = None,
        details: dict[str, str | int | float | bool | None] | None = None,
    ) -> CommandOut:
        return CommandOut(
            dry_run=dry_run,
            key=spec.key,
            category=spec.category,
            name=spec.name,
            command_class=spec.command_class,
            can_perform=can,
            status=status,
            verified=verified,
            instructions=instructions,
            details=details or {},
        )

    def _fire(self, spec: CommandSpec, *, force: bool = False) -> None:
        params: JsonObject = {"key": spec.key}
        if force:
            params["force"] = True
        self.call("cmd.run", params)

    def _status_for(self, spec: CommandSpec) -> tuple[CommandStatus, str | None]:
        if spec.command_class == "dialog":
            return "awaiting_user", f"Cubase opened a dialog for '{spec.name}': ask the user to complete or cancel it"
        if spec.command_class == "confirm":
            return "fired", "Cubase may ask the user to confirm"
        if spec.command_class == "ui_selection":
            return "fired", "acts on the selection in the Cubase window, which Trackwright cannot see: ask the user"
        return "fired", None

    @operation
    def run_command(self, key: str, *, dry_run: bool = True, force: bool = False) -> CommandOut:
        spec = self._spec(key)
        can = self._can_perform(key)
        if can is False and not force:
            raise PreconditionFailedError(
                f"Cubase reports that '{spec.name}' cannot be performed now", code="CANNOT_PERFORM"
            )
        if dry_run:
            return self._out(spec, dry_run=True, can=can, status="planned", verified=None)
        if key not in NAVIGATION_COMMANDS:
            self.policy.check_project_write()
        self._fire(spec, force=force)
        status, instructions = self._status_for(spec)
        return self._out(
            spec, dry_run=False, can=can, status=status, verified="not_observable", instructions=instructions
        )

    # ------------------------------------------------------------------ markers
    @operation
    def markers(self, action: str, *, dry_run: bool = True) -> CommandOut:
        key = MARKER_ACTIONS.get(action)
        if key is None:
            raise PreconditionFailedError(f"action must be one of {sorted(MARKER_ACTIONS)}", code="BAD_REQUEST")
        spec = self._spec(key)
        can = self._can_perform(key)
        if can is False:
            raise PreconditionFailedError(
                f"Cubase reports that '{spec.name}' cannot be performed now", code="CANNOT_PERFORM"
            )
        if dry_run:
            return self._out(spec, dry_run=True, can=can, status="planned", verified=None)
        if key not in NAVIGATION_COMMANDS:
            self.policy.check_project_write()
        before = self._cursor()
        self._fire(spec)
        if key in NAVIGATION_COMMANDS:
            after = self._cursor()
            return self._out(
                spec,
                dry_run=False,
                can=can,
                status="done",
                verified=after is not None,
                details={"cursor_before": before, "cursor_after": after},
            )
        return self._out(
            spec,
            dry_run=False,
            can=can,
            status="done",
            verified="not_observable",
            instructions="marker tracks are not visible through the API: check in Cubase",
            details={"cursor": before},
        )

    def _cursor(self) -> str | None:
        raw = (self.call("transport.get").get("primary") or {}).get("locator")
        return str(raw["time"]) if isinstance(raw, dict) else None

    # ------------------------------------------------------------------ removing tracks
    @operation
    def remove_selected_tracks(self, expect_selected: str, *, dry_run: bool = True) -> CommandOut:
        spec = self._spec("project.remove_selected_tracks")
        expected = self.resolve_track(TrackSelector.parse(expect_selected))
        base = int(self.call("da.base").get("base", -1))
        # "Remove Selected Tracks" removes *every* selected track: require exactly one, the expected one.
        selected = [self.track_info(c).name for c in self.channels() if self.track_info(c).selected]
        if base != expected["id"] or selected != [self.track_info(expected).name]:
            raise PreconditionFailedError(
                "the selection must be exactly the expected track; select it alone first (cubase_select_track)",
                code="SELECTION_MISMATCH",
                details={"expected": self.track_info(expected).name, "selected": selected},
            )
        name = self.track_info(expected).name
        can = self._can_perform(spec.key)
        if dry_run:
            return self._out(spec, dry_run=True, can=can, status="planned", verified=None, details={"track": name})
        self.policy.check_track(name)
        self._fire(spec)
        listing = self.wait_until(
            lambda: {"ids": [c["id"] for c in self.channels()]}, lambda d: expected["id"] not in d["ids"]
        )
        if expected["id"] in listing["ids"]:
            return self._out(
                spec,
                dry_run=False,
                can=can,
                status="pending_confirmation",
                verified=False,
                instructions="Cubase is asking for confirmation (the track has events): ask the user",
                details={"track": name},
            )
        return self._out(spec, dry_run=False, can=can, status="done", verified=True, details={"track": name})

    # ------------------------------------------------------------------ split at locators
    @operation
    def split_at_locators(self, left: str, right: str, *, dry_run: bool = True) -> CommandOut:
        spec = self._spec("edit.split_loop")
        left_pos, right_pos = bars_tuple(left), bars_tuple(right)
        if left_pos is None or right_pos is None:
            raise PreconditionFailedError("locators look like '2. 1. 1. 0'", code="BAD_TIME")
        if left_pos >= right_pos:
            raise PreconditionFailedError("the left locator must be before the right one", code="BAD_TIME")
        previous = dict(self.call("transport.get").get("primary") or {})
        details: dict[str, str | int | float | bool | None] = {
            "left": format_bars(left_pos),
            "right": format_bars(right_pos),
            # The locators are left at the split points: restoring them right away could race with the
            # command, which Cubase runs in its own idle tick. Report them so they can be restored.
            "previous_left": (previous.get("cycleLeft") or {}).get("time"),
            "previous_right": (previous.get("cycleRight") or {}).get("time"),
            "warning": "splits every track with events crossing the locators; the locators stay at the split points",
        }
        if dry_run:
            return self._out(
                spec, dry_run=True, can=self._can_perform(spec.key), status="planned", verified=None, details=details
            )
        self.policy.check_project_write()
        for which, text in (("cycleLeft", format_bars(left_pos)), ("cycleRight", format_bars(right_pos))):
            self.call("transport.setTime", {"which": which, "display": "primary", "time": text})
        locators = self.wait_until(
            lambda: dict(self.call("transport.get").get("primary") or {}),
            lambda p: (
                bars_tuple(str((p.get("cycleLeft") or {}).get("time", ""))) == left_pos
                and bars_tuple(str((p.get("cycleRight") or {}).get("time", ""))) == right_pos
            ),
        )
        if (
            bars_tuple(str((locators.get("cycleLeft") or {}).get("time", ""))) != left_pos
            or bars_tuple(str((locators.get("cycleRight") or {}).get("time", ""))) != right_pos
        ):
            raise PreconditionFailedError("the locators could not be set; nothing was split", code="VERIFY_FAILED")
        can = self._can_perform(spec.key)
        if can is False:
            raise PreconditionFailedError(
                "Cubase reports that 'Split Loop' cannot be performed now", code="CANNOT_PERFORM"
            )
        self._fire(spec)
        return self._out(
            spec,
            dry_run=False,
            can=can,
            status="done",
            verified="not_observable",
            instructions="events are not visible through the API: check the result in Cubase",
            details=details,
        )

    # ------------------------------------------------------------------ add a track with the user's help
    @operation
    def add_track_interactive(self, phase: Literal["start", "confirm"], kind: str, suggested_name: str) -> CommandOut:
        key = TRACK_KINDS.get(kind)
        if key is None:
            raise PreconditionFailedError(f"kind must be one of {sorted(TRACK_KINDS)}", code="BAD_REQUEST")
        spec = self._spec(key)
        if phase == "start":
            self.policy.check_project_write()
            if any(self.track_info(c).name == suggested_name for c in self.channels()):
                # Otherwise 'confirm' could report an old track as the new one.
                raise PreconditionFailedError(
                    f"a track called {suggested_name!r} already exists; suggest another name", code="NAME_CONFLICT"
                )
            can = self._can_perform(key)
            if can is False:
                raise PreconditionFailedError(
                    f"Cubase reports that '{spec.name}' cannot be performed now", code="CANNOT_PERFORM"
                )
            self._fire(spec)
            return self._out(
                spec,
                dry_run=False,
                can=can,
                status="awaiting_user",
                verified=None,
                instructions=f"In Cubase's Add Track dialog, name the track '{suggested_name}' and accept it "
                f"(or cancel). Then call this tool again with phase='confirm'.",
                details={"suggested_name": suggested_name},
            )
        if phase != "confirm":
            raise PreconditionFailedError("phase must be 'start' or 'confirm'", code="BAD_REQUEST")
        if kind == "folder":
            return self._out(
                spec,
                dry_run=False,
                can=None,
                status="done",
                verified="not_observable",
                instructions="folder tracks have no mixer channel: confirm visually in Cubase",
                details={"suggested_name": suggested_name},
            )
        found = [c for c in self.channels() if self.track_info(c).name == suggested_name]
        if not found:
            return self._out(
                spec,
                dry_run=False,
                can=None,
                status="not_found",
                verified=False,
                instructions="no new track with that name: the dialog may have been cancelled or the name changed",
                details={"suggested_name": suggested_name},
            )
        return self._out(
            spec,
            dry_run=False,
            can=None,
            status="done",
            verified=True,
            details={"suggested_name": suggested_name, "track": f"uid:{found[0]['uid']}"},
        )
