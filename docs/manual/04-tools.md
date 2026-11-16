# MCP tool reference

**English** · [Español](04-tools.es.md)

The `trackwright` server exposes 49 tools. Each one has an input schema and an output schema that the MCP client receives automatically; this page explains how to use them and what their limitations are.

Trackwright aims to support several DAWs, but today it only implements **Cubase**. That is why every tool is named `cubase_*` and this page describes Cubase's behavior: it was verified against Cubase Elements 15.0.30, with experiment scripts and from Claude Code (see the [verification log](../verification.md)). Any MCP client receives the same tools. Another DAW would get its own set of tools; see [Extension to other DAWs](../architecture.md#extension-to-other-daws-possible-not-implemented).

## Common concepts

### How to specify a track: `track`

| Form | Example | Notes |
|---|---|---|
| `"selected"` | `"selected"` | The track selected in Cubase. This is the default. |
| `"uid:<UID>"` | `"uid:79CDBA14…"` | **Recommended.** A stable identifier, even after restarting Cubase. Get it from `cubase_list_tracks`. |
| Exact name | `"Voice"` or `"name:Voice"` | Fails with `TRACK_AMBIGUOUS` if two tracks have the same name. Use `name:` if the name is literally `selected`. |

Only tracks that have a **mixer channel** (audio, instrument, group, FX, outputs) are visible. Marker tracks and folders do not appear.

### Which part of a track: `target`

| Value | What it is |
|---|---|
| `channel` | The channel parameters: name (1024), volume (1025), mute (1027), solo (1028), selection (4000), record arm (4002)… |
| `insert:N` | The plugin loaded in insert slot N, from 1 to the number of slots of your Cubase (8 in Elements; `cubase_status` gives `insert_slots`). |
| `strip:eq` | The channel strip EQ. |

### References (`ref`) and sessions

Outputs include opaque `ref` values for objects. They are **informational**: no tool accepts them as input. They identify the object within the script's current session.

After restarting Cubase, internal identifiers change and are reused for other objects. To refer to a track durably, use its `uid:`.

Each tool pins the script session while it runs. If Cubase reloads the script in the middle of an operation, the tool stops with `STALE_SESSION` **before writing anything else**. Just run it again.

### Dry run and apply (`dry_run`)

Every tool that modifies the project has `dry_run`, which defaults to `true`: it returns the plan (current value and requested value) without touching anything. With `dry_run=false` it applies the change, reads the value back and returns `verified`.

There is one exception: `cubase_add_track_interactive`. Its `start` phase only opens a Cubase dialog, and you are the one who decides, in that dialog, whether the track is created.

Writes are **never retried**. If one times out (`TIMEOUT`), its outcome is unknown: the error includes the value read back (`read_back`).

### Command classes

Tools based on Cubase commands report `command_class`:

| Class | Meaning |
|---|---|
| `direct` | Acts without intervention. |
| `dialog` | Opens a Cubase dialog that the user must complete. **Never considered finished.** |
| `confirm` | Cubase may ask for confirmation (for example, when deleting a track with events), unless the user has checked "don't ask again". |
| `ui_selection` | Acts on the selection in the Cubase window, which Trackwright cannot see. |
| `unknown` | Cubase accepts it, but its effect has not been observed. |

### Errors

Errors arrive as tool errors, in the format `CODE: message | details: {...}`. The most common:

| Code | Cause |
|---|---|
| `BRIDGE_UNAVAILABLE` | The bridge is not running (`trackwright bridge`). |
| `BUSY` | Another write was still in progress and this one **was not sent**. It can be retried. |
| `INTERNAL_ERROR` | Unexpected error in the bridge. For writes, the outcome is unknown (`outcome: unknown`). |
| `STALE_SESSION` | Cubase reloaded the script during the operation; it stopped before writing further. |
| `TIMEOUT` | Cubase did not respond in time. For writes: outcome unknown. |
| `WRITES_DISABLED`, `NOT_ALLOWED` | The configuration does not allow that write. |
| `ANALYSIS_DISABLED`, `TOO_LONG` | The configuration does not allow reading audio, or the file is longer than allowed. |
| `WORKSPACE_DISABLED` | The configuration does not allow writing the project's `Trackwright/` folder. |
| `TRACK_NOT_FOUND`, `TRACK_AMBIGUOUS`, `NO_SELECTION` | The track cannot be resolved. |
| `INVALID_OBJECT` | The object no longer exists (for example, it was removed in Cubase). |
| `CANNOT_PERFORM` | Cubase says the command cannot be run right now. |
| `PRECONDITION_FAILED` and others (`SLOT_OCCUPIED`, `NAME_CONFLICT`, `SELECTION_MISMATCH`…) | The current state does not allow the operation. |

## Read tools

They do not modify anything.

### `cubase_status`

Connection status: script version, Cubase application and version, mixer and transport access, number of commands and write policy. `simulated: true` means the simulator is responding, not Cubase. `script_outdated: true` means Cubase is running another script than the one this Trackwright installs (`packaged_script_version`): install it with `trackwright setup` and restart Cubase.

### `cubase_list_tracks`

- **Input:** `offset`, `limit` (≤ 128).
- **Output:** per track, `track` (`uid:` selector), `name`, `type`, `selected`, `volume`, `mute`, `solo`, `input`, `output` and `ref`.

### `cubase_get_selected_channel`

The selected track and its sections (Inserts, Strips, Sends…). If the selected track has no mixer channel, `track` is `null`.

### `cubase_list_inserts`

- **Input:** `track`.
- **Output:** the 8 slots, with `empty` and, if occupied, the `name` and `plugin_uid` of the loaded plugin.

### `cubase_list_available_plugins`

- **Input:** `track`, `slot`, `filter` (name, vendor or category), `offset`, `limit`.
- **Output:** the plugins that can be loaded, with their `uid`. Channel strip slots do not offer a catalog (`NO_COLLECTION`).

### `cubase_list_parameters`

- **Input:** `target`, `track`, `offset`, `limit` (≤ 25), `filter`.
- **Output:** the parameters, with `tag`, `title` (localized), `process`, `display`, `plain` and `automatable`.
- **Pagination:** the output includes `next_offset`, which is the `offset` to request the next page, and `truncated: true` while parameters remain. With `filter`, each call scans at most 500 parameters; no match is lost between pages.

### `cubase_get_parameter`

- **Input:** `target`, `tag`, `track`.
- **Output:** a single parameter.

### `cubase_get_transport`

Cursor position, cycle locators and tempo, in bars. If Cubase has not sent any value yet, it responds `UNAVAILABLE`: move the cursor once in Cubase and try again.

### `cubase_poll_changes`

Changes Cubase has notified since the last call; the call clears the log. A `removed` event is a **hint to check again**, not proof of deletion: Cubase also emits it when the selected track changes.

Only the first 20 distinct objects are checked. The remaining events carry `still_valid: null`, and `unchecked` says how many there are.

### `cubase_get_project` (read)

- **Input:** `include_folders` (default `true`).
- **Output:**
  - tempo;
  - **time signature at the cursor position** (`signature`: text, numerator and denominator);
  - cycle (enabled and locators);
  - punch in/out and its range;
  - pre-roll and post-roll;
  - metronome (enabled, click level, whether it sounds during recording and playback) and precount;
  - transport state (`stopped`, `playing`, `recording`);
  - time display formats and record and playback modes, as Cubase shows them.
- **`project_folders`:** the folders of the open projects. They are inferred from the audio files Cubase has open (`lsof`), without reading the folder or the `.cpr`. It is empty if the project has no audio.
- **`unavailable`:** what the Cubase API does not expose (sample rate, bit depth, project length and name) and why.
- **How it works:** reads Cubase's internal `Transport` and `Metronome` objects, which are located by type. Verified with 4/4 and 3/4.
- **Cost:** about 1 s.

### `cubase_set_project` (write, with dry run)

- **Input:** any of these settings, plus `dry_run`:
  - switches (`true`/`false`): `cycle`, `metronome`, `precount`, `punch_in`, `punch_out`, `pre_roll` and `post_roll` (use pre-roll and post-roll), `click_in_playback` and `click_in_record`;
  - `click_level`, from 0 to 127.
- **What it does:** writes each setting to Cubase's `Transport` or `Metronome` object and reads it back. The output gives the before, requested and read-back values and `verified` for each one. If a write fails or times out, the error lists the settings already `applied` and the `failed_setting`, with its value read back after a timeout; nothing is retried.
- **Verified in Cubase Elements:** the 9 switches and the click level (experiment TW-1210).
- **Not available:**
  - **time signature:** Cubase does not accept writing it this way; change it in the Transport Bar or in "Project Setup";
  - pre-roll and post-roll **length**: its scale is not verified;
  - **tempo track.**
  - Tempo is changed with `cubase_set_tempo`.

## Write and navigation tools

### `cubase_set_parameter` (write)

- **Input:** `track` (required), `target`, `tag`, `value`, `unit` (`process` from 0 to 1, or `plain` in real units via Cubase), `expect_title`, `dry_run`.
- **Output:** includes `track_uid` (`uid:<UID>`); pass it as `track` when applying a dry run, because `"selected"` may point to another track by then.
- **Verification:** read-back, with a tolerance of 1e-3.
- **Protected channel parameters:** on target `channel`, the input and output routing (tags 4101 and 4102), the name (1024) and the selection (4000) are refused with `READ_ONLY_PARAM`, also in a dry run. Writing the routing disconnects the track; name and selection have their own verified tools (`cubase_rename_track`, `cubase_select_track`).
- **Errors:** `OUT_OF_RANGE`, `PARAM_LOCKED`, `PARAM_NOT_FOUND` and `READ_ONLY_PARAM`.

### `cubase_insert_plugin` (write)

- **Input:** `track` (required), `slot`, `plugin_uid`, `dry_run`.
- **Output:** includes `track_uid`, to reuse when applying the dry run.
- Empty slots only (`SLOT_OCCUPIED`).
- **Verification:** the slot contains a plugin with that `uid`.

### `cubase_set_track_mix` (write)

- **Input:** `track` and at least one of `volume` (normalized from 0 to 1), `mute`, `solo` or `record_arm`; plus `dry_run`.
- Works on **unselected** tracks.
- Volume in dB is not available yet.
- If a change fails after others were applied, the error includes `applied`, with the changes that did go through.

### `cubase_rename_track` (write)

- **Input:** `track`, `new_name`, `dry_run`.
- Rejects names already used by another track (`NAME_CONFLICT`).
- After the change, use the `uid:` selector: the name selector no longer works.

### `cubase_select_track` (navigation)

- **Input:** `track`, or `step` (`next` or `previous`).
- Selection is exclusive: it deselects all other tracks.
- With `step`, `verified` is `true` only if the selection moved (at the first or last track it does not).

### `cubase_track_edges` (navigation)

Where one track's events start and end (TW-1610). The API cannot read events, so the tool selects the track and walks its edges with Locate Next Event from `start` (seconds) up to `end`, then puts the cursor and the selection back.

- **Input:** `track`, `start` (default 0), `end` (default: to the last edge), `limit` (most edges to walk, default 100, up to 400; each takes a moment).
- **Output:** `edges` (starts and ends together, in order), `first` and `last` (the track's extent), `complete` (false when `limit` stopped the walk: probe again from the last edge).
- **Limits:** an event starting exactly at 0 s is not seen (the probe finds edges after the cursor; TW-1606), so `first` may be its end; edges of adjacent events coincide; silence inside an event is not seen (analyze an export for that). The transport must be stopped (`TRANSPORT_RUNNING`).

### `cubase_set_position` (navigation)

- **Input:** `which` (`cursor`, `cycle_left` or `cycle_right`), `time`, `unit` (`bars` or `seconds`) and `dry_run`.
- **Bars format:** `"3. 1. 1. 0"` (bar, beat, sixteenth, tick).
- **Seconds format:** `"2.5"`, `"1:30"` or `"0:00:02.000"`.
- **Permission:** moving the cursor is navigation and works with writes disabled. The cycle locators are saved with the project, so moving them requires `[writes] enabled = true` (`WRITES_DISABLED`). The tool keeps `dry_run` false by default, like the other navigation tools.
- **In seconds,** the position is read back using Cubase's seconds display, without assuming time signature or tempo. The locators cannot be moved using the seconds display (verified), so they are placed by moving the cursor there and using "Set Left/Right Locator"; the cursor then returns to where it was.

### `cubase_set_tempo` (write)

- **Input:** `bpm` (from 20 to 300) and `dry_run`.
- **Verification:** read-back, with a tolerance of 0.01.

### `cubase_plugin_preset` (write, with dry run; sometimes with the user)

- **Input:** `track`, `slot`, `direction` (`next` or `previous`) and `dry_run`.
- **What it does:**
  1. opens the plugin editor (the slot's "Edit" parameter, tag 4101; "Edición" in a Spanish Cubase) if it is closed;
  2. runs `Preset / Next` or `Previous`;
  3. compares the plugin parameters before and after, ignoring meters;
  4. closes the editor if it opened it.
- **Output:** `changed` (parameter: before → after), `verified` and `status`.
- **Requirements verified in Cubase Elements** (experiment TW-1205):
  - **a preset loaded** in the plugin; without one, the commands do nothing;
  - **keyboard focus on its window:** this requires **one click from the user the first time**. After that it works even if Trackwright closes and reopens the editor.
- **`awaiting_user`:** if nothing changes, it leaves the editor open and asks for that click (and a loaded preset). The next call then works.
- It is **not possible** to choose a preset by name **or read its name**: the API does not expose it. You only know it changed, from its parameters.
- **Undo:** the opposite step (`previous` after `next`) restores exactly the previous values.

## Command-based tools

### `cubase_markers`

- **`action`:** `add_marker_track` (`direct`, write), `insert_at_cursor` (`direct`, write; requires a marker track), `locate_prev` or `locate_next` (navigation: the cursor jumps to the previous or next marker).
- With no next marker, `locate_next` goes to the end of the last event in the project; with no previous one, `locate_prev` goes to the start. They do not stop at the locators.
- Track and marker creation cannot be read through the API, so it returns `verified: "not_observable"`.

### `cubase_remove_selected_track` (destructive)

- **Input:** `expect_selected` and `dry_run`.
- It only acts if the given track is the **only** selected track (`SELECTION_MISMATCH`, with the list of selected tracks), because the Cubase command deletes all selected tracks. Select it first with `cubase_select_track`.
- Limitation: it cannot see tracks without a mixer channel (markers, folders), so it does not know whether any of them is selected. Check the screen before applying.
- If the track has events, Cubase may ask for confirmation (unless that warning has been disabled) and the tool returns `pending_confirmation`.
- For tracks without a mixer channel (markers, folders), select them by hand and use `cubase_run_command` with `project.remove_selected_tracks`.

### `cubase_split_at_locators` (destructive)

- **Input:** `left`, `right`, `unit` (`bars`, the default, or `seconds`) and `dry_run`.
- Sets the locators, reads them back and runs "Split Loop". In seconds, the locators are placed by moving the cursor and using "Set Left/Right Locator" (the seconds display cannot move them); the cursor goes back, and the output adds `left_bars` and `right_bars`.
- **Splits every track** that has events in that range, so it is refused with `NOT_ALLOWED` while `[writes] allowed_tracks` is set.
- The locators **stay** at the split points; restoring them immediately could get ahead of the command. The output includes `previous_left` and `previous_right`, so you can restore them later with `cubase_set_position`.

### `cubase_add_track_interactive` (write, with the user)

- **Input:** `phase` (`start` or `confirm`), `kind` (`audio`, `group` or `folder`) and `suggested_name`.
- **`start`:** opens Cubase's "Add Track" dialog and returns `awaiting_user` with instructions for the user. It rejects names that already exist (`NAME_CONFLICT`), so that `confirm` does not mistake an old track for the new one.
- **`confirm`:** checks that the track exists. Folders have no mixer channel, so in that case verification is visual.

### `cubase_run_command` (destructive, advanced)

- **Input:** `key`, `dry_run` and `force`.
- Runs a command from the allowlist. The specific tools are preferable.
- **Refused here** (`USE_DEDICATED_TOOL`, also in a dry run): `file.save` and `file.save_new_version` (use `cubase_save_project`, which checks `[writes] save` and verifies the file) and `project.remove_selected_tracks` (use `cubase_remove_selected_track`, which checks the selection).
- **Permission:** commands act on the selection in the Cubase window, which may include any track, so every command except navigation needs writes enabled and is refused with `NOT_ALLOWED` while `[writes] allowed_tracks` is set.

| `key` | Class |
|---|---|
| `zoom.in`, `zoom.out` | unknown |
| `edit.undo`, `edit.redo`, `edit.cut`, `edit.copy`, `edit.paste`, `edit.delete`, `edit.split_at_cursor`, `edit.split_range`, `edit.select_all`, `edit.select_none`, `edit.select_in_loop` | ui_selection |
| `edit.split_loop` | direct |
| `addtrack.audio`, `addtrack.group`, `addtrack.folder`, `audio.detect_silence`, `file.export_audio_mixdown`, `file.import_audio` | dialog (export and import: verified, TW-1204 and TW-1203; the import file picker blocks Cubase while it is open) |
| `addtrack.marker`, `marker.insert`, `project.select_track_next`, `project.select_track_prev`, `transport.locate_next_marker`, `transport.locate_prev_marker` | direct |
| `project.remove_selected_tracks` | confirm (refused here: use `cubase_remove_selected_track`) |
| `project.selected_to_new_folder`, `transport.return_to_zero`, `transport.locators_to_selection` | unknown |
| `automation.mode_touch`, `automation.mode_auto_latch`, `automation.mode_cross_over`, `automation.next_mode`, `automation.toggle_write_selected` | unknown (experiment TW-1206) |
| `transport.start`, `transport.stop` | direct (verified: plays and stops; never records) |
| `edit.delete_time`, `edit.cut_time`, `edit.insert_silence`, `edit.crop_range`, `edit.select_all_on_tracks` | ui_selection (verified, TW-1211: they act on the range selection) |
| `transport.set_left_locator`, `transport.set_right_locator`, `transport.locate_next_event`, `transport.locate_selection`, `transport.locate_selection_end` | direct (verified, TW-1211) |
| `process.silence` | dialog (verified, TW-1211: asks whether the audio file is shared) |
| `edit.select_events_under_cursor`, `transport.locate_prev_event`, `transport.to_left_locator`, `tool.range`, `tool.select` | unknown |
| `file.save`, `file.save_new_version` | direct (verified, TW-1202, on a project that was already saved; refused here: use `cubase_save_project`) |
| `preset.next`, `preset.previous` | ui_selection (verified, TW-1205: they act on the plugin editor that has focus) |

## Range editing in seconds

### `cubase_edit_range` (destructive, with dry run)

Designed for podcast editing: it works in **seconds** and the time signature does not matter.

- **Input:**
  - `start` and `end`: seconds (`"2"`, `"2.5"`, `"1:30"`, `"0:01:30.250"`) or bars with `unit: "bars"`;
  - `action`:

    | Action | Effect |
    |---|---|
    | `delete` | Deletes the audio in the range and leaves the gap; nothing moves |
    | `delete_time` | Deletes the range and moves everything after it earlier, closing the gap |
    | `cut_time` | Like `delete_time`, and also copies the range |
    | `insert_silence` | Inserts silence as long as the range, at its start |
    | `crop` | Keeps only the range |
  - `verify_track`: a track with audio whose event edges are probed before and after to check the result. **Recommended.**
  - `dry_run`.
- **Scope: every track with events in the range.** This is what Cubase does with "Select in Loop". For a podcast, `delete_time` cuts the section from all tracks at once.
- **A single track** (`track`, only with `action: "delete"`): deletes the audio in the range on that track only, for example a cough on one mic. It uses the Object Selection tool:
  1. splits the track's events at both ends;
  2. deletes the pieces inside one by one, placing the cursor over them and using "Select Events under Cursor", which only looks at the selected track;
  3. repeats the probe until nothing is left, because pieces may be hidden under others.
  - **Safety:** before each deletion it measures the selection; if it goes outside the range (a split did not happen), it stops with `SPLIT_FAILED` without deleting anything else.
  - **Undo:** takes several steps. `undo_steps` says how many.
  - **Duration:** it takes longer, about 25 s for a range with 6 events.
  - Closing or opening time on a single track is **not allowed**: it would put it out of sync with the rest.
- **What it does:**
  1. sets the locators to the range: moves the cursor to each end, in seconds, and uses "Set Left/Right Locator";
  2. activates the **Range Selection** tool, runs "Select in Loop" and performs the action;
  3. switches back to the **Object Selection** tool (it cannot know which one you had before);
  4. restores the locators, the cursor and the selected track.
- **Verification:** with `verify_track`, it walks the event edges of that track with "Locate Next Event" (starts and ends, without distinguishing them) and checks that they match what is expected. It checks up to 48 edges starting 1 s before the range.
- **Errors:** `BAD_TIME`, `TRANSPORT_RUNNING`, `NO_RANGE_SELECTION` (Cubase did not create the selection, for example because the Project window is not in front), `SPLIT_FAILED`, `WRITES_DISABLED` and `NOT_ALLOWED` (with `track`, a track outside `[writes] allowed_tracks`; without `track`, any edit while `allowed_tracks` is set, because it acts on every track).
- **Undo:** **Edit > Undo** in Cubase reverts it, as verified with each action. The project is not saved.
- **Not included:** "Process > Silence" opens a dialog if the audio file is shared by several events.

## Saving the project

### `cubase_save_project` (destructive, with dry run)

**Only when the user asks to save.** Trackwright never saves on its own initiative or chains a save after other writes.

- **Permission:** requires `[writes] enabled = true` **and** `[writes] save = true`.
- **Input:**
  - `mode`:
    - `save`: overwrites the open `.cpr`;
    - `new_version`: creates `<name>-NN.cpr`, and Cubase switches to working on it;
  - `dry_run`, default `true`.
- **Dry run:** shows the project folder (inferred from the open audio files) and its `.cpr` files with date and size, so you know what will be overwritten.
- **Verification:** some `.cpr` in the folder with a date later than the command; with `new_version`, a new one. Only names, sizes and dates are read.
- **Unknown folder:** when the project folder is unknown, or several projects seem to be open, the status is `fired` and `verified` is `null`: the save was requested, but nothing proves it (a project that was never saved shows *Save As*).
- **States:** `done` or `awaiting_user`. The latter if nothing was written within 10 s: there is probably a dialog, such as "Save As" on a project that was never saved.
- **Verified in Cubase Elements:** `Save` rewrote `TEST.cpr` in 1 s, and `Save New Version` created `TEST-01.cpr`. Neither opened a dialog.
- Closing, reverting and quitting are **not offered**.

## Importing audio

### `cubase_import_audio` (with the user, two phases)

- **`start` phase** (`dry_run` by default):
  - **Input:**
    - `track` and `position` (seconds or bars);
    - `file`, optional: the path of the file the user will choose. It is used to tell the user the path and to get its duration (from the header with soundfile; macOS `afinfo` only for AAC).
  - **What it does:**
    1. selects the track;
    2. moves the cursor to the position;
    3. opens "Import Audio File".
  - **While the file picker is open, Cubase does not respond to the script** (verified). That is why the phase does nothing else and returns `awaiting_user`, with instructions: Cmd+Shift+G and the path.
- **The user** chooses the file and accepts the options. Cubase copies it to the project's *Audio* folder.
- **`confirm` phase** (same track, position and file, plus `since`):
  - if Cubase still does not respond: `awaiting_user`, because the file picker is still open;
  - otherwise, it probes the track and looks for edges at the position and at the position plus the duration. It returns `done` and `verified`, or `not_found` if it was canceled or went somewhere else. Only **new** edges count: the start phase probes the track before opening the dialog, so an event that was already at that position does not confirm a canceled import, and each expected position needs its own edge. If the start phase ran in another server session, the edges before are unknown and `verified` is `null`;
  - at the project start (position 0) the start edge cannot be probed (Locate Next Event never stops at 0, and Locate Previous Event goes to 0 even without an event there): the new end edge at the position plus the file's duration stands for it, with a note (TW-1606);
  - `copied_to_project` lists the new copies in `<project>/Audio`, by name only.
- **Verified in Cubase Elements:** a 3 s tone ended up on POC-TEST from 150 to 153 s.
- **Undo** removes the event, **not** the copy on disk.
- **Renders** (`file` in `Trackwright/renders/` with its provenance, TW-1606): `start` refuses a position other than the render's (`MISALIGNED`), the track the render replaces (`BAD_REQUEST`), and a render that changed after it was made (`BAD_RENDER`); the instructions ask to untick "Copy file to project folder". `confirm` returns `render` and, with `[workspace] enabled`, records the render and the new track in `state.json` as the rendering skill's (`owned: true`), and reminds to mute the original track; if an earlier render track of the same skill replaced the same track, it says so, to be removed once the user confirms.

## Exporting the mix

### `cubase_export_mix` (with the user, two phases)

> **Muted tracks and `solo`** (TW-1616): in Cubase a soloed track sounds even when it is muted. `solo` therefore leaves muted tracks out, with a note, unless `include_muted` is true; when every track asked for is muted, it refuses (`BAD_REQUEST`).

Trackwright **never exports by itself**: it sets the range and opens the Cubase dialog; the format and the button are up to the user.

- **`start` phase** (`dry_run` by default):
  - **Input:** `start` and `end` in seconds (or bars with `unit: "bars"`). Without them, it exports **all the audio**: "Select All" and "Locators to Selection" set the locators from the first to the last event.
  - **What it does:** sets the locators to the range and opens "Export Audio Mixdown". In Elements the dialog has no range field: it exports between the locators (verified).
  - **Output:** `awaiting_user`, the folder Cubase will suggest (`<project folder>/Mixdown`, inferred from the open files), the expected duration and `since` (a timestamp).
- **The user,** in the dialog, checks the channel (Stereo Out), the name, the path and the format (WAV for archiving, MP3 for publishing) and clicks **Export Audio**.
- **`confirm` phase:**
  - **Input:** `since` and `expected_seconds` from the previous phase; `folder` if another folder was chosen.
  - **What it does:** looks in the folder for audio files created after `since` and reads **only** their name, size, date and duration (from the header with soundfile, exact for MP3 too; macOS `afinfo`, whose MP3 duration is an estimate that was 6.3 s short on 46 minutes, only for AAC; TW-1612).
  - **Output:** `done` and `verified`, with the duration difference for each file (`difference_seconds`), or `not_found`.
  - **Tolerance:**
    - ±0.15 s for WAV and AIFF;
    - ±(0.5 s + 0.2%) for MP3, AAC and OGG, whose duration is an estimate and which lose or gain frames at the end. Verified: an MP3 of the 139.976 s episode measured 139.721 s.
- The locators **stay** on the exported range.
- **Exporting some tracks alone** (TW-1605): Cubase Elements exports only Stereo Out, so `start` takes `solo`, a list of tracks. While exporting, only those are soloed (another solo the user had is cleared for that time); `confirm` puts every solo back as it was, reads each one back and reports `solo_restored`, even when the file is not found. If the user closes the dialog without exporting, `phase: "cancel"` with `since` restores the solos without looking for a file. If something fails before the dialog opens, the solos are restored at once. With `[writes] allowed_tracks`, only those tracks' solo can change (`NOT_ALLOWED`).
- **Errors:** `TRANSPORT_RUNNING`, `CANNOT_PERFORM` (another dialog is open), `BAD_TIME`, `WRITES_DISABLED` and `NOT_ALLOWED`.

### `cubase_detect_speech` (read, needs `[analysis] enabled`)

Where a voice track has speech (TW-1604), for skills that act around the voice: ducking the music, leveling, placing transitions. Export the voice track alone first (solo it): each voice on its own track means the question is only "speech or not", never "who".

- **Input:** `file` (absolute path), `start` (project time of the file's first sample, as in `cubase_analyze_audio`), `on_db` (12), `off_db` (6), `hangover` (0.15 s), `merge_gap` (0.2 s), `min_region` (0.08 s), `faint_db` (30), `offset`, `limit` (100, at most 500).
- **How it decides:** the speech band (100 Hz to 4 kHz, so mains hum and hiss do not count) is measured every 10 ms; the noise floor is the 10th percentile of those levels, digital silence left out. Speech starts when the level rises `on_db` above the floor and lasts while it stays `off_db` above it, so the dips between syllables do not split a word; `hangover` is added after each region for word endings, gaps shorter than `merge_gap` are joined and regions shorter than `min_region` (clicks) are dropped. Fragments more than `faint_db` below the typical speech level are dropped before joining: on a real episode, small noises 30 dB or more below the voice were bridging pauses and hiding them.
- **Output:** `regions` in project time (start, end, duration, mean level of the speech band, `confidence` from how far above the noise floor it is), `total`, `speech_seconds`, the noise floor and both thresholds, the typical speech level (`speech_level_db`) and how many faint fragments were dropped (`faint_dropped`), and `contrast_db` (with less than `on_db` of contrast there is no clear speech, and a note says so).
- **Limits:** it is an energy detector. A loud laugh, cough or door in the voice band counts as activity, which is what ducking and leveling need; finding words is the transcription's job (TW-1630).
- **Errors:** `ANALYSIS_DISABLED`, `TOO_LONG`, `NOT_FOUND`, `BAD_AUDIO`, `BAD_TIME`, `BAD_REQUEST`.

### `cubase_measure_loudness` (read, needs `[analysis] enabled`)

Loudness as delivery specifications state it, measured as ITU-R BS.1770 and EBU R128 define it (TW-1603).

- **Input:** `file`, an absolute path: WAV, AIFF, FLAC, Ogg, MP3, or AAC (`.m4a`, decoded with macOS `afconvert` into a temporary file that is removed afterwards).
- **Output:**

  | Field | Meaning |
  |---|---|
  | `integrated_lufs` | Integrated loudness: 400 ms blocks, gated at −70 LUFS and 10 LU below their mean. `null` for silence or a file under 400 ms. |
  | `momentary_max_lufs`, `short_term_max_lufs` | The loudest 400 ms block and the loudest 3 s window. |
  | `loudness_range_lu` | Loudness range (EBU Tech 3342): spread of the short-term values between their 10th and 95th percentiles. `null` under about 3 s. |
  | `sample_peak_dbfs`, `true_peak_dbtp` | The largest sample, and the peak of the signal oversampled 4× (what a ceiling such as −1 dBTP refers to). |
- **Mono files** are measured as one channel: they read 3 dB lower than the same signal on two channels (a note says so).
- **Checked against** the test signals of EBU Tech 3341 (integrated loudness, gating; ±0.1 LU) and Tech 3342 (loudness range; ±1 LU), the coefficient tables of BS.1770 at 48 kHz, and an independent implementation (pyloudnorm, ±0.1 LU).
- **Errors:** `ANALYSIS_DISABLED`, `TOO_LONG`, `NOT_FOUND`, `BAD_AUDIO`, `BAD_REQUEST`.

## Project workspace

### `cubase_workspace` (`status` reads; `init`, `record` and `forget` write files, with dry run)

The `Trackwright/` folder inside the open project's folder, where skills keep their files (TW-1602). The project folder comes from the files Cubase has open; with no project, or several, it is not guessed.

- **Input:** `action` (`status` by default, or `init`) and `dry_run` (for `init`).
- **`status`:** says whether the folder exists, which subfolders `init` would create, whether `state.json` and `profile.toml` exist, how many items each skill has recorded (`owned`, by `skill:kind`) and a summary of the episode profile. Always allowed.
- **`init`:** creates `Trackwright/` and its subfolders `renders/`, `previews/`, `analysis/` and `reports/`, and nothing else. Needs `[workspace] enabled`; idempotent.
- **`record`, `forget`** (TW-1609): keep `state.json`, what each skill created. `record` takes `kind` (`track`, `plugin`, `render`, `preview`, `marker`, `automation`, `report`), `key` (a track uid, `<track uid>/slot:N`, a path…), `skill`, `run_id` and `details`; a record with the same kind and key replaces the old one (the newest creator owns it, and a note says whose it was); from the **same skill** its `details` are merged into the old ones (TW-1619: the licence added to the render the import recorded). A `key` that is an absolute path inside `Trackwright/` is stored relative (`renders/x.wav`), as the import records it. `forget` removes it. **`credits`** (TW-1621) gathers every sound recorded with a licence (`details.license`, from any skill) into `Trackwright/credits.md`: the credits the licences ask for, to paste into the episode notes, then a table of each sound, its licence, source, credit, where it is used and by which skill; the dry run returns them in `credits` without writing. `record`, `forget` and `credits`: dry run by default (`before` and `after`); need `[workspace] enabled` and the workspace created. `status` lists the items (`items`, the first 200). See [the skill contract](07-skill-contract.md).
- **Layout:**

  | Path | Content |
  |---|---|
  | `renders/` | processed audio that skills import back into Cubase |
  | `previews/` | short files to listen to before approving a change |
  | `analysis/` | analysis results tied to the export they come from |
  | `reports/` | quality-control and delivery reports |
  | `state.json` | what each skill created, so a re-run updates its own items and never the user's |
  | `profile.toml` | the episode profile: track roles, protected ranges, notes |
- **Safety:** every path is checked to stay inside `Trackwright/` (no `..`, absolute paths or symbolic links leading out); a `Trackwright` that is a symbolic link or a file is refused; files are written atomically.
- **Errors:** `WORKSPACE_DISABLED`, `NO_PROJECT_FOLDER` (unknown or ambiguous), `BAD_WORKSPACE`, `NO_WORKSPACE`.

### `cubase_profile` (reads; `write_show` and `write_episode` write files, with dry run)

Show, episode and delivery profiles (TW-1607). Three layers, each overriding the one before: **built-in** (Trackwright's defaults: the silence criteria of `cubase_analyze_audio`) < **show** (`~/.config/trackwright/shows/<show>.toml`, shared by every episode) < **episode** (`Trackwright/profile.toml`, which also names its show). Tables merge key by key; lists are replaced whole.

- **Input:** `action`, `show` (default: the one the episode names), `data` (for writes: the whole profile, as the TOML file's tables), `dry_run`.
- **`resolve`** (default): the merged `settings`, `origins` (which layer each value came from, as `editing.padding_seconds: show`), the episode's `protected` ranges, the delivery profiles of `delivery.targets`, and `episode`: the episode profile as stored (start from it to `write_episode`, never from `settings`, or the show's values would be copied into the episode).
- **`shows`:** the show profiles found. **`delivery`:** every delivery profile available, built-in and the show's or episode's own.
- **`write_show`, `write_episode`:** validate `data` and replace the whole file; the dry run returns `before` and `after` (TOML) to show the user. Need `[workspace] enabled`; the episode needs the workspace created.
- **Settings:** `track_roles` and `voices` (`pan`) by track **name** (uids repeat across projects made from one template); `music.approved`; `ducking` (`depth_db`, `pre_roll_seconds`, `hold_seconds`, `release_seconds`); `editing` (`min_silence_seconds`, `padding_seconds`); `delivery` (`targets`, and `profiles` of the show's own hosts). The episode adds `show`, `protected` (`start`, `end`, `note` in seconds) and `notes`.
- **Delivery profiles:** loudness target and tolerance, true peak ceiling, whether the platform normalizes playback, codecs, channels, sample rates, bit rates, file size, what is required and what only recommended, and `sources`. **Every value must be covered by a source** (a URL, the date it was read, the fields it supports, a short quote), or the profile is refused. Built-in, read on 2026-11-15:

  | Name | Loudness | True peak | Format | Source |
  |---|---|---|---|---|
  | `apple` | −16 LUFS ±1 | −1 dBTP | AAC or MP3; 44.1/48 kHz; 64–256 kbps | Apple Podcasts for Creators, audio requirements |
  | `spotify` | not published for podcasts | not published | MP3, M4A or WAV; mono or stereo; 128 kbps or more | Spotify for Creators; Podcast Delivery Specification v1.10 |
  | `youtube` | not published | not published | AAC or Opus; stereo; 48 kHz; 384 kbps; up to 256 GB or 12 h | YouTube Help |
  | `ivoox` | not published | not published | MP3, M4A or WAV; 300 MB (advice, 2022 blog) | iVoox blog (the help centre could not be read) |

  Spotify's −14 LUFS is on its music page, not for podcasts, so it is not used. A show can add a host with `delivery.profiles.<name>` and the user's source.
- **Errors:** `WORKSPACE_DISABLED`, `NO_PROJECT_FOLDER`, `NO_WORKSPACE`, `NOT_FOUND` (a show), `BAD_PROFILE`, `BAD_REQUEST`.

### `cubase_library` (read)

The user's licensed audio library (TW-1620, `[library] folders`).

- **`search`** (default): licensed sounds whose title, tags, kind, file name or notes contain **every** word of `query`, filtered by `kind`, an allowed `use` (for example `podcast`) and length (`min_seconds`, `max_seconds`); each with its file, length, licence, source, the `attribution` to credit and its allowed uses and restrictions. Paged with `offset` and `limit`.
- **`check`:** the sounds left out (no sidecar, or a sidecar without a licence or not valid, with the field and why) and sidecars whose sound is gone.
- A sound without a licence is **never offered**; nothing is ever downloaded; only the sidecars and the files' headers are read.
- **Errors:** `NO_LIBRARY` (no folders configured), `BAD_REQUEST`.

### `cubase_music_analysis` (read, needs `[analysis] enabled`)

Analyzes a music file for a bed (TW-1617), without writing anything.

- **Input:** `file`, `top` (loop candidates to return, 5).
- **Tempo:** spectral-flux onsets, their autocorrelation between 60 and 180 BPM weighed toward 120 BPM (a tempo and its half correlate alike; a strong half-time accent still wins, as in a march counted at the half note), and a beat grid fitted to the onset peaks. `tempo_confidence` under 0.3 means no usable beat (ambient music): loop lengths are then whole seconds and must be checked by ear.
- **Loops** (only before the ending): for each repetition lag in whole bars of 4 beats (up to 40 s), the music is compared with itself that much later in timbre (24 bands) **and** harmony (chroma, 12 pitch classes), the lower of the two counting. The seam goes where they agree best within 1 s; the loop's end is then lined up with its start by correlation (envelopes within 80 ms, waveforms within 3 ms). `score` (0..1) is the agreement over a bar on each side of the seam: a jump between two equal chords that drops the rest of a progression agrees within 1 s but not over a bar. Among equal scores, the shortest first. `crossfade`: half a beat.
- **`ending`:** `tail` (where the level falls for good below the typical level minus 10 dB), `start` (the beginning of the last bar before it), `end` (the last moment above −60 dBFS).
- **Checked on** synthetic music at 75, 97, 120 and 140 BPM (tempo within 0.1 BPM, beats within 10 ms, the 4-bar pattern found as the loop although shorter jumps match in timbre), and by ear on a real bed, a 36 s march (TW-1617): its best loop (15.02 s, score 0.59) gave seams the user found "hardly noticeable, more than acceptable". A piece that changes as it goes scores low; listen to the seam before using it.
- With `source` and the cache of TW-1608. **Errors:** `ANALYSIS_DISABLED`, `TOO_LONG`, `NOT_FOUND`, `BAD_AUDIO`.

### `cubase_preview` (writes a file, with dry run)

A short file to listen to before changing the project (TW-1615): up to 8 exports, each placed by its project start and with its own gain, mixed over a project range of up to 120 s, and written as a 32-bit float WAV to `Trackwright/previews/` (never overwriting: the next one gets `-2`). For example, the voice export plus the ducked music around a first word. The user listens to it outside Cubase (Quick Look in the Finder, or any player).

- **Input:** `sources` (`[{file, start, gain_db}]`), `start` and `end` (project seconds), `name`, `skill`, `dry_run`.
- **`levels_db`:** each source's level in the range; a note says when one is silent there (a preview in a gap of the music only plays the voice).
- **Mixing:** silence where a source has no audio; a mono source on both channels; every source must have the same sample rate (`BAD_AUDIO` otherwise).
- **Needs** `[analysis] enabled` and `[workspace] enabled`, and the workspace created.
- **Errors:** `WORKSPACE_DISABLED`, `ANALYSIS_DISABLED`, `NO_WORKSPACE`, `NO_PROJECT_FOLDER`, `NOT_FOUND`, `BAD_AUDIO`, `BAD_TIME`, `BAD_REQUEST`.

### `cubase_voice_diagnostics` (read, needs `[analysis] enabled`)

Diagnoses a voice recording (TW-1623), without treating anything.

- **Input:** `file` (the export of **one voice track alone**) and `start` (its range start, so the times are project times).
- **How:** one pass in 30 s blocks (a 46-minute episode in about 5 s), with the speech regions of the voice. Each finding has `detected`, `severity` (`none`, `mild`, `moderate`, `strong`), a `confidence` (0 to 1: how much the data supports it, not how bad it is), `measures`, `times` (where to listen, strongest first, up to 20) and a `note`:
  - **`spectrum`:** the long-term speech spectrum in six bands (rumble 20–80 Hz, low, body, presence, sibilance 4–10 kHz, air), in dB relative to the whole;
  - **`hum`:** peaks at 50 or 60 Hz and five harmonics against the spectrum 5–15 Hz around each, measured in the pauses (frames of 0.68 s), with each harmonic's prominence (`h1_db`…`h6_db`, for the notches a cleanup needs); with no pauses long enough, measured over everything, and then the mains fundamental must stand out itself (a voice's harmonics make peaks too);
  - **`noise`:** the signal-to-noise ratio (typical speech level against the floor of the pauses: under 25 dB strong, 35 moderate, 45 mild) and the floor's colour (rumble, hiss, broadband);
  - **`plosives`:** bursts under 80 Hz that carry more than half the energy of a 10 ms window inside speech;
  - **`clicks`:** transients above 3 kHz more than 30 times their surroundings and 12 times their own 10 ms window, near speech and no more than 30 dB under the typical speech level; mild from 2 a minute;
  - **`sibilance`:** windows where 5–10 kHz is as loud as typical speech; `band_low_hz` and `band_high_hz` give where the esses' energy lies (the sixth-octave bands within 3 dB of the strongest, over the frames where 5–10 kHz outweighs 1–4 kHz: often flat over several kHz, so a band and not a peak), for a de-esser;
  - **`reverb`:** the time to fall from 5 to 25 dB below each phrase's last loud moment, scaled to a T60 (the voice's own fall counts too: an estimate).
- **The thresholds** are starting values, chosen on synthetic faults and checked on a whole real episode with the user listening (see the verification log): listen to the `times` before treating anything.
- **Errors:** `NOT_FOUND`, `ANALYSIS_DISABLED`.

### `cubase_leveling_plan` (read, needs `[analysis] enabled`)

Plans the leveling of the voices (TW-1622), without writing anything.

- **Input:** `voices` (1 to 8: `[{file, start, name}]`, each the export of **one voice track alone**, placed by its range start), `target_lufs` (the speech loudness to reach; default the median voice), `max_gain_db` (6), `tolerance_db` (2), `join_gap` (1.5 s), `min_segment` (3 s), `ramp` (0.2 s), `offset` and `limit` (segments per voice).
- **How:** speech regions per voice (as for ducking); loudness is BS.1770 K-weighted power over the **speech only** (pauses never count), measured in 10 ms steps. Phrases separated by less than `join_gap` form a **segment** (an intervention: the API cannot read events, so takes are told from the audio). Each voice gets the gain that brings it to the target; a segment straying more than `tolerance_db` from its voice gets back **the excess only**; nothing changes inside a segment (whispers, laughs, emphasis), and a segment shorter than `min_segment` gets only its voice's gain. Every total gain is bounded by `max_gain_db`; gains change in the middle of the pauses, over `ramp`.
- **Output:** `target_lufs`, `parameters`, and per voice: `loudness_lufs`, `voice_gain_db`, `segments_total`, `corrected`, `bounded`, `gain_range_db`, `segments` (each with `loudness_lufs`, `deviation_db`, `segment_gain_db`, `gain_db`, `reason`), `compare` (up to three fragments: the most raised, the most lowered, a typical one) and `level` (the object for `cubase_render` `process: "level"`).
- **Errors:** `BAD_REQUEST`, `NOT_FOUND`, `ANALYSIS_DISABLED`.

### `cubase_effect_plan` (read, needs `[analysis] enabled`)

Plans a sound effect at the point the user approved (TW-1621), without writing anything.

- **Input:** `effect_file` (absolute path, usually from `cubase_library`), `at` (where it goes, project time: never moved), `voice_file` and `voice_start` (the voice tracks' export, optional), `relative_db` (its level against the voice; default −12 dB when it lands on speech, −3 dB in a pause: starting values, not norms).
- **Output:** `start`, `end` (where its sound ends: its **audible** length, above −60 dBFS), `effect_seconds`, `audible_seconds`, `sample_rate` (the effect's), `effect_level_db` (RMS over the part where it sounds, so a short effect is not diluted by the silence in its file), `speech_level_db` (the voice's typical level), `under_speech` (the speech it lands on, seconds) and `under_speech_seconds`, `relative_db`, `suggested_gain_db` (the `gain_db` for `cubase_render` `process: "clip"` that puts it `relative_db` from the voice), `overlaps` (effects of `podcast-sound-effects` already placed whose sound overlaps it, from `state.json`, with the track they are on: on the same track the events would overlap), `preview` (3 s around it) and `notes`.
- **Errors:** `BAD_TIME`, `NOT_FOUND`, `SILENT_SOURCE`, `ANALYSIS_DISABLED`.

### `cubase_transition_plan` (read, needs `[analysis] enabled`)

Plans where a transition (a stinger, a short music in or out) goes between two sections (TW-1619), without writing anything.

- **Input:** `voice_file` (the voice tracks' export), `voice_start` (its range start), `at` (about where it goes, project time: the API cannot read markers), `stinger_file` (absolute path, usually from `cubase_library`), `pre_gap` and `post_gap` (0.3 s).
- **How:** the speech regions of the voice (as for ducking, detected once per version of the file); the pause between them nearest to `at` (containing it when it falls in one; pauses under 0.3 s do not count). The stinger starts `pre_gap` after the end of the last phrase (at 0 before the first one), never earlier. Its length is its **audible** length (where its sound ends above −60 dBFS), not the file's.
- **Output:** `pause_start`, `pause_end` (null after the last phrase), `start` (and `start_time`), `end` (where its tail ends), `fits`, `overlap` (seconds the tail plus `post_gap` would run into the next phrase), `stinger_seconds`, `audible_seconds`, `sample_rate` (the stinger's), `preview` (a range from before the last phrase to after the next one, for `cubase_preview`) and `notes` (a pause more than 5 s from `at`, a pause before the first phrase, silence at the end of the file).
- **When it does not fit**, `options`: open the pause (`cubase_edit_range` `insert_silence` at the next phrase, by `overlap`), fade the tail out so it ends before the next phrase (`cubase_render` `process: "clip"`), or a stinger of at most the given length. Nothing is cut or moved by the plan.
- **Errors:** `BAD_TIME`, `NOT_FOUND`, `SILENT_SOURCE` (a stinger without sound), `ANALYSIS_DISABLED`.

### `cubase_ducking_plan` (read, needs `[analysis] enabled`)

Plans how the music goes down under the voice (TW-1614), without writing anything. The same `ducking` object renders the music with `cubase_render` (`process: "duck"`).

- **Input:** `ducking`: `voice_file` (the export of the voice tracks soloed together) and `voice_start` (its range start), `attenuation_db` (−10), `pre_roll` (0.25 s), `hold` (0.8 s), `recovery` (1.2 s), `merge_gap` (0.9 s), `overrides` and `use_protected` (true); `music_start` and `music_seconds` (the music export's place, to cut the spans to it); `offset`, `limit`. The defaults are the brainstorm's starting values, not norms.
- **How:** speech regions from the voice export (as `cubase_detect_speech`), joined over pauses shorter than `merge_gap`, held `hold` after the last word; two spans too close for the music to come up and go down again become one (no pumping). The music starts going down `pre_roll` before the first word and comes back up over `recovery`, along straight lines in dB: no jumps, exactly `attenuation_db` on the flat part.
- **Overrides** (project seconds): `hold` keeps the music down over a span ("do not bring it up between those two phrases"), `free` keeps it up ("no ducking under the intro"), `depth` uses another `depth_db`. With `use_protected`, the episode profile's protected ranges are kept up too. Next to a `free` span or a protected range, the duck ends `recovery` before it and starts `pre_roll` after it, so the music is at full level all through it.
- **Output:** the number of speech regions, the protected ranges used, the ducked spans (start and end, depth, where the ramps begin and end), the ducked time, and `moments` to preview (each span's first word and recovery; with `music_file`, the music export, only those where the music has sound around them, with its level). With `previous` (the plan before an edit, TW-1615), `changed` lists the spans where the music changes, to preview and check only those.
- **Errors:** `ANALYSIS_DISABLED`, `TOO_LONG`, `NOT_FOUND`, `BAD_REQUEST` (a bad specification), `BAD_TIME`.

### `cubase_render` (`render` writes files, with dry run; `list` reads)

Processed audio for the project, written to `Trackwright/renders/` (TW-1606). Cubase's API cannot process a track's audio, so a skill exports the track alone, processes the export in Python, and imports the result on a new track, muting the original.

- **Input:** `action` (`render` by default, or `list`); for `render`: `file` (absolute path of the export), `start` (project time of the export's first sample: its range start), `process` (`gain`, `duck`, `bed`, `clip` or `level`), `level` (for `level`: a voice's object from `cubase_leveling_plan`: `gains` as `[start, end, gain_db]`, `ramp`, `max_gain_db`), `bed` (for `bed`: `loop_start`, `loop_end`, `ending_start`, `target_seconds`, `crossfade`, `align`, `sample_rate`), `clip` (for `clip`: `trim_end`, `fade_in`, `fade_out`, `sample_rate`), `gain_db` (±40), `ducking` (for `duck`: the object of `cubase_ducking_plan`), `name` (default `<track or source>-<process>`), `track` (the track the render replaces), `skill` and `run_id` (who renders, recorded in the provenance), `dry_run`.
- **`render`:** writes `<name>.wav` (32-bit float WAV, the source's rate and channels) and `<name>.json`, the **provenance**: the source's path, size and SHA-256, the process and its parameters, the project position, the track it replaces (name and uid), the render's own SHA-256 and peak, and the Trackwright version. An existing render is never overwritten (Cubase may still reference it): the next one is `<name>-2.wav`. Needs `[analysis] enabled` (it reads audio, with its `max_seconds`) and `[workspace] enabled`, and the workspace created with `cubase_workspace`.
- **`level`** (TW-1622): the leveling plan's gains over project time: each held over its span, ramped in the pauses, held before the first and after the last; gains beyond `max_gain_db` or with the end before the start are refused.
- **`clip`** (TW-1619): a stinger or an effect made ready to place: `gain_db`, cut at `trim_end` seconds, linear `fade_in` and `fade_out` (the fade out ends at the new end, so a cut tail dies away), resampled to `sample_rate` (the project's). Fades longer than the clip are refused.
- **`bed`** (TW-1617): a music bed of `target_seconds` from the music file: the music to `loop_end`, back to `loop_start` as many times as fit, and on the last pass on to the end of the file, so the only artificial seams are the loop's own; with `ending_start`, the last pass jumps to that ending instead. An equal-power `crossfade` (0.1 s by default; pass the loop's from `cubase_music_analysis`) at every seam. With `align` (a region the user marked) `loop_end` is first lined up with `loop_start` by correlation. With `sample_rate` the bed is resampled (polyphase) to the project's rate: Cubase converts a file at another rate on import by copying it into `Audio/` (TW-1618: a 44.1 kHz music in a 48 kHz project). The provenance and the dry run give `seams` (where each falls in the bed, seconds), `seam_score` (as `cubase_music_analysis` scores its loops; null for a whole file looped on itself) and a note when it is under 0.5 (TW-1618). As many repeats as fit **without going over** the target, never time-stretched: the result and how much shorter it is are reported (`short_by`). The values come from `cubase_music_analysis` or from the user.
- **`duck`** (TW-1614): the music export (`file`, `start`) ducked under the voice with the envelope `cubase_ducking_plan` shows for the same `ducking` object; the provenance stores the whole object, the voice export's SHA-256, the protected ranges used and the ducked time.
- **Then:** create an audio track (`cubase_add_track_interactive`), import the render on it with `cubase_import_audio` at the position returned, and mute the original track (`cubase_set_track_mix`). In Cubase's import options, untick "Copy file to project folder" (the render already is in the project folder) and leave the 24-bit conversion off.
- **`list`:** every render with its provenance, the track it was imported on (from `state.json`), whether that track is still in the project, and `problems`: the render changed after it was made, its source changed or is gone.
- **Errors:** `WORKSPACE_DISABLED`, `ANALYSIS_DISABLED`, `TOO_LONG`, `NO_PROJECT_FOLDER`, `NO_WORKSPACE`, `NOT_FOUND`, `BAD_AUDIO`, `BAD_TIME`, `BAD_REQUEST`, `BAD_RENDER`.

## Analyzing audio

### Which audio, and the cache (TW-1608)

`cubase_analyze_audio`, `cubase_measure_loudness` and `cubase_detect_speech` say which audio they measured and keep their results:

- **`source`:** the file, its size, modification time and SHA-256, and the project range it covers (`start`, `end`). `project_saved_after` is true when a project file (`.cpr`) in the project folder was saved after the file was written: the project may have changed (cuts, processing, automation), so a skill asks whether to export again (null for a file outside the open project's folder). Unsaved changes cannot be seen; only the modification times of the folder's `.cpr` files are read.
- **`cache`:** for a file inside the open project's folder, with the workspace created and `[workspace] enabled`, every result is stored in `Trackwright/analysis/` under a key made of the analysis, the file's SHA-256 and the parameters (`start` included). The same question about the same audio answers from there (`hit`) without reading the file again; a new export has other bytes, so it is never mistaken for the old one (`stored`: computed and kept; `off`: no cache). `hashes.json` remembers each file's hash by path, size and modification time, so a long episode is not hashed on every call. Paging (`offset`, `limit`) works on the cached result.

### `cubase_final_qc` (read, needs `[analysis] enabled`)

Final quality control of an episode file, the delivered one or a fresh export (TW-1611). One reading of the file, compared with the delivery profiles (`targets`, by default the profile's `delivery.targets`; see `cubase_profile`).

- **Input:** `file`, `start` (project time of its first sample), `expected_seconds` (the approved range), `targets`, `long_pause_seconds` (3), `jump_lu` (6), `report`.
- **Checks** (`pass` or `fail`, each with the platform's `source`): codec (from the extension: `.m4a` is AAC), channels, sample rate, average bit rate for compressed files (size over duration, ±2 %), file size, integrated loudness against target ± tolerance, true peak against the ceiling, and duration against `expected_seconds` (±0.01 s for PCM, ±0.1 s for MP3/AAC, which add encoder padding). A value the platform does not publish gives an `info` item ("not published by the platform"), never a pass or a fail.
- **Warnings** (`warn`, never a failure): silence at the start or end, pauses of `long_pause_seconds` or more, level changes of `jump_lu` or more between consecutive 10 s sections (short-term loudness, pauses left out), samples at full scale, a bit rate under the recommended one.
- **Manual items:** tracks that must not be in the file (a mixdown cannot show them), tags and artwork, content.
- **`moments`:** where to listen, in project time: the start, the end, the longest pauses, the level changes, the loudest 3 s.
- **`verdict`:** `fail` when any check failed. `source` says which file was measured (TW-1608).
- **`report`:** also writes `Trackwright/reports/qc-<file>-<time>.json` and `.md`; needs `[workspace] enabled` and the workspace created.
- **Errors:** `ANALYSIS_DISABLED`, `TOO_LONG`, `NOT_FOUND`, `BAD_AUDIO`, `BAD_TIME`, `BAD_REQUEST` (an unknown target), `WORKSPACE_DISABLED`, `NO_WORKSPACE`, `NO_PROJECT_FOLDER`.

### `cubase_delivery_plan` (read, needs `[analysis] enabled`)

What to set on Stereo Out to deliver the mix to a delivery profile (TW-1613), from a master export and the current fader. Nothing is changed: the skill `podcast-delivery` applies the plan with `cubase_set_parameter` and `cubase_insert_plugin` after the user agrees.

- **Input:** `file` (the master: a WAV export of the whole episode), `target` (a delivery profile), `codec` (the format to deliver: `mp3`, `aac`, `wav`; default the profile's first).
- **Output:** the target's loudness, tolerance and ceiling with their `source`; the master's integrated loudness and true peak; `fader_now_db`, `gain_db` (target − measured) and `fader_db` (the setting to apply); `reachable` (false when it would pass the fader's +6.02 dB); `predicted_lufs` and `predicted_true_peak` of the delivered file before any limiter; `limiter`, `threshold_db` and `peak_reduction_db` when the ceiling would be passed; `limiter_slot` (Stereo Out's slot 7 or 8, reusing a limiter already there).
- **The figures behind it** (TW-1612, `experiments/tw1612/`): the fader moves the loudness by exactly its gain; slots 1–6 are before the fader and 7–8 after it, so a limiter in 1–6 is no ceiling once the fader raises the level (noted when one is there); the Brickwall Limiter lets 0.24 dB of intersample peaks through; MP3 128 kbps raised the true peak by 0.82 dB (used for AAC too, with a warning: not measured). The threshold is the ceiling minus both margins, rounded down to 0.1 dB.
- **Warnings:** a target the fader cannot reach; more than 6 dB of peak reduction (a job for compression or leveling upstream); the loudness that limiting takes (expect a second round); a profile without a loudness target or a ceiling; slots 7 and 8 taken by other plugins.
- **Errors:** `ANALYSIS_DISABLED`, `TOO_LONG`, `NOT_FOUND`, `BAD_AUDIO` (a silent master), `BAD_REQUEST` (an unknown target, a fader at −∞).

### `cubase_analyze_audio` (read, needs `[analysis] enabled`)

The Cubase API cannot read what a track contains, so silences and noise are measured on an **exported file**. An export between the locators is aligned with the project to the sample (verified, TW-1501): project time = range start + time in the file.

- **Typical flow:**
  1. Solo the track to analyze (`cubase_set_track_mix`): Cubase Elements exports only Stereo Out.
  2. `cubase_export_mix` with the range; the user exports WAV, 32-bit float, at the project's sample rate.
  3. `cubase_analyze_audio` with the file from the `confirm` phase and `start` = the range start. Undo the solo.
- **Input:**
  - `file`: absolute path (WAV, AIFF, FLAC or Ogg).
  - `start`: project time of the file's first sample, in seconds (`"2"`, `"0:00:02.000"`); `"0"` by default.
  - `min_seconds` (2), `above_floor_db` (10), `threshold_db` (none), `padding_seconds` (0.25), `merge_gap_seconds` (0.05: shorter than a syllable, so speech is never taken for a blip), `offset` and `limit` (100, at most 500).
- **How it measures:** the RMS level of every 20 ms window, over all channels together. The noise floor is the 10th percentile of those levels, leaving out digital silence (the exact zeros an export holds before and after the events). A silence is a span below the threshold lasting at least `min_seconds`; blips shorter than `merge_gap_seconds` inside it do not break it, and `padding_seconds` is kept at each side so words are not cut (not at the file's ends).
- **Threshold:** noise floor + `above_floor_db`, which does not depend on faders or pan law (a centered mono track exports 3 dB lower). Only when it stays below the level of the sound (90th percentile); otherwise only digital silence counts, and a note says so. `threshold_db` gives an absolute value in dBFS instead.
- **Output:** format, sample rate, channels and duration; `noise_floor_db`, `threshold_db`, `peak_db`, `rms_db`; `silences` in project time (`start`, `end`, their values in seconds, `seconds`, `level_db`, `digital`), `total` and `total_seconds`. The levels are the export's, not the source file's.
- **Reads only the file:** nothing is sent to Cubase, and only the measurements are returned.
- **Errors:** `ANALYSIS_DISABLED`, `TOO_LONG` (longer than `[analysis] max_seconds`), `NOT_FOUND`, `BAD_AUDIO`, `BAD_TIME`, `BAD_REQUEST` (relative path, invalid criteria).

## Opening Cubase

### `cubase_launch` (write, with dry run)

- **Input:** `project` (path to a `.cpr`, optional) and `dry_run`.
- **What it does:**
  - checks whether the script responds and whether the Cubase process exists (`pgrep -x`);
  - if Cubase is closed, opens it with `open -a "Cubase 15"` (and the project, if given);
  - waits up to `[cubase] launch_timeout` for the script to respond.
- **States:**

  | State | Meaning |
  |---|---|
  | `planned` | Dry run: Cubase is closed and would be opened. |
  | `already_running` | The script already responds. Does nothing. |
  | `running_without_script` | Cubase is open but the script does not respond (no project, a dialog open, or the script not installed). **It does not open a second instance.** |
  | `ready` | Cubase open and the script responding. |
  | `awaiting_user` | Cubase is starting, but the script has not responded in time: there is probably a dialog waiting for the user. |
- It **never** closes Cubase, force-quits it or saves projects.
- Requires writes to be enabled.

## Automation tools

Mechanism verified in Cubase Elements 15.0.30: the script has one control per parameter on the MIDI Remote surface, bound to the **selected track**. Moving it while "touched", with automation write (W) enabled on the track and the project playing, records automation, like a hardware controller in Touch mode. Writing the parameter directly does **not** record.

### `cubase_list_automation_targets` (navigation)

- **Input:** `track`.
- **Output:** each automatable parameter with its key (`parameter`), the Cubase parameter it is bound to (`title`, for example "Compressor / Threshold"), its current value and whether it is available (`available`).
- **Selection:** the automation controls follow the selected track, and Cubase binds them to a new selection a moment later. This tool, `cubase_convert_value` and `cubase_record_automation` select the track and wait (up to 3 s) until the volume control is titled with its name; if the controls never follow, they stop with `CONTROLS_NOT_BOUND` and touch nothing (TW-1616: read at once, POC-TEST's volume came back as another track's).
- **Keys:**
  - `volume`, `pan`;
  - `send1.level` to `send4.level`;
  - `eq1.gain`, `eq1.freq` and `eq1.q`, up to band 4;
  - `prefilter.gain`, `prefilter.lowcut` and `prefilter.highcut`;
  - `qc1` to `qc8` (Quick Controls);
  - `insert1.p1` to `insert2.p8`: the parameters of the plugins in slots 1 and 2, in the bank order Cubase decides.
- **It selects the track,** because the controls follow the selection.
- **`display`** is the current value as Cubase shows it, in real units ("-18.2", "-20.0 dB", "100.0Hz").
- **`converts_units`** indicates whether the parameter accepts values in real units. All do except the Quick Controls.

### `cubase_convert_value` (navigation, changes nothing)

- **Input:** `track`, `parameter` and **one** of these two: `plain` (real units: −20 for −20 dB, 1000 for 1 kHz) or `value` (0..1).
- **Output:** both values. Cubase does the conversion (`convertParameterPlainToProcessValue`) and it is exact.
- **What it is for:** it replaces any calibration. Verified in Cubase Elements: volume goes from 0 dB → 0.7891 to −20 dB → 0.2551, a **non-linear** scale, so there is no need to estimate values.
- **Verified units:**
  - volume, sends and gains in dB;
  - frequencies in Hz;
  - Q unitless;
  - compressor Ratio as a number (4 = 4:1);
  - **pan from −100 (left) to +100 (right)**, with 0 at the center.
- **Errors:** `OUT_OF_RANGE` (outside the parameter's range), `NO_UNIT_CONVERSION` (Quick Controls) and `NOT_AUTOMATABLE`.

### `cubase_record_automation` (write, plays audio)

- **Input:**
  - `track` and `parameter`;
  - `points`: from 1 to 64 points in increasing order. Each point has a `position` ("9. 1. 1. 0") and **one** of these two values:
    - `plain`: in real units, converted by Cubase. **This is recommended;**
    - `value`: normalized, from 0 to 1;
  - `verify` (default `true`) and `dry_run`.
- **What it does:**
  1. selects the track;
  2. enables W and disables R;
  3. plays from one bar before the first point;
  4. "touches" the control, follows the curve (linear between points) according to the cursor position and "releases" it;
  5. stops playback, leaves W as it was and **R enabled**, so the new curve plays (TW-1616: with R back off, an export played the last point's value instead of the curve); `read_automation` reports it.
  - With `verify`, it plays again with R enabled and compares the value read with the curve (tolerance 0.05).
- **Output:** the curve with the normalized value of each point (`points`), the values written (`written`), `complete` (`false` when playback stopped before the last point, for example because the user pressed Stop: the curve is cut), `read_automation`, `verified`, the discrepancies (`mismatches`) and notes.
- **Errors:** `PARAM_NOT_FOUND`, `OUT_OF_RANGE`, `NO_UNIT_CONVERSION`, `NOT_AUTOMATABLE` (nothing is bound: empty slot or unassigned Quick Control), `TRANSPORT_RUNNING`, `NOT_RECORDED`, `BAD_TIME`, `CONTROLS_NOT_BOUND` (the controls did not follow the track's selection) and `WRITES_DISABLED`.
- **Limitations:**
  - positions use the time signature at the cursor position (`cubase_get_project`). Time signature changes across the project are not followed; if Cubase does not report the time signature, 4/4 is assumed;
  - a point is written every ~0.1–0.3 s;
  - **a track created after the MIDI Remote script loaded records no automation from it** (TW-1616: the parameter moves, but Cubase writes nothing; after reloading the scripts the same curve recorded and verified). Use `verify`: a failed read-back says so; reload the MIDI Remote scripts or restart Cubase, then record again;
  - the curve acts where the parameter does: PreGain is before the inserts, so a compressor on the track changes how much of a PreGain drop is heard (TW-1616: −10 dB came out as −7 to −9 dB);
  - **it makes sound**: turn down the monitor volume;
  - with R enabled, the recorded curve overrides the parameter.

## What cannot be done

Verified in the proof of concept:
- **Routing:** changing inputs, outputs or send destinations. The API ignores it or leaves it on "No Bus".
- **Reading track contents:** events, audio, markers as data, or automation curves.
- **Completing Cubase dialogs:** adding tracks with options or detecting silence.
- **Loading channel strip modules** other than the EQ (Cubase Elements).
