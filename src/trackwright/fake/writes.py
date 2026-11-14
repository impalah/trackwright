"""Write operations of the script."""

from __future__ import annotations

from trackwright.errors import HostError
from trackwright.fake.automation import FakeAutomation
from trackwright.fake.model import PLUGINS, Param
from trackwright.jsontypes import JsonObject


class FakeWrites(FakeAutomation):
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
