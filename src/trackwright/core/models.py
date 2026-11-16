"""Structured outputs of the MCP tools (their JSON schemas are published to MCP clients)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trackwright.commands import CommandClass
from trackwright.jsontypes import JsonObject


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
    packaged_script_version: str | None = Field(default=None, description="the script this Trackwright installs")
    script_outdated: bool | None = Field(
        default=None,
        description="Cubase runs another script than the packaged one: "
        "install it (trackwright setup) and restart Cubase",
    )
    host_app: str | None
    host_version: str | None
    insert_slots: int | None
    mixer_access: bool
    transport_access: bool
    commands_bound: int | None
    writes_enabled: bool
    allowed_tracks: list[str]
    analysis_enabled: bool = Field(default=False, description="[analysis] enabled: audio files may be read")
    workspace_enabled: bool = Field(
        default=False, description="[workspace] enabled: the Trackwright/ folder may be written in the project folder"
    )


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
    track_uid: str | None = Field(
        default=None, description='"uid:<UID>" of the track: pass it as `track` when applying a dry run'
    )
    changes: list[Change]
    verified: bool | None = Field(description="all changes read back as requested (null in dry runs)")
    note: str | None = None


class InsertPluginOut(_Out):
    dry_run: bool
    track: str
    track_uid: str | None = Field(
        default=None, description='"uid:<UID>" of the track: pass it as `track` when applying a dry run'
    )
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
    position: str = Field(
        description="bar position, e.g. '9. 1. 1. 0' (bar. beat. 16th. tick), in the time signature at the cursor"
    )
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
    complete: bool | None = Field(
        default=None, description="playback reached the last point (false: stopped early, the curve is cut)"
    )
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


# ---------------------------------------------------------------------------- project properties (TW-1209)
class Signature(_Out):
    text: str = Field(description="as Cubase shows it, e.g. '3/4'")
    numerator: int | None
    denominator: int | None


class Span(_Out):
    active: bool | None
    start: str | None
    end: str | None


class Roll(_Out):
    active: bool | None
    length: str | None


class Metronome(_Out):
    active: bool | None
    click_level: str | None
    in_record: bool | None
    in_playback: bool | None


class ProjectOut(_Out):
    tempo_bpm: float | None
    signature: Signature | None = Field(description="time signature at the cursor (verified with 4/4 and 3/4)")
    cycle: Span
    punch_in: bool | None
    punch_out: bool | None
    punch_range: Span
    pre_roll: Roll
    post_roll: Roll
    metronome: Metronome
    precount: bool | None
    transport: Literal["stopped", "playing", "recording", "unknown"]
    time_formats: list[str | None] = Field(description="primary and secondary time displays")
    modes: dict[str, str | None] = Field(description="record and playback modes, as Cubase shows them")
    project_folders: list[str] | None = Field(
        description="folders of the open project(s), deduced from the audio files Cubase has open; "
        "null when not requested, empty when Cubase has no audio file open"
    )
    unavailable: dict[str, str] = Field(description="properties the Cubase API does not expose, and why")


# ---------------------------------------------------------------------------- range editing (TW-1211)
class RangeEditOut(_Out):
    dry_run: bool
    action: str
    start: str = Field(description="h:mm:ss.mmm")
    end: str
    length_seconds: float
    effect: str
    scope: str
    track: str | None = Field(default=None, description="the only track edited (single-track delete)")
    verify_track: str | None = Field(description="track whose event edges were probed to verify")
    applied: bool = False
    locators: list[str] = Field(default_factory=list, description="the range as bars, while editing")
    edges_before: list[str] = Field(default_factory=list, description="event edges (starts and ends) probed")
    edges_after: list[str] = Field(default_factory=list)
    undo_steps: int = Field(default=0, description="Undo steps that revert the edit in Cubase")
    verified: bool | None = None
    mismatches: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------- export (TW-1204)
class WorkspaceOut(_Out):
    action: Literal["status", "init", "record", "forget"]
    dry_run: bool
    enabled: bool = Field(description="[workspace] enabled: skills may write the folder")
    status: Literal["unknown_project", "absent", "planned", "created", "exists", "recorded", "forgotten"]
    project_folder: str | None = None
    path: str | None = Field(default=None, description="<project folder>/Trackwright")
    exists: bool = False
    missing: list[str] = Field(default_factory=list, description="folders 'init' would create (relative paths)")
    created: list[str] = Field(default_factory=list)
    has_state: bool = False
    owned: dict[str, int] = Field(default_factory=dict, description="items recorded in state.json, by skill:kind")
    items: list[JsonObject] = Field(default_factory=list, description="status: the items of state.json (first 200)")
    before: JsonObject | None = Field(default=None, description="record/forget: the item recorded under kind and key")
    after: JsonObject | None = Field(default=None, description="record: the item as it will be recorded")
    has_profile: bool = False
    profile: dict[str, str | int | None] | None = None
    notes: list[str] = Field(default_factory=list)


class RenderItemOut(_Out):
    file: str = Field(description="absolute path of the render")
    provenance: str = Field(description="its provenance file (.json)")
    skill: str
    run: str
    process: str
    parameters: JsonObject
    position: str = Field(description="project time of its first sample: import it there")
    position_seconds: float
    seconds: float
    sample_rate: int
    channels: int
    peak_dbfs: float | None
    replaces: str | None = Field(description="the track it replaces (to mute after the import)")
    source: str
    imported_on: str | None = Field(default=None, description="uid of the track it was imported on (state.json)")
    track_present: bool | None = Field(default=None, description="that track is still in the project")
    problems: list[str] = Field(default_factory=list, description="render or source changed, source gone")


class RenderOut(_Out):
    action: Literal["render", "list"]
    dry_run: bool
    status: Literal["planned", "done", "listed"]
    workspace: str | None = Field(default=None, description="<project folder>/Trackwright")
    render: RenderItemOut | None = Field(default=None, description="render: what was (or would be) written")
    renders: list[RenderItemOut] = Field(default_factory=list, description="list: the workspace's renders")
    instructions: str | None = None
    notes: list[str] = Field(default_factory=list)


class DeliverySourceOut(_Out):
    url: str
    retrieved: str
    covers: list[str]
    quote: str


class DeliveryProfileOut(_Out):
    name: str
    origin: Literal["built-in", "show/episode"]
    title: str
    loudness_lufs: float | None
    loudness_tolerance_lu: float | None
    true_peak_dbtp: float | None
    normalizes: bool | None
    normalization_lufs: float | None
    codecs: list[str]
    channels: list[str]
    sample_rates: list[int]
    bitrate_kbps: int | None
    min_bitrate_kbps: int | None
    max_bitrate_kbps: int | None
    max_file_mb: float | None
    requirement: str
    notes: str
    sources: list[DeliverySourceOut] = Field(description="where every value comes from")


class ProfileOut(_Out):
    action: Literal["resolve", "shows", "delivery", "write_show", "write_episode"]
    dry_run: bool
    status: Literal["read", "planned", "written"]
    shows_dir: str = Field(description="where show profiles live")
    show: str | None = None
    show_path: str | None = None
    episode_path: str | None = Field(default=None, description="<project>/Trackwright/profile.toml")
    settings: JsonObject | None = Field(default=None, description="resolve: built-in < show < episode")
    episode: JsonObject | None = Field(
        default=None,
        description="resolve: the episode profile as stored (start from it to write_episode, so the show's "
        "values are not copied into the episode)",
    )
    origins: dict[str, str] = Field(default_factory=dict, description="resolve: dotted setting -> layer")
    protected: list[JsonObject] = Field(default_factory=list, description="resolve: the episode's protected ranges")
    delivery: list[DeliveryProfileOut] = Field(
        default_factory=list, description="resolve: the targets; delivery: every profile available"
    )
    shows: list[str] = Field(default_factory=list, description="shows: the show profiles found")
    before: str | None = Field(default=None, description="write: the file now (null if new)")
    after: str | None = Field(default=None, description="write: the file as it would be written")
    changed: bool | None = None
    notes: list[str] = Field(default_factory=list)


class AudioSourceOut(_Out):
    """Which audio an analysis measured (TW-1608): its numbers hold for this version of the file only."""

    file: str
    size_bytes: int
    modified: str = Field(description="file modification time (UTC, ISO 8601)")
    sha256: str
    start: str = Field(description="project time of the file's first sample")
    end: str = Field(description="project time of its last sample")
    start_seconds: float
    end_seconds: float
    project_saved_after: bool | None = Field(
        description="the project file (.cpr) was saved after this file was written: if the project changed "
        "(cuts, processing, automation), export again; null when unknown. Unsaved changes cannot be seen."
    )


AnalysisCacheState = Literal["hit", "stored", "off"]


class TrackEdgesOut(_Out):
    track: str
    track_uid: str
    start: str = Field(description="where the probe started (project time)")
    end: str | None = Field(description="where it stopped looking; null = to the last edge")
    edges: list[str] = Field(description="event edges (starts and ends together), in order, h:mm:ss.mmm")
    edges_seconds: list[float]
    first: str | None = Field(description="the first edge: where the track's audio starts (but see notes)")
    last: str | None = Field(description="the last edge: where it ends")
    complete: bool = Field(description="every edge up to end (or the last one) was found")
    notes: list[str] = Field(default_factory=list)


class QcItemOut(_Out):
    id: str = Field(description="what was checked, e.g. loudness, true_peak, codec, long_pauses")
    kind: Literal["check", "warning", "manual"] = Field(
        description="check: objective, against a target; warning: worth a listen; manual: cannot be verified here"
    )
    status: Literal["pass", "fail", "warn", "info"]
    title: str
    target: str | None = Field(default=None, description="the delivery profile it was checked against")
    measured: str | None = None
    expected: str | None = None
    source: str | None = Field(default=None, description="the platform's page the expected value comes from")
    at: list[str] = Field(default_factory=list, description="project times concerned (h:mm:ss.mmm)")


class QcMomentOut(_Out):
    at: str = Field(description="project time to listen at")
    at_seconds: float
    why: str


class QcOut(_Out):
    file: str
    format: str
    subtype: str
    codec: str | None = Field(description="from the extension: wav, mp3, aac (.m4a), flac…")
    sample_rate: int
    channels: int
    seconds: float
    bitrate_kbps: float | None = Field(description="average, for compressed files (size over duration)")
    integrated_lufs: float | None
    loudness_range_lu: float | None
    true_peak_dbtp: float | None
    sample_peak_dbfs: float | None
    targets: list[str] = Field(description="the delivery profiles checked against")
    verdict: Literal["pass", "fail"] = Field(description="fail when any objective check failed")
    failed: int
    warnings: int
    items: list[QcItemOut]
    moments: list[QcMomentOut] = Field(description="where to listen, in project time")
    source: AudioSourceOut | None = None
    report: list[str] = Field(default_factory=list, description="the report files written (JSON and Markdown)")
    notes: list[str] = Field(default_factory=list)


class DeliveryPlanOut(_Out):
    target: str = Field(description="the delivery profile")
    codec: str = Field(description="the format to deliver: mp3, aac, wav…")
    target_lufs: float | None
    tolerance_lu: float | None
    ceiling_dbtp: float | None
    source: str | None = Field(description="the platform's page for the loudness and the ceiling")
    master: str = Field(description="the measured master (an export of the mix)")
    measured_lufs: float
    measured_true_peak: float
    stereo_out: str = Field(description="the output channel the plan acts on")
    fader_now_db: float
    gain_db: float = Field(description="change to the Stereo Out fader")
    fader_db: float = Field(description="the fader setting to apply (at most +6.02 dB)")
    reachable: bool = Field(description="the target is within the fader's range")
    predicted_lufs: float
    predicted_true_peak: float = Field(description="of the delivered file before any limiter (encoding included)")
    limiter: bool = Field(description="a limiter is needed to keep the ceiling")
    threshold_db: float | None = Field(description="its threshold: ceiling minus intersample and encoding margins")
    peak_reduction_db: float | None
    limiter_slot: int | None = Field(description="post-fader slot (7 or 8) for it: free, or holding a limiter")
    limiter_in_slot: str | None = Field(description="the plugin already in that slot, if any")
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DuckSpanOut(_Out):
    start: str = Field(description="the music is at depth_db from here (the first word)")
    end: str = Field(description="to here (the end of the hold)")
    start_seconds: float
    end_seconds: float
    depth_db: float
    fall_from: float = Field(description="where the music starts going down (project seconds)")
    rise_to: float = Field(description="where it is back at full level")


class DuckMomentOut(_Out):
    at: float = Field(description="project seconds")
    why: str


class DuckingPlanOut(_Out):
    parameters: dict[str, float]
    changed: list[list[float]] | None = Field(
        default=None, description="with previous: the spans (project seconds) where the edit changes the music"
    )
    moments: list[DuckMomentOut] = Field(
        default_factory=list, description="where to preview: each page span's first word and its recovery"
    )
    speech_regions: int = Field(description="speech regions found in the voice export")
    protected: list[list[float]] = Field(description="protected ranges kept at full level (project seconds)")
    total: int = Field(description="ducked spans")
    ducked_seconds: float
    spans: list[DuckSpanOut] = Field(description="paged with offset and limit")
    points: int = Field(description="points of the gain envelope")
    notes: list[str] = Field(default_factory=list)


class PreviewOut(_Out):
    dry_run: bool
    status: Literal["planned", "done"]
    file: str = Field(description="the preview file (Trackwright/previews/), to listen to")
    start: str = Field(description="project time of its first sample")
    end: str
    seconds: float
    sources: list[str] = Field(description="the files mixed, with their gain")
    peak_dbfs: float | None = None
    notes: list[str] = Field(default_factory=list)


class SpeechRegionOut(_Out):
    start: str = Field(description="project time, h:mm:ss.mmm")
    end: str
    start_seconds: float
    end_seconds: float
    seconds: float
    level_db: float = Field(description="mean level of the speech band (dBFS)")
    confidence: float = Field(description="0..1, how far above the noise floor (30 dB or more is 1)")


class SpeechOut(_Out):
    file: str
    sample_rate: int
    channels: int
    seconds: float
    start: str = Field(description="project time of the file's first sample")
    start_seconds: float
    noise_floor_db: float | None = Field(description="speech band, 10th percentile; null for a silent file")
    on_threshold_db: float | None
    off_threshold_db: float | None
    contrast_db: float | None = Field(description="90th minus 10th percentile; under on_db no clear speech")
    speech_level_db: float | None = Field(description="typical speech level (duration-weighted median)")
    faint_dropped: int = Field(description="fragments dropped for being faint_db below the typical speech level")
    criteria: dict[str, float]
    total: int = Field(description="number of speech regions")
    speech_seconds: float
    regions: list[SpeechRegionOut] = Field(description="in project seconds, ordered; paged with offset and limit")
    source: AudioSourceOut | None = Field(default=None, description="the file measured and its project range")
    cache: AnalysisCacheState = Field(
        default="off", description="hit: from Trackwright/analysis/; stored: computed and cached; off: no cache"
    )
    notes: list[str] = Field(default_factory=list)


class LoudnessOut(_Out):
    file: str
    format: str
    subtype: str
    sample_rate: int
    channels: int
    seconds: float
    integrated_lufs: float | None = Field(description="BS.1770 integrated loudness (gated); null for silence")
    momentary_max_lufs: float | None = Field(description="loudest 400 ms block")
    short_term_max_lufs: float | None = Field(description="loudest 3 s window")
    loudness_range_lu: float | None = Field(description="EBU Tech 3342 loudness range; null under ~3 s")
    sample_peak_dbfs: float | None
    true_peak_dbtp: float | None = Field(description="peak of the signal oversampled 4x")
    source: AudioSourceOut | None = Field(default=None, description="the file measured and its project range")
    cache: AnalysisCacheState = Field(
        default="off", description="hit: from Trackwright/analysis/; stored: computed and cached; off: no cache"
    )
    notes: list[str] = Field(default_factory=list)


class SilenceOut(_Out):
    start: str = Field(description="project time, h:mm:ss.mmm (padding already applied)")
    end: str
    start_seconds: float
    end_seconds: float
    seconds: float
    level_db: float | None = Field(description="mean level of the span in dBFS; null for exact digital silence")
    digital: bool = Field(description="the whole span is exact zeros (no audio there in the project)")


class AnalysisOut(_Out):
    file: str
    format: str
    subtype: str = Field(description="sample format, e.g. FLOAT, PCM_24")
    sample_rate: int
    channels: int
    seconds: float = Field(description="duration of the file")
    start: str = Field(description="project time of the file's first sample (the export's left locator)")
    start_seconds: float
    noise_floor_db: float | None = Field(description="10th percentile of 20 ms levels, digital silence excluded")
    threshold_db: float | None = Field(description="threshold used; null when only digital silence counted")
    quiet_sound_db: float | None = Field(
        description="10th percentile of the levels above the threshold: the quietest part of the sound (soft "
        "speech); a noise gate threshold belongs between noise_floor_db and this value"
    )
    sound_db: float | None = Field(description="median level above the threshold: the typical level of the sound")
    peak_db: float | None
    rms_db: float | None = Field(description="RMS of the whole file")
    criteria: dict[str, float | None]
    total: int = Field(description="number of silences found")
    total_seconds: float = Field(description="their total duration")
    silences: list[SilenceOut] = Field(description="in project seconds, ordered; paged with offset and limit")
    source: AudioSourceOut | None = Field(default=None, description="the file measured and its project range")
    cache: AnalysisCacheState = Field(
        default="off", description="hit: from Trackwright/analysis/; stored: computed and cached; off: no cache"
    )
    notes: list[str] = Field(default_factory=list)


class ExportedFileOut(_Out):
    path: str
    size_bytes: int
    duration_seconds: float | None
    difference_seconds: float | None = Field(default=None, description="duration minus the expected one")
    duration_matches: bool | None = Field(
        description="the duration equals the range: ±0.15 s, or ±(0.5 s + 0.2 %) for MP3/AAC/OGG (estimated)"
    )


class SoloChangeOut(_Out):
    track_uid: str
    name: str
    before: bool = Field(description="solo before the export")
    during: bool = Field(description="solo while exporting")
    restored: bool | None = Field(default=None, description="read back after confirm or cancel")


class ExportOut(_Out):
    phase: Literal["start", "confirm", "cancel"]
    status: Literal["planned", "awaiting_user", "done", "not_found", "cancelled"]
    dry_run: bool
    start: str | None = Field(description="range start (h:mm:ss.mmm)")
    end: str | None
    expected_seconds: float | None
    folder: str | None = Field(description="where Cubase proposes to export (<project folder>/Mixdown)")
    since: float | None = Field(description="pass it back to the confirm phase")
    files: list[ExportedFileOut] = Field(default_factory=list)
    solo: list[SoloChangeOut] = Field(
        default_factory=list,
        description="solo flags the start phase changed so only the given tracks are exported; confirm and cancel "
        "put them back",
    )
    solo_restored: bool | None = Field(default=None, description="every changed solo read back as before")
    verified: bool | None = None
    instructions: str | None = None
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------- save (TW-1202)
class ProjectFileOut(_Out):
    name: str
    size_bytes: int
    modified: str = Field(description="local time, YYYY-MM-DD HH:MM:SS")


class SaveOut(_Out):
    mode: Literal["save", "new_version"]
    dry_run: bool
    status: Literal["planned", "done", "fired", "awaiting_user"] = Field(
        description="'fired': requested but not verifiable (unknown project folder)"
    )
    folder: str | None = Field(description="project folder (deduced from the audio files Cubase has open)")
    files_before: list[ProjectFileOut] = Field(default_factory=list, description=".cpr files, newest first")
    saved: ProjectFileOut | None = Field(default=None, description="the .cpr written by this save")
    verified: bool | None = None
    instructions: str | None = None
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------- import (TW-1203)
class ImportOut(_Out):
    phase: Literal["start", "confirm"]
    status: Literal["planned", "awaiting_user", "done", "not_found"]
    dry_run: bool
    track: str
    position: str = Field(description="where the audio goes (h:mm:ss.mmm)")
    file: str | None = Field(description="the file to pick in the dialog, when given")
    expected_seconds: float | None = Field(description="duration of that file (afinfo)")
    since: float | None = Field(description="pass it back to the confirm phase")
    edges_found: list[str] = Field(default_factory=list, description="event edges at the start and end")
    copied_to_project: list[str] = Field(default_factory=list, description="new files in <project>/Audio")
    render: str | None = Field(default=None, description="the file is a Trackwright render: its provenance file")
    owned: bool | None = Field(
        default=None, description="confirm of a render: the track was recorded in state.json as the skill's"
    )
    verified: bool | None = None
    instructions: str | None = None
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------- project settings (TW-1210)
class SettingChange(_Out):
    setting: str
    before: bool | int | None
    requested: bool | int
    after: bool | int | None
    verified: bool | None


class ProjectSettingsOut(_Out):
    dry_run: bool
    changes: list[SettingChange]
    verified: bool | None
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------- plugin presets (TW-1205)
class PresetStepOut(_Out):
    dry_run: bool
    track: str
    slot: int
    plugin: str
    direction: Literal["next", "previous"]
    status: Literal["planned", "done", "awaiting_user"] = "planned"
    changed: dict[str, str] = Field(default_factory=dict, description="parameter: 'before -> after'")
    instructions: str | None = None
    verified: bool | None = Field(description="some parameter changed (the preset was applied)")
    notes: list[str] = Field(default_factory=list)
