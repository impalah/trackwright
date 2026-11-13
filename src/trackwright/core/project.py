"""Project properties (TW-1209), read from Cubase's own DirectAccess objects.

Verified in Cubase Elements 15.0.30 (experiments/tw1209): besides the mixer, DirectAccess reaches the studio
objects under "Device Root". The "Transport" object has the time signature, cycle, punch, pre/post-roll,
metronome, precount and record modes; "Metronome" has the click level. Their ids change between sessions,
so they are found by type. Parameters are matched by their (English, internal) title.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from trackwright.core.base import MIXER, ServiceBase, operation
from trackwright.core.models import Metronome, ProjectOut, Roll, Signature, Span
from trackwright.errors import NotFoundError, TrackwrightError

JsonObject = dict[str, Any]
DEVICE_ROOT_SCAN = 64
TAG_SIGNATURE = 4027  # Transport "signature" (verified in Cubase 15)
TAG_TIME_BARS, TAG_TIME_SECONDS = 4023, 4101  # Transport "time" / "time2": the cursor (verified, TW-1211)
SECONDS_TOLERANCE = 0.0015
CLOCK = re.compile(r"^\s*(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d+)?)\s*$")


def parse_seconds(text: str) -> float | None:
    """'2', '2.5', '1:30', '0:01:30.250' → seconds; ``None`` when it is not a time."""
    match = CLOCK.match(text)
    if match is None:
        return None
    first, second, seconds = match.groups()
    hours, minutes = (first, second) if second is not None else (None, first)
    return int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(seconds)


def format_seconds(seconds: float) -> str:
    """Seconds → 'h:mm:ss.mmm', the format of Cubase's seconds display."""
    millis = round(max(seconds, 0.0) * 1000)
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    return f"{hours}:{minutes:02d}:{rest // 1000:02d}.{rest % 1000:03d}"


UNAVAILABLE = {
    "sample_rate": "not exposed by the MIDI Remote API (Project Setup dialog only)",
    "bit_depth": "not exposed by the MIDI Remote API (Project Setup dialog only)",
    "project_length": "not exposed by the MIDI Remote API (Project Setup dialog only)",
    "project_name": "not exposed by the MIDI Remote API; see project_folders",
}
MODE_TITLES = {
    "record_button": "recordButtonMode",
    "audio_record": "audioRecordMode",
    "midi_record": "midiRecordMode",
    "midi_cycle_record": "midiCycleRecordMode",
    "record_start": "recordStartMode",
    "play_start": "startPlayModes",
    "return_on_stop": "returnOnStop",
}
SIGNATURE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")


def parse_signature(text: str | None) -> Signature | None:
    if not text:
        return None
    match = SIGNATURE.match(text)
    if match is None:
        return Signature(text=text, numerator=None, denominator=None)
    return Signature(text=text, numerator=int(match.group(1)), denominator=int(match.group(2)))


class ProjectMixin(ServiceBase):
    def _device_root(self) -> int:
        for oid in (1, *range(DEVICE_ROOT_SCAN)):  # id 1 in Cubase 15; scan in case that changes
            try:
                if self.call("da.object", {"id": oid, **MIXER}).get("type") == "Device Root":
                    return int(oid)
            except TrackwrightError:
                continue
        raise NotFoundError("Cubase's Device Root object was not found", code="UNAVAILABLE")

    def _studio_objects(self) -> dict[str, int]:
        root: int = self._device_root()
        found: dict[str, int] = {}
        offset = 0
        while True:
            page = self.call("da.children", {"id": root, "offset": offset, "limit": 50, **MIXER})
            for child in page.get("items", []):
                found.setdefault(str(child.get("type")), int(child["id"]))
            offset += len(page.get("items", []))
            if not page.get("items") or offset >= int(page.get("total", 0)):
                return found

    def _params_by_title(self, oid: int | None) -> dict[str, JsonObject]:
        if oid is None:
            return {}
        out: dict[str, JsonObject] = {}
        offset = 0
        while True:
            page = self.call("da.params", {"id": oid, "offset": offset, "limit": 25, **MIXER})
            for param in page.get("items", []):
                out.setdefault(str(param.get("title")), param)
            offset += len(page.get("items", []))
            if not page.get("items") or offset >= int(page.get("total", 0)):
                return out

    # ------------------------------------------------------------------ time in seconds (TW-1211)
    def _transport_id(self) -> int:
        transport = self._studio_objects().get("Transport")
        if transport is None:
            raise NotFoundError("Cubase's Transport object was not found", code="UNAVAILABLE")
        return transport

    def _cursor_seconds(self, transport: int) -> float:
        display = str(self.call("da.param.get", {"id": transport, "tag": TAG_TIME_SECONDS, **MIXER}).get("display"))
        seconds = parse_seconds(display)
        if seconds is None:
            raise TrackwrightError(f"unexpected cursor time {display!r}", code="UNAVAILABLE")
        return seconds

    def _cursor_bars(self) -> str:
        raw = (self.call("transport.get").get("primary") or {}).get("locator") or {}
        return str(raw.get("time", ""))

    def _move_cursor_seconds(self, transport: int, seconds: float) -> float:
        """Put the cursor at ``seconds`` through the seconds display (verified) and return where it landed."""
        self.call("transport.setTime", {"which": "locator", "display": "secondary", "time": format_seconds(seconds)})
        return self.wait_until(
            lambda: self._cursor_seconds(transport), lambda now: abs(now - seconds) <= SECONDS_TOLERANCE
        )

    def _set_locator_seconds(self, transport: int, which: str, seconds: float) -> str:
        """Set the left or right locator at ``seconds``: cursor there, then Set Left/Right Locator.

        Setting the locators through the seconds display does not work (verified, TW-1211). Returns the
        locator's bar position, which must equal the cursor's.
        """
        self._move_cursor_seconds(transport, seconds)
        target = self._cursor_bars()
        field = "cycleLeft" if which == "left" else "cycleRight"
        self.call("cmd.run", {"key": f"transport.set_{which}_locator"})

        def read() -> str:
            raw = (self.call("transport.get").get("primary") or {}).get(field) or {}
            return str(raw.get("time", ""))

        return self.wait_until(read, lambda now: now == target)

    def current_signature(self) -> Signature | None:
        """The time signature at the cursor, or ``None`` when Cubase does not report it."""
        try:
            transport = self._studio_objects().get("Transport")
            if transport is None:
                return None
            param = self.call("da.param.get", {"id": transport, "tag": TAG_SIGNATURE, **MIXER})
        except TrackwrightError:
            return None
        if param.get("title") != "signature":
            return None
        return parse_signature(str(param.get("display") or ""))

    @operation
    def get_project(self, *, include_folders: bool = True) -> ProjectOut:
        objects = self._studio_objects()
        transport = self._params_by_title(objects.get("Transport"))
        metronome = self._params_by_title(objects.get("Metronome"))
        if not transport:
            raise NotFoundError("Cubase's Transport object was not found", code="UNAVAILABLE")

        def flag(params: dict[str, JsonObject], title: str) -> bool | None:
            param = params.get(title)
            return None if param is None else float(param.get("process") or 0) >= 0.5

        def text(params: dict[str, JsonObject], title: str) -> str | None:
            param = params.get(title)
            return None if param is None else str(param.get("display") or "").strip() or None

        state: Literal["stopped", "playing", "recording", "unknown"]
        if flag(transport, "record"):
            state = "recording"
        elif flag(transport, "start"):
            state = "playing"
        elif flag(transport, "stop"):
            state = "stopped"
        else:
            state = "unknown"
        tempo = self.call("transport.get").get("tempoBPM")
        folders = None
        if include_folders and self.launcher is not None:
            folders = self.launcher.project_folders()
        return ProjectOut(
            tempo_bpm=float(tempo) if isinstance(tempo, int | float) else None,
            signature=parse_signature(text(transport, "signature")),
            cycle=Span(
                active=flag(transport, "cycle"),
                start=text(transport, "cycleLeftTime"),
                end=text(transport, "cycleRightTime"),
            ),
            punch_in=flag(transport, "punchIn"),
            punch_out=flag(transport, "punchOut"),
            punch_range=Span(active=None, start=text(transport, "punchInTime"), end=text(transport, "punchOutTime")),
            pre_roll=Roll(active=flag(transport, "usePreRoll"), length=text(transport, "preRoll")),
            post_roll=Roll(active=flag(transport, "usePostRoll"), length=text(transport, "postRoll")),
            metronome=Metronome(
                active=flag(transport, "metronomeOn"),
                click_level=text(metronome, "clickLevel"),
                in_record=flag(metronome, "tickInRecord"),
                in_playback=flag(metronome, "tickInPlayback"),
            ),
            precount=flag(transport, "precountOn"),
            transport=state,
            time_formats=[text(transport, "timeFormat"), text(transport, "timeFormat2")],
            modes={key: text(transport, title) for key, title in MODE_TITLES.items()},
            project_folders=folders,
            unavailable=dict(UNAVAILABLE),
        )
