"""Structured outputs of the MCP tools (their JSON schemas are published to MCP clients)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trackwright.commands import CommandClass


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------- shared pieces
class Value(_Out):
    process: float | None = Field(description="normalized value as stored by Cubase")
    display: str | None = Field(description="value as Cubase shows it (localized)")


class TrackInfo(_Out):
    track: str = Field(description='selector to reuse in other tools: "uid:<UID>" (stable across restarts)')
    uid: str
    name: str
    type: str = Field(description="AudioChannel, Synth, GroupChannel, OutputChannel...")
    ref: str = Field(description="opaque reference, valid only in the current script session")
    mixer_index: int | None
    selected: bool
    volume: Value | None
    mute: bool | None
    solo: bool | None
    input: str | None
    output: str | None


class ParameterInfo(_Out):
    tag: int = Field(description="stable identifier of the parameter for a given plugin/channel")
    title: str = Field(description="localized title")
    process: float | None
    display: str | None
    units: str | None
    plain: float | None = Field(description="value in real units (dB, Hz...) when the plugin provides it")
    value_type: str | None
    automatable: bool | None
    edit_locked: bool | None


class Change(_Out):
    tag: int
    title: str
    before: Value
    requested: float | str
    after: Value | None
    verified: bool | None


# ---------------------------------------------------------------------------- read tools
class StatusOut(_Out):
    connected: bool
    simulated: bool = Field(description="true when answering from the built-in simulator, not Cubase")
    session: str | None
    script_version: str | None
    host_app: str | None
    host_version: str | None
    insert_slots: int | None
    mixer_access: bool
    transport_access: bool
    commands_bound: int | None
    writes_enabled: bool
    allowed_tracks: list[str]


class TrackListOut(_Out):
    total: int
    tracks: list[TrackInfo]
    note: str = "tracks without a mixer channel (marker, folder) are not listed"


class Section(_Out):
    kind: str = Field(description="Inserts, Strips, Sends, Panner...")
    title: str
    ref: str


class SelectedChannelOut(_Out):
    track: TrackInfo | None = Field(description="null when the selected track has no mixer channel or none is selected")
    sections: list[Section]


class PluginInSlot(_Out):
    name: str
    plugin_uid: str
    ref: str


class SlotInfo(_Out):
    index: int
    empty: bool
    ref: str
    plugin: PluginInSlot | None


class InsertsOut(_Out):
    track: TrackInfo
    slots: list[SlotInfo]


class PluginEntry(_Out):
    name: str
    vendor: str
    version: str
    uid: str
    sub_categories: str


class PluginCatalogOut(_Out):
    collection: str | None
    total: int
    matched: int
    offset: int
    items: list[PluginEntry]


class ParametersOut(_Out):
    target: str
    target_ref: str
    target_name: str
    total: int
    offset: int
    scanned: int
    items: list[ParameterInfo]
    next_offset: int = Field(description="offset to pass to get the following parameters")
    truncated: bool = Field(description="true when more parameters remain after next_offset")


class ParameterOut(_Out):
    target: str
    target_ref: str
    target_name: str
    parameter: ParameterInfo


class TimePosition(_Out):
    time: str
    format: str | None


class TransportOut(_Out):
    cursor: TimePosition
    cycle_left: TimePosition | None
    cycle_right: TimePosition | None
    tempo_bpm: float | None


class ChangeEvent(_Out):
    kind: str
    tag: int | None
    ref: str | None
    title: str | None
    still_valid: bool | None = Field(description="null when the object was not checked (see unchecked)")


class ChangesOut(_Out):
    events: list[ChangeEvent]
    dropped: int
    unchecked: int = Field(description="events whose object was not looked up (only the first 20 objects are)")
    advice: str


# ---------------------------------------------------------------------------- write tools
class WriteOut(_Out):
    dry_run: bool
    target: str
    changes: list[Change]
    verified: bool | None = Field(description="all changes read back as requested (null in dry runs)")
    note: str | None = None


class InsertPluginOut(_Out):
    dry_run: bool
    track: str
    slot: int
    plugin_uid: str
    plugin_name: str
    inserted: bool | None
    verified: bool | None
    plugin_ref: str | None


class SelectOut(_Out):
    selected_before: str | None
    selected_after: str | None
    verified: bool


class PositionOut(_Out):
    dry_run: bool
    which: str
    requested: str
    before: TimePosition | None
    after: TimePosition | None
    verified: bool | None
    note: str | None = None


class TempoOut(_Out):
    dry_run: bool
    before: float | None
    requested: float
    after: float | None
    verified: bool | None


CommandStatus = Literal["planned", "fired", "awaiting_user", "pending_confirmation", "done", "not_found"]


class CommandOut(_Out):
    dry_run: bool
    key: str
    category: str
    name: str
    command_class: CommandClass
    can_perform: bool | None
    status: CommandStatus
    verified: bool | Literal["not_observable"] | None
    instructions: str | None = None
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


# ---------------------------------------------------------------------------- automation (TW-1207)
class AutomationPoint(BaseModel):
    """One point of an automation curve (input): give ``plain`` (real units) or ``value`` (normalized)."""

    model_config = ConfigDict(extra="forbid")
    position: str = Field(description="bar position, e.g. '9. 1. 1. 0' (bar. beat. 16th. tick); 4/4 assumed")
    plain: float | None = Field(
        default=None, description="value in real units (dB, Hz...), converted exactly by Cubase. Preferred."
    )
    value: float | None = Field(default=None, ge=0, le=1, description="normalized value 0..1 (use plain instead)")

    @model_validator(mode="after")
    def _one_value(self) -> AutomationPoint:
        if (self.plain is None) == (self.value is None):
            raise ValueError("give exactly one of plain or value")
        return self


class AutomationTarget(_Out):
    parameter: str = Field(description="key to pass to cubase_record_automation, e.g. 'volume' or 'insert1.p1'")
    title: str | None = Field(description="the Cubase parameter bound to it, e.g. 'Compressor / Threshold'")
    value: float | None
    display: str | None = Field(description="current value as Cubase shows it, in real units (dB, Hz, L/R...)")
    available: bool = Field(description="false when nothing is bound (empty insert slot, unassigned quick control)")
    converts_units: bool = Field(description="plain values (real units) are accepted for this parameter")


class AutomationTargetsOut(_Out):
    track: str
    targets: list[AutomationTarget]
    note: str = "the track was selected: automation controls follow the selected track"


class ResolvedPoint(_Out):
    position: str
    value: float = Field(description="normalized value written")
    plain: float | None = Field(description="the value in real units, when given or converted")


class ConvertOut(_Out):
    track: str
    parameter: str
    title: str | None
    plain: float
    value: float = Field(description="normalized value 0..1")
    note: str = "exact conversion by Cubase (convertParameterPlainToProcessValue / ProcessValueToPlain)"


class WrittenPoint(_Out):
    position: str
    value: float
    display: str | None


class AutomationRecordOut(_Out):
    dry_run: bool
    track: str
    parameter: str
    title: str | None
    value_before: float | None
    display_before: str | None
    start: str = Field(description="where playback starts (pre-roll before the first point)")
    points: list[ResolvedPoint] = Field(description="the curve, with the normalized value used for each point")
    written: list[WrittenPoint]
    verified: bool | None = Field(description="a read-back pass followed the curve (null when not verified)")
    mismatches: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------- lifecycle (TW-1201)
class LaunchOut(_Out):
    status: Literal["planned", "already_running", "running_without_script", "ready", "awaiting_user"]
    app: str
    dry_run: bool
    process_running: bool
    script_version: str | None
    project: str | None
    instructions: str | None = None
