"""Automation tools (TW-1207).

Mechanism verified in Cubase Elements 15.0.30 (experiments TW-1206 B2 and TW-1207 B3): the script has
surface faders bound to parameters of the *selected* track. Moving a *touched* control while the
track's automation write (W) is on and the transport plays records automation in Touch mode, the way a
hardware controller does. Writing the parameter through DirectAccess does **not** record (variant A).

Positions are bar strings ("9. 1. 1. 0"). They are converted to quarter notes with the project's time
signature at the cursor (TW-1209; constant signature assumed) and 120 ticks per 16th; the cursor position
reported by Cubase during playback drives the timing.
"""

from __future__ import annotations

import itertools
import re
import time
from collections.abc import Iterator

from trackwright.core.base import MIXER, converted_value, operation
from trackwright.core.models import (
    AutomationPoint,
    AutomationRecordOut,
    AutomationTarget,
    AutomationTargetsOut,
    ConvertOut,
    ResolvedPoint,
    WrittenPoint,
)
from trackwright.core.project import ProjectMixin
from trackwright.core.refs import TrackSelector
from trackwright.core.tags import Channel, Panner, Send
from trackwright.core.timefmt import bars_tuple, format_bars
from trackwright.errors import NotFoundError, PreconditionFailedError, TrackwrightError, UnavailableError
from trackwright.jsontypes import JsonObject

CONTROLS_TIMEOUT = 3.0  # seconds to wait for the controls to follow a selection (TW-1616)
MAX_POINTS = 64
VERIFY_TOLERANCE = 0.05
TICKS_PER_BEAT = 480
PREFILTER_TITLES = {"gain": "PreGain", "lowcut": "LC-Freq", "highcut": "HC-Freq"}
EQ_TITLES = {"gain": "Gain", "freq": "Freq", "q": "Q"}
SEND_KEY = re.compile(r"^send([1-4])\.level$")  # the script binds sends 1-4
EQ_KEY = re.compile(r"^eq([1-4])\.(gain|freq|q)$")
PREFILTER_KEY = re.compile(r"^prefilter\.(gain|lowcut|highcut)$")
INSERT_KEY = re.compile(r"^insert([12])\.p[1-8]$")  # the script binds slots 1-2 (TW-1413, C-19)
STALL_SECONDS = 2.0


Meter = tuple[int, int]
COMMON_TIME: Meter = (4, 4)


def to_beats(position: tuple[int, int, int, int], meter: Meter = COMMON_TIME) -> float:
    """Bars/beats/16ths/ticks to quarter notes from the project start, for a constant time signature."""
    bar, beat, sixteenth, ticks = position
    numerator, denominator = meter
    beat_length = 4 / denominator
    return (bar - 1) * numerator * beat_length + (beat - 1) * beat_length + (sixteenth - 1) / 4 + ticks / TICKS_PER_BEAT


def from_beats(beats: float, meter: Meter = COMMON_TIME) -> tuple[int, int, int, int]:
    numerator, denominator = meter
    beat_length = 4 / denominator
    bar, rest = divmod(max(beats, 0.0), numerator * beat_length)
    beat, rest = divmod(rest, beat_length)
    sixteenth, rest = divmod(rest, 0.25)
    return int(bar) + 1, int(beat) + 1, int(sixteenth) + 1, round(rest * TICKS_PER_BEAT)


def interpolate(points: list[tuple[float, float]], beat: float) -> float:
    """Piecewise-linear value of the curve at ``beat`` (held before the first and after the last point)."""
    if beat <= points[0][0]:
        return points[0][1]
    for (b0, v0), (b1, v1) in itertools.pairwise(points):
        if beat <= b1:
            return v0 + (v1 - v0) * (beat - b0) / (b1 - b0)
    return points[-1][1]


class AutomationMixin(ProjectMixin):
    # ------------------------------------------------------------------ helpers
    def _auto_controls(self) -> dict[str, JsonObject]:
        listed = self.call("auto.list")
        if not listed.get("enabled"):
            raise TrackwrightError(
                "the installed Cubase script has no automation controls; install script 1.4.0 or later",
                code="UNSUPPORTED",
            )
        return {str(c["key"]): c for c in listed.get("controls", [])}

    def _cursor_beats(self, meter: Meter = COMMON_TIME) -> float:
        raw = (self.call("transport.get").get("primary") or {}).get("locator") or {}
        position = bars_tuple(str(raw.get("time", "")))
        if position is None:
            raise UnavailableError("the cursor position is not available")
        return to_beats(position, meter)

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
            converts_units=bound and not key.startswith("qc"),
        )

    def _flag(self, item: JsonObject, tag: int, on: bool) -> None:
        self.call("da.param.set", {"id": item["id"], "tag": tag, "value": 1.0 if on else 0.0, "scope": "mixer"})

    def _flag_state(self, item: JsonObject, tag: int) -> bool:
        return float(self.read_parameter(int(item["id"]), tag).get("process") or 0) >= 0.5

    # ------------------------------------------------------------------ time signature (TW-1209)
    def _read_meter(self) -> tuple[Meter, str]:
        signature = self.current_signature()
        if signature is None or signature.numerator is None or signature.denominator is None:
            return COMMON_TIME, "time signature unknown: positions assume 4/4"
        meter = (signature.numerator, signature.denominator)
        return meter, f"positions use the time signature at the cursor ({signature.text}); changes are not followed"

    # ------------------------------------------------------------------ unit conversion (TW-1208)
    def _child_of_type(self, item: JsonObject, kind: str) -> JsonObject:
        for child in self.children(int(item["id"])):
            if child.get("type") == kind:
                return child
        raise NotFoundError(f"the track has no {kind}", code="NO_UNIT_CONVERSION")

    def _tag_by_title(self, obj: JsonObject, title: str) -> int:
        for param in self.paged("da.params", {"id": obj["id"]}, 25):
            if param.get("title") == title:
                return int(param["tag"])
        raise NotFoundError(f"parameter {title!r} not found on {obj.get('title')}", code="NO_UNIT_CONVERSION")

    def _da_parameter(self, item: JsonObject, key: str, control: JsonObject) -> tuple[JsonObject, int]:
        """The DirectAccess object and tag behind an automation control (for exact unit conversion)."""
        if key == "volume":
            return item, Channel.VOLUME
        if key == "pan":
            return self._child_of_type(item, "Panner"), Panner.PAN
        if match := SEND_KEY.match(key):
            sends = self.children(int(self.section(item, "Sends")["id"]))
            index = int(match.group(1))
            if not 1 <= index <= len(sends):
                raise NotFoundError(f"send {index} does not exist (1..{len(sends)})", code="PARAM_NOT_FOUND")
            return sends[index - 1], Send.LEVEL
        if match := EQ_KEY.match(key):
            eq = self.resolve_target(item, "strip:eq")
            return eq, self._tag_by_title(eq, f"EQ {match.group(1)} {EQ_TITLES[match.group(2)]}")
        if match := PREFILTER_KEY.match(key):
            input_filter = self._child_of_type(item, "InputFilter")
            return input_filter, self._tag_by_title(input_filter, PREFILTER_TITLES[match.group(1)])
        if match := INSERT_KEY.match(key):
            plugin = self.resolve_target(item, f"insert:{match.group(1)}")
            title = str(control.get("title") or "").split(" / ", 1)[-1]
            return plugin, self._tag_by_title(plugin, title)
        raise PreconditionFailedError(
            f"{key} has no known Cubase parameter for unit conversion: use normalized values",
            code="NO_UNIT_CONVERSION",
        )

    def _to_value(self, target: tuple[JsonObject, int], plain: float) -> float:
        obj, tag = target
        value = converted_value(self.call("da.convert", {"id": obj["id"], "tag": tag, "plain": plain, **MIXER}))
        if not 0.0 <= value <= 1.0:
            raise PreconditionFailedError(
                f"{plain} is outside the parameter's range", code="OUT_OF_RANGE", details={"normalized": value}
            )
        return value

    def _to_plain(self, target: tuple[JsonObject, int], value: float) -> float:
        obj, tag = target
        return float(
            self.call("da.convert", {"id": obj["id"], "tag": tag, "process": value, **MIXER})["plainFromProcess"]
        )

    def _controls_of(self, item: JsonObject) -> dict[str, JsonObject]:
        """Select ``item`` and wait until the automation controls are bound to it (TW-1616).

        Cubase binds the controls to a new selection a moment later: read right away, they still belonged to the
        previous track (seen live: a volume titled "POC-TEST ducked" for POC-TEST, an insert of Stereo Out).
        The volume control's title starts with the channel's name once they follow it; if that does not happen
        in time, nothing is read or written on the wrong track."""
        self.select_channel(int(item["id"]))
        prefix = f"{self.track_info(item).name} / "

        def bound(controls: dict[str, JsonObject]) -> bool:
            return str((controls.get("volume") or {}).get("title") or "").startswith(prefix)

        controls = self._auto_controls()
        deadline = time.monotonic() + max(self._settle_timeout, CONTROLS_TIMEOUT)
        while not bound(controls) and time.monotonic() < deadline:
            self._sleep(0.1)
            controls = self._auto_controls()
        if not bound(controls):
            title = (controls.get("volume") or {}).get("title")
            raise PreconditionFailedError(
                f"the automation controls did not follow the selection of {self.track_info(item).name!r} "
                f"(they still show {title!r}): try again",
                code="CONTROLS_NOT_BOUND",
                details={"volume_title": title},
            )
        return controls

    def _bound_control(self, item: JsonObject, parameter: str) -> tuple[JsonObject, AutomationTarget]:
        controls = self._controls_of(item)
        if parameter not in controls:
            raise NotFoundError(f"unknown automation parameter {parameter!r}", code="PARAM_NOT_FOUND",
                                details={"known": sorted(controls)})  # fmt: skip
        target = self._target(parameter, controls[parameter])
        if not target.available:
            raise PreconditionFailedError(
                f"{parameter} is not bound to any parameter on this track (empty slot or unassigned control)",
                code="NOT_AUTOMATABLE",
            )
        return controls[parameter], target

    # ------------------------------------------------------------------ tools
    @operation
    def list_automation_targets(self, track: str) -> AutomationTargetsOut:
        """Parameters of ``track`` that can be automated. Selects the track (the controls follow the selection)."""
        item = self.resolve_track(TrackSelector.parse(track))
        controls = self._controls_of(item)
        targets = [self._target(key, c) for key, c in controls.items()]
        return AutomationTargetsOut(track=self.track_info(item).name, targets=targets)

    @operation
    def convert_value(
        self, track: str, parameter: str, *, plain: float | None = None, value: float | None = None
    ) -> ConvertOut:
        """Exact conversion between real units and normalized values, done by Cubase. Selects the track."""
        if (plain is None) == (value is None):
            raise PreconditionFailedError("give exactly one of plain or value", code="BAD_REQUEST")
        item = self.resolve_track(TrackSelector.parse(track))
        control, target = self._bound_control(item, parameter)
        da = self._da_parameter(item, parameter, control)
        if plain is not None:
            normalized = self._to_value(da, plain)
            return ConvertOut(track=self.track_info(item).name, parameter=parameter, title=target.title,
                              plain=plain, value=normalized)  # fmt: skip
        assert value is not None
        if not 0.0 <= value <= 1.0:
            raise PreconditionFailedError("value must be within [0, 1]", code="OUT_OF_RANGE")
        return ConvertOut(track=self.track_info(item).name, parameter=parameter, title=target.title,
                          plain=self._to_plain(da, value), value=value)  # fmt: skip

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
        if not 1 <= len(points) <= MAX_POINTS:
            raise PreconditionFailedError(f"give 1 to {MAX_POINTS} points", code="BAD_REQUEST")
        item = self.resolve_track(TrackSelector.parse(track))
        name = self.track_info(item).name
        control, target = self._bound_control(item, parameter)
        resolved = self._resolve_points(item, parameter, control, points)
        meter, signature_note = self._read_meter()  # C-26: passed explicitly, no thread-local state
        curve = self._validate_points(resolved, meter)
        numerator, denominator = meter
        start_beats = max(curve[0][0] - numerator * 4 / denominator * pre_roll_bars, 0.0)
        out = AutomationRecordOut(
            dry_run=dry_run,
            track=name,
            parameter=parameter,
            title=target.title,
            value_before=target.value,
            display_before=target.display,
            start=format_bars(from_beats(start_beats, meter)),
            points=resolved,
            written=[],
            verified=None,
            notes=[signature_note, "playback is audible: lower the monitor level"],
        )
        if dry_run:
            return out
        self.policy.check_track(name)
        if self._is_playing():
            raise PreconditionFailedError("stop the transport before recording automation", code="TRANSPORT_RUNNING")
        out.written, out.complete = self._record(item, parameter, curve, start_beats, meter)
        if not out.complete:
            out.notes.append(
                f"playback stopped at {out.written[-1].position}, before the last point: the curve is incomplete"
            )
        if verify:
            out.verified, out.mismatches = self._verify(item, parameter, curve, start_beats, meter)
            if out.verified is False:
                out.notes.append("the read-back did not follow the curve: check the automation lane in Cubase")
        out.notes.append("with read automation (R) on, the recorded curve controls the parameter")
        return out

    # ------------------------------------------------------------------ internals
    def _resolve_points(
        self, item: JsonObject, parameter: str, control: JsonObject, points: list[AutomationPoint]
    ) -> list[ResolvedPoint]:
        """Convert ``plain`` points with Cubase; keep normalized ones as given."""
        da: tuple[JsonObject, int] | None = None
        resolved = []
        for point in points:
            if point.plain is None:
                assert point.value is not None
                resolved.append(ResolvedPoint(position=point.position, value=point.value, plain=None))
                continue
            da = da or self._da_parameter(item, parameter, control)
            resolved.append(ResolvedPoint(position=point.position, value=self._to_value(da, point.plain),
                                          plain=point.plain))  # fmt: skip
        return resolved

    @staticmethod
    def _validate_points(points: list[ResolvedPoint], meter: Meter) -> list[tuple[float, float]]:
        curve: list[tuple[float, float]] = []
        for point in points:
            position = bars_tuple(point.position)
            if position is None:
                raise PreconditionFailedError(f"bad position {point.position!r}: use '9. 1. 1. 0'", code="BAD_TIME")
            beats = to_beats(position, meter)
            if curve and beats <= curve[-1][0]:
                raise PreconditionFailedError("positions must be strictly increasing", code="BAD_TIME")
            curve.append((beats, point.value))
        if len(curve) == 1:  # a single point is held for one beat
            curve.append((curve[0][0] + 1, curve[0][1]))
        return curve

    def _play_from(self, start_beats: float, meter: Meter) -> None:
        self.call(
            "transport.setTime",
            {"which": "locator", "display": "primary", "time": format_bars(from_beats(start_beats, meter))},
        )
        self.call("cmd.run", {"key": "transport.start"})

    def _stop(self) -> None:
        self.call("cmd.run", {"key": "transport.stop"})

    @staticmethod
    def _deadline(start_beats: float, end_beats: float) -> float:
        """Upper bound for a pass: 2 s per beat (below 30 BPM) plus 10 s to start."""
        return time.monotonic() + 10.0 + max(end_beats - start_beats, 1.0) * 2.0

    def _positions(self, start: float, end: float, meter: Meter) -> Iterator[float]:
        """Yield cursor positions (beats) while the transport advances; stop if it stalls for STALL_SECONDS."""
        deadline = self._deadline(start, end)
        previous: float | None = None
        last_progress = time.monotonic()
        while time.monotonic() < deadline:
            beat = self._cursor_beats(meter)
            now = time.monotonic()
            if beat != previous:
                last_progress = now
            elif now - last_progress > STALL_SECONDS:
                return  # transport stopped (e.g. the user pressed Stop) or never started
            previous = beat
            yield beat

    def _record(
        self, item: JsonObject, key: str, curve: list[tuple[float, float]], start: float, meter: Meter
    ) -> tuple[list[WrittenPoint], bool]:
        """Write the curve while playing; return the points written and whether the last point was reached."""
        write_before = self._flag_state(item, Channel.WRITE_AUTOMATION)
        read_before = self._flag_state(item, Channel.READ_AUTOMATION)
        written: list[WrittenPoint] = []
        touched = complete = False
        try:
            self._flag(item, Channel.READ_AUTOMATION, False)  # existing automation must not fight the new curve
            self._flag(item, Channel.WRITE_AUTOMATION, True)
            self._play_from(start, meter)
            for beat in self._positions(start, curve[-1][0], meter):
                if beat < curve[0][0]:
                    self._sleep(0.02)
                    continue
                value = interpolate(curve, beat)
                result = self.call("auto.control", {"key": key, "value": value, **({} if touched else {"touch": True})})
                touched = True
                written.append(WrittenPoint(position=format_bars(from_beats(beat, meter)), value=value,
                                            display=result.get("display")))  # fmt: skip
                if beat >= curve[-1][0]:
                    complete = True
                    break
        finally:
            if touched:
                self.call("auto.control", {"key": key, "touch": False})
            self._stop()
            self._flag(item, Channel.WRITE_AUTOMATION, write_before)
            self._flag(item, Channel.READ_AUTOMATION, read_before)
        if not written:
            raise TrackwrightError("playback did not reach the first point; nothing was recorded", code="NOT_RECORDED")
        return written, complete

    def _verify(
        self, item: JsonObject, key: str, curve: list[tuple[float, float]], start: float, meter: Meter
    ) -> tuple[bool, list[str]]:
        read_before = self._flag_state(item, Channel.READ_AUTOMATION)
        mismatches: list[str] = []
        checked = 0
        try:
            self._flag(item, Channel.READ_AUTOMATION, True)
            self._play_from(start, meter)
            pending = list(curve)
            for beat in self._positions(start, curve[-1][0], meter):
                if not pending:
                    break
                if beat + 1e-9 < pending[0][0]:
                    self._sleep(0.02)
                    continue
                expected = interpolate(curve, beat)
                value = self._auto_controls()[key].get("value")
                checked += 1
                if not isinstance(value, int | float) or abs(value - expected) > VERIFY_TOLERANCE:
                    mismatches.append(f"{format_bars(from_beats(beat, meter))}: expected {expected:.3f}, read {value}")
                while pending and pending[0][0] <= beat + 1e-9:
                    pending.pop(0)
        finally:
            self._stop()
            self._flag(item, Channel.READ_AUTOMATION, read_before)
        return checked > 0 and not mismatches, mismatches
