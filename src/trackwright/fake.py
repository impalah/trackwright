"""FakeCubase: an in-memory simulator of the Trackwright script and of Cubase.

It answers the same operations with the same result shapes as ``Trackwright_Bridge.js`` and
reproduces the behaviours verified against Cubase Elements 15.0.30 in the POC:

- the mixer's last child duplicates the last channel (same id);
- removed objects return sentinels and ``INVALID_OBJECT``;
- process writes outside [0, 1] are refused; routing values (e.g. 22) cannot be written back;
- selection is single; ``da.base`` follows it and is ``-1`` on tracks without a mixer channel;
- after a script reload the session changes and old ids point at *different* objects;
- commands: ``dialog`` ones leave a pending dialog, ``confirm`` ones may wait for confirmation;
- "Locate Next Marker" without a next marker moves to the end of the last event (``last_event_end``).

It is used by the unit and contract tests and by ``trackwright serve --simulate``. Everything it
reports is flagged ``simulated``: it is never evidence about real Cubase behaviour.
"""

from __future__ import annotations

import itertools
import secrets
from dataclasses import dataclass, field
from typing import Any

from trackwright.commands import COMMANDS
from trackwright.cubase import SCRIPT_VERSION
from trackwright.errors import HostError, StaleSessionError, TrackwrightError
from trackwright.ops import SESSIONLESS_OPS

JsonObject = dict[str, Any]
BARS = "Compases+Tiempos"
SECONDS = "Segundos"

PLUGINS: tuple[JsonObject, ...] = (
    {
        "name": "StudioEQ",
        "vendor": "Steinberg Media Technologies",
        "version": "1.0.0",
        "format": "VST3",
        "subCategories": "Fx|EQ",
        "uid": "946051208E29496E804F64A825C8A047",
        "path": "",
    },
    {
        "name": "Compressor",
        "vendor": "Steinberg Media Technologies",
        "version": "1.0.0",
        "format": "VST3",
        "subCategories": "Fx|Dynamics",
        "uid": "5B38F28281144FFE80285FF7CCF20483",
        "path": "",
    },
)


@dataclass
class Param:
    title: str
    kind: str  # "continuous" | "discrete" | "text"
    value: float
    text: str | None = None
    automatable: bool = False


@dataclass
class Obj:
    id: int
    type: str
    title: str
    unique_name: str
    uid: str
    children: list[int] = field(default_factory=list)
    params: dict[int, Param] = field(default_factory=dict)
    removed: bool = False
    has_events: bool = False


class FakeCubase:
    """In-memory host. Use the helper methods (``remove``, ``reload_script``...) to drive scenarios."""

    simulated = True

    def __init__(
        self, *, tracks: tuple[tuple[str, str], ...] = (("Synth", "POC-INSTR"), ("AudioChannel", "POC-TEST"))
    ) -> None:
        self._ids = itertools.count(100)
        self.objects: dict[int, Obj] = {}
        self.session = self._new_session()
        self.mixer = self._obj("VST Mixer", "VST Mixer")
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
        # Automation simulation (TW-1207): playback advances the cursor on every transport.get.
        self.automation_controls = True
        self.playing = False
        self.position = 0.0  # beats from the project start
        self.beats_per_poll = 0.25
        self.auto_values: dict[tuple[int, str], float] = {}
        self.auto_touched: set[str] = set()
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
        remapped: dict[int, int] = {}
        live = sorted(self.objects)
        rotated = live[1:] + live[:1]  # every id now names a different object
        for old, new in zip(live, rotated, strict=True):
            remapped[old] = new
        objects = {}
        for old, obj in self.objects.items():
            obj.id = remapped[old]
            obj.children = [remapped[c] for c in obj.children]
            objects[obj.id] = obj
        self.objects = objects
        self.mixer = self.objects[remapped[self.mixer.id]]
        self.channels = [remapped[c] for c in self.channels]
        self.selected = remapped.get(self.selected, -1)

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

    def call(self, op: str, params: JsonObject | None = None) -> JsonObject:
        p = dict(params or {})
        self.calls.append((op, p))
        if op in self.fail_next:
            raise self.fail_next.pop(op)
        handler = getattr(self, "_op_" + op.replace(".", "_"), None)
        if handler is None:
            raise HostError(f"unknown op {op}", code="UNKNOWN_OP")
        result: JsonObject = handler(p)
        return result

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

    def _guard(self, p: JsonObject) -> JsonObject:
        base = self.objects.get(self.selected)
        title = base.title if base else None
        expected = p.get("expectChannelTitle")
        if isinstance(expected, str) and title != expected:
            raise HostError(f'base channel title is "{title}", expected "{expected}"', code="PRECONDITION_FAILED")
        return {"base": self.selected, "baseTitle": title, "policy": "open"}

    def _select(self, oid: int) -> None:
        for cid in self.channels:
            self.objects[cid].params[4000].value = 0
        self.objects[oid].params[4000].value = 1
        self.selected = oid

    # ------------------------------------------------------------------ direct ops
    def _host(self) -> JsonObject:
        return {"appName": "Cubase", "appVersion": "15.0.30 (simulated)", "insertSlots": 8}

    def _op_hello(self, _p: JsonObject) -> JsonObject:
        return {
            "scriptVersion": SCRIPT_VERSION,
            "protocol": 1,
            "sessionId": self.session,
            "loadedAt": 0,
            "host": self._host(),
        }

    def _op_ping(self, p: JsonObject) -> JsonObject:
        return {"pong": True, "scriptVersion": SCRIPT_VERSION, "protocol": 1, "echo": p.get("echo")}

    def _op_status(self, _p: JsonObject) -> JsonObject:
        return {
            "deviceActive": True,
            "pageActive": True,
            "daActive": True,
            "daMixActive": True,
            "queue": 0,
            "dupInFlightDropped": 0,
            "lastError": "",
            "simulated": True,
        }

    def _op_capabilities(self, _p: JsonObject) -> JsonObject:
        caps = {
            "json": True,
            "directAccessCreated": True,
            "mixerDirectAccessCreated": True,
            "mixerDirectAccessActive": True,
            "transportTimeDisplay": True,
            "commandsBound": len(COMMANDS),
            "commandErrors": 0,
            "writePolicy": "open",
            "simulated": True,
        }
        return {"capabilities": caps, "host": self._host()}

    def _op_events(self, _p: JsonObject) -> JsonObject:
        events, self.events = self.events, []
        return {"events": events, "dropped": 0, "lastSeq": self.event_seq, "idleTicks": 0, "ms": 0}

    def _time(self, value: str, display: str) -> JsonObject:
        return {"time": value, "format": BARS if display == "primary" else SECONDS, "ms": 0}

    def _op_transport_get(self, _p: JsonObject) -> JsonObject:
        if self.playing:  # verified: the cursor position is reported while playing
            self.position += self.beats_per_poll
            self.transport["locator"] = _beats_to_bars(self.position)
        # Verified quirk: the secondary display reports bar strings while declaring "Segundos".
        out: JsonObject = {"available": True, "tempoBPM": self.tempo, "updates": 1}
        for display in ("primary", "secondary"):
            out[display] = {k: self._time(v, display) for k, v in self.transport.items()}
        return out

    def _op_cmd_list(self, _p: JsonObject) -> JsonObject:
        commands = [
            {"key": s.key, "category": s.category, "name": s.name, "fired": self.fired.count(s.key)}
            for s in COMMANDS.values()
        ]
        return {"commands": commands, "errors": []}

    # ------------------------------------------------------------------ DirectAccess reads
    def _op_da_base(self, p: JsonObject) -> JsonObject:
        base = self._base(p)
        if base < 0:
            return {"base": base}
        return {"base": base, "object": self._describe(self.objects[base])}

    def _op_da_object(self, p: JsonObject) -> JsonObject:
        return self._describe(self._live(int(self._num(p, "id"))))

    def _op_da_children(self, p: JsonObject) -> JsonObject:
        obj = self._live(int(self._num(p, "id")))
        offset = int(self._num(p, "offset", 0))
        limit = min(int(self._num(p, "limit", 20)), 50)
        items = [self._describe(self.objects[c]) | {"index": i} for i, c in enumerate(obj.children) if i >= offset][
            :limit
        ]
        return {"id": obj.id, "total": len(obj.children), "offset": offset, "items": items}

    def _op_da_params(self, p: JsonObject) -> JsonObject:
        obj = self._live(int(self._num(p, "id")))
        offset = int(self._num(p, "offset", 0))
        limit = min(int(self._num(p, "limit", 10)), 25)
        tags = list(obj.params)
        items = [self._describe_param(obj, t) | {"index": i} for i, t in enumerate(tags) if i >= offset][:limit]
        return {"id": obj.id, "total": len(tags), "offset": offset, "items": items}

    def _op_da_param_get(self, p: JsonObject) -> JsonObject:
        return self._describe_param(self._live(int(self._num(p, "id"))), int(self._num(p, "tag")))

    def _op_da_convert(self, p: JsonObject) -> JsonObject:
        obj = self._live(int(self._num(p, "id")))
        out: JsonObject = {"id": obj.id, "tag": int(self._num(p, "tag"))}
        if "process" in p:
            out["plainFromProcess"] = self._num(p, "process") * 48 - 24
        if "plain" in p:
            out["processFromPlain"] = (self._num(p, "plain") + 24) / 48
        return out

    def _op_da_channels(self, p: JsonObject) -> JsonObject:
        base = self._base(p)
        if base < 0:
            return {"base": base, "total": 0, "items": [], "duplicates": []}
        offset = int(self._num(p, "offset", 0))
        limit = min(int(self._num(p, "limit", 16)), 32)
        tags = p.get("tags") or [1024, 4000, 1025, 1027, 1028, 4101, 4102]
        children = [*self.channels, self.channels[-1]] if base == self.mixer.id else self.objects[base].children
        items: list[JsonObject] = []
        duplicates: list[JsonObject] = []
        seen: set[int] = set()
        for index, cid in enumerate(children):
            if index < offset or len(items) >= limit:
                continue
            if cid in seen:
                duplicates.append({"index": index, "id": cid})
                continue
            seen.add(cid)
            obj = self.objects[cid]
            values = {
                str(t): {
                    "title": obj.params[t].title,
                    "display": self._display(obj.params[t]),
                    "process": obj.params[t].value,
                }
                if t in obj.params
                else None
                for t in tags
            }
            items.append(
                self._describe(obj)
                | {
                    "index": index,
                    "mixerVisible": True,
                    "mixerIndex": index - 1 if index else -1,
                    "mixerZone": 0,
                    "values": values,
                }
            )
        return {
            "base": base,
            "baseObject": self._describe(self.objects[base]),
            "total": len(children),
            "offset": offset,
            "items": items,
            "duplicates": duplicates,
        }

    def _op_pm_collections(self, p: JsonObject) -> JsonObject:
        slot = self._live(int(self._num(p, "slot")))
        total = 1 if slot.type == "Slot" and slot.params.get(4125) else 0
        items = [{"index": 0, "name": "Por defecto", "entries": len(PLUGINS)}] if total else []
        return {"slot": slot.id, "total": total, "items": items, "defaultIndex": 0, "activeIndex": 0 if total else -1}

    def _op_pm_entries(self, p: JsonObject) -> JsonObject:
        slot = self._live(int(self._num(p, "slot")))
        if int(self._num(p, "collection")) != 0 or not slot.params.get(4125):
            raise HostError("collection not found", code="NOT_FOUND")
        offset = int(self._num(p, "offset", 0))
        limit = min(int(self._num(p, "limit", 20)), 40)
        needle = str(p.get("filter") or "").lower()
        matched = [
            e | {"index": i}
            for i, e in enumerate(PLUGINS)
            if needle in f"{e['name']} {e['vendor']} {e['subCategories']}".lower()
        ]
        return {
            "slot": slot.id,
            "collection": 0,
            "collectionName": "Por defecto",
            "total": len(PLUGINS),
            "matched": len(matched),
            "offset": offset,
            "items": matched[offset : offset + limit],
        }

    def _op_cmd_canPerform(self, p: JsonObject) -> JsonObject:  # noqa: N802 - mirrors the op name
        keys = [p["key"]] if p.get("key") else list(COMMANDS)
        return {"canPerform": {k: k not in self.can_perform_false for k in keys if k in COMMANDS}}

    # ------------------------------------------------------------------ writes
    def _op_da_param_set(self, p: JsonObject) -> JsonObject:
        obj = self._live(int(self._num(p, "id")))
        tag = int(self._num(p, "tag"))
        value = self._num(p, "value")
        guard = self._guard(p)
        before = self._describe_param(obj, tag)
        if value < 0 or value > 1:
            raise HostError("process value must be in [0,1]", code="BAD_REQUEST")
        expected = p.get("expectTitle")
        if isinstance(expected, str) and before["title"] != expected:
            raise HostError(
                f'parameter title is "{before["title"]}", expected "{expected}"', code="PRECONDITION_FAILED"
            )
        param = obj.params.get(tag)
        if param is not None:
            if tag == 4000 and value >= 0.5:
                self._select(obj.id)
            else:
                param.value = round(value, 6) if param.kind == "continuous" else (1 if value >= 0.5 else 0)
                if tag in (4101, 4102):
                    param.text = "Sin bus"  # verified: writing routing ends on 'Sin bus'
            self._event("param", obj.id, tag)
        return {"guard": guard, "before": before, "after": self._describe_param(obj, tag), "requested": value}

    def _op_da_param_setDisplay(self, p: JsonObject) -> JsonObject:  # noqa: N802 - mirrors the op name
        obj = self._live(int(self._num(p, "id")))
        tag = int(self._num(p, "tag"))
        text = p.get("value")
        if not isinstance(text, str):
            raise HostError("value must be a string", code="BAD_REQUEST")
        guard = self._guard(p)
        before = self._describe_param(obj, tag)
        param = obj.params.get(tag)
        if param is not None and param.kind == "text":  # verified: routing ignores display writes
            param.text = text
            if tag == 1024:
                obj.title = text
        return {"guard": guard, "before": before, "after": self._describe_param(obj, tag), "requested": text}

    def _op_pm_set(self, p: JsonObject) -> JsonObject:
        slot = self._live(int(self._num(p, "slot")))
        uid = p.get("uid")
        if not isinstance(uid, str) or not uid:
            raise HostError("uid required", code="BAD_REQUEST")
        guard = self._guard(p)
        before = self._describe(slot)
        if slot.type != "Slot":
            raise HostError(f"target is not a Slot (type={slot.type})", code="PRECONDITION_FAILED")
        if slot.children:
            raise HostError(f"slot has {len(slot.children)} child object(s)", code="SLOT_NOT_EMPTY")
        entry = next((e for e in PLUGINS if e["uid"] == uid), None)
        if entry is not None:
            plugin = self._obj("Plugin", entry["name"], unique_name=f"{uid}-0")
            plugin.params[4207] = Param("GainP1L", "continuous", 0.5, automatable=True)
            for n in range(1, 9):  # bank parameters, titled like the automation controls report them
                plugin.params[4300 + n] = Param(f"Param {n}", "continuous", 0.5, automatable=True)
            slot.children.append(plugin.id)
            slot.params[4125] = Param("Tipo de efecto", "discrete", 1, entry["name"])
        return {"guard": guard, "result": entry is not None, "before": before, "after": self._describe(slot)}

    # ------------------------------------------------------------------ automation controls (TW-1207)
    AUTO_KEYS: tuple[str, ...] = (
        "volume",
        "pan",
        *(f"send{i}.level" for i in range(1, 5)),
        *(f"eq{b}.{p}" for b in range(1, 5) for p in ("gain", "freq", "q")),
        "prefilter.gain",
        "prefilter.lowcut",
        "prefilter.highcut",
        *(f"qc{i}" for i in range(1, 9)),
        *(f"insert{s}.p{n}" for s in (1, 2) for n in range(1, 9)),
    )

    def _auto_title(self, key: str) -> str:
        """Title of the parameter bound to a control on the selected track (' / ' when nothing is bound)."""
        if key.startswith("qc"):
            return " / "
        if key.startswith("insert"):
            slot_index, param_index = int(key[6]) - 1, int(key.split(".p")[1])
            inserts = next(
                self.objects[c] for c in self.objects[self.selected].children if self.objects[c].type == "Inserts"
            )
            slot = self.objects[inserts.children[slot_index]]
            if not slot.children:
                return " / "
            return f"{self.objects[slot.children[0]].title} / Param {param_index}"
        return {"volume": f"{self.objects[self.selected].title} / Volumen", "pan": "Panner / Izquierda-derecha"}.get(
            key, f"Channel / {key}"
        )

    def _auto_value(self, key: str) -> float:
        recorded = self.automation.get((self.selected, key))
        reading = self.objects[self.selected].params[4014].value >= 0.5
        if self.playing and reading and recorded and key not in self.auto_touched:
            earlier = [value for beat, value in recorded if beat <= self.position]
            if earlier:
                return earlier[-1]
        if key == "volume":
            return self.objects[self.selected].params[1025].value
        return self.auto_values.get((self.selected, key), 0.5)

    def _require_controls(self) -> None:
        if not self.automation_controls:
            raise HostError("automation controls are not enabled in this script build", code="UNSUPPORTED")
        if self.selected < 0:
            raise HostError("no selected channel", code="NO_BASE_OBJECT")

    def _describe_control(self, key: str) -> JsonObject:
        value = self._auto_value(key)
        bound = self._auto_title(key).strip(" /") != ""
        return {"key": key, "value": value if bound else None, "display": f"{value:.2f}" if bound else "",
                "title": self._auto_title(key), "touched": key in self.auto_touched, "errors": []}  # fmt: skip

    def _op_auto_control(self, p: JsonObject) -> JsonObject:
        self._require_controls()
        key = p.get("key")
        if key not in self.AUTO_KEYS:
            raise HostError(f"unknown automation control {key}", code="NOT_FOUND")
        touched_before = key in self.auto_touched
        if p.get("touch") is True:
            self.auto_touched.add(key)
        if "value" in p:
            value = self._num(p, "value")
            if not 0 <= value <= 1:
                raise HostError("value must be in [0,1]", code="BAD_REQUEST")
            if key == "volume":
                self.objects[self.selected].params[1025].value = value
            else:
                self.auto_values[(self.selected, key)] = value
            writing = self.objects[self.selected].params[4013].value >= 0.5
            if writing and self.playing and key in self.auto_touched:  # verified: touched + W + playing records
                self.automation.setdefault((self.selected, key), []).append((self.position, value))
        if p.get("touch") is False:
            self.auto_touched.discard(key)
        return self._describe_control(key) | {"touchedBefore": touched_before}

    def _op_auto_list(self, _p: JsonObject) -> JsonObject:
        if not self.automation_controls:
            return {"enabled": False, "controls": []}
        if self.selected < 0:
            return {"enabled": True, "controls": [], "errors": ["no selected channel"]}
        return {"enabled": True, "controls": [self._describe_control(k) for k in self.AUTO_KEYS], "errors": []}

    def _op_sel_step(self, p: JsonObject) -> JsonObject:
        direction = p.get("direction")
        if direction not in ("next", "prev"):
            raise HostError("direction must be next|prev", code="BAD_REQUEST")
        tracks = self.channels[1:]
        if self.selected in tracks:
            i = tracks.index(self.selected) + (1 if direction == "next" else -1)
            if 0 <= i < len(tracks):
                self._select(tracks[i])
        return {"triggered": direction}

    def _op_transport_setTime(self, p: JsonObject) -> JsonObject:  # noqa: N802 - mirrors the op name
        which = p.get("which", "locator")
        display = p.get("display", "secondary")
        time = p.get("time")
        if which not in self.transport:
            raise HostError("which must be locator|cycleLeft|cycleRight", code="BAD_REQUEST")
        if display not in ("primary", "secondary"):
            raise HostError("display must be primary|secondary", code="BAD_REQUEST")
        if not isinstance(time, str) or not 0 < len(time) <= 32:
            raise HostError("time must be a non-empty string", code="BAD_REQUEST")
        before = self._time(self.transport[which], display)
        self.transport[which] = time if display == "primary" else _seconds_to_bars(time, self.tempo)
        return {"which": which, "display": display, "requested": time, "before": before}

    def _op_transport_setTempo(self, p: JsonObject) -> JsonObject:  # noqa: N802 - mirrors the op name
        bpm = self._num(p, "bpm")
        if not 20 <= bpm <= 300:
            raise HostError("bpm must be in [20,300]", code="BAD_REQUEST")
        before, self.tempo = self.tempo, float(bpm)
        return {"requested": bpm, "before": before}

    def _op_cmd_run(self, p: JsonObject) -> JsonObject:
        key = p.get("key")
        spec = COMMANDS.get(str(key))
        if spec is None:
            raise HostError(f"unknown command key {key}", code="NOT_FOUND")
        can = spec.key not in self.can_perform_false
        if not can and p.get("force") is not True:
            raise HostError(f"canPerform=false for {spec.category}/{spec.name}", code="CANNOT_PERFORM")
        self.fired.append(spec.key)
        self._apply_command(spec.key)
        return {
            "key": spec.key,
            "category": spec.category,
            "name": spec.name,
            "canPerform": can,
            "fired": self.fired.count(spec.key),
        }

    def _apply_command(self, key: str) -> None:
        if COMMANDS[key].command_class == "dialog" and key != "audio.detect_silence":
            self.pending_dialog = key
        elif key.startswith("transport."):
            self._apply_transport(key)
        else:
            self._apply_project(key)

    def _apply_project(self, key: str) -> None:
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
        cursor = self.transport["locator"]
        if key == "transport.start":
            self.playing = True
            self.position = _bars_to_beats(cursor)
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


def _bars_to_beats(time: str) -> float:
    bar, beat, sixteenth, ticks = (int(part) for part in time.replace(".", " ").split())
    return (bar - 1) * 4 + (beat - 1) + (sixteenth - 1) / 4 + ticks / 480


def _beats_to_bars(beats: float) -> str:
    bar, rest = divmod(beats, 4)
    beat, rest = divmod(rest, 1)
    sixteenth, rest = divmod(rest * 4, 1)
    return f"{int(bar) + 1}. {int(beat) + 1}. {int(sixteenth) + 1}.{round(rest * 120):>3}"


def _bars(time: str) -> tuple[int, ...]:
    return tuple(int(part) for part in time.replace(".", " ").split())


def _seconds_to_bars(time: str, tempo: float) -> str:
    """Convert ``h:mm:ss.mmm`` to a 4/4 bar string (the simulator assumes 4/4)."""
    hours, minutes, seconds = time.split(":")
    total = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    beats = total * tempo / 60
    return f"{int(beats // 4) + 1}. {int(beats % 4) + 1}. 1.  0"
