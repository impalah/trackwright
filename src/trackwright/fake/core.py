"""The simulator's state, the HostPort entry point and helpers that mirror the script."""

from __future__ import annotations

import itertools
import secrets
from collections.abc import Callable
from typing import Any

from trackwright.errors import HostError, RequestTimeoutError, StaleSessionError, TrackwrightError
from trackwright.fake.model import BARS, SECONDS, Obj, Param
from trackwright.fake.timeline import _bars_to_beats, _format_seconds
from trackwright.jsontypes import JsonObject
from trackwright.ops import SESSIONLESS_OPS


class FakeCore:
    """In-memory host. Use the helper methods (``remove``, ``reload_script``...) to drive scenarios."""

    simulated = True

    def __init__(
        self, *, tracks: tuple[tuple[str, str], ...] = (("Synth", "POC-INSTR"), ("AudioChannel", "POC-TEST"))
    ) -> None:
        self._ids = itertools.count(100)
        self.objects: dict[int, Obj] = {}
        self.session = self._new_session()
        self.mixer = self._obj("VST Mixer", "VST Mixer")
        self._studio()
        self.channels: list[int] = [self._channel("OutputChannel", "Stereo Out").id]
        for kind, title in tracks:
            self.channels.append(self._channel(kind, title).id)
        self.selected: int = self.channels[-1]
        self.objects[self.selected].params[4000].value = 1
        self.non_mixer_tracks: list[str] = []
        self.transport = {
            "locator": "1. 1. 1.  0",
            "cycleLeft": "1. 1. 1.  0",
            "cycleRight": "1. 1. 1.  0",
        }
        self.tempo = 120.0
        self.online = True  # False simulates Cubase closed or still starting (TW-1201)
        # Range editing (TW-1211): audio events per channel in seconds, the active tool, the range selection
        # and an undo history, as observed in Cubase 15 (experiments/tw1211).
        self.track_events: dict[int, list[tuple[float, float]]] = {
            self.channel_by_title(title).id: list(events)
            for title, events in (
                ("POC-TEST", [(0.0, 2.4), (2.0, 6.8), (6.0, 18.0), (18.0, 22.0), (22.0, 139.976)]),
                ("POC-INSTR", [(0.0, 2.0), (2.0, 4.0), (4.0, 6.0), (6.0, 8.0)]),
            )
            if any(self.objects[c].title == title for c in self.channels)
        }
        self.tool = "select"
        self.range: tuple[float, float] | None = None
        self.history: list[dict[int, list[tuple[float, float]]]] = []
        self.clipboard_seconds = 0.0
        self.selected_events: list[tuple[int, tuple[float, float]]] = []  # object selection (TW-1212)
        self.editor_focused = True
        """The user has clicked on the plugin window once (Preset Next/Previous need it, TW-1205)."""
        self.preset_loaded = True
        """The plugin shows a preset (Preset Next/Previous do nothing without one, TW-1205)."""
        self.auto_select_under_cursor = True
        """Cubase preference seen on the user's system (TW-1212): moving the cursor selects the events under it."""
        # Automation simulation (TW-1207): playback advances the cursor on every transport.get.
        self.automation_controls = True
        self.playing = False
        self.position = 0.0  # beats from the project start
        self.beats_per_poll = 0.25
        self.auto_values: dict[tuple[int, str], float] = {}
        self.auto_touched: set[str] = set()
        # TW-1616: Cubase binds the automation controls to a new selection a moment later; each entry is the
        # channel title one auto.list still reports before the controls follow the selection
        self.auto_lag: list[str] = []
        self.automation: dict[tuple[int, str], list[tuple[float, float]]] = {}
        self.markers: list[str] = []
        self.last_event_end: str | None = "9. 1. 1.  0"
        """End of the last event in the project (``None`` = no events). Used by "Locate Next Marker"."""
        self.fired: list[str] = []
        self.pending_dialog: str | None = None
        self.pending_removal: int | None = None
        self.events: list[JsonObject] = []
        self.event_seq = 0
        self.calls: list[tuple[str, JsonObject]] = []
        self.overrides: dict[str, Callable[[JsonObject], JsonObject]] = {}
        self.fail_next: dict[str, TrackwrightError] = {}
        self.can_perform_false: set[str] = {"edit.undo", "edit.redo", "edit.paste"}

    # ------------------------------------------------------------------ model building
    @staticmethod
    def _new_session() -> str:
        return secrets.token_hex(6)

    def _obj(self, kind: str, title: str, **extra: Any) -> Obj:
        oid = next(self._ids)
        obj = Obj(
            id=oid, type=kind, title=title, unique_name=extra.pop("unique_name", kind), uid=f"UID{oid:06d}", **extra
        )
        self.objects[oid] = obj
        return obj

    def _studio(self) -> None:
        """Device Root with the Transport and Metronome objects (TW-1209), as in Cubase 15."""
        root = self._obj("Device Root", "Device Root")
        del self.objects[root.id]  # id 1, as in Cubase 15
        root.id = 1
        self.objects[1] = root
        transport = self._obj("Transport", "Transporte")
        on_off = ("start", "record", "cycle", "punchIn", "punchOut", "usePreRoll", "usePostRoll", "metronomeOn",
                  "precountOn", "returnOnStop")  # fmt: skip
        tags = {
            "start": 4015,
            "record": 4019,
            "cycle": 4022,
            "punchIn": 4020,
            "punchOut": 4021,
            "usePreRoll": 4037,
            "usePostRoll": 4038,
            "metronomeOn": 4099,
            "precountOn": 4100,
            "returnOnStop": 4150,
        }  # as in Cubase 15
        transport.params = {tags[title]: Param(title, "discrete", 0) for title in on_off}
        transport.params[4016] = Param("stop", "discrete", 1)
        texts = {"signature": "4/4", "cycleLeftTime": "1. 1. 1.  0", "cycleRightTime": "1. 1. 1.  0",
                 "punchInTime": "1. 1. 1.  0", "punchOutTime": "1. 1. 1.  0", "preRoll": "0. 0. 0.  0",
                 "postRoll": "0. 0. 0.  0", "timeFormat": "Compases+Tiempos", "timeFormat2": "Segundos",
                 "recordButtonMode": "Punch in/out", "audioRecordMode": "Mantener historial",
                 "midiRecordMode": "Nuevas partes", "midiCycleRecordMode": "Mix",
                 "recordStartMode": "Iniciar en cursor", "startPlayModes": "Inicio desde posición"}  # fmt: skip
        for i, (title, value) in enumerate(texts.items()):
            transport.params[4027 if title == "signature" else 4200 + i] = Param(title, "text", 0, value)
        metronome = self._obj("Metronome", "Metronome")
        metronome.params = {1: Param("clickLevel", "continuous", 1.0), 2: Param("tickInRecord", "discrete", 0),
                            3: Param("tickInPlayback", "discrete", 0)}  # fmt: skip
        root.children = [self._obj("MIDI System", "CoreMIDI").id, transport.id, metronome.id]
        self.studio = {"root": root, "transport": transport, "metronome": metronome}

    @property
    def meter(self) -> tuple[int, int]:
        numerator, denominator = (self.studio["transport"].params[4027].text or "4/4").split("/")
        return int(numerator), int(denominator)

    def studio_param(self, kind: str, title: str) -> Param:
        return next(p for p in self.studio[kind].params.values() if p.title == title)

    def _channel(self, kind: str, title: str) -> Obj:
        ch = self._obj(kind, title)
        ch.params = {
            1024: Param("Nombre", "text", 1, title),
            4000: Param("Seleccionado", "discrete", 0),
            1025: Param("Volumen", "continuous", 0.7890865802764893, automatable=True),
            1027: Param("Enmudecer", "discrete", 0, automatable=True),
            1028: Param("Solo", "discrete", 0),
            4002: Param("Habilitar grabación", "discrete", 0),
            4013: Param("Escribir automatización", "discrete", 0),
            4014: Param("Leer automatización", "discrete", 0),
            4101: Param(
                "Entrada",
                "discrete",
                19 if kind == "AudioChannel" else 0,
                "Stereo In" if kind == "AudioChannel" else "Sin bus",
            ),
            4102: Param(
                "Salida",
                "discrete",
                0 if kind == "OutputChannel" else 22,
                "Sin bus" if kind == "OutputChannel" else "Stereo Out",
            ),
        }
        inserts = self._obj("Inserts", "Inserciones")
        for i in range(1, 9):
            slot = self._obj("Slot", str(i), unique_name="Slot")
            slot.params[4125] = Param("Tipo de efecto", "discrete", 0, "Ningún efecto")
            slot.params[4101] = Param("Edición", "discrete", 0)  # opens the plugin editor (verified, TW-1205)
            inserts.children.append(slot.id)
        strips = self._obj("Strips", "Strip")
        for i in range(1, 7):
            slot = self._obj("Slot", str(i), unique_name="Slot")
            if i == 3:
                eq = self._obj("EQ", "EQ")
                eq.params[4232] = Param("EQ 1 Gain", "continuous", 0.5, automatable=True)
                for band in range(1, 5):  # remaining EQ parameters, titled as in Cubase 15
                    for offset, name in enumerate(("Gain", "Freq", "Q")):
                        tag = 4300 + band * 10 + offset
                        if not (band == 1 and name == "Gain"):
                            eq.params[tag] = Param(f"EQ {band} {name}", "continuous", 0.5, automatable=True)
                slot.children.append(eq.id)
            strips.children.append(slot.id)
        sends = self._obj("Sends", "Envíos")
        for i in range(1, 9):
            send = self._obj("Slot", str(i), unique_name="Slot")
            send.params[4097] = Param("Nivel", "continuous", 0.7890865802764893, automatable=True)
            sends.children.append(send.id)
        panner = self._obj("Panner", "Panner")
        panner.params[4201] = Param("Izquierda-derecha", "continuous", 0.5, automatable=True)
        input_filter = self._obj("InputFilter", "Input Filter")
        input_filter.params = {
            4201: Param("PreGain", "continuous", 0.5, automatable=True),
            4204: Param("LC-Freq", "continuous", 0.0, automatable=True),
            4206: Param("HC-Freq", "continuous", 1.0, automatable=True),
        }
        ch.children = [input_filter.id, panner.id, inserts.id, strips.id, sends.id]
        return ch

    # ------------------------------------------------------------------ scenario helpers
    def channel_by_title(self, title: str) -> Obj:
        return next(self.objects[c] for c in self.channels if self.objects[c].title == title)

    def remove(self, oid: int) -> None:
        """Delete an object as if the user removed it in Cubase."""
        self.objects[oid].removed = True
        for parent in self.objects.values():
            if oid in parent.children:
                parent.children.remove(oid)
        if oid in self.channels:
            self.channels.remove(oid)
        self._event("mix.removed", oid)

    def reload_script(self) -> None:
        """Restart Cubase / reload the script: new session, and ids are reassigned so old ids are reused."""
        self.session = self._new_session()
        live = sorted(self.objects)
        rotated = live[1:] + live[:1]  # every id now names a different object
        remapped = dict(zip(live, rotated, strict=True))
        objects = {}
        for old, obj in self.objects.items():
            obj.id = remapped[old]
            obj.children = [remapped[c] for c in obj.children]
            objects[obj.id] = obj
        self.objects = objects
        self.mixer = self.objects[remapped[self.mixer.id]]
        self.channels = [remapped[c] for c in self.channels]
        self.selected = remapped.get(self.selected, -1)

    def finish_import(self, duration: float | None) -> None:
        """The user picks a file in the import selector (``None`` = cancels): it lands on the selected track
        at the cursor, as verified in Cubase."""
        self.pending_dialog = None
        if duration is not None:
            self._snapshot()
            start = self._seconds(self.transport["locator"])
            self.track_events.setdefault(self.selected, []).append((start, start + duration))

    def complete_dialog(self, name: str) -> None:
        """The user fills in and accepts the pending Add Track dialog."""
        kind = {"addtrack.audio": "AudioChannel", "addtrack.group": "GroupChannel"}.get(self.pending_dialog or "")
        if self.pending_dialog == "addtrack.folder":
            self.non_mixer_tracks.append(name)
        elif kind:
            ch = self._channel(kind, name)
            self.channels.append(ch.id)
            self._select(ch.id)
        self.pending_dialog = None

    def confirm_pending_removal(self) -> None:
        if self.pending_removal is not None:
            self.remove(self.pending_removal)
            self.pending_removal = None
            self.selected = -1

    def _event(self, kind: str, oid: int, tag: int = -1) -> None:
        self.event_seq += 1
        self.events.append({"n": self.event_seq, "k": kind, "id": oid, "t": tag, "i": 0, "ms": 0})

    # ------------------------------------------------------------------ HostPort
    @property
    def session_id(self) -> str | None:
        return self.session

    def call(self, op: str, params: JsonObject | None = None, *, session: str | None = None) -> JsonObject:
        p = dict(params or {})
        self.calls.append((op, p))
        if session is not None and op not in SESSIONLESS_OPS and session != self.session:
            raise StaleSessionError(f"expected session {self.session}")
        if not self.online or self.pending_dialog == "file.import_audio":
            # Cubase closed, or blocked by the macOS file selector (verified, TW-1203): the bridge times out.
            raise RequestTimeoutError(f"no answer from Cubase for {op}", outcome_unknown=op not in SESSIONLESS_OPS)
        if op in self.fail_next:
            raise self.fail_next.pop(op)
        handler = self.overrides.get(op) or getattr(self, "_op_" + op.replace(".", "_"), None)
        if handler is None:
            raise HostError(f"unknown op {op}", code="UNKNOWN_OP")
        result: JsonObject = handler(p)
        return result

    def override(self, op: str, handler: Callable[[JsonObject], JsonObject]) -> None:
        """Answer ``op`` with ``handler`` (tests: simulate a Cubase behaviour without touching internals)."""
        self.overrides[op] = handler

    def request_with_session(self, op: str, sid: str, params: JsonObject | None = None) -> JsonObject:
        """Like the script: refuse a foreign session id (used to test stale sessions)."""
        if op not in SESSIONLESS_OPS and sid != self.session:
            raise StaleSessionError(f"expected session {self.session}")
        return self.call(op, params)

    # ------------------------------------------------------------------ helpers mirroring the script
    def _live(self, oid: Any) -> Obj:
        obj = self.objects.get(oid) if isinstance(oid, int) else None
        if obj is None or obj.removed:
            raise HostError(f"object {oid} is not valid (removed or unknown)", code="INVALID_OBJECT")
        return obj

    @staticmethod
    def _num(p: JsonObject, name: str, default: float | None = None) -> float:
        value = p.get(name, default)
        if value is None:
            raise HostError(f"missing {name}", code="BAD_REQUEST")
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise HostError(f"{name} must be a number", code="BAD_REQUEST")
        return value

    def _base(self, p: JsonObject) -> int:
        return self.mixer.id if p.get("scope") == "mixer" else self.selected

    def _describe(self, obj: Obj) -> JsonObject:
        return {
            "id": obj.id,
            "title": obj.title,
            "type": obj.type,
            "uniqueName": obj.unique_name,
            "uid": obj.uid,
            "children": len(obj.children),
            "params": len(obj.params),
        }

    @staticmethod
    def _display(param: Param) -> str:
        if param.kind == "text" or (param.text is not None and param.value > 1):
            return param.text or ""
        if param.text is not None and param.kind == "discrete" and param.value == 0:
            return param.text
        if param.kind == "discrete":
            return "Activ." if param.value >= 0.5 else "Desact."
        return f"{param.value:.2f}"

    def _describe_param(self, obj: Obj, tag: int) -> JsonObject:
        if obj is self.studio["transport"]:  # cursor position, live (verified: time and time2 follow the cursor)
            try:
                seconds_text = _format_seconds(self._seconds(self.transport["locator"]))
            except ValueError:
                seconds_text = ""
            obj.params[4023] = Param("time", "text", 0, self.transport["locator"])
            obj.params[4101] = Param("time2", "text", 0, seconds_text)
        param = obj.params.get(tag)
        if param is None:
            return {
                "tag": tag,
                "title": "",
                "process": -1,
                "display": "",
                "units": "",
                "valueType": "",
                "automatable": False,
                "editLock": False,
                "defaultProcess": -1,
                "plain": -1,
            }
        plain = param.value * 48 - 24 if param.kind == "continuous" else param.value
        return {
            "tag": tag,
            "title": param.title,
            "process": param.value,
            "display": self._display(param),
            "units": "",
            "valueType": param.kind,
            "automatable": param.automatable,
            "editLock": False,
            "defaultProcess": -1,
            "plain": plain,
        }

    def _guard(self, _p: JsonObject) -> JsonObject:
        """Like the script since 1.6.0: only the base object, no subtree path or caller precondition."""
        base = self.selected
        channel = self.objects.get(base) if base >= 0 else None
        return {"base": base, "baseTitle": channel.title if channel else None}

    def _select(self, oid: int) -> None:
        for cid in self.channels:
            self.objects[cid].params[4000].value = 0
        self.objects[oid].params[4000].value = 1
        self.selected = oid

    # ------------------------------------------------------------------ helpers used by several layers
    def _snapshot(self) -> None:
        self.history.append({tid: list(events) for tid, events in self.track_events.items()})

    def _seconds(self, bars: str) -> float:
        return _bars_to_beats(bars, self.meter) * 60 / self.tempo

    def _time(self, value: str, display: str) -> JsonObject:
        return {"time": value, "format": BARS if display == "primary" else SECONDS, "ms": 0}

    RANGE_ACTIONS = ("edit.delete", "edit.delete_time", "edit.cut_time", "edit.insert_silence", "edit.crop_range")

    def _can(self, key: str) -> bool:
        """canPerform as observed (TW-1211/1212): undo needs history and no open dialog, range actions a
        range, object actions a selection, Select Events under Cursor an event under the cursor."""
        rules: dict[str, Callable[[], bool]] = {
            "edit.undo": lambda: bool(self.history) and self.pending_dialog is None,
            "edit.delete": lambda: self.range is not None if self.tool == "range" else bool(self.selected_events),
            "edit.select_events_under_cursor": lambda: bool(self._under_cursor()),
            "edit.split_at_cursor": lambda: bool(self.selected_events),
            "edit.select_in_loop": lambda: (
                self._seconds(self.transport["cycleLeft"]) < self._seconds(self.transport["cycleRight"])
            ),
        }
        rules.update({k: lambda: self.range is not None for k in self.RANGE_ACTIONS if k != "edit.delete"})
        rule = rules.get(key)
        return rule() if rule is not None else key not in self.can_perform_false

    def _under_cursor(self) -> list[tuple[int, tuple[float, float]]]:
        here = self._seconds(self.transport["locator"])
        return [(self.selected, e) for e in self.track_events.get(self.selected, []) if e[0] - 1e-6 <= here < e[1]]
