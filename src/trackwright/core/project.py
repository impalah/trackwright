"""Project properties (TW-1209), read from Cubase's own DirectAccess objects.

Verified in Cubase Elements 15.0.30 (experiments/tw1209): besides the mixer, DirectAccess reaches the studio
objects under "Device Root". The "Transport" object has the time signature, cycle, punch, pre/post-roll,
metronome, precount and record modes; "Metronome" has the click level. Their ids change between sessions,
so they are found by type. Parameters are matched by their (English, internal) title.
"""

from __future__ import annotations

import re
from typing import Literal

from trackwright.core.base import MIXER, ServiceBase, operation
from trackwright.core.models import Metronome, ProjectOut, Roll, Signature, Span
from trackwright.core.tags import Transport
from trackwright.core.timefmt import SECONDS_TOLERANCE, format_seconds, parse_seconds
from trackwright.errors import NotFoundError, TrackwrightError
from trackwright.jsontypes import JsonObject

DEVICE_ROOT_SCAN = 64

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


def click_level(metronome: dict[str, JsonObject]) -> str | None:
    """The click level 0-127 (verified: value x 127, TW-1210)."""
    param = metronome.get("clickLevel")
    return None if param is None else str(round(float(param.get("process") or 0) * 127))


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
        for child in self.paged("da.children", {"id": root}, 50):
            found.setdefault(str(child.get("type")), int(child["id"]))
        return found

    def _params_by_title(self, oid: int | None) -> dict[str, JsonObject]:
        if oid is None:
            return {}
        out: dict[str, JsonObject] = {}
        for param in self.paged("da.params", {"id": oid}, 25):
            out.setdefault(str(param.get("title")), param)
        return out

    # ------------------------------------------------------------------ time in seconds (TW-1211)
    def _transport_id(self) -> int:
        transport = self._studio_objects().get("Transport")
        if transport is None:
            raise NotFoundError("Cubase's Transport object was not found", code="UNAVAILABLE")
        return transport

    def _cursor_seconds(self, transport: int) -> float:
        display = str(
            self.call("da.param.get", {"id": transport, "tag": Transport.TIME_SECONDS, **MIXER}).get("display")
        )
        seconds = parse_seconds(display)
        if seconds is None:
            raise TrackwrightError(f"unexpected cursor time {display!r}", code="UNAVAILABLE")
        return seconds

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
        target = self.cursor_bars()
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
            param = self.call("da.param.get", {"id": transport, "tag": Transport.SIGNATURE, **MIXER})
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
                click_level=click_level(metronome),
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
