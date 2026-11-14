# MCP tool reference

**English** · [Español](04-tools.es.md)

The `trackwright` server exposes 32 tools. Each one has an input schema and an output schema that the MCP client receives automatically; this page explains how to use them and what their limitations are.

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
| `insert:N` | The plugin loaded in insert slot N (1–8). |
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
| `TRACK_NOT_FOUND`, `TRACK_AMBIGUOUS`, `NO_SELECTION` | The track cannot be resolved. |
| `STALE_REF`, `INVALID_OBJECT` | The reference is from another session or the object no longer exists. |
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

- **Input:** `track`, or `step` (`next` or `prev`).
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

### `cubase_remove_selected_tracks` (destructive)

- **Input:** `expect_selected` and `dry_run`.
- It only acts if the given track is the **only** selected track (`SELECTION_MISMATCH`, with the list of selected tracks), because the Cubase command deletes all selected tracks. Select it first with `cubase_select_track`.
- Limitation: it cannot see tracks without a mixer channel (markers, folders), so it does not know whether any of them is selected. Check the screen before applying.
- If the track has events, Cubase may ask for confirmation (unless that warning has been disabled) and the tool returns `pending_confirmation`.
- For tracks without a mixer channel (markers, folders), select them by hand and use `cubase_run_command` with `project.remove_selected_tracks`.

### `cubase_split_at_locators` (destructive)

- **Input:** `left`, `right` and `dry_run`.
- Sets the locators, reads them back and runs "Split Loop".
- **Splits every track** that has events in that range, so it is refused with `NOT_ALLOWED` while `[writes] allowed_tracks` is set.
- The locators **stay** at the split points; restoring them immediately could get ahead of the command. The output includes `previous_left` and `previous_right`, so you can restore them later with `cubase_set_position`.

### `cubase_add_track_interactive` (write, with the user)

- **Input:** `phase` (`start` or `confirm`), `kind` (`audio`, `group` or `folder`) and `suggested_name`.
- **`start`:** opens Cubase's "Add Track" dialog and returns `awaiting_user` with instructions for the user. It rejects names that already exist (`NAME_CONFLICT`), so that `confirm` does not mistake an old track for the new one.
- **`confirm`:** checks that the track exists. Folders have no mixer channel, so in that case verification is visual.

### `cubase_run_command` (destructive, advanced)

- **Input:** `key`, `dry_run` and `force`.
- Runs a command from the allowlist. The specific tools are preferable.
- **Refused here** (`USE_DEDICATED_TOOL`, also in a dry run): `file.save` and `file.save_new_version` (use `cubase_save_project`, which checks `[writes] save` and verifies the file) and `project.remove_selected_tracks` (use `cubase_remove_selected_tracks`, which checks the selection).
- **Permission:** commands act on the selection in the Cubase window, which may include any track, so every command except navigation needs writes enabled and is refused with `NOT_ALLOWED` while `[writes] allowed_tracks` is set.

| `key` | Class |
|---|---|
| `zoom.in`, `zoom.out` | unknown |
| `edit.undo`, `edit.redo`, `edit.cut`, `edit.copy`, `edit.paste`, `edit.delete`, `edit.split_at_cursor`, `edit.split_range`, `edit.select_all`, `edit.select_none`, `edit.select_in_loop` | ui_selection |
| `edit.split_loop` | direct |
| `addtrack.audio`, `addtrack.group`, `addtrack.folder`, `audio.detect_silence`, `file.export_audio_mixdown`, `file.import_audio` | dialog (export and import: verified, TW-1204 and TW-1203; the import file picker blocks Cubase while it is open) |
| `addtrack.marker`, `marker.insert`, `project.select_track_next`, `project.select_track_prev`, `transport.locate_next_marker`, `transport.locate_prev_marker` | direct |
| `project.remove_selected_tracks` | confirm (refused here: use `cubase_remove_selected_tracks`) |
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
- **States:** `saved` or `awaiting_user`. The latter if nothing was written within 10 s: there is probably a dialog, such as "Save As" on a project that was never saved.
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
- **Errors:** `TRANSPORT_RUNNING`, `CANNOT_PERFORM` (another dialog is open), `BAD_TIME` and `WRITES_DISABLED`.

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
