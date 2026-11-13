"""Change project and transport settings (TW-1210) through Cubase's Transport and Metronome objects.

Verified in Cubase Elements 15.0.30 (experiments/tw1210): every switch below and the click level accept a
DirectAccess write and read back; the time signature does not (its value is outside [0, 1]).
"""

from __future__ import annotations

from typing import Any

from trackwright.core.base import MIXER, operation
from trackwright.core.models import ProjectSettingsOut, SettingChange
from trackwright.core.project import ProjectMixin
from trackwright.errors import NotFoundError, PreconditionFailedError

JsonObject = dict[str, Any]
SWITCHES: dict[str, tuple[str, str]] = {  # setting -> (object type, parameter title)
    "cycle": ("Transport", "cycle"),
    "metronome": ("Transport", "metronomeOn"),
    "precount": ("Transport", "precountOn"),
    "punch_in": ("Transport", "punchIn"),
    "punch_out": ("Transport", "punchOut"),
    "pre_roll": ("Transport", "usePreRoll"),
    "post_roll": ("Transport", "usePostRoll"),
    "click_in_playback": ("Metronome", "tickInPlayback"),
    "click_in_record": ("Metronome", "tickInRecord"),
}
CLICK_LEVEL = ("Metronome", "clickLevel")


class SettingsMixin(ProjectMixin):
    @operation
    def set_project(self, settings: dict[str, bool | int], *, dry_run: bool = True) -> ProjectSettingsOut:
        if not settings:
            raise PreconditionFailedError("give at least one setting to change", code="BAD_REQUEST")
        unknown = sorted(set(settings) - set(SWITCHES) - {"click_level"})
        if unknown:
            raise PreconditionFailedError(f"unknown settings {unknown}", code="BAD_REQUEST",
                                          details={"known": [*SWITCHES, "click_level"]})  # fmt: skip
        level = settings.get("click_level")
        if level is not None and (isinstance(level, bool) or not 0 <= int(level) <= 127):
            raise PreconditionFailedError("click_level must be 0..127", code="OUT_OF_RANGE")
        objects = self._studio_objects()
        params = {kind: self._params_by_title(objects.get(kind)) for kind in ("Transport", "Metronome")}
        plan: list[tuple[str, int, int, float, bool | int | None]] = []  # name, object, tag, value, before
        for name, requested in settings.items():
            kind, title = SWITCHES.get(name, CLICK_LEVEL)
            param = params[kind].get(title)
            if param is None or objects.get(kind) is None:
                raise NotFoundError(f"Cubase does not expose {kind}/{title}", code="UNAVAILABLE")
            value = int(requested) / 127 if name == "click_level" else (1.0 if requested else 0.0)
            plan.append((name, int(objects[kind]), int(param["tag"]), value, self._setting_value(name, param)))
        out = ProjectSettingsOut(
            dry_run=dry_run,
            changes=[
                SettingChange(setting=n, before=b, requested=settings[n], after=None, verified=None)
                for n, _o, _t, _v, b in plan
            ],
            verified=None,
        )
        if dry_run:
            return out
        self.policy.check_project_write()
        for change, (name, oid, tag, value, _before) in zip(out.changes, plan, strict=True):
            self.call("da.param.set", {"id": oid, "tag": tag, "value": value, **MIXER})
            change.after = self._read_setting(name, oid, tag, change.requested)
            change.verified = change.after == change.requested
        out.verified = all(c.verified for c in out.changes)
        return out

    def _read_setting(self, name: str, oid: int, tag: int, wanted: bool | int) -> bool | int:
        def read() -> bool | int:
            return self._setting_value(name, self.call("da.param.get", {"id": oid, "tag": tag, **MIXER}))

        return self.wait_until(read, wanted.__eq__)

    @staticmethod
    def _setting_value(name: str, param: JsonObject) -> bool | int:
        process = float(param.get("process") or 0)
        return round(process * 127) if name == "click_level" else process >= 0.5
