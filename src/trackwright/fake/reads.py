"""Direct and DirectAccess read operations: the complete simulator."""

from __future__ import annotations

from trackwright.commands import COMMANDS
from trackwright.cubase import SCRIPT_VERSION
from trackwright.errors import HostError
from trackwright.fake.model import DIRECT_ACCESS_METHODS, MAX_CHANNEL_TAGS, PLUGINS, clamp_limit
from trackwright.fake.timeline import (
    _beats_to_bars,
)
from trackwright.fake.writes import FakeWrites
from trackwright.jsontypes import JsonObject


class FakeCubase(FakeWrites):
    """The simulated Cubase: core state and helpers, editing model, automation, writes and reads (TW-1414).

    Each layer subclasses the previous one (core → editing → automation → writes → reads), so a layer can use
    whatever the earlier ones define.
    """

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
            # diagnostics the script reports too (TW-1408: same shape as the script)
            "idleTicks": 0,
            "deviceIdleTicks": 0,
            "sysexIn": len(self.calls),
            "framesRejected": 0,
            "pendingAssemblies": 0,
            "changedObjects": 0,
            "changedParameters": 0,
            "removedObjects": 0,
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
            # fields the script reports too (TW-1408: same shape as the script)
            "makeDirectAccess": True,
            "directAccessError": None,
            "mixerDirectAccessError": None,
            "panel": {"enabled": True, "errors": []},
            "automationControls": {"enabled": True, "count": len(self.AUTO_KEYS), "errors": []},
            "pageMOnIdle": True,
            "methods": dict.fromkeys(DIRECT_ACCESS_METHODS, True),
            "pluginManager": True,
            "simulated": True,
        }
        return {"capabilities": caps, "host": self._host()}

    def _op_events(self, _p: JsonObject) -> JsonObject:
        events, self.events = self.events, []
        return {"events": events, "dropped": 0, "lastSeq": self.event_seq, "idleTicks": 0, "ms": 0}

    def _op_transport_get(self, _p: JsonObject) -> JsonObject:
        if self.playing:  # verified: the cursor position is reported while playing
            self.position += self.beats_per_poll
            self.transport["locator"] = _beats_to_bars(self.position, self.meter)
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
        limit = clamp_limit(self._num(p, "limit", 20), 50)
        items = [self._describe(self.objects[c]) | {"index": i} for i, c in enumerate(obj.children) if i >= offset][
            :limit
        ]
        return {"id": obj.id, "total": len(obj.children), "offset": offset, "items": items}

    def _op_da_params(self, p: JsonObject) -> JsonObject:
        obj = self._live(int(self._num(p, "id")))
        offset = int(self._num(p, "offset", 0))
        limit = clamp_limit(self._num(p, "limit", 10), 25)
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
        limit = clamp_limit(self._num(p, "limit", 16), 32)
        tags = p.get("tags") or [1024, 4000, 1025, 1027, 1028, 4101, 4102]
        if len(tags) > MAX_CHANNEL_TAGS:  # like script 1.6.0 (S-03)
            raise HostError(f"at most {MAX_CHANNEL_TAGS} tags", code="BAD_REQUEST")
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
                # verified in Cubase (2026-11-14): a missing tag reads as process -1 and an empty display, with
                # the title of another parameter ("Nombre"); the script passes it through
                else {"title": "Nombre", "display": "", "process": -1}
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
        limit = clamp_limit(self._num(p, "limit", 20), 40)
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
        return {"canPerform": {k: self._can(k) for k in keys if k in COMMANDS}}
