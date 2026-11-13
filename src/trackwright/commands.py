"""Cubase commands bound by the script, with the behaviour observed for each one.

Commands give no result back: only ``canPerform`` (which depends on context) and whatever state
can be read afterwards. Each command is classified by what was **observed** in the POC
(phases 4 and 2b, Cubase Elements 15.0.30):

- ``direct``: acts immediately without UI (verified).
- ``dialog``: opens a Cubase dialog; the user must complete it (verified). Never report as done.
- ``confirm``: may ask the user to confirm (verified when a removed track has events).
- ``ui_selection``: acts on the GUI selection/focus, which the API cannot see; results are not
  controllable from the script (verified: Paste went to another track than the one selected).
- ``unknown``: bound and accepted by Cubase but its effect was not observed.

The keys must match ``COMMANDS`` in ``cubase/Trackwright_Bridge.js`` (checked by a test).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CommandClass = Literal["direct", "dialog", "confirm", "ui_selection", "unknown"]


@dataclass(frozen=True, slots=True)
class CommandSpec:
    key: str
    category: str
    name: str
    command_class: CommandClass
    description: str
    evidence: str


_SPECS = [
    CommandSpec(
        "zoom.in",
        "Zoom",
        "Zoom In",
        "unknown",
        "Zoom in the focused window",
        "fired, no visible effect (focus-dependent)",
    ),
    CommandSpec("zoom.out", "Zoom", "Zoom Out", "unknown", "Zoom out the focused window", "not observed"),
    CommandSpec(
        "edit.undo",
        "Edit",
        "Undo",
        "ui_selection",
        "Undo the last step",
        "verified: one step per call; a paste may create two steps",
    ),
    CommandSpec("edit.redo", "Edit", "Redo", "ui_selection", "Redo the last undone step", "not observed"),
    CommandSpec(
        "addtrack.audio", "AddTrack", "Audio", "dialog", "Add an audio track", "verified: opens the Add Track dialog"
    ),
    CommandSpec(
        "addtrack.marker",
        "AddTrack",
        "Marker",
        "direct",
        "Add a marker track",
        "verified: created and selected directly",
    ),
    CommandSpec(
        "addtrack.group",
        "AddTrack",
        "Group Channel",
        "dialog",
        "Add a group channel",
        "verified: opens the Add Track dialog",
    ),
    CommandSpec(
        "addtrack.folder", "AddTrack", "Folder", "dialog", "Add a folder track", "verified: opens the Add Track dialog"
    ),
    CommandSpec(
        "project.remove_selected_tracks",
        "Project",
        "Remove Selected Tracks",
        "confirm",
        "Remove the selected tracks",
        "verified: may ask for confirmation when the track has events, unless the user disabled that prompt",
    ),
    CommandSpec(
        "project.selected_to_new_folder",
        "Project",
        "Folding: Tracks To Folder",
        "unknown",
        "Move the selected tracks into a new folder",
        "not observed",
    ),
    CommandSpec(
        "project.select_track_next", "Project", "Select Track: Next", "direct", "Select the next track", "verified"
    ),
    CommandSpec(
        "project.select_track_prev", "Project", "Select Track: Prev", "direct", "Select the previous track", "verified"
    ),
    CommandSpec(
        "transport.return_to_zero",
        "Transport",
        "Return to Zero",
        "unknown",
        "Move the cursor to the project start",
        "not observed",
    ),
    CommandSpec(
        "transport.locate_next_marker",
        "Transport",
        "Locate Next Marker",
        "direct",
        "Move the cursor to the next marker",
        "verified; without a next marker it goes to the end of the last event (Cubase 15)",
    ),
    CommandSpec(
        "transport.locate_prev_marker",
        "Transport",
        "Locate Previous Marker",
        "direct",
        "Move the cursor to the previous marker",
        "verified; ignores the locators; goes to the project start without markers",
    ),
    CommandSpec(
        "transport.set_left_locator",
        "Transport",
        "Set Left Locator",
        "unknown",
        "Set the left locator at the cursor",
        "not observed",
    ),
    CommandSpec(
        "transport.set_right_locator",
        "Transport",
        "Set Right Locator",
        "unknown",
        "Set the right locator at the cursor",
        "not observed",
    ),
    CommandSpec(
        "transport.locators_to_selection",
        "Transport",
        "Locators to Selection",
        "unknown",
        "Set the locators to the selection range",
        "not observed",
    ),
    CommandSpec(
        "marker.insert",
        "Marker",
        "Insert Marker",
        "direct",
        "Insert a marker at the cursor",
        "verified (needs a marker track)",
    ),
    CommandSpec("edit.cut", "Edit", "Cut", "ui_selection", "Cut the selection", "not observed"),
    CommandSpec(
        "edit.copy", "Edit", "Copy", "ui_selection", "Copy the selection", "verified: acts on the GUI selection"
    ),
    CommandSpec(
        "edit.paste",
        "Edit",
        "Paste",
        "ui_selection",
        "Paste at the cursor",
        "verified: pasted into another track than the one selected through the API",
    ),
    CommandSpec("edit.delete", "Edit", "Delete", "ui_selection", "Delete the selection", "not observed"),
    CommandSpec(
        "edit.split_at_cursor",
        "Edit",
        "Split at Cursor",
        "ui_selection",
        "Split the selected events at the cursor",
        "verified: split a MIDI part at the cursor",
    ),
    CommandSpec(
        "edit.split_loop",
        "Edit",
        "Split Loop",
        "direct",
        "Split every event crossing the locators",
        "verified: all tracks with events in the range",
    ),
    CommandSpec(
        "edit.split_range", "Edit", "Split Range", "ui_selection", "Split at the range selection", "not observed"
    ),
    CommandSpec("edit.select_all", "Edit", "Select All", "ui_selection", "Select all events", "not observed"),
    CommandSpec("edit.select_none", "Edit", "Select None", "ui_selection", "Clear the selection", "not observed"),
    CommandSpec(
        "edit.select_in_loop",
        "Edit",
        "Select in Loop",
        "ui_selection",
        "Select the range between the locators",
        "verified: range selection",
    ),
    CommandSpec(
        "audio.detect_silence",
        "Audio",
        "Detect Silence",
        "dialog",
        "Open Detect Silence for the selected audio event",
        "verified: opens its dialog; needs a selected audio event",
    ),
    CommandSpec(
        "automation.mode_touch",
        "Automation",
        "Automation Mode - Touch",
        "unknown",
        "Automation mode Touch: writes only while a control is touched",
        "not observed (TW-1206)",
    ),
    CommandSpec(
        "automation.mode_auto_latch",
        "Automation",
        "Automation Mode - Auto-Latch",
        "unknown",
        "Automation mode Auto-Latch: writing starts on any change and lasts until stop",
        "not observed (TW-1206)",
    ),
    CommandSpec(
        "automation.mode_cross_over",
        "Automation",
        "Automation Mode - Cross-Over",
        "unknown",
        "Automation mode Cross-Over: like Auto-Latch, stops when crossing existing automation",
        "not observed (TW-1206)",
    ),
    CommandSpec(
        "automation.next_mode",
        "Automation",
        "Next Automation Mode",
        "unknown",
        "Switch to the next automation mode",
        "not observed (TW-1206)",
    ),
    CommandSpec(
        "automation.toggle_write_selected",
        "Automation",
        "Toggle Write Enable Selected Tracks",
        "unknown",
        "Toggle automation write on the selected tracks",
        "used by factory scripts; not observed",
    ),
    CommandSpec(
        "transport.start",
        "Transport",
        "Start",
        "direct",
        "Start playback (never records)",
        "verified: the cursor advances (2026-11-13)",
    ),
    CommandSpec(
        "transport.stop",
        "Transport",
        "Stop",
        "direct",
        "Stop playback",
        "verified: the cursor stops at once (2026-11-13)",
    ),
]

COMMANDS: dict[str, CommandSpec] = {spec.key: spec for spec in _SPECS}
