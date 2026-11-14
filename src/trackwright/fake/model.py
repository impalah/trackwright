"""State objects, constants and helpers shared by the simulator layers."""

from __future__ import annotations

from dataclasses import dataclass, field

from trackwright.jsontypes import JsonObject

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


# DirectAccess methods the script reports in capabilities.methods (TW-1408: same shape as the script)
DIRECT_ACCESS_METHODS = (
    "pm.getNumberOfPluginCollections",
    "pm.getPluginCollectionByIndex",
    "pm.getIndexOfDefaultPluginCollection",
    "pm.getIndexOfActivePluginCollection",
    "pm.trySetSlotPlugin",
    "pm.resetSlotPlugin",
    "activate",
    "deactivate",
    "update",
    "getBaseObjectID",
    "getNumberOfChildObjects",
    "getChildObjectID",
    "getObjectUniqueName",
    "getObjectTypeName",
    "getObjectUniqueIDString",
    "getObjectTitle",
    "getNumberOfParameters",
    "getParameterTagByIndex",
    "getParameterTitle",
    "getParameterProcessValue",
    "setParameterProcessValue",
    "getParameterDisplayValue",
    "getParameterDisplayUnits",
    "getParameterProcessValueType",
    "isParameterAutomatable",
    "convertParameterProcessValueToPlain",
    "convertParameterPlainToProcessValue",
    "getParameterEditLockState",
    "getParameterDefaultProcessValue",
    "getMixerChannelIndex",
    "getMixerChannelZone",
    "isMixerChannelVisible",
    "setParameterDisplayValue",
)


MAX_CHANNEL_TAGS = 16


def clamp_limit(value: float, maximum: int) -> int:
    """Like the script's ``clampLimit``: at least 1 (verified in Cubase: ``limit`` 0 returns one item)."""
    return 1 if value < 1 else min(int(value), maximum)
