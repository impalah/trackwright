# MCP tool reference

**English** · [Español](04-tools.es.md)

The `trackwright` server exposes 37 tools. Each one has an input schema and an output schema that the MCP client receives automatically; this page explains how to use them and what their limitations are.

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
    - `file`, optional: the path of the file the user will choose. It is used to tell the user the path and to get its duration with `afinfo`.
  - **What it does:**
    1. selects the track;
    2. moves the cursor to the position;
    3. opens "Import Audio File".
  - **While the file picker is open, Cubase does not respond to the script** (verified). That is why the phase does nothing else and returns `awaiting_user`, with instructions: Cmd+Shift+G and the path.
- **The user** chooses the file and accepts the options. Cubase copies it to the project's *Audio* folder.
- **`confirm` phase** (same track, position and file, plus `since`):
  - if Cubase still does not respond: `awaiting_user`, because the file picker is still open;
  - otherwise, it probes the track and looks for edges at the position and at the position plus the duration. It returns `done` and `verified`, or `not_found` if it was canceled or went somewhere else. Only **new** edges count: the start phase probes the track before opening the dialog, so an event that was already at that position does not confirm a canceled import, and each expected position needs its own edge. If the start phase ran in another server session, the edges before are unknown and `verified` is `null`;
  - `copied_to_project` lists the new copies in `<project>/Audio`, by name only.
- **Verified in Cubase Elements:** a 3 s tone ended up on POC-TEST from 150 to 153 s.
- **Undo** removes the event, **not** the copy on disk.
- **Renders** (`file` in `Trackwright/renders/` with its provenance, TW-1606): `start` refuses a position other than the render's (`MISALIGNED`), the track the render replaces (`BAD_REQUEST`), and a render that changed after it was made (`BAD_RENDER`); the instructions ask to untick "Copy file to project folder". `confirm` returns `render` and, with `[workspace] enabled`, records the render and the new track in `state.json` as the rendering skill's (`owned: true`), and reminds to mute the original track; if an earlier render track of the same skill replaced the same track, it says so, to be removed once the user confirms.

## Exporting the mix

### `cubase_export_mix` (with the user, two phases)

Trackwright **never exports by itself**: it sets the range and opens the Cubase dialog; the format and the button are up to the user.

- **`start` phase** (`dry_run` by default):
  - **Input:** `start` and `end` in seconds (or bars with `unit: "bars"`). Without them, it exports **all the audio**: "Select All" and "Locators to Selection" set the locators from the first to the last event.
  - **What it does:** sets the locators to the range and opens "Export Audio Mixdown". In Elements the dialog has no range field: it exports between the locators (verified).
  - **Output:** `awaiting_user`, the folder Cubase will suggest (`<project folder>/Mixdown`, inferred from the open files), the expected duration and `since` (a timestamp).
- **The user,** in the dialog, checks the channel (Stereo Out), the name, the path and the format (WAV for archiving, MP3 for publishing) and clicks **Export Audio**.
- **`confirm` phase:**
  - **Input:** `since` and `expected_seconds` from the previous phase; `folder` if another folder was chosen.
  - **What it does:** looks in the folder for audio files created after `since` and reads **only** their name, size, date and duration (with macOS `afinfo`).
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

### `cubase_workspace` (`status` reads; `init` writes files, with dry run)

The `Trackwright/` folder inside the open project's folder, where skills keep their files (TW-1602). The project folder comes from the files Cubase has open; with no project, or several, it is not guessed.

- **Input:** `action` (`status` by default, or `init`) and `dry_run` (for `init`).
- **`status`:** says whether the folder exists, which subfolders `init` would create, whether `state.json` and `profile.toml` exist, how many items each skill has recorded (`owned`, by `skill:kind`) and a summary of the episode profile. Always allowed.
- **`init`:** creates `Trackwright/` and its subfolders `renders/`, `previews/`, `analysis/` and `reports/`, and nothing else. Needs `[workspace] enabled`; idempotent.
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

### `cubase_render` (`render` writes files, with dry run; `list` reads)

Processed audio for the project, written to `Trackwright/renders/` (TW-1606). Cubase's API cannot process a track's audio, so a skill exports the track alone, processes the export in Python, and imports the result on a new track, muting the original.

- **Input:** `action` (`render` by default, or `list`); for `render`: `file` (absolute path of the export), `start` (project time of the export's first sample: its range start), `process` (`gain`), `gain_db` (±40), `name` (default `<track or source>-<process>`), `track` (the track the render replaces), `skill` and `run_id` (who renders, recorded in the provenance), `dry_run`.
- **`render`:** writes `<name>.wav` (32-bit float WAV, the source's rate and channels) and `<name>.json`, the **provenance**: the source's path, size and SHA-256, the process and its parameters, the project position, the track it replaces (name and uid), the render's own SHA-256 and peak, and the Trackwright version. An existing render is never overwritten (Cubase may still reference it): the next one is `<name>-2.wav`. Needs `[analysis] enabled` (it reads audio, with its `max_seconds`) and `[workspace] enabled`, and the workspace created with `cubase_workspace`.
- **Then:** create an audio track (`cubase_add_track_interactive`), import the render on it with `cubase_import_audio` at the position returned, and mute the original track (`cubase_set_track_mix`). In Cubase's import options, untick "Copy file to project folder" (the render already is in the project folder) and leave the 24-bit conversion off.
- **`list`:** every render with its provenance, the track it was imported on (from `state.json`), whether that track is still in the project, and `problems`: the render changed after it was made, its source changed or is gone.
- **Errors:** `WORKSPACE_DISABLED`, `ANALYSIS_DISABLED`, `TOO_LONG`, `NO_PROJECT_FOLDER`, `NO_WORKSPACE`, `NOT_FOUND`, `BAD_AUDIO`, `BAD_TIME`, `BAD_REQUEST`, `BAD_RENDER`.

## Analyzing audio

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
  5. stops playback and leaves W and R as they were.
  - With `verify`, it plays again with R enabled and compares the value read with the curve (tolerance 0.05).
- **Output:** the curve with the normalized value of each point (`points`), the values written (`written`), `complete` (`false` when playback stopped before the last point, for example because the user pressed Stop: the curve is cut), `verified`, the discrepancies (`mismatches`) and notes.
- **Errors:** `PARAM_NOT_FOUND`, `OUT_OF_RANGE`, `NO_UNIT_CONVERSION`, `NOT_AUTOMATABLE` (nothing is bound: empty slot or unassigned Quick Control), `TRANSPORT_RUNNING`, `NOT_RECORDED`, `BAD_TIME` and `WRITES_DISABLED`.
- **Limitations:**
  - positions use the time signature at the cursor position (`cubase_get_project`). Time signature changes across the project are not followed; if Cubase does not report the time signature, 4/4 is assumed;
  - a point is written every ~0.1–0.3 s;
  - **it makes sound**: turn down the monitor volume;
  - with R enabled, the recorded curve overrides the parameter.

## What cannot be done

Verified in the proof of concept:
- **Routing:** changing inputs, outputs or send destinations. The API ignores it or leaves it on "No Bus".
- **Reading track contents:** events, audio, markers as data, or automation curves.
- **Completing Cubase dialogs:** adding tracks with options or detecting silence.
- **Loading channel strip modules** other than the EQ (Cubase Elements).
