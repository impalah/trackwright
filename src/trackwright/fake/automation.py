"""Automation controls and recording (TW-1206/1207)."""

from __future__ import annotations

from trackwright.commands import COMMANDS
from trackwright.errors import HostError
from trackwright.fake.editing import FakeEditing
from trackwright.fake.timeline import (
    _parse_seconds,
)
from trackwright.jsontypes import JsonObject


class FakeAutomation(FakeEditing):
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
        if display == "primary":
            self.transport[which] = time
        elif which == "locator":
            self.transport[which] = self._bars_at(_parse_seconds(time))
            self._cursor_moved()
        else:  # verified bug (TW-1211): locators set through the seconds display land elsewhere
            self.transport[which] = "1. 1. 1.  0"
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
        can = self._can(spec.key)
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
        elif key.startswith(("tool.", "edit.")) and self._apply_edit(key):
            return
        else:
            self._apply_project(key)
