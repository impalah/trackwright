# E12 — Extended features

**English** · [Español](E12-extended-features.es.md)

**Epic status: closed (2026-11-13).** All 12 issues are closed or done, all verified in Cubase Elements 15.0.30, and almost all also by the user from Claude Code. Script 1.5.5; 32 tools.

Origin: the user's questions of 2026-11-13. The analysis and the source of each fact are in [`docs/research.md`](../research.md); the commands, in [`docs/reference/cubase-commands.txt`](../reference/cubase-commands.txt).

Common rule: an untested command is **not** exposed as a tool until its class (`direct`, `dialog`, `confirm`…) and its observable effect have been verified in Cubase.

## TW-1201 Automatic startup of Cubase and the bridge

- **Status:** closed. Verified in Cubase on 2026-11-13: bridge started by `serve`, Cubase opened by `cubase_launch`, and `awaiting_user` until the project was opened
- **Goal:** the user should not have to open Cubase or the bridge by hand.
- **Scope:**
  - **`cubase_launch`** (system write, with confirmation):
    - checks whether Cubase is open, by the process and by the script responding;
    - if not, opens it with `open -a "Cubase 15"`, optionally with a `.cpr` project;
    - waits, with a configurable timeout, for the script to respond.
  - **Bridge startup:** `trackwright serve` starts it as a separate process if it does not respond. It must be optional (`[bridge] autostart`) and must not be duplicated if it already exists.
  - **Configuration:** application path (`[cubase] app = "Cubase 15"`) and wait timeout.
- **Risks:**
  - startup dialogs (MediaBay notice, Steinberg Hub) that block until the user responds: the tool must report `awaiting_user` if the script does not respond in time;
  - not opening two instances.
- **Tests:**
  - unit tests, with the launcher and the process checker mocked;
  - manual verification: Cubase closed → tool → Cubase open and the script responding.

## TW-1202 Saving the project and other file operations

- **Status:** closed. `cubase_save_project` tested by the user from Claude Code on 2026-11-13. Experiment in [experiments/tw1202](../../experiments/tw1202/README.md). `Close`, `Revert` and `Quit` are discarded
- **Goal:** save from Trackwright; for example, before and after a session of changes.
- **Prior experiment**, in a throwaway project: class and effect of `File / Save`, `Save New Version` and, only to classify them, `Save As`, `Open`, `New`, `Close` and `Revert`.
- **Scope after the experiment:**
  - **`cubase_save_project`:** `Save` or `Save New Version`. Verification: no dialog, and a visual check or a check of the file date if the path is known.
  - **`Close`, `Revert` and `Quit`:** at most in the `cubase_run_command` list, classified as destructive.
- **Note:** this changes the current policy (“Trackwright never saves”). It must be documented and require `dry_run` and confirmation.

## TW-1203 Guided audio import flow

- **Status:** closed. `cubase_import_audio` tested by the user from Claude Code on 2026-11-13. Experiment in [experiments/tw1203](../../experiments/tw1203/README.md)
- **Goal:** «Importa este audio en la pista X en el compás N» (*Import this audio into track X at bar N*) with minimal effort from the user.
- **Flow:**
  1. select the track [VER];
  2. place the cursor [VER];
  3. `File / Import Audio File` [CMD], which opens the file picker;
  4. the user chooses the file, and Trackwright tells them which one, if it has been given a path;
  5. confirmation, in two phases, like `cubase_add_track_interactive`.
- **Prior experiment:** class of the command, and whether the import goes to the selected track and the cursor position (or asks for copy and conversion options).
- **Verification:** ~~visual~~ by probing event edges (TW-1211).

## TW-1204 Guided audio export flow

- **Status:** closed. `cubase_export_mix` tested by the user on 2026-11-13 with the full episode as MP3. The duration tolerance was widened for compressed formats ([experiments/tw1204](../../experiments/tw1204/README.md))
- **Goal:** export the mix of a range.
- **Flow:**
  1. place the locators [VER];
  2. `File / Export Audio Mixdown` [CMD], which opens its dialog;
  3. the user reviews the options and exports;
  4. two-phase confirmation.
- **Prior experiment:** class of the command and whether the dialog takes the range from the locators.

## TW-1205 Experiment: plugin presets

- **Status:** closed. `cubase_plugin_preset` tested by the user from Claude Code on 2026-11-13. Experiment in [experiments/tw1205](../../experiments/tw1205/README.md). Requires a loaded preset and a click by the user on the plugin window the first time; the preset name is not accessible
- **Hypothesis:** `Preset / Next` and `Previous` act on the plugin editor that has the focus.
- **Experiment:**
  1. open the plugin editor from the API, with the slot's edit parameter;
  2. read the parameters;
  3. run `Preset / Next`;
  4. read again and compare.
  - Also test with the editor closed and with another plugin focused, to find out what it acts on.
- **If it works:** tool `cubase_plugin_preset_step(track, slot, direction)`, which verifies by comparing parameters. Choosing a preset by name is not possible [NE].

## TW-1206 Experiment: recording volume automation

- **Status:** done. **Positive result with variant B2** (2026-11-13); A does not record and B1 is not available in Elements
- **Hypothesis:** with automation write enabled (parameter 4013) and the transport running, volume changes made through the API are recorded as automation and play back with read enabled (4014).
- **Experiment**, without changing the script, on a track with audio in a throwaway project:

  | Step | Action | Measurement |
  |---|---|---|
  | A0 | Note the volume, 4013 and 4014, the cursor and the visible automation mode | initial state |
  | A1 | 4013 = 1 (write enabled) on POC-TEST; cursor at bar 1 | readback |
  | A2 | **The user presses Play.** Trackwright writes a volume ramp (0.79 → 0.40 over about 4 s, one step every 0.2 s). **The user presses Stop** | writes with readback |
  | A3 | 4013 = 0 and 4014 = 1; cursor at bar 1; volume set to 0.79 by hand | readback |
  | A4 | **The user presses Play.** Trackwright **reads** the volume every 0.2 s for about 5 s. The user presses Stop | does it play back the ramp? |
  | A5 | The user looks at the volume automation lane of POC-TEST | does the curve appear? |
  | A6 | Cleanup: the user deletes the automation, or Undo; 4014 = 0; original volume | final state same as A0 |

- **Caution:** audio is played. Turn down the monitor or mute the output; muting the output does not affect the track's automation.
- **Result of variant A (2026-11-13): it does not record.** Details in [verification.md](../verification.md). The fader moves during playback, but no automation is left; with read enabled, the volume does not change.
- **Pending variants:**
  - **B1 — discarded in Elements (2026-11-13):** the mode commands give `canPerform=false` and the selector does not appear in the interface.
  - *(B1, original approach)* **Without changing the script:** the user manually sets the automation mode to **Auto-Latch** (or Cross-Over), in which writing starts with any change of the parameter, and A1–A4 are repeated.
  - **B2 — WORKS (2026-11-13):** the surface fader with touch records the automation, and it plays back with R enabled (from 0 to −12.2 dB between bars 1 and 4.3). See [verification.md](../verification.md).
  - *(B2, preparation)* script 1.2.1 with the fader behind `AUTOMATION_FADER_ENABLED`; test version `1.2.1+tw1206` with `experiments/tw1206/build.py`; step `record-b2` in `experiments/tw1206/automation.py`; tests with the harness in `tests/script/test_automation_fader.py`. Protocol in `experiments/tw1206/README.md`.
  - *(B2, approach)* **With changes to the script:** a surface fader bound (`makeValueBinding`) to the volume of the selected track (`mTrackSelection.mMixerChannel.mValue.mVolume`). The script would move the fader with its touch state (`mTouchState`), like a physical controller, which is how controllers record automation.
- **If any variant works:** design `cubase_record_automation(track, parameter, points)`. It would require starting the transport from Trackwright, with `Transport / Start` or `mTransport.mValue.mStart`, which would need to be verified.

## TW-1207 Automation tool and extension to other parameters

- **Status:** closed. Verified in Cubase on 2026-11-13: volume fade recorded from Claude Code with script 1.4.0
- **Goal:** the `cubase_record_automation` tool and automation of more parameters than volume.
- **Verified basis:**
  - surface fader with touch (TW-1206 B2);
  - `Transport / Start` and `Stop` from Trackwright (2026-11-13).
- **Experiment B3** (script `1.3.0`, controls behind `AUTOMATION_CONTROLS_ENABLED`; automatic test in `experiments/tw1206/controls.py`):
  - **controls bound to the selected track (45):** volume, pan, level of sends 1 to 4, channel EQ (gain, frequency and Q of bands 1 to 4), pre-filter (gain, low cut and high cut), Quick Controls 1 to 8, and parameters 1 to 8 of insert slots 1 and 2 (plugin parameter banks);
  - **identification:** each control reports the title of the parameter bound to it (`auto.list`), so we know which plugin parameter falls in each bank position;
  - **criterion:** a control “records” if, during playback with read, its value follows the ramp without anyone touching it.
- **Planned design of the tool, after the experiment:** `cubase_record_automation(track, parameter, points[(position, value)])`:
  1. selects the track;
  2. enables W;
  3. places the cursor before the first point and starts playback;
  4. touches the control, writes the values in sync with the cursor position and releases it;
  5. stops playback and disables W;
  6. verifies with a read playback (optional).
  - It will require writes enabled and confirmation, because it plays audio and modifies the project.

## TW-1208 Real units in automation (Cubase's exact conversion)

- **Status:** closed. Verified in Cubase on 2026-11-13: conversion of 12 parameters and recording with `plain` from Claude Code
- **Origin:** in real use (2026-11-13), the model did not know the mapping between the normalized value and dB. It estimated −20 dB ≈ 0.36 (it is 0.2551) and proposed calibrating by moving the fader.
- **Evidence:** `da.convert` (`convertParameterPlainToProcessValue`) converts exactly and in both directions the volume, sends, EQ (gain and frequency), pre-filter and plugin parameters ([verification.md](../verification.md)).
- **Scope:**
  1. **Mapping** between each automation control and its DirectAccess parameter:

     | Control | Object | Parameter |
     |---|---|---|
     | `volume` | channel | tag 1025 |
     | `pan` | Panner | tag 4201 |
     | `sendN.level` | send slot N | tag 4097 |
     | `eqB.gain/freq/q` | strip EQ | title «EQ B Gain/Freq/Q» |
     | `prefilter.gain/lowcut/highcut` | InputFilter | `PreGain`, `LC-Freq` and `HC-Freq` |
     | `insertS.pN` | plugin in slot S | by title, taken from the control's title, for example «Compressor / Threshold» → «Threshold» |

     The `qcN` have no known mapping: they only accept normalized values.
  2. **`cubase_record_automation`:** each point accepts `value` (normalized) **or** `plain` (real units: dB, Hz…). `plain` values are converted with Cubase before recording, and the dry run shows the conversion.
  3. **Tool `cubase_convert_value(track, parameter, plain | value)`:** read-only, converts in both directions. It replaces calibration: it is exact and moves nothing.
  4. **`cubase_list_automation_targets`:** the `display` field is already in real units. This is documented instead of converting the 45 parameters, which would take several seconds.
- **Tests:** simulator with the Panner objects, send slots, InputFilter, EQ with 12 parameters and plugins with named parameters; tests of mapping, conversion, errors (`NO_UNIT_CONVERSION` on Quick Controls, `OUT_OF_RANGE`) and the MCP contract.

## TW-1209 Reading the properties of the open project

- **Status:** closed. `cubase_get_project`, verified in Cubase on 2026-11-13 (3/4, metronome, project folder); automation uses the time signature read. Out of scope: following time signature changes along the project
- **Goal:** the model should know the project context before acting: name, tempo, time signature, sample rate, length, cycle and metronome. Today it assumes 4/4 and does not know the name or the sample rate.
- **What exists today:** `cubase_get_transport` already reads the cursor, the cycle locators and the tempo.
- **What the MIDI Remote API offers** (according to Cubase 15's `midiremote_api_v1.d.ts`; **unverified**):

  | Property | Candidate route | Reading |
  |---|---|---|
  | Cycle enabled | `mHostAccess.mTransport.mValue.mCycleActive` (host value, bindable to a surface control) | Probable, like the automation controls |
  | Metronome enabled and click level | `mTransport.mValue.mMetronomeActive` and `mMetronomeClickLevel` | Probable |
  | Tempo, cursor, locators | `mTimeDisplay` | **Verified** |
  | Project name and path | Not in the API. Alternative: the `.cpr` opened by the Cubase process (`lsof`), without opening the file | To explore; **requires the user's permission** |
  | Time signature (numerator/denominator) | Not in the API. Alternatives: a DirectAccess object outside the mixer (to explore) or deducing it from the relationship between the primary and secondary time displays | Uncertain |
  | Sample rate, resolution, frame rate, project start and length | Not in the API (they belong to «Configuración del proyecto» (*Project Setup*), a dialog) | Probably impossible from the script |
  | Precount, use of the tempo track | Only as commands that toggle the state (`Transport / Precount On`, `Tempo Track Rehearsal Mode On/Off`), with no reading | Impossible to read the state |
- **Prior experiment (TW-1209a):**
  1. add to the script, in an experiment build, surface controls bound to `mCycleActive`, `mMetronomeActive` and `mMetronomeClickLevel`, and check that their values arrive;
  2. explore with DirectAccess the project objects outside the mixer, read-only, looking for the time signature or sample rate;
  3. with the user's permission, check whether `lsof` identifies the open `.cpr`.
- **Deliverable:** tool `cubase_get_project`, which returns what is verified and marks as `null`, with its reason, what cannot be read.
- **Consequence:** if the time signature can be read, `cubase_record_automation` and the seconds conversion stop assuming 4/4.

## TW-1210 Modifying the project properties

- **Status:** closed. `cubase_set_project` tested by the user from Claude Code on 2026-11-13. Experiment in [experiments/tw1210](../../experiments/tw1210/README.md): 9 switches and the click level. Out of scope: time signature, pre-roll and post-roll duration, and tempo track
- **Goal:** change from the MCP the project properties that the API allows, with dry run, confirmation and readback, like the rest of the writes.
- **What exists today:** `cubase_set_tempo` (verified) and `cubase_set_position` (cursor and cycle locators, verified).
- **Candidates:**

  | Property | Candidate route | Readback |
  |---|---|---|
  | Cycle on/off | Host value `mCycleActive` from a surface control, or the `Transport / Cycle` command (toggles) | Depends on TW-1209 |
  | Metronome enabled and click level | `mMetronomeActive` and `mMetronomeClickLevel` | Depends on TW-1209 |
  | Precount, use of the tempo track | Commands that toggle, with no reading: they would only be safe if the state could be read | No readback: **not implemented** unless TW-1209 finds how to read them |
  | Time signature, sample rate, length | Only in the «Configuración del proyecto» (*Project Setup*) dialog (command `Project / Setup`, class `dialog`) | Interactive tool like `cubase_add_track_interactive`: Trackwright opens the dialog, the user changes it and Trackwright reads back what it can |
- **Rules:** every write checks the policy (`check_project_write`), does a dry run by default and reads back. Nothing without readback is presented as verified.

## TW-1211 Range editing in seconds (podcast)

- **Status:** closed. Verified in Cubase on 2026-11-13 from Claude Code (`delete_time` 2–30 s, `verified: true`, state restored and undone with Undo)
- **Origin:** the user edits podcasts, where the bar does not matter. They want to give orders such as «borra el audio de la pista X entre el segundo 2 y el 30» (*delete the audio on track X between second 2 and second 30*).
- **What exists:**
  - `cubase_set_position` with `unit: "seconds"` for the cursor and the locators. Its verification assumes 4/4 and constant tempo: it must switch to reading back `time2` from the Transport object (TW-1209);
  - verified commands: `Split Loop` cuts all tracks with events in the range, and `Select in Loop` creates a range selection.
- **API limitation:** events cannot be read or modified. All editing goes through commands that act between the locators or on the selection.
- **Experiment** ([experiments/tw1211](../../experiments/tw1211/README.md)):
  1. position in seconds and read back with `time2`;
  2. see whether `Locate Next/Previous Event` allows reading event edges (event probing, for verification);
  3. see the scope of `Select in Loop`: selected tracks or all of them?;
  4. see the effect of each action on the 2–30 s range of a track:

     | Action | Command |
     |---|---|
     | Delete leaving a gap | `Delete` on the range selection |
     | Delete closing the gap | `Delete Time` |
     | Cut time | `Cut Time` |
     | Silence | `Process / Silence` |
     | Insert silence | `Insert Silence` |
     | Crop | `Crop Range` |
  5. class of each command (direct, dialog, selection) and whether `Undo` undoes it.
- **Deliverable:** tool `cubase_edit_range(tracks, start, end, unit, action)`, with dry run, confirmation and, if event probing works, verification.
- **Risks:**
  - `Delete Time` and `Split Loop` affect all tracks;
  - without event probing there is no readback;
  - that is why the experiment is done with the project saved and with the user watching.

## TW-1212 Range editing on a single track

- **Status:** closed. `cubase_edit_range` with `track` (only `delete`). Verified in Cubase on 2026-11-13, first by Claude (`verified: true`, 7 undo steps, reported and actual) and then by the user from Claude Code. Details in [experiments/tw1212](../../experiments/tw1212/README.md)
- **Origin:** `cubase_edit_range` acts on all tracks, because `Select in Loop` with the range tool selects all of them (TW-1211). For a podcast it is also necessary to remove, for example, a cough from a guest's mic without touching the others.
- **Routes to investigate:**
  1. **Object instead of range:** `Split Loop` cuts at the locators (on all tracks, without changing the sound); then, select only the track's events within the range (with `Select All on Tracks`, `Select Events under Cursor` or `Select from Cursor to End` with the track selected) and apply `Delete`. The scope of each selection must be verified.
  2. **Hide or lock the other tracks** during editing, if the API or the commands allow it, and if `Select in Loop` respects locked or hidden tracks.
  3. **Commands from the official list** that limit the range to the selected tracks.
  4. **Silence instead of delete** with automated volume (TW-1207). It does not touch the events, so it has different semantics.
- **Verification:** event probing (TW-1211), which already works per selected track, on the edited track and on another one that must not change.
- **Deliverable:** a `tracks` parameter in `cubase_edit_range`, or a separate tool, if any route works.
