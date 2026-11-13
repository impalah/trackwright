"""Automation tools (TW-1207).

Mechanism verified in Cubase Elements 15.0.30 (experiments TW-1206 B2 and TW-1207 B3): the script has
surface faders bound to parameters of the *selected* track. Moving a *touched* control while the
track's automation write (W) is on and the transport plays records automation in Touch mode, the way a
hardware controller does. Writing the parameter through DirectAccess does **not** record (variant A).

Positions are bar strings ("9. 1. 1. 0"). They are converted to beats assuming 4/4 and 480 ticks per
beat; the cursor position reported by Cubase during playback drives the timing.
"""

from __future__ import annotations

import itertools
import time
from collections.abc import Iterator
from typing import Any

from trackwright.core.base import TAG_SELECTED, ServiceBase, operation
from trackwright.core.models import (
    AutomationPoint,
    AutomationRecordOut,
    AutomationTarget,
    AutomationTargetsOut,
    WrittenPoint,
)
from trackwright.core.refs import TrackSelector
from trackwright.core.writing import bars_tuple, format_bars
from trackwright.errors import NotFoundError, PreconditionFailedError, TrackwrightError

TAG_WRITE, TAG_READ = 4013, 4014
MAX_POINTS = 64
VERIFY_TOLERANCE = 0.05
TICKS_PER_BEAT = 480
STALL_SECONDS = 2.0
JsonObject = dict[str, Any]


def to_beats(position: tuple[int, int, int, int]) -> float:
    """Bars/beats/16ths/ticks to beats from the project start (4/4 assumed)."""
    bar, beat, sixteenth, ticks = position
    return (bar - 1) * 4 + (beat - 1) + (sixteenth - 1) / 4 + ticks / TICKS_PER_BEAT


def from_beats(beats: float) -> tuple[int, int, int, int]:
    beats = max(beats, 0.0)
    bar, rest = divmod(beats, 4)
    beat, rest = divmod(rest, 1)
    sixteenth, rest = divmod(rest * 4, 1)
    return int(bar) + 1, int(beat) + 1, int(sixteenth) + 1, round(rest * TICKS_PER_BEAT / 4)


def interpolate(points: list[tuple[float, float]], beat: float) -> float:
    """Piecewise-linear value of the curve at ``beat`` (held before the first and after the last point)."""
    if beat <= points[0][0]:
        return points[0][1]
    for (b0, v0), (b1, v1) in itertools.pairwise(points):
        if beat <= b1:
            return v0 + (v1 - v0) * (beat - b0) / (b1 - b0)
    return points[-1][1]


class AutomationMixin(ServiceBase):
    # ------------------------------------------------------------------ helpers
    def _auto_controls(self) -> dict[str, JsonObject]:
        listed = self.call("auto.list")
        if not listed.get("enabled"):
            raise TrackwrightError(
                "the installed Cubase script has no automation controls; install script 1.4.0 or later",
                code="UNSUPPORTED",
            )
        return {str(c["key"]): c for c in listed.get("controls", [])}

    def _select(self, item: JsonObject) -> None:
        self.call("da.param.set", {"id": item["id"], "tag": TAG_SELECTED, "value": 1, "scope": "mixer"})
        self.wait_until(lambda: self.call("da.base"), lambda b: b.get("base") == item["id"])

    def _cursor_beats(self) -> float:
        raw = (self.call("transport.get").get("primary") or {}).get("locator") or {}
        position = bars_tuple(str(raw.get("time", "")))
        if position is None:
            raise TrackwrightError("the cursor position is not available", code="UNAVAILABLE")
        return to_beats(position)

    def _is_playing(self) -> bool:
        first = self._cursor_beats()
        self._sleep(0.3)
        return self._cursor_beats() != first

    @staticmethod
    def _target(key: str, control: JsonObject) -> AutomationTarget:
        title = str(control.get("title") or "").strip()
        bound = bool(title.strip(" /"))
        value = control.get("value")
        return AutomationTarget(
            parameter=key,
            title=title if bound else None,
            value=value if isinstance(value, int | float) else None,
            display=control.get("display") or None,
            available=bound,
        )

    def _flag(self, item: JsonObject, tag: int, on: bool) -> None:
        self.call("da.param.set", {"id": item["id"], "tag": tag, "value": 1.0 if on else 0.0, "scope": "mixer"})

    def _flag_state(self, item: JsonObject, tag: int) -> bool:
        return float(self.read_parameter(int(item["id"]), tag).get("process") or 0) >= 0.5

    # ------------------------------------------------------------------ tools
    @operation
    def list_automation_targets(self, track: str) -> AutomationTargetsOut:
        """Parameters of ``track`` that can be automated. Selects the track (the controls follow the selection)."""
        item = self.resolve_track(TrackSelector.parse(track))
        self._select(item)
        controls = self._auto_controls()
        targets = [self._target(key, c) for key, c in controls.items()]
        return AutomationTargetsOut(track=self.track_info(item).name, targets=targets)

    @operation
    def record_automation(
        self,
        track: str,
        parameter: str,
        points: list[AutomationPoint],
        *,
        dry_run: bool = True,
        verify: bool = True,
        pre_roll_bars: int = 1,
    ) -> AutomationRecordOut:
        curve = self._validate_points(points)
        item = self.resolve_track(TrackSelector.parse(track))
        name = self.track_info(item).name
        self._select(item)
        controls = self._auto_controls()
        if parameter not in controls:
            raise NotFoundError(f"unknown automation parameter {parameter!r}", code="PARAM_NOT_FOUND",
                                details={"known": sorted(controls)})  # fmt: skip
        target = self._target(parameter, controls[parameter])
        if not target.available:
            raise PreconditionFailedError(
                f"{parameter} is not bound to any parameter on this track (empty slot or unassigned control)",
                code="NOT_AUTOMATABLE",
            )
        start_beats = max(curve[0][0] - 4 * pre_roll_bars, 0.0)
        out = AutomationRecordOut(
            dry_run=dry_run,
            track=name,
            parameter=parameter,
            title=target.title,
            value_before=target.value,
            display_before=target.display,
            start=format_bars(from_beats(start_beats)),
            points=points,
            written=[],
            verified=None,
            notes=["positions assume 4/4", "playback is audible: lower the monitor level"],
        )
        if dry_run:
            return out
        self.policy.check_track(name)
        if self._is_playing():
            raise PreconditionFailedError("stop the transport before recording automation", code="TRANSPORT_RUNNING")
        out.written = self._record(item, parameter, curve, start_beats)
        if verify:
            out.verified, out.mismatches = self._verify(item, parameter, curve, start_beats)
            if out.verified is False:
                out.notes.append("the read-back did not follow the curve: check the automation lane in Cubase")
        out.notes.append("with read automation (R) on, the recorded curve controls the parameter")
        return out

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _validate_points(points: list[AutomationPoint]) -> list[tuple[float, float]]:
        if not 1 <= len(points) <= MAX_POINTS:
            raise PreconditionFailedError(f"give 1 to {MAX_POINTS} points", code="BAD_REQUEST")
        curve: list[tuple[float, float]] = []
        for point in points:
            position = bars_tuple(point.position)
            if position is None:
                raise PreconditionFailedError(f"bad position {point.position!r}: use '9. 1. 1. 0'", code="BAD_TIME")
            beats = to_beats(position)
            if curve and beats <= curve[-1][0]:
                raise PreconditionFailedError("positions must be strictly increasing", code="BAD_TIME")
            curve.append((beats, point.value))
        if len(curve) == 1:  # a single point is held for one beat
            curve.append((curve[0][0] + 1, curve[0][1]))
        return curve

    def _play_from(self, start_beats: float) -> None:
        self.call(
            "transport.setTime",
            {"which": "locator", "display": "primary", "time": format_bars(from_beats(start_beats))},
        )
        self.call("cmd.run", {"key": "transport.start"})

    def _stop(self) -> None:
        self.call("cmd.run", {"key": "transport.stop"})

    @staticmethod
    def _deadline(start_beats: float, end_beats: float) -> float:
        """Upper bound for a pass: 2 s per beat (below 30 BPM) plus 10 s to start."""
        return time.monotonic() + 10.0 + max(end_beats - start_beats, 1.0) * 2.0

    def _positions(self, start: float, end: float) -> Iterator[float]:
        """Yield cursor positions (beats) while the transport advances; stop if it stalls for STALL_SECONDS."""
        deadline = self._deadline(start, end)
        previous: float | None = None
        last_progress = time.monotonic()
        while time.monotonic() < deadline:
            beat = self._cursor_beats()
            now = time.monotonic()
            if beat != previous:
                last_progress = now
            elif now - last_progress > STALL_SECONDS:
                return  # transport stopped (e.g. the user pressed Stop) or never started
            previous = beat
            yield beat

    def _record(self, item: JsonObject, key: str, curve: list[tuple[float, float]], start: float) -> list[WrittenPoint]:
        write_before = self._flag_state(item, TAG_WRITE)
        read_before = self._flag_state(item, TAG_READ)
        written: list[WrittenPoint] = []
        touched = False
        try:
            self._flag(item, TAG_READ, False)  # existing automation must not fight the new curve
            self._flag(item, TAG_WRITE, True)
            self._play_from(start)
            for beat in self._positions(start, curve[-1][0]):
                if beat < curve[0][0]:
                    self._sleep(0.02)
                    continue
                value = interpolate(curve, beat)
                result = self.call("auto.control", {"key": key, "value": value, **({} if touched else {"touch": True})})
                touched = True
                written.append(WrittenPoint(position=format_bars(from_beats(beat)), value=value,
                                            display=result.get("display")))  # fmt: skip
                if beat >= curve[-1][0]:
                    break
        finally:
            if touched:
                self.call("auto.control", {"key": key, "touch": False})
            self._stop()
            self._flag(item, TAG_WRITE, write_before)
            self._flag(item, TAG_READ, read_before)
        if not written:
            raise TrackwrightError("playback did not reach the first point; nothing was recorded", code="NOT_RECORDED")
        return written

    def _verify(
        self, item: JsonObject, key: str, curve: list[tuple[float, float]], start: float
    ) -> tuple[bool, list[str]]:
        read_before = self._flag_state(item, TAG_READ)
        mismatches: list[str] = []
        checked = 0
        try:
            self._flag(item, TAG_READ, True)
            self._play_from(start)
            pending = list(curve)
            for beat in self._positions(start, curve[-1][0]):
                if not pending:
                    break
                if beat + 1e-9 < pending[0][0]:
                    self._sleep(0.02)
                    continue
                expected = interpolate(curve, beat)
                value = self._auto_controls()[key].get("value")
                checked += 1
                if not isinstance(value, int | float) or abs(value - expected) > VERIFY_TOLERANCE:
                    mismatches.append(f"{format_bars(from_beats(beat))}: expected {expected:.3f}, read {value}")
                while pending and pending[0][0] <= beat + 1e-9:
                    pending.pop(0)
        finally:
            self._stop()
            self._flag(item, TAG_READ, read_before)
        return checked > 0 and not mismatches, mismatches
