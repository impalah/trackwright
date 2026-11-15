"""The Trackwright MCP server: tool registration on top of :class:`~trackwright.core.service.CubaseService`.

Every tool is a thin async wrapper: it runs the blocking service call in a worker thread and turns
:class:`~trackwright.errors.TrackwrightError` into an MCP tool error ``"CODE: message"`` so the
model can read it and correct itself.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated, Any, Literal

import anyio.to_thread
from loguru import logger
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from trackwright import SERVER_NAME, __version__
from trackwright.core.models import (
    AnalysisOut,
    AutomationPoint,
    AutomationRecordOut,
    AutomationTargetsOut,
    ChangesOut,
    CommandOut,
    ConvertOut,
    ExportOut,
    ImportOut,
    InsertPluginOut,
    InsertsOut,
    LaunchOut,
    LoudnessOut,
    ParameterOut,
    ParametersOut,
    PluginCatalogOut,
    PositionOut,
    PresetStepOut,
    ProfileOut,
    ProjectOut,
    ProjectSettingsOut,
    RangeEditOut,
    RenderOut,
    SaveOut,
    SelectedChannelOut,
    SelectOut,
    SpeechOut,
    StatusOut,
    TempoOut,
    TrackEdgesOut,
    TrackListOut,
    TransportOut,
    WorkspaceOut,
    WriteOut,
)
from trackwright.core.service import CubaseService
from trackwright.errors import TrackwrightError

INSTRUCTIONS = """\
Trackwright controls a running Cubase through its MIDI Remote API.

Rules for using these tools:
- Designate tracks with the `track` selector: "selected", "uid:<UID>" (stable, preferred) or an exact name.
  Take uids from cubase_list_tracks. Object `ref`s are only valid until Cubase reloads the script.
  When applying a dry run, pass the `track_uid` it returned: "selected" may point elsewhere by then.
- Every tool that modifies the project has `dry_run` (default true). First call it with dry_run=true,
  show the plan to the user, and only after the user agrees call it again with dry_run=false.
- Writes are never retried automatically. After a TIMEOUT the outcome is unknown: read the value back.
- Commands report a `command_class`. "dialog" means Cubase opened a dialog that the user must complete:
  never claim it is done. "ui_selection" commands act on the Cubase window selection, which these tools
  cannot see: ask the user to check the result.
- Routing (inputs, outputs, send destinations) cannot be changed through this API.
- With [writes] allowed_tracks set, only those tracks can be changed: tools that can affect every track
  (range edits on all tracks, split at locators, cubase_run_command) fail with NOT_ALLOWED.
- Podcast-style editing: cubase_edit_range works in seconds and acts on every track in the range.
- Never save on your own initiative: cubase_save_project only when the user asks to save, after a dry run.
- Automation: list the parameters with cubase_list_automation_targets, then record a curve with
  cubase_record_automation. Recording plays the project (audible) and writes the track's automation.
  Give points in real units ("plain": -20 for -20 dB, 1000 for 1 kHz, pan -100 left..0..+100 right):
  Cubase converts them exactly. Never guess
  normalized values; use cubase_convert_value when you need one.
- If a tool fails with WRITES_DISABLED, writes are disabled in the user's Trackwright configuration.
"""

TrackArg = Annotated[str, Field(description='"selected", "uid:<UID>" (from cubase_list_tracks) or an exact track name')]
TargetArg = Annotated[
    str,
    Field(description="'channel' (track parameters), 'insert:N' (plugin in slot N, 1..insert_slots) or 'strip:eq'"),
]
DryRunArg = Annotated[bool, Field(description="true (default): only return the plan; false: apply it")]
TimeArg = Annotated[str, Field(description="'3. 1. 1. 0' (bar. beat. 16th. tick) or, with unit=seconds, '0:00:02.000'")]

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
NAVIGATE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)


def tool_error(exc: TrackwrightError) -> ToolError:
    text = f"{exc.code}: {exc.message}"
    if exc.details:
        text += f" | details: {json.dumps(exc.details, ensure_ascii=False, default=str)}"
    return ToolError(text)


async def run[T](fn: Callable[[], T]) -> T:
    """Run a blocking service call off the event loop and map domain errors to tool errors."""
    try:
        return await anyio.to_thread.run_sync(fn)
    except TrackwrightError as exc:
        logger.info("tool error {}", exc)
        raise tool_error(exc) from exc
    except Exception as exc:  # C-15: a bug must still reach the client with a stable code, not a bare traceback
        logger.exception("unexpected error in a tool")
        error = TrackwrightError(f"unexpected error: {type(exc).__name__}: {exc}", code="INTERNAL_ERROR")
        raise tool_error(error) from exc


def build_server(service: CubaseService) -> MCPServer:
    server: MCPServer = MCPServer(name=SERVER_NAME, version=__version__, instructions=INSTRUCTIONS)

    # ------------------------------------------------------------------ read tools (E05)
    @server.tool(annotations=READ, description="Connection, script version, capabilities and write policy.")
    async def cubase_status() -> StatusOut:
        return await run(service.status)

    @server.tool(annotations=READ, description="All mixer channels with name, uid, volume, mute, solo and routing.")
    async def cubase_list_tracks(
        offset: Annotated[int, Field(ge=0)] = 0, limit: Annotated[int, Field(ge=1, le=128)] = 32
    ) -> TrackListOut:
        return await run(lambda: service.list_tracks(offset, limit))

    @server.tool(annotations=READ, description="The selected track and its sections (Inserts, Strips, Sends...).")
    async def cubase_get_selected_channel() -> SelectedChannelOut:
        return await run(service.get_selected_channel)

    @server.tool(
        annotations=READ,
        description="The insert slots of a track and the plugin loaded in each "
        "(8 in Cubase Elements; cubase_status gives insert_slots).",
    )
    async def cubase_list_inserts(track: TrackArg = "selected") -> InsertsOut:
        return await run(lambda: service.list_inserts(track))

    @server.tool(annotations=READ, description="Plugins that can be loaded in an insert slot (name, vendor, uid).")
    async def cubase_list_available_plugins(
        track: TrackArg = "selected",
        slot: Annotated[int, Field(ge=1, le=16)] = 1,
        filter: Annotated[str | None, Field(description="text to match in name, vendor or category")] = None,  # noqa: A002
        offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=40)] = 20,
    ) -> PluginCatalogOut:
        return await run(lambda: service.list_available_plugins(track, slot, filter, offset, limit))

    @server.tool(annotations=READ, description="Parameters of the channel, of a plugin or of the strip EQ.")
    async def cubase_list_parameters(
        target: TargetArg,
        track: TrackArg = "selected",
        offset: Annotated[int, Field(ge=0, description="use next_offset from the previous page")] = 0,
        limit: Annotated[int, Field(ge=1, le=25)] = 25,
        filter: Annotated[str | None, Field(description="text to match in the parameter title")] = None,  # noqa: A002
    ) -> ParametersOut:
        return await run(lambda: service.list_parameters(track, target, offset, limit, filter))

    @server.tool(annotations=READ, description="One parameter, by tag, with its display value and units.")
    async def cubase_get_parameter(target: TargetArg, tag: int, track: TrackArg = "selected") -> ParameterOut:
        return await run(lambda: service.get_parameter(track, target, tag))

    @server.tool(
        annotations=READ,
        description="Properties of the open project: tempo, time signature at the cursor, cycle, punch, pre/post-roll, "
        "metronome, precount, transport state, record modes and the project folder. Says which properties the "
        "Cubase API does not expose (sample rate, length, name).",
    )
    async def cubase_get_project(
        include_folders: Annotated[
            bool, Field(description="find the project folder from the files Cubase has open (lsof)")
        ] = True,
    ) -> ProjectOut:
        return await run(lambda: service.get_project(include_folders=include_folders))

    @server.tool(annotations=READ, description="Cursor position, cycle locators and tempo.")
    async def cubase_get_transport() -> TransportOut:
        return await run(service.get_transport)

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=False),
        description="Changes Cubase reported since the last call (hints to re-read objects). Empties the buffer.",
    )
    async def cubase_poll_changes() -> ChangesOut:
        return await run(service.poll_changes)

    # ------------------------------------------------------------------ write and navigation tools (E06)
    @server.tool(
        annotations=WRITE,
        description="Set a parameter (process 0..1 or plain units) and verify it. On the channel, routing "
        "(input/output), name and selection are refused: READ_ONLY_PARAM.",
    )
    async def cubase_set_parameter(
        track: TrackArg,
        target: TargetArg,
        tag: int,
        value: float,
        unit: Literal["process", "plain"] = "process",
        expect_title: Annotated[str | None, Field(description="refuse if the parameter title differs")] = None,
        dry_run: DryRunArg = True,
    ) -> WriteOut:
        return await run(
            lambda: service.set_parameter(
                track, target, tag, value, unit=unit, dry_run=dry_run, expect_title=expect_title
            )
        )

    @server.tool(annotations=WRITE, description="Load a plugin (by uid) into an empty insert slot and verify it.")
    async def cubase_insert_plugin(
        track: TrackArg,
        slot: Annotated[int, Field(ge=1, le=16)],
        plugin_uid: Annotated[str, Field(description="uid from cubase_list_available_plugins")],
        dry_run: DryRunArg = True,
    ) -> InsertPluginOut:
        return await run(lambda: service.insert_plugin(track, slot, plugin_uid, dry_run=dry_run))

    @server.tool(annotations=WRITE, description="Volume (normalized 0..1), mute, solo or record arm of any track.")
    async def cubase_set_track_mix(
        track: TrackArg,
        volume: Annotated[float | None, Field(ge=0, le=1, description="normalized fader value")] = None,
        mute: bool | None = None,
        solo: bool | None = None,
        record_arm: bool | None = None,
        dry_run: DryRunArg = True,
    ) -> WriteOut:
        return await run(
            lambda: service.set_track_mix(
                track, volume=volume, mute=mute, solo=solo, record_arm=record_arm, dry_run=dry_run
            )
        )

    @server.tool(annotations=WRITE, description="Rename a track (refuses names used by another track).")
    async def cubase_rename_track(
        track: TrackArg, new_name: Annotated[str, Field(min_length=1, max_length=64)], dry_run: DryRunArg = True
    ) -> WriteOut:
        return await run(lambda: service.rename_track(track, new_name, dry_run=dry_run))

    @server.tool(
        annotations=NAVIGATE,
        description="Where one track's events start and end (TW-1610): walks its event edges with Locate Next "
        "Event from start (seconds) up to end, then puts the cursor and the selection back. First and last "
        "edge give the track's extent. An event starting exactly at 0 s is not seen; silence inside an event "
        "is not seen either (analyze an export for that). Transport stopped.",
    )
    async def cubase_track_edges(
        track: TrackArg,
        start: Annotated[str, Field(description="project time to start from (seconds)")] = "0",
        end: Annotated[str | None, Field(description="stop after this time; null = to the last edge")] = None,
        limit: Annotated[int, Field(ge=1, le=400, description="most edges to walk (each takes a moment)")] = 100,
    ) -> TrackEdgesOut:
        return await run(lambda: service.track_edges(track, start=start, end=end, limit=limit))

    @server.tool(annotations=NAVIGATE, description="Select a track, or the next/previous one. Single selection.")
    async def cubase_select_track(
        track: Annotated[str | None, Field(description="track selector; omit when using step")] = None,
        step: Literal["next", "previous"] | None = None,
    ) -> SelectOut:
        return await run(lambda: service.select_track(track, step))

    @server.tool(
        annotations=NAVIGATE,
        description="Move the cursor or a cycle locator (transport stopped). The locators are saved with "
        "the project, so moving them needs writes enabled; the cursor does not.",
    )
    async def cubase_set_position(
        which: Literal["cursor", "cycle_left", "cycle_right"],
        time: TimeArg,
        unit: Literal["bars", "seconds"] = "bars",
        dry_run: Annotated[bool, Field(description="true: only show the current and requested positions")] = False,
    ) -> PositionOut:
        return await run(lambda: service.set_position(which, time, unit=unit, dry_run=dry_run))

    @server.tool(annotations=WRITE, description="Set the project tempo in BPM (20..300).")
    async def cubase_set_tempo(bpm: Annotated[float, Field(ge=20, le=300)], dry_run: DryRunArg = True) -> TempoOut:
        return await run(lambda: service.set_tempo(bpm, dry_run=dry_run))

    # ------------------------------------------------------------------ command tools (E07)
    @server.tool(annotations=WRITE, description="Marker track, insert a marker at the cursor, or jump between markers.")
    async def cubase_markers(
        action: Literal["add_marker_track", "insert_at_cursor", "locate_prev", "locate_next"],
        dry_run: DryRunArg = True,
    ) -> CommandOut:
        return await run(lambda: service.markers(action, dry_run=dry_run))

    @server.tool(
        annotations=DESTRUCTIVE,
        description="Remove the selected track. expect_selected must match the current selection exactly.",
    )
    async def cubase_remove_selected_track(expect_selected: TrackArg, dry_run: DryRunArg = True) -> CommandOut:
        return await run(lambda: service.remove_selected_track(expect_selected, dry_run=dry_run))

    @server.tool(annotations=DESTRUCTIVE, description="Split every event crossing the given locators (all tracks).")
    async def cubase_split_at_locators(
        left: TimeArg,
        right: TimeArg,
        unit: Annotated[Literal["bars", "seconds"], Field(description="how left and right are given")] = "bars",
        dry_run: DryRunArg = True,
    ) -> CommandOut:
        return await run(lambda: service.split_at_locators(left, right, unit=unit, dry_run=dry_run))

    @server.tool(
        annotations=WRITE,
        description="Create an audio/group/folder track with the user's help: 'start' opens Cubase's dialog, "
        "'confirm' checks that the track exists.",
    )
    async def cubase_add_track_interactive(
        phase: Literal["start", "confirm"],
        kind: Literal["audio", "group", "folder"],
        suggested_name: Annotated[str, Field(min_length=1, max_length=64)],
    ) -> CommandOut:
        return await run(lambda: service.add_track_interactive(phase, kind, suggested_name))

    @server.tool(
        annotations=DESTRUCTIVE,
        description="Run a Cubase command from the allow-list (see the tools reference). Advanced: prefer the "
        "dedicated tools; save and track removal are refused here (USE_DEDICATED_TOOL). Commands act on the "
        "Cubase window selection, so they are refused while [writes] allowed_tracks is set. "
        "Reports the observed command class.",
    )
    async def cubase_run_command(
        key: Annotated[str, Field(description="command key, e.g. 'edit.undo' or 'zoom.in'")],
        dry_run: DryRunArg = True,
        force: Annotated[bool, Field(description="fire even if Cubase says it cannot be performed")] = False,
    ) -> CommandOut:
        return await run(lambda: service.run_command(key, dry_run=dry_run, force=force))

    # ------------------------------------------------------------------ range editing (TW-1211)
    @server.tool(
        annotations=DESTRUCTIVE,
        description="Edit a time range of the project, in seconds (or bars), on EVERY track with events in it "
        "(or, with track and action 'delete', on that track only): "
        "delete (leave a gap), delete_time or cut_time (remove and close the gap), insert_silence, crop. "
        "With verify_track (a track with audio), checks the result by probing its event edges before and after. "
        "Undo in Cubase reverts it. Dry run by default.",
    )
    async def cubase_edit_range(
        start: Annotated[str, Field(description="range start: seconds ('2', '1:30', '0:01:30.250') or bars")],
        end: Annotated[str, Field(description="range end, same unit")],
        action: Annotated[
            Literal["delete", "delete_time", "cut_time", "insert_silence", "crop"],
            Field(description="what to do with the range"),
        ],
        unit: Annotated[Literal["seconds", "bars"], Field(description="unit of start and end")] = "seconds",
        verify_track: Annotated[
            str | None, Field(description="track whose audio edges are probed to verify (recommended)")
        ] = None,
        track: Annotated[
            str | None,
            Field(description="edit ONLY this track (action 'delete' only, e.g. a cough on one microphone)"),
        ] = None,
        dry_run: DryRunArg = True,
    ) -> RangeEditOut:
        return await run(
            lambda: service.edit_range(
                start, end, action, unit=unit, verify_track=verify_track, track=track, dry_run=dry_run
            )
        )

    # ------------------------------------------------------------------ plugin presets (TW-1205)
    @server.tool(
        annotations=WRITE,
        description="Step to the next or previous preset of the plugin in an insert slot (opens its editor for the "
        "command). Verified by comparing the plugin's parameters. Presets cannot be chosen or read by name, and a "
        "preset must already be loaded in the plugin. Dry run by default.",
    )
    async def cubase_plugin_preset(
        track: TrackArg,
        slot: Annotated[int, Field(ge=1, le=16, description="insert slot number, 1..insert_slots of cubase_status")],
        direction: Literal["next", "previous"],
        dry_run: DryRunArg = True,
    ) -> PresetStepOut:
        return await run(lambda: service.plugin_preset(track, slot, direction, dry_run=dry_run))

    # ------------------------------------------------------------------ project settings (TW-1210)
    @server.tool(
        annotations=WRITE,
        description="Change project/transport settings: cycle, metronome, precount, punch in/out, use of pre/post-"
        "roll, click in playback/record (true/false) and click level (0-127). Each one is read back. Dry run by "
        "default. Time signature, tempo track and project setup are not settable here (use cubase_set_tempo).",
    )
    async def cubase_set_project(
        cycle: bool | None = None,
        metronome: bool | None = None,
        precount: bool | None = None,
        punch_in: bool | None = None,
        punch_out: bool | None = None,
        pre_roll: bool | None = None,
        post_roll: bool | None = None,
        click_in_playback: bool | None = None,
        click_in_record: bool | None = None,
        click_level: Annotated[int | None, Field(ge=0, le=127)] = None,
        dry_run: DryRunArg = True,
    ) -> ProjectSettingsOut:
        given = {k: v for k, v in {
            "cycle": cycle, "metronome": metronome, "precount": precount, "punch_in": punch_in,
            "punch_out": punch_out, "pre_roll": pre_roll, "post_roll": post_roll,
            "click_in_playback": click_in_playback, "click_in_record": click_in_record, "click_level": click_level,
        }.items() if v is not None}  # fmt: skip
        return await run(lambda: service.set_project(given, dry_run=dry_run))

    # ------------------------------------------------------------------ save (TW-1202)
    @server.tool(
        annotations=DESTRUCTIVE,
        description="Save the project file, ONLY when the user explicitly asks to save. mode 'save' overwrites "
        "the open .cpr; 'new_version' writes <name>-NN.cpr and Cubase continues on it. Needs [writes] save = "
        "true. Dry run by default: show the plan and ask for confirmation. Verified by the .cpr file dates.",
    )
    async def cubase_save_project(
        mode: Annotated[Literal["save", "new_version"], Field(description="overwrite or save a new version")] = "save",
        dry_run: DryRunArg = True,
    ) -> SaveOut:
        return await run(lambda: service.save_project(mode, dry_run=dry_run))

    # ------------------------------------------------------------------ import (TW-1203)
    @server.tool(
        annotations=WRITE,
        description="Import an audio file with the user, in two phases. 'start' selects the track, puts the "
        "cursor at the position (seconds or bars) and opens Cubase's file selector: the user picks the file "
        "(Cubase does not answer until the selector is closed). 'confirm' (same track, position and file, plus "
        "since) probes the track for the new event edges and lists the copy in the project's Audio folder.",
    )
    async def cubase_import_audio(
        phase: Literal["start", "confirm"],
        track: TrackArg,
        position: Annotated[str, Field(description="where the audio starts: seconds ('0', '1:30') or bars")],
        unit: Annotated[Literal["seconds", "bars"], Field(description="unit of position")] = "seconds",
        file: Annotated[
            str | None, Field(description="path of the file the user will pick (to tell them and check duration)")
        ] = None,
        since: Annotated[float | None, Field(description="confirm: the 'since' returned by start")] = None,
        dry_run: DryRunArg = True,
    ) -> ImportOut:
        return await run(
            lambda: service.import_audio(phase, track, position, unit=unit, file=file, since=since, dry_run=dry_run)
        )

    # ------------------------------------------------------------------ export (TW-1204)
    @server.tool(
        annotations=WRITE,
        description="Export the mix with the user, in two phases. 'start' puts the locators on the range "
        "(seconds or bars; omit start/end for all the audio) and opens Cubase's Export Audio Mixdown dialog: "
        "the user picks the format and exports. 'confirm' (with since and expected_seconds from 'start') finds "
        "the new file in the export folder and checks its duration. Trackwright never exports by itself. "
        "With 'solo' (track selectors) only those tracks are exported: their solo is set and any other solo "
        "cleared during the export, and 'confirm' or 'cancel' (the user closed the dialog) puts every solo back.",
    )
    async def cubase_export_mix(
        phase: Literal["start", "confirm", "cancel"],
        solo: Annotated[
            list[str] | None,
            Field(description="start: export only these tracks (soloed for the export, restored afterwards)"),
        ] = None,
        start: Annotated[str | None, Field(description="range start; omit with end for the whole project")] = None,
        end: Annotated[str | None, Field(description="range end")] = None,
        unit: Annotated[Literal["seconds", "bars"], Field(description="unit of start and end")] = "seconds",
        since: Annotated[float | None, Field(description="confirm: the 'since' returned by start")] = None,
        expected_seconds: Annotated[float | None, Field(description="confirm: the expected duration")] = None,
        folder: Annotated[str | None, Field(description="confirm: export folder if not the proposed one")] = None,
        dry_run: DryRunArg = True,
    ) -> ExportOut:
        return await run(
            lambda: service.export_mix(
                phase, solo=solo, start=start, end=end, unit=unit, since=since, expected_seconds=expected_seconds,
                folder=folder, dry_run=dry_run,
            )
        )  # fmt: skip

    @server.tool(
        annotations=READ,
        description="Loudness of an audio file as delivery specifications state it (ITU-R BS.1770 / EBU R128): "
        "integrated loudness (LUFS), momentary and short-term maxima, loudness range (LU), sample peak and true "
        "peak (dBTP, 4x oversampled). WAV, AIFF, FLAC, Ogg, MP3, and AAC through macOS afconvert. Reads the file "
        "only; needs [analysis] enabled.",
    )
    async def cubase_measure_loudness(
        file: Annotated[str, Field(description="absolute path of the audio file")],
    ) -> LoudnessOut:
        return await run(lambda: service.measure_loudness(file))

    @server.tool(
        annotations=READ,
        description="Where a voice track has speech: regions in project seconds from an export of that track alone "
        "(solo it; Cubase Elements exports only Stereo Out). Energy in the speech band (100 Hz-4 kHz) with "
        "hysteresis: starts on_db above the noise floor, lasts while off_db above it; short gaps joined, short "
        "bumps dropped. Reads the file only; needs [analysis] enabled.",
    )
    async def cubase_detect_speech(
        file: Annotated[str, Field(description="absolute path of the voice track's export")],
        start: Annotated[str, Field(description="project time of the file's first sample (seconds)")] = "0",
        on_db: Annotated[float, Field(ge=0, le=60, description="speech starts this far above the floor")] = 12.0,
        off_db: Annotated[float, Field(ge=0, le=60, description="and lasts while this far above it")] = 6.0,
        hangover: Annotated[float, Field(ge=0, le=2, description="seconds added after each region")] = 0.15,
        merge_gap: Annotated[float, Field(ge=0, le=5, description="gaps shorter than this are joined")] = 0.2,
        min_region: Annotated[float, Field(ge=0, le=5, description="shorter regions are dropped")] = 0.08,
        faint_db: Annotated[
            float, Field(ge=0, le=80, description="fragments this far below the typical speech level are dropped")
        ] = 30.0,
        offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=500)] = 100,
    ) -> SpeechOut:
        return await run(
            lambda: service.detect_speech(
                file, start=start, on_db=on_db, off_db=off_db, hangover=hangover, merge_gap=merge_gap,
                min_region=min_region, faint_db=faint_db, offset=offset, limit=limit,
            )
        )  # fmt: skip

    # ------------------------------------------------------------------ project workspace (TW-1602)
    @server.tool(
        annotations=WRITE,
        description="The Trackwright/ folder inside the open project's folder, where skills keep renders, "
        "previews, analyses, reports, the episode profile (profile.toml) and what they created (state.json). "
        "'status' only reads; 'init' creates the folder and its subfolders (dry run by default; needs "
        "[workspace] enabled). 'record' and 'forget' keep state.json, what each skill created (a plugin slot, a "
        "track, a marker…), so a re-run updates its own items and never the user's (dry run by default; needs "
        "[workspace] enabled). Nothing outside Trackwright/ is written.",
    )
    async def cubase_workspace(
        action: Annotated[
            Literal["status", "init", "record", "forget"],
            Field(description="status (read), init (create), record or forget an item a skill created"),
        ] = "status",
        kind: Annotated[
            Literal["track", "plugin", "render", "preview", "marker", "automation", "report"] | None,
            Field(description="record/forget: what the item is"),
        ] = None,
        key: Annotated[
            str | None, Field(max_length=256, description="record/forget: a track uid, '<track uid>/slot:N', a path…")
        ] = None,
        skill: Annotated[str | None, Field(max_length=64, description="record: the skill that created it")] = None,
        run_id: Annotated[str | None, Field(max_length=64, description="record: the skill run")] = None,
        details: Annotated[dict[str, Any] | None, Field(description="record: anything the skill needs later")] = None,
        dry_run: DryRunArg = True,
    ) -> WorkspaceOut:
        return await run(
            lambda: service.workspace(
                action, dry_run=dry_run, kind=kind, key=key, skill=skill, run=run_id, details=details
            )
        )

    # ------------------------------------------------------------------ profiles (TW-1607)
    @server.tool(
        annotations=WRITE,
        description="Show, episode and delivery profiles. 'resolve' (default) merges built-in < show "
        "(~/.config/trackwright/shows/<show>.toml) < episode (Trackwright/profile.toml): settings, where each "
        "came from, protected ranges and the delivery targets. 'shows' lists the show profiles; 'delivery' "
        "lists every delivery profile (Apple, Spotify, YouTube, iVoox… each value with its published source). "
        "'write_show' and 'write_episode' replace a whole profile with 'data' (dry run by default: show the "
        "user 'after' first; needs [workspace] enabled). Track roles go by track name.",
    )
    async def cubase_profile(
        action: Annotated[
            Literal["resolve", "shows", "delivery", "write_show", "write_episode"],
            Field(description="what to do"),
        ] = "resolve",
        show: Annotated[
            str | None, Field(max_length=64, description="show name (default: the one the episode names)")
        ] = None,
        data: Annotated[
            dict[str, Any] | None, Field(description="write_*: the whole profile, as the TOML file's tables")
        ] = None,
        dry_run: DryRunArg = True,
    ) -> ProfileOut:
        return await run(lambda: service.profile(action, show=show, data=data, dry_run=dry_run))

    # ------------------------------------------------------------------ renders (TW-1606)
    @server.tool(
        annotations=WRITE,
        description="Processed audio for the project, written to Trackwright/renders/ with a provenance file "
        "(.json: source and its hash, process, project position, the track it replaces). 'render' reads an "
        "export (cubase_export_mix with solo) and writes a 32-bit float WAV, never overwriting an earlier "
        "render; dry run by default; needs [analysis] and [workspace] enabled. Then import it on a new track at "
        "the given position with cubase_import_audio, which checks the position and records the track in "
        "state.json, and mute the original. 'list' shows the renders, where they were imported and whether "
        "the render or its source changed. Processes: gain (gain_db).",
    )
    async def cubase_render(
        action: Annotated[Literal["render", "list"], Field(description="render (write) or list (read)")] = "render",
        file: Annotated[str | None, Field(description="render: absolute path of the export to process")] = None,
        start: Annotated[str, Field(description="project time of the export's first sample (seconds)")] = "0",
        process: Annotated[Literal["gain"], Field(description="what to do to the audio")] = "gain",
        gain_db: Annotated[float, Field(ge=-40, le=40, description="gain: dB to apply")] = 0.0,
        name: Annotated[
            str | None, Field(max_length=64, description="file name (default: <track or source>-<process>)")
        ] = None,
        track: Annotated[
            str | None, Field(description="the track the render replaces (selector), to mute after the import")
        ] = None,
        skill: Annotated[str, Field(min_length=1, max_length=64, description="the skill that renders")] = "manual",
        run_id: Annotated[str | None, Field(max_length=64, description="identifier of the skill run")] = None,
        dry_run: DryRunArg = True,
    ) -> RenderOut:
        return await run(
            lambda: service.render(
                action, file=file, start=start, process=process, gain_db=gain_db, name=name, track=track,
                skill=skill, run=run_id, dry_run=dry_run,
            )
        )  # fmt: skip

    # ------------------------------------------------------------------ audio analysis (TW-1504)
    @server.tool(
        annotations=READ,
        description="Analyze an exported audio file: noise floor, levels and the silences longer than "
        "min_seconds, in project seconds. Export first with cubase_export_mix (Cubase Elements exports only "
        "Stereo Out: solo the track to analyze it alone) and pass the file and the range start. Reads the file "
        "only; needs [analysis] enabled. Levels are the export's (pan law, faders, inserts): prefer the "
        "threshold relative to the noise floor.",
    )
    async def cubase_analyze_audio(
        file: Annotated[str, Field(description="absolute path of the audio file (WAV, AIFF, FLAC, Ogg)")],
        start: Annotated[
            str, Field(description="project time of the file's first sample: the export's range start (seconds)")
        ] = "0",
        min_seconds: Annotated[float, Field(gt=0, le=3600, description="shortest silence reported")] = 2.0,
        above_floor_db: Annotated[
            float, Field(ge=0, le=60, description="threshold = noise floor + this many dB (if threshold_db is null)")
        ] = 10.0,
        threshold_db: Annotated[
            float | None, Field(ge=-120, le=0, description="absolute threshold in dBFS instead of the relative one")
        ] = None,
        padding_seconds: Annotated[
            float, Field(ge=0, le=5, description="kept before and after each silence so words are not cut")
        ] = 0.25,
        merge_gap_seconds: Annotated[
            float,
            Field(
                ge=0,
                le=5,
                description="louder blips shorter than this (a click) do not break a silence; keep it below a syllable",
            ),
        ] = 0.05,
        offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=500)] = 100,
    ) -> AnalysisOut:
        return await run(
            lambda: service.analyze_audio(
                file, start=start, min_seconds=min_seconds, above_floor_db=above_floor_db,
                threshold_db=threshold_db, padding_seconds=padding_seconds,
                merge_gap_seconds=merge_gap_seconds, offset=offset, limit=limit,
            )
        )  # fmt: skip

    # ------------------------------------------------------------------ lifecycle (TW-1201)
    @server.tool(
        annotations=WRITE,
        description="Open Cubase (optionally with a .cpr project) when it is closed, and wait until the "
        "Trackwright script answers. Never opens a second instance and never closes Cubase. Returns "
        "awaiting_user when Cubase shows a dialog (Steinberg Hub, project choice) that the user must answer.",
    )
    async def cubase_launch(
        project: Annotated[str | None, Field(description="path of a .cpr project to open (optional)")] = None,
        dry_run: DryRunArg = True,
    ) -> LaunchOut:
        return await run(lambda: service.launch_cubase(project, dry_run=dry_run))

    # ------------------------------------------------------------------ automation tools (TW-1207)
    @server.tool(
        annotations=NAVIGATE,
        description="Parameters of a track that can be automated (volume, pan, sends, channel EQ, pre-filter, "
        "quick controls, insert plugin parameters), with the Cubase parameter bound to each. Selects the track.",
    )
    async def cubase_list_automation_targets(track: TrackArg) -> AutomationTargetsOut:
        return await run(lambda: service.list_automation_targets(track))

    @server.tool(
        annotations=NAVIGATE,
        description="Exact conversion done by Cubase between a parameter's real units (dB, Hz...) and its "
        "normalized 0..1 value, in either direction. Give plain or value. Changes nothing (selects the track).",
    )
    async def cubase_convert_value(
        track: TrackArg,
        parameter: Annotated[str, Field(description="key from cubase_list_automation_targets, e.g. 'volume'")],
        plain: Annotated[float | None, Field(description="value in real units, e.g. -20 (dB)")] = None,
        value: Annotated[float | None, Field(description="normalized value 0..1")] = None,
    ) -> ConvertOut:
        return await run(lambda: service.convert_value(track, parameter, plain=plain, value=value))

    @server.tool(
        annotations=WRITE,
        description="Record an automation curve on a track parameter: plays the project from just before the "
        "first point and moves the parameter through the points (linear in between). Audible. Optionally "
        "verifies with a read-back pass. Positions are bars in the project's time signature. "
        "Give each point as plain (real units, preferred) "
        "or value.",
    )
    async def cubase_record_automation(
        track: TrackArg,
        parameter: Annotated[str, Field(description="key from cubase_list_automation_targets, e.g. 'volume'")],
        points: Annotated[list[AutomationPoint], Field(min_length=1, max_length=64)],
        verify: Annotated[bool, Field(description="play again with read automation to check the curve")] = True,
        dry_run: DryRunArg = True,
    ) -> AutomationRecordOut:
        return await run(lambda: service.record_automation(track, parameter, points, dry_run=dry_run, verify=verify))

    return server
