"""Step through a plugin's presets (TW-1205).

Verified in Cubase Elements 15.0.30 (experiments/tw1205): the slot's "Edición" parameter opens the plugin
editor; ``Preset / Next`` and ``Previous`` act on that editor only once the user has clicked on its window
(keyboard focus), and from then on also after closing and reopening it through the API; they do nothing
when the editor is closed or no preset is loaded. The result is checked by comparing the plugin's
parameters. Presets cannot be chosen or read by name.
"""

from __future__ import annotations

from typing import Any, Literal

from trackwright.core.base import MIXER, ServiceBase, operation
from trackwright.core.models import PresetStepOut
from trackwright.core.refs import TrackSelector
from trackwright.errors import PreconditionFailedError

JsonObject = dict[str, Any]
TAG_EDIT = 4101
METERS = ("Vu", "Gain Red", "Max", "Gain Reduction", " PH", "Meter")
KEYS = {"next": "preset.next", "previous": "preset.previous"}
EDITOR_SETTLE_SECONDS = 1.0


class PresetMixin(ServiceBase):
    def _plugin_values(self, plugin: int) -> dict[str, tuple[float, str]]:
        values: dict[str, tuple[float, str]] = {}
        offset = 0
        while True:
            page = self.call("da.params", {"id": plugin, "offset": offset, "limit": 25, **MIXER})
            for param in page.get("items", []):
                title = str(param.get("title"))
                if title and not any(m in title for m in METERS):
                    values[title] = (float(param.get("process") or 0), str(param.get("display")))
            offset += len(page.get("items", []))
            if not page.get("items") or offset >= int(page.get("total", 0)):
                return values

    def _editor_open(self, slot: int) -> bool:
        return float(self.call("da.param.get", {"id": slot, "tag": TAG_EDIT, **MIXER}).get("process") or 0) >= 0.5

    def _set_editor(self, slot: int, open_: bool) -> None:
        self.call("da.param.set", {"id": slot, "tag": TAG_EDIT, "value": 1.0 if open_ else 0.0, **MIXER})
        self.wait_until(lambda: self._editor_open(slot), open_.__eq__)

    @operation
    def plugin_preset(
        self, track: str, slot: int, direction: Literal["next", "previous"], *, dry_run: bool = True
    ) -> PresetStepOut:
        if direction not in KEYS:
            raise PreconditionFailedError("direction must be 'next' or 'previous'", code="BAD_REQUEST")
        item = self.resolve_track(TrackSelector.parse(track))
        name = self.track_info(item).name
        slot_obj = self.insert_slot(item, slot)
        plugin = self.resolve_target(item, f"insert:{slot}")
        out = PresetStepOut(dry_run=dry_run, track=name, slot=slot, plugin=str(plugin.get("title")),
                            direction=direction, verified=None)  # fmt: skip
        out.notes.append("the plugin's editor is opened for the command and closed again if it was closed")
        if dry_run:
            return out
        self.policy.check_track(name)
        slot_id, plugin_id = int(slot_obj["id"]), int(plugin["id"])
        before = self._plugin_values(plugin_id)
        was_open = self._editor_open(slot_id)
        if not was_open:
            self._set_editor(slot_id, True)
            self._sleep(EDITOR_SETTLE_SECONDS)
        self.call("cmd.run", {"key": KEYS[direction]})
        after = self.wait_until(lambda: self._plugin_values(plugin_id), lambda now: now != before)
        out.changed = {
            t: f"{before[t][1]} -> {after[t][1]}" for t in before if t in after and after[t][0] != before[t][0]
        }
        out.verified = bool(out.changed)
        if not out.changed:
            out.status = "awaiting_user"  # the editor stays open so that the user can click on it
            out.instructions = (
                f"The {out.plugin} window is open in Cubase. Click once on an empty area of it (Cubase needs it to "
                "have the keyboard focus; only the first time), make sure a preset is loaded in its preset bar, "
                "then call this tool again."
            )
            return out
        out.status = "done"
        if not was_open:
            self._set_editor(slot_id, False)
        other = "previous" if direction == "next" else "next"
        out.notes.append(f"the opposite step ('{other}') returns to the previous values")
        return out
