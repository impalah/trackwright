# Cubase verification log

**English** · [Español](verification.es.md)

Each entry records a **real** run against Cubase. Tests with the simulator are not recorded here.

## 2026-11-12 — first verification of Trackwright 0.1.0 (script 1.0.0)

- **Environment:** macOS 27.2 (arm64), Cubase **Elements** 15.0.30, test project with `POC-INSTR` (instrument, with StudioEQ in slot 1) and `POC-TEST` (audio).
- **Installation:** `trackwright script install --apply` (after fixing TW-1014). Cubase restarted. The "Trackwright – Bridge" surface appeared on its own when the bridge started.
- **`trackwright doctor`:** all checks passed (script `up_to_date`, bridge running, Cubase responds with script 1.0.0 and application 15.0.30).
- **`trackwright ping`:** OK in 16 ms, with the Unicode echo `hola-ñ-✓`.
- **Read integration tests** (`TRACKWRIGHT_INTEGRATION=1`): 3 passed. The 2 write tests were skipped: they were not requested.
- **The 9 read tools**, run against the real service:

| Tool | Result | Time |
|---|---|---|
| `cubase_status` | session `dv06ye6vc1gb`, script 1.0.0, mixer access | 36 ms |
| `cubase_list_tracks` | 3 channels (Stereo Out, POC-INSTR, POC-TEST), without the trailing duplicate | 129 ms |
| `cubase_get_selected_channel` | `track: null`: no track with a channel was selected | 108 ms |
| `cubase_list_inserts` (POC-INSTR) | slot 1 = StudioEQ, 2 through 8 empty | 449 ms |
| `cubase_list_available_plugins` (filter "eq") | collection "Por defecto" (Default), 53 plugins, 3 matches (CurveEQ, DJ-Eq, StudioEQ) | 562 ms |
| `cubase_list_parameters` (channel, limit 5) | 39 parameters; `next_offset` = 5, `truncated` = true | 224 ms |
| `cubase_list_parameters` (filter "vol") | `Volumen` (1025) and `clickVolume` (4117) | 339 ms |
| `cubase_get_parameter` (strip:eq, 4232) | "EQ 1 Gain" = 0.5 ("0.0dB", plain 0.0) | 554 ms |
| `cubase_get_transport` | cursor at 1. 1. 1. 0; cycle between bars 2 and 4 | 17 ms |
| `cubase_poll_changes` | 2 events | 207 ms |

### Reversible writes (integration tests)

Command: `TRACKWRIGHT_ALLOW_WRITES=1 TRACKWRIGHT_TEST_TRACK="POC-TEST"`. Result: **5 passed** in 1.52 s.

- **`test_mute_roundtrip`:** `cubase_set_track_mix` turns on mute for POC-TEST, verifies it by reading it back and restores it.
- **`test_cursor_roundtrip`:** `cubase_set_position` moves the cursor to bar 3, verifies it and returns it to its position.
- **State before and after,** read independently: mute `False` → `False`; cursor `1. 1. 1.  0` → `1. 1. 1.  0`. Nothing was left changed.

### Remaining writes and commands (second batch)

Run directly against the service, with the write policy enabled only for this session. The user visually confirmed the steps the API cannot observe.

**Part A, without intervention:** 23 of 25 steps correct. The 2 errors were the expected ones (`PRECONDITION_FAILED` due to a wrong `expect_title`, and `SLOT_OCCUPIED`).

| Tool | Test | Result |
|---|---|---|
| `cubase_set_track_mix` | volume 0.7 and solo on POC-TEST, then restore | `-1.98` dB and `Activ.` (on); restored and verified |
| `cubase_rename_track` | POC-TEST → TW-RENAMED → POC-TEST, by `uid:` | verified in both directions |
| `cubase_set_parameter` | strip EQ +3 dB (`unit=plain`) and restore | display `3.0dB`; restored |
| `cubase_set_parameter` | wrong `expect_title` | `PRECONDITION_FAILED`, nothing written |
| `cubase_select_track` | POC-INSTR, next, previous, POC-TEST | 4/4 verified |
| `cubase_set_tempo` | 120 → 100 → 120 | read back 99.99999 → 120 |
| `cubase_set_position` | cycle 3–5, cursor at second 4 (→ bar 3), then restore | verified |
| `cubase_insert_plugin` | Compressor in slot 1 of POC-TEST, then repeat | inserted and verified; the repeat gives `SLOT_OCCUPIED` |
| `cubase_list_parameters` | Threshold of the inserted Compressor | tag 4201, `-20.0 dB` |

The final state of POC-TEST (volume, mute, solo, name), the tempo and the cursor match the initial state. **Compressor is deliberately left inserted** in slot 1 of POC-TEST: the API has no verified way to remove plugins.

**Part B, with visual confirmation:**

| Tool | Test | Result |
|---|---|---|
| `cubase_markers` | create a marker track; marker at bar 2 | visually confirmed |
| `cubase_markers` | `locate_prev` from bar 4 | → bar 2 |
| `cubase_markers` | `locate_next` from bar 2, with no further markers | → `70. 4. 4. 97`, the end of the POC-TEST audio. **Finding:** in the POC it was observed to stay put; it now goes to the end of the last event |
| `cubase_run_command` | `project.remove_selected_tracks` with the marker track selected by hand | deleted; the other tracks intact. **No confirmation dialog**, because the user had checked "no volver a preguntar" (*Don't ask again*) in Cubase |
| `cubase_split_at_locators` | bars 10–12 | POC-TEST audio split at 10 and 12 (visually confirmed); `previous_left` and `previous_right` = 2 and 4; restored afterwards |
| `cubase_add_track_interactive` | `start` (dialog) and `confirm` | dialog opened; the user named it `TW-GROUP`; `confirm` → `done`, verified, with its `uid:` |
| `cubase_remove_selected_tracks` | with a wrong expected track | `SELECTION_MISMATCH`, nothing deleted |
| `cubase_remove_selected_tracks` | TW-GROUP, after selecting it | `done`, verified; Stereo Out, POC-INSTR and POC-TEST remain |

**Conclusion:** all **21 tools** have been run against Cubase Elements 15.0.30. The results the API cannot observe were visually confirmed by the user.

**Changes left in the test project:**
- Compressor in slot 1 of POC-TEST;
- POC-TEST audio split at bars 10 and 12;
- POC-TEST selected.

The project was not saved.

## 2026-11-13 — real use from Claude Code

- **Registration:** `claude mcp add --scope user trackwright -- uv --directory /path/to/trackwright run trackwright serve`. `claude mcp list` → `✔ Connected`.
- **Configuration:** `~/.config/trackwright/config.toml` with `[writes] enabled = true`, with no track restriction.
- **New Claude Code session,** without the development context. According to the user, the following worked:
  - `cubase_status`;
  - the track listing;
  - muting and unmuting a track. The model **first rehearsed** (`dry_run`) and **asked for confirmation** before applying, following the server instructions.
- **Conclusion:** the full chain MCP client → `trackwright serve` → bridge → Cubase works in real use, and a model with no prior knowledge of the project uses the tools based on their descriptions.

## 2026-11-13 — TW-1101 experiment (status panel, script 1.0.1+tw1101)

- **Protocol:** [`experiments/tw1101/README.md`](../experiments/tw1101/README.md).
- **Installation:** `script install --file experiments/tw1101/Trackwright_Bridge.js --apply` and Cubase restart.
- **Observation:** the user's screenshots of the MIDI Remote tab.

| Step | Mechanism | Observed result |
|---|---|---|
| E1 (bridge stopped) | surface without an active page | Only the lamp is drawn, round and at its position (8, 2). The text fields are not visible and "Página de mapeado" (*Mapping Page*) shows "-" |
| E2 (bridge running) | `page.setLabelFieldText` | ✅ Row 0: "Trackwright 1.0.1+tw1101", boxed and with lines at the sides |
| E2 | `lamp.mSurfaceValue.setProcessValue` every 9 cycles | ✅ The lamp blinks once per second, according to the user |
| E2/E3 | `lamp.mSurfaceValue.setDisplayValue` + `statusField.relateTo(lamp)` | ❌ Row 2 always shows "-", also after `ping --echo "hola panel"` (09:41:53). The API reports no error (`capabilities.panel.errors = []`) |
| E4 | `page.setLabelFieldHostObject(…, mTrackSelection.mMixerChannel)` | ✅ Row 1 shows "-" with no selection and "POC-TEST" when it is selected. It updates on its own |
| E5 | performance | ✅ `ping` in 15.9 ms, the same as without the panel |
| E6 | `capabilities.panel` | `{enabled: true, errors: []}` |

**Conclusions:**
- **The old drawing** (a box with a white bar and lines at the sides) was the **empty** text field `makeLabelField(0, 0, 4, 1)`: Cubase draws fields without text ("-") that way. This resolves the open question of TW-1101.
- **Works:** fixed text, the name of the selected track, and a lamp controlled by the script.
- **Does not work:** showing variable text through a field related to an element (`relateTo` + `setDisplayValue`). Judging by the top bar ("Último control tocado: Ningún mapeado" (*Last touched control: No mapping*)), a related field seems to show the element's mapping, not its value. This is an unverified hypothesis.

## 2026-11-13 — status panel in script 1.1.0

- **Installation:** `script install --apply` (1.1.0) and Cubase restart. `capabilities.panel = {enabled: true, errors: []}`.
- **Observed by the user:**
  - **Row 1:** "Trackwright 1.1.0".
  - **Row 2:** the name of the selected track.
  - **Activity lamp:**
    - three `ping` calls 2 s apart (09:47:39–09:47:45) → **three short flashes**;
    - ten consecutive `da.channels` calls over 1.0 s (09:47:45–09:47:46) → **lit for that whole second** and off when finished.
- **Conclusion:** TW-1101 verified in Cubase Elements 15.0.30.

## 2026-11-13 — TW-1206 experiment (recording volume automation), variant A

- **Script:** `experiments/tw1206/automation.py`. Full data in `experiments/tw1206/results.json`.
- **Track:** POC-TEST, with audio. Automation mode: whatever the project had, presumably **Touch** (the usual one; not checked).

| Step | Result |
|---|---|
| A0–A1 | Initial state: volume 0.79 (0 dB), W and R off. Write (4013) → "Activ." (on) |
| A2 (10:42:56) | Playback detected through the transport notifications. Ramp of 21 writes from 0.79 to 0.40 (−12.2 dB), all read back exactly. **The fader moved** (observed by the user). Each step took about 0.33 s, because each write resolves the track again |
| Observation | **No curve appeared** in the volume automation lane |
| A3–A4 (10:46:07) | Write off and read (4014) on; volume set to 0.79. During 5 s of playback the volume **stayed at 0.79** the whole time (12 reads) |
| A6 | Restored: 0 dB, W and R off, cursor at bar 1 |

**Findings:**
1. **No automation is recorded** when writing the volume parameter through DirectAccess (`setParameterProcessValue`) with write enabled and during playback. Hypothesis: Cubase does not consider those changes a "touched" control, which is what it needs to record in Touch.
2. **The script receives the cursor position during playback** (`mTransportLocator.mOnChange`): it advanced from bar 1 to bar 4 over the course of the ramp. This makes it possible to detect playback and follow the position.
3. **Latency:** a full write including track resolution costs about 0.33 s. For fast writes in series, writes would have to target the already resolved object.

## 2026-11-13 — TW-1206, variant B1 (automation modes), script 1.2.0

- Script 1.2.0 loaded; 35 commands bound, 0 errors.
- **`canPerform`**, with no track selected and with POC-TEST selected (same result):
  - `false`: `automation.mode_touch`, `automation.mode_auto_latch`, `automation.mode_cross_over` and `automation.next_mode`;
  - `true`: `automation.toggle_write_selected`.
- The user **cannot find** the automation mode selector in the toolbar of their Spanish-language Cubase.
- **Conclusion:** in Cubase **Elements** 15.0.30 the automation modes cannot be changed by command. Hypothesis, not confirmed in Steinberg's documentation: Elements does not offer selectable modes and always works in Touch. **Variant B1 does not apply to this edition.**

## 2026-11-13 — TW-1206, variant B2 (surface fader with touch): **records automation**

- **Script:** `1.2.1+tw1206` (`AUTOMATION_FADER_ENABLED = true`), with bridge and Cubase restarted. `capabilities.automationFader = {enabled: true, errors: []}`.
- **Mechanism:**
  - a surface fader, `makeFader(10, 0, 1, 2)`, bound with `page.makeValueBinding` to `mTrackSelection.mMixerChannel.mValue.mVolume`;
  - its `mTouchState.bindTo(customVariable)`;
  - the script sets that variable to 1 (touch), moves the fader with `mSurfaceValue.setProcessValue` and sets it to 0 (release).
- **Data:** `experiments/tw1206/results-variante-b2.json`. Variant A's, in `results-variante-a.json`.

| Step | Result |
|---|---|
| A0–A1 (11:05:30) | Initial state: 0 dB, W and R off, cursor at bar 1. W turned on |
| A2 (11:06:08) | POC-TEST selected; playback detected; touch → 21 values from 0.79 to 0.40 → release, no errors. **The track volume followed the fader** (from −0.38 to −12.2 dB). The user saw both faders move and, **after stopping, a curve appeared in the volume automation lane** |
| A3–A4, 1st attempt (11:07:17) | **Invalid:** playback detection fooled by the notifications from the cursor's own movement. Fixed in the script: it waits 0.6 s and only counts the cursor advancing |
| A3–A4, retry (11:08:06) | W off and R on. Without any action from Trackwright, the volume **played back the ramp**: −0.07 dB (bar 1) → −2.27 (bar 2) → −6.12 (bar 3) → **−12.2 dB (bar 4.3)**, and held |
| A6 | Volume 0 dB, W and R off, cursor at bar 1. **The recorded curve remains in the project**, with no effect while R is off |

**Conclusions:**
1. **Volume automation can be recorded from Trackwright in Cubase Elements 15.0.30:** with a surface fader bound to the parameter, touched and released by the script. This is how physical controllers record in Touch mode.
2. Writing directly through DirectAccess (variant A) moves the value, but does **not** count as a touch.
3. **Current limitations of the mechanism:**
   - only the **volume** of the **selected track**: the binding is to `mTrackSelection.mMixerChannel`;
   - time resolution of about 0.33 s per point, with playback running;
   - playback is started and stopped by the user.

## 2026-11-13 — playback from Trackwright (script 1.2.2+tw1206)

- **`canPerform`:** `true` for `transport.start` and `transport.stop`.
- **`cubase_run_command("transport.start")`:** the cursor advanced from `1. 1. 1. 0` to `1. 4. 3. 94` in 2.1 s, according to the transport notifications during playback. The user confirms that it played.
- **`cubase_run_command("transport.stop")`:** the cursor stopped at `2. 1. 4. 17` and did not change over the following 0.8 s. The user confirms that it stopped.
- **Conclusion:** Trackwright can start and stop playback (class `direct`).

## 2026-11-13 — TW-1207, experiment B3: automation of more parameters (script 1.3.0+tw1206)

- **Controls:** 45, bound to the selected track (POC-TEST), no errors. `auto.list` reports the parameter bound to each one:
  - volume and pan;
  - sends 1 to 4 ("Nivel" (*Level*));
  - channel EQ ("EQ n Gain/Freq/Q");
  - pre-filter ("PreGain", "LC-Freq", "HC-Freq");
  - **slot 1 (Compressor), in this bank order:** Threshold, Ratio, Attack, Release, AutoRelease, Hold, MakeUp and AutoMakeUp;
  - empty: the Quick Controls (unassigned on an audio track) and slot 2 (empty).
- **Automated test** (`experiments/tw1206/controls.py run`, data in `results-b3.json`). Playback started and stopped by Trackwright (`transport.start` and `transport.stop`). For each parameter: recording of a ramp with touch, check in read mode, and restore.

| Parameter | Ramp | Played back in read mode? |
|---|---|---|
| volume | 0.00 → −8.69 dB | ✅ |
| pan | C → L60 | ✅ |
| send1.level | 0.00 → −8.69 dB | ✅ |
| eq1.gain | 0.0 → −14.4 dB | ✅ |
| prefilter.gain | 0.0 → −28.8 dB | ✅ |
| insert1.p1 (Compressor Threshold) | −20 → −38 dB | ✅ |
| insert1.p2 (Compressor Ratio) | 2:1 → 4.10:1 | ✅ |
| qc1 | no parameter assigned | ❌ (expected) |

- **Method issue:** each parameter's restore was undone by the read pass of the next one, because **R (read automation) affects all of the track's parameters** and plays back the curves already recorded. Restored at the end, with R off, and verified through DirectAccess: volume 0.00, EQ 0.0 dB, Threshold −20 dB, Ratio 2:1, pan C, send 0.00 and pre-filter 0.0 dB.
- **Conclusions:**
  - Trackwright can record automation of **volume, pan, sends, channel EQ, pre-filter and insert plugin parameters** (per bank), and can start and stop playback on its own.
  - The Quick Controls depend on the track having them assigned.
  - **For the tool:** with R on, automation overrides the value. This must be reported, and values must not be "restored" under read.
- **Left in the project:** the recorded curves, with no effect while R is off.

## 2026-11-13 — real use of `cubase_record_automation` and unit conversion

- **From Claude Code** (independent session), with script 1.4.0: volume fade recorded on POC-TEST; **the curve appears in the lane**, according to the user.
- **Problem detected in that session:** the model did not know the mapping between the normalized value and dB. It estimated −20 dB ≈ 0.36 and proposed calibrating by moving the fader.
- **Cubase conversion** (`da.convert`, `convertParameterPlainToProcessValue`), read-only, exact round trip:

| Parameter (object, tag) | Conversions |
|---|---|
| Volume (channel, 1025) | 0 dB → 0.7891 · −6 → 0.5708 · **−20 → 0.2551** · −60 → 0.0255 · +6 → 0.9990 |
| Send 1 level (send slot, 4097) | 0 dB → 0.7891 · −20 → 0.2551 |
| EQ 1 Gain (strip EQ, 4232) | 0 dB → 0.5 · −6 → 0.375 · +6 → 0.625 |
| EQ 1 Freq (strip EQ) | 100 Hz → 0.2811 · 1000 Hz → 0.5 |
| PreGain (InputFilter, 4201) | 0 dB → 0.5 · −12 → 0.375 |
| Threshold (Compressor) | −20 dB → 0.6667 · −35 → 0.4167 |

- **Panner:** "Izquierda-derecha" (*Left-Right*) is tag 4201, with plain 0 at the center; scale not measured. InputFilter: `PreGain` 4201, `LC-Freq` 4204, `HC-Freq` 4206.
- **Conclusion:** the 0.36 estimate for −20 dB was wrong (it is 0.2551; the scale is not linear). **There is no need to calibrate by moving the fader:** Cubase converts exactly and without changing anything. Proposal: accept real units in the tools (TW-1208).

## 2026-11-13 — TW-1208: mapping between controls and Cubase parameters (`cubase_convert_value`)

Measured on POC-TEST with the TW-1208 code, through the bridge. Read-only, except for selecting the track. All 12 conversions are exact in both directions:

| Key | Cubase parameter | Conversion |
|---|---|---|
| `volume` | POC-TEST / Volumen (*Volume*) | −20 dB → 0.2551 · 0 dB → 0.7891 |
| `pan` | Panner / Izquierda-derecha (*Left-Right*) | **scale −100 (left) … 0 (center) … +100 (right)**: 0 → 0.5 · −50 → 0.25 |
| `send1.level` | 1 / Nivel (*Level*) | −20 dB → 0.2551 |
| `eq1.gain` | EQ / EQ 1 Gain | +6 dB → 0.625 |
| `eq2.freq` | EQ / EQ 2 Freq | 1000 Hz → 0.5 |
| `eq1.q` | EQ / EQ 1 Q | 1 → 0.0833 |
| `prefilter.gain` | Input Filter / PreGain | −12 dB → 0.375 |
| `prefilter.lowcut` | Input Filter / LC-Freq | 100 Hz → 0.2811 |
| `prefilter.highcut` | Input Filter / HC-Freq | 10 kHz → 0.8535 |
| `insert1.p1` | Compressor / Threshold | −35 dB → 0.4167 |
| `insert1.p2` | Compressor / Ratio | 4:1 → 0.4286 |

- `qc1` and `insert2.p1` show up as unavailable: nothing is assigned and there is no plugin in slot 2.
- **Recording with `plain` from the other Claude Code session:** according to the user, it worked correctly.

## 2026-11-13 — TW-1201: automatic bridge startup and `cubase_launch`

- **Automatic startup,** with a test configuration (ports "TW1201 Test To/From" and socket `/tmp/tw1201-test`, so as not to interfere with the real bridge or with Cubase):
  - `status` with no bridge → `serve` started it as an independent process in **0.2 s**; then `TIMEOUT`, as expected because Cubase does not use those ports;
  - a second session **reused** the bridge: there was still only one;
  - the bridge log was written to `bridge.log` in the socket directory;
  - the test bridge was stopped when finished.
- **`cubase_launch`** as a dry run, with Cubase open → `already_running`, script 1.4.0. It does not open anything.
- **Full test by the user,** from Claude Code, with Cubase and the bridge closed: `serve` started the bridge and `cubase_launch` opened Cubase. It returned **`awaiting_user`** until the user opened the project in Steinberg Hub; after that the script responded. The script only starts responding once a project is open.

## 2026-11-13 — TW-1209: project properties experiment

Details in [experiments/tw1209/README.md](../experiments/tw1209/README.md).

- **DirectAccess:** the "Transporte" (*Transport*) object (`type: Transport`) gives `signature` = "4/4", `cycle`, `metronomeOn`, `precountOn`, punch, pre-roll and post-roll, and the record modes. "Metronome" gives `clickLevel`.
- **Time signature deduced by cursor normalization:** 4/4, consistent with the above.
- **`lsof`:** the `.cpr` is not kept open; the project folder is deduced from the open audio files.
- **Not accessible:** sample rate, project length and project name.

## 2026-11-13 — TW-1209: `cubase_get_project`

- **Against Cubase, in 0.96 s:**
  - tempo 120 and time signature **3/4** (changed by the user);
  - cycle off, with the locators at `2. 2. 1. 0` and `5. 1. 1. 0`. These are the same instants as before in 4/4, renumbered by the time signature change;
  - metronome on (click 127), precount off and transport stopped;
  - record modes;
  - project folder: `/path/to/projects/TEST`.
- **Consequence:** with 3/4, automation that assumed 4/4 would have computed the positions incorrectly. It now uses the time signature it reads; tested in the simulator with 3/4 and 6/8.

## 2026-11-13 — TW-1211: range editing experiment

Details in [experiments/tw1211/README.md](../experiments/tw1211/README.md).

- **Work and are verified:** `Delete`, `Delete Time`, `Cut Time`, `Insert Silence` and `Crop Range` over a 2–30 s range, measured with event probing (`Locate Next Event`) and undone with `Undo`.
- **With a dialog:** `Process / Silence`.
- **Locators in seconds:** setting them directly fails; it works by placing the cursor in seconds and using `Set Left/Right Locator`.
- **Scope:** `Select in Loop` only creates a range with the Range tool, and does so on all tracks.

## 2026-11-13 — TW-1211: `cubase_edit_range` from Claude Code

- **Test:** script 1.5.1, from another Claude Code session, with the test project saved. The request was «quita el tramo entre el segundo 2 y el 30 cerrando el hueco; comprueba con POC-TEST» (*remove the section between second 2 and second 30, closing the gap; check with POC-TEST*).
- **Result, according to the user, all correct:**
  - prior dry run;
  - applied with `verified: true`;
  - locators, cursor and selected track restored;
  - Object Selection tool active at the end;
  - **Undo** in Cubase brought the audio back.

## 2026-11-13 — TW-1212: deleting on a single track

- **Tool:** `cubase_edit_range(2, 30, delete, track=POC-TEST)`.
- **First attempt:** deleted too much, because of the auto-select-events-under-cursor preference; restored with Undo.
- **After the fix:** `verified: true`; POC-INSTR intact; 7 undo steps, reported and real.
- Details in [experiments/tw1212](../experiments/tw1212/README.md).
- **The user verified it from another Claude Code session:** it works.

## 2026-11-13 — TW-1204: exporting the mix

- **Experiment** ([experiments/tw1204](../experiments/tw1204/README.md)):
  - the dialog opens and exports between the locators: `TEST.mp3` lasts 27.99 s for a 2–30 s range;
  - Select All + Locators to Selection put the locators at 0 → 2:19.976 s.
- **`cubase_export_mix`, against Cubase:**
  - the `start` dry run proposes the folder `…/TEST/Mixdown`, deduced with `lsof`;
  - `confirm` found `TEST.mp3` (27.99 s), with `verified: true`.
- **User test, full episode in MP3:** 139.721 s for 139.976 s. The tolerance is widened for compressed formats.

## 2026-11-13 — TW-1202: saving

- **Experiment,** with the user's authorization: `File / Save` rewrote `TEST.cpr` and `Save New Version` created `TEST-01.cpr`, both without a dialog. Details in [experiments/tw1202](../experiments/tw1202/README.md).
- **`cubase_save_project`:** as a dry run, against Cubase, it listed both `.cpr` files; without `[writes] save`, the real save gives `SAVE_DISABLED`.
- **User test from Claude Code,** with `[writes] save = true`: it works.

## 2026-11-13 — TW-1203: importing audio

- **Experiment** ([experiments/tw1203](../experiments/tw1203/README.md)):
  - the 3 s tone lands on the selected track at the cursor: edges at 150 and 153 s of POC-TEST;
  - Cubase copies the file to `Audio/`;
  - while the file chooser is open, Cubase does not respond to the script;
  - Undo removes the event, not the copy.
- **`cubase_import_audio`** against Cubase: the dry run plans 0:02:30.000 and 3.0 s; `confirm` gives `not_found`, which is correct because it had been undone, and lists the copies.
- **User test from Claude Code** (importing the tone into POC-TEST): it works.

## 2026-11-13 — TW-1210: project settings

- **Experiment** ([experiments/tw1210](../experiments/tw1210/README.md)): the 9 switches of the Transport and the Metronome, and the click level, are written, read back and restored.
- **`cubase_set_project`** against Cubase: metronome, level 100 and cycle, with `verified: true`; restored with `verified: true`.
- **User test from Claude Code** (metronome and precount): it works.

## 2026-11-13 — TW-1205: plugin presets

- **Next and Previous** change the Compressor's parameters and bring them back when its editor has keyboard focus, which is obtained with a click by the user the first time. Without focus or without a loaded preset, they do nothing.
- **The preset name** is not accessible.
- Details in [experiments/tw1205](../experiments/tw1205/README.md).
- **User test from Claude Code:** it works.

## 2026-11-13 — TW-1302: CoreMIDI transport with `ctypes`

- **Without Cubase,** with a loopback test using dedicated test ports (now also an automated test on macOS):
  - 13 frames of a 3 KB message in each direction, identical;
  - the ports disappear on close.
- **CoreMIDI delivers universal SysEx messages twice** (`F0 7E …`, Identity Request) in two separate callbacks; Trackwright frames (`7D`) arrive only once. This is probably macOS's MIDI-CI layer. No effect: they are counted as foreign and discarded.
- **With Cubase:**
  - the previous bridge (rtmidi) was stopped and `serve` started a new one with CoreMIDI;
  - **Cubase reconnected in 4.2 s** (script 1.5.5);
  - `ping` OK and `doctor` 5/5;
  - reads: tracks, 46 Compressor parameters (9 KB, fragmented messages) and 45 automation controls;
  - write: POC-TEST mute written and restored, both verified;
  - 260 frames received, no transport errors.
- **Environment without `mido` or `python-rtmidi`** (`uv sync` removed them): everything above works without them.

## 2026-11-13 — TW-1301: `trackwright setup`

- **On the real installation,** with no input (every question would have been answered "no"): script 1.5.5 up to date, existing configuration, and server already registered in Claude Code (`claude mcp get`, read-only). All three steps were skipped, nothing was written, and `doctor` gave 5/5.
- **Installation from scratch, isolated** (temporary HOME and TMPDIR, no `claude` on the `PATH`, answers yes/yes/no/yes):
  - script installed in the MIDI Remote folder of the temporary HOME;
  - configuration created with `enabled = true`, `save = false` and permissions `600`;
  - the Claude Code step showed the command to register it by hand;
  - `doctor`: only "bridge running" in red, as expected without an MCP server. Temporary directories deleted.

## 2026-11-13 — TW-1303: 0.3.0 package for PyPI

- `uv build`: `trackwright-0.3.0-py3-none-any.whl` and `trackwright-0.3.0.tar.gz`, with `License-Expression: AGPL-3.0-or-later` (changed from `-only` the same day, before publishing) and `LICENSE` included. `twine check --strict`: passes on both.
- The sdist contains only `src/trackwright`, `pyproject.toml`, `README.md` and `LICENSE`.
- **`uv tool install` of the wheel in temporary directories:** `version` gives 0.3.0 and `doctor` 5/5 against the real Cubase. `setup` with no input skips all three steps and writes nothing.
- **`uvx --from <wheel>`:** the executable is in the uv cache (`archive-v0`), and `setup` proposes `uvx --from trackwright==0.3.0 trackwright serve` instead of that temporary path.

## 2026-11-13 — TW-1303: 0.3.0 published on PyPI

- The user published with `make publish` (build, `twine check --strict`, `uv publish`) from the commit tagged `v0.3.0`.
- The first attempt was rejected with `403 Invalid or non-existent authentication information`: the token stored in the Keychain had exactly 128 characters, truncated by the interactive prompt of `security add-generic-password -w`. With a new token stored from the clipboard the upload worked. Nothing was uploaded by the failed attempt.
- **Checked afterwards:** the PyPI JSON API reports `trackwright` 0.3.0, `License-Expression: AGPL-3.0-or-later`, `Requires-Python: >=3.14` and the `Author` URL; the SHA-256 of the wheel and the sdist on PyPI match the local `dist/`; `uvx trackwright@0.3.0 version` from an unrelated folder downloads it from PyPI and answers `0.3.0`.

## 2026-11-14 — E14 phase 1 (TW-1401, TW-1402) in Cubase

Cubase Elements 15.0.30, script 1.5.5, the test project. The bridge was restarted with the new code (an older bridge ignores the session field).

- **Policy refusals** (TW-1401), with a policy of `enabled = true`, `save = false`, `allowed_tracks = ["POC-TEST"]`; for each case, the write operations sent to Cubase were recorded: none.
  - `cubase_run_command("file.save")` → `USE_DEDICATED_TOOL`; `marker.insert` → `NOT_ALLOWED`;
  - `edit_range` on POC-INSTR → `NOT_ALLOWED`; on every track → `NOT_ALLOWED`; `split_at_locators` → `NOT_ALLOWED`;
  - `set_parameter` on the channel's output (4102) and input (4101) routing → `READ_ONLY_PARAM`;
  - moving `cycle_left` with writes disabled → `WRITES_DISABLED`.
- **Session through the bridge** (TW-1402):
  - a `da.param.set` sent with a made-up session was refused by the script with `STALE_SESSION`; POC-TEST's mute did not change;
  - `cubase_set_track_mix` on POC-TEST (mute on, then off) sent both writes with the current session; both verified, `track_uid` returned; mute restored.
- **Selection cleared before *Select in Loop*** (TW-1401): `edit_range("19", "20", "delete", verify_track="POC-TEST")` on every track ran `edit.select_none` before `tool.range` and `edit.select_in_loop`; result verified (new edges at 19 s and 20 s inside the 18–22 s event); `Edit > Undo` brought POC-TEST's edges back exactly.
- **Through the MCP layer** (Claude Code reconnected to the new server): the tool schemas require `track` in `cubase_set_parameter` and `cubase_insert_plugin`; a `cubase_set_parameter` dry run on POC-TEST's volume returned `track_uid`; the output routing (4102) was refused with `READ_ONLY_PARAM` and `cubase_run_command("file.save")` with `USE_DEDICATED_TOOL`.
- **Not checked live:** the TW-1403 changes that need a dialog or playback (import, save without a known folder, a recording cut short); they are covered by unit tests against the simulator.

## 2026-11-14 — E14 phase 2 (TW-1405, TW-1406, TW-1407) in Cubase

- **Bridge** (TW-1405): restarted with the new code. The documented `pkill -f "trackwright bridge"` did not stop the autostarted bridge (it runs as `python -m trackwright --config … bridge`); the new `trackwright bridge-stop` stopped it (pid from `bridge.status`), the launcher started a new one and Cubase reconnected in 3 s. `bridge.status` reports `duplicate_responses`.
- **Running script version** (TW-1407): `doctor` reported "script loaded in Cubase" with 1.5.5 = packaged before the upgrade, and 1.6.0 = packaged after it.
- **Script 1.6.0** (TW-1406): installed with the user's permission (it replaced 1.5.5; mode 0644) and loaded by the user restarting Cubase ("Trackwright 1.6.0" on the surface).
  - `doctor`: every check ok; integration tests (reads and reversible writes on POC-TEST): 5 passed;
  - `da.channels` with 17 tags → `BAD_REQUEST`; with 2 tags it lists the three channels;
  - `da.param.set` returns `guard` with `base` and `baseTitle` only; POC-TEST's mute set and restored;
  - write latency, 20 `da.param.set` on POC-TEST's mute: median 112 ms with 1.5.5 and 112 ms with 1.6.0. In a three-track project the tree walk removed by S-01 cost nothing measurable; one idle tick dominates.

## 2026-11-14 — 0.4.0 prepared

- `make check`: 547 passed, 6 skipped; `uv build` and `twine check --strict` correct; the wheel carries script 1.6.0 and the `Repository`, `Issues` and `Author` links.
- **Upgrade rehearsal** in throwaway folders: `trackwright==0.3.0` from PyPI, whose `setup` installed script 1.5.5; then the 0.4.0 wheel. `bridge-stop` with no bridge answers `stopped: false`; `setup` replaced 1.5.5 with 1.6.0 (mode 0644) and listed the next steps.
- Found while rehearsing: a server registered with `uvx --from trackwright==0.3.0` would keep running 0.3.0 after the upgrade. `setup` now warns when the registration pins another version; the upgrade steps of the changelog say how to replace it.
- The 0.4.0 wheel installed in isolation: `doctor` against the user's bridge and Cubase, every check ok (script 1.6.0 = packaged).

## 2026-11-14 — Script 1.6.1: the panel explains the faders

- Installed by the user (`trackwright script install --apply`, replacing 1.6.0) and loaded by restarting Cubase.
- **Seen by the user:** the three fixed lines under the track name ("Faders on the right:", "automation (Trackwright)", "do not move or map them") are visible on the surface.
- `doctor`: every check ok, "script loaded in Cubase" 1.6.1 = packaged; `capabilities.panel`: enabled, no errors; integration tests (reads and reversible writes on POC-TEST): 5 passed.

## 2026-11-14 — 0.4.0 published

- **CI:** the first GitHub Actions run (push of `a342347`) passed every step on macOS: environment, lint/format/types/tests with coverage, Node tests of the script, build and `twine check`.
- **PyPI:** the user published 0.4.0 with `make publish`. The wheel and the sdist on PyPI have the same SHA-256 as the local build of commit `fc506e1` (tag `v0.4.0`); the metadata has the `Repository`, `Issues` and `Author` links.
- `uvx --refresh trackwright@0.4.0 version` from an unrelated folder answers `0.4.0`. Without `--refresh`, uv first said no 0.4.0 existed: its cached index was older than the upload.

## 2026-11-14 — TW-1408: what the simulator must imitate

Two questions the conformance test raised, asked to Cubase Elements 15.0.30 (reads only, test project):
- `da.channels` with a tag the channels do not have (9999): every channel answers `{"title": "Nombre", "display": "", "process": -1}` — a title of another parameter, an empty display and `process` -1. The script passes it through; the simulator returned `null`. Both now return the same, and `track_info` treats `process: -1` as absent.
- `da.children` with `limit` 0: one item (of 6), because the script clamps the limit to at least 1. The simulator returned none; it now clamps the same way.

## 2026-11-14 — TW-1410: mutation testing of the safety modules

mutmut 3.8.1 through `uv run --with`, 4 workers, ~2 minutes for 899 mutants.

| Module | Mutants | Killed | Score |
|---|---|---|---|
| `protocol` | 198 | 188 | 94.9 % |
| `hostport` | 63 | 62 | 98.4 % |
| `host` | 406 | 338 | 83.3 % |
| `core/policy` | 63 | 49 | 77.8 % |
| `core/refs` | 169 | 110 | 65.1 % |

- **First run** (protocol, policy, refs): 72 % killed. Meaningful survivors: inverting the `save` check in `check_save` broke no selected test; JSON encoding options; `>`/`>=` boundaries; the eviction of the oldest assembly; a one-letter `name:` selector. Tests in `tests/unit/test_mutation_edges.py`.
- **With `host` and `hostport`:** the most serious survivor was `BridgeHost` retrying when the send outcome is uncertain (`sent is False` instead of `is not False`), the case the never-retry rule forbids; its tests live in `test_launcher.py`, which mutmut cannot run. Also: writes losing their session, the caller's deadline not reaching every internal step, history bounds and error texts. Tests in `tests/unit/test_mutation_host.py` (28).
- **Remaining survivors, all reviewed:** message texts and log arguments; changes equivalent in Python (`"ascii"`/`"ASCII"`, `allow_nan=None`, `code=None` where the default code is the same, initial values with no effect, a branch that cannot be reached after the lock wait); and `ObjectRef.decode`/`check_*`, which no tool calls (C-25, TW-1412).
- **Score without `core/refs`:** 637 of 730 mutants killed, 87.3 % (goal: 85 %). No survivor that changes behavior is left in `protocol`, `policy`, `hostport` or `host`.

## 2026-11-14 — TW-1411: more live integration tests

Cubase Elements 15.0.30, script 1.6.1, test project, `TRACKWRIGHT_TEST_TRACK=POC-TEST`.

- **New read tests** (10 pass): selected channel, plugin catalog, channel parameters and one parameter, project properties, changes, automation targets and the exact conversion of 0 dB (0.7891), marker navigation with the cursor put back.
- **New reversible write tests** (7 pass with the earlier ones): volume through `set_parameter`, rename, selection, tempo and metronome, each restored in `finally`.
- **Incident in the first run:** the rename test renamed POC-TEST to "TW-RENAME-TEST" and then could not rename it back: its policy allowed only `POC-TEST`, and the track was no longer called that. The name was restored by hand at once (verified), and the test now allows both names. After the corrected run every track has its name, volume 0.00 dB, no mute, tempo 120 and the metronome off, as before.
- **Live coverage:** 20 of the 32 tools have a repeatable live test (6 before). Still manual, because they open dialogs, play audio or remove things: `insert_plugin`, `remove_selected_tracks`, `split_at_locators`, `add_track_interactive`, `run_command`, `edit_range`, `plugin_preset`, `save_project`, `import_audio`, `export_mix`, `launch` and `record_automation`; their checks are in this log.

## 2026-11-14 — TW-1413: split in seconds and the cursor format, in Cubase

- `split_at_locators("19", "20", unit="seconds")` on the test project: the locators went to `10. 3. 1. 0` and `11. 1. 1. 0` (19 s and 20 s at 120 BPM in 4/4), Split Loop ran, and POC-TEST got new event edges at 19 s and 20 s. `Edit > Undo` brought its edges back exactly; the locators stay at the split points, as documented.
- `set_position("cursor", "1.5", unit="seconds")` answers with the cursor's bar position and the format Cubase reports (`Compases+Tiempos` in this Spanish Cubase), no longer a text written in the code.

## 2026-11-14 — TW-1501: exporting one track to analyze it

- In Cubase Elements 15 the "Export Audio Mixdown" dialog exports only Stereo Out; a track is isolated with solo. WAV up to 64-bit float, 8 to 192 kHz.
- A known test signal imported at 4.000 s and exported between locators at 2 and 36 s (WAV, 48 kHz, 32-bit float), with its track in solo: the alignment click lands at 3.000 s in the file, **0 samples** off; 34.000 s long. The mono track arrives on both channels 3 dB lower (centered pan law). Before and after the event the file holds exact zeros. Details in `experiments/tw1501/`.

## 2026-11-15 — TW-1504: `cubase_analyze_audio` through MCP

- With `[analysis] enabled = true`, `cubase_status` reports `analysis_enabled: true`.
- `cubase_analyze_audio` on the TW-1501 export (`tw1501-a.wav`, range start 2 s, `min_seconds` 3): noise floor −63.19 dB, threshold −53.19 dB, peak −3.1 dB; four silences in project time, 2.00–5.75, 10.25–13.75, 21.25–25.75 and 29.25–36.00 s, which are where the test signal (placed at 4 s) has its silences of 3 s or more, with 0.25 s of padding; the 1 s silence is not reported.
- Seen on the way: right after an MCP reconnection the bridge was autostarted and the first request (`hello`) timed out; the second, a few seconds later, was answered. Cubase took a moment to bind to the new virtual ports.

## 2026-11-15 — TW-1509: waiting for Cubase after autostarting the bridge

- `trackwright bridge-stop`, then `status()` from a new process with the new code: it started the bridge, a first `hello` failed (the bridge counted one error) and the next was answered; `status` returned connected, script 1.6.1, 3.7 s after the call. The same situation gave `TIMEOUT` on the first request before this change (see TW-1504).

## 2026-11-15 — TW-1506: the `podcast-silence-trim` flow on the test project

- The steps of the skill, followed from a Claude Code session against the real Cubase (not yet loaded through the plugin): `cubase_status` (writes and analysis enabled); the user chose to analyze `TW1501` alone; solo on (read back), `cubase_export_mix` 2–36 s, the user exported `silence-check.wav` (WAV, 48 kHz, 32-bit float), confirm found it (34 s, difference 0), solo off (read back).
- `cubase_analyze_audio` (`start` 2, `min_seconds` 3): the four expected silences, 18.5 s in total. The user approved all four.
- Dry run of the latest cut, then `delete_time` from the end to the start: 29.25–36.00, 21.25–25.75, 10.25–13.75 and 2.00–5.75 s, each `verified: true` against the edges of `TW1501` (final edges 2.000, 6.500, 14.000 and 17.500 s) and one undo step each.

- **Through the plugin** (reported by the user, 2026-11-15; not observed from this session): in a fresh Claude Code session with `TRACKWRIGHT_FROM=$PWD claude --plugin-dir plugins/claude-code`, the request worked correctly. Afterwards the project was checked from here: `TW1501` back to one event at 4.000–34.000 s, no track left in solo.

## 2026-11-15 — TW-1507: the `noise-gate` flow on the test project

- `experiments/tw1507/make_fixture.py` (noise −55 dBFS, syllable phrases at −16 and −36 dBFS, pauses) imported by the user on a new mono track `TW1507` at 0 s.
- Discovery: filters `gate`, `expander`, `noise` found `Gate` and `MidiGate` (Steinberg); `MidiGate` left out (MIDI-triggered); the catalog also lists a third-party VST (Voxengo CurveEQ), so other vendors' gates would appear the same way. Once loaded, `Gate` has Threshold (tag 4201, dB, −60…0 linear), Range (4243), Attack (4202), Hold (4204), Release (4203), and a band-pass side-chain filter on by default.
- Export with the track in solo (`gate-check.wav`): noise floor −58.2 dB, quietest speech −39.0 dB, typical −19.1 dB (the source levels minus the 3 dB pan law). Threshold on the export −48.5 dB, translated to the gate's input (+3 dB for a centered mono track, faders at 0 dB): −45.5 dB. The user approved: Threshold −45.5 dB, Range −30 dB, Hold 50 ms, Release 200 ms; each set with `expect_title` and read back.
- Second export with the gate (`gate-after.wav`), analyzed with the first threshold (−48.2 dB): noise floor −88.05 dB (−30 dB, the Range); quietest speech −39.0 dB and typical −19.06 dB, unchanged; pauses at −83 to −85 dB (the first 200 ms are the release), both phrases at the same level as before.
- Found on the way: (1) the default `merge_gap_seconds` of 0.3 s took the 250 ms syllables for blips and reported the whole file as one silence; lowered to 0.05 s. (2) Re-analyzing after the gate with the relative threshold compares different things (the threshold drops with the noise); the skill now passes the first threshold.

## 2026-11-15 — Release 0.5.0 checks

- `make check`: 691 tests passed, 18 skipped (integration), coverage 98 %. `claude plugin validate --strict` passes for the plugin and the marketplace.
- Mutation testing on the safety modules: first 705 of 856 mutants killed (82.4 %), because the new tests of TW-1502 and TW-1509 were not in mutmut's test selection; with them, **747 of 856 (87.3 %)**, and 748 after one more assertion that kills the `>=`/`>` boundary of the wait for Cubase. The remaining survivors in the new code are message texts and a default value overridden in production.
- The 0.5.0 wheel started through `uvx --from <wheel>` reads the user's configuration with `[analysis]` (0.4.0 refuses it), and `TRACKWRIGHT_FROM=<wheel> claude --plugin-dir plugins/claude-code mcp list` shows the plugin's server connected.

## 2026-11-15 — TW-1601: what Cubase Elements offers for the podcast skills

- Limiter on Stereo Out inserted and set (−1.0 dB, read back); the Compressor's side-chain is not reachable through parameters, the button and the source choice are in its window (user); volume automation recorded in real time lands ~0.1 s late (export midpoints 7.185 and 8.655 s for steps requested at 7.0–7.125 and 8.5–8.625 s), with an unexplained flat first export; PreGain automatable; fade, crossfade, duplicate and repeat key commands exist (user); Cubase's MP3 decodes with soundfile, no AAC export; a render imported at 40 s landed at 40.000–43.000 s; cycle playback with the Gate's Bypass toggled five times, heard by the user, no clicks. Details in `experiments/tw1601/`.

## 2026-11-15 — TW-1602: the project workspace, read live

- `workspace()` (status) from the repository against the open test project: project folder `X0001.test` found through the files Cubase has open; `Trackwright/` exists (from TW-1601) and `previews/`, `analysis/`, `reports/` are missing; `init` refused with `WORKSPACE_DISABLED` under the user's configuration; `cubase_status` reports `workspace_enabled: false`.

## 2026-11-15 — TW-1603: loudness of real Cubase exports

- `measure_loudness` on the nine exports in the test project's `Mixdown/` (WAV 32-bit float and Cubase's MP3): integrated loudness within 0.04-0.07 LU of pyloudnorm (for example the 140 s episode `X0001.mp3`: −21.13 against −21.18 LUFS); the 1 ms click of `tw1501-a.wav` gives a true peak 1.1 dB above its sample peak; 140 s measured in 0.59 s.

## 2026-11-15 — TW-1604: voice activity on a real episode

- A 46-minute episode with one voice and five music and effects tracks: `Pod Mic` exported alone (solo, whole project, WAV 32-bit float, duration exact). Detection in 2.5 s; floor −61.8 dB, contrast 52 dB, typical speech −13.1 dB, 87 % speech.
- A 0.37 s fragment at −52 dB at 17:15.36 was a noise inside a pause (the user checked: a pause there); with `faint_db` the detector drops 108 such fragments before joining, and the pause at 17:15 is whole again.
- The user listened to the first 10 minutes with a tone on the right channel during detected speech: it starts and stops in the right places.
- Seen on the way: the episode's `Pod Mic` and the test project's `POC-TEST` have the same track uid (projects from the same template).

## 2026-11-15 — TW-1605: an export of one track with every solo restored

- On the test project, with `POC-TEST` soloed beforehand: `start` with `solo=[TW1507]` cleared `POC-TEST`'s solo and soloed `TW1507`; the user exported `tw1605-a.wav` (identical to the earlier `gate-after` export, difference 1e-10); `confirm` found it, reported `solo_restored: true`, and `cubase_list_tracks` showed `POC-TEST` soloed and `TW1507` not.
- A second `start` with the same solo; the user closed the dialog without exporting; `cancel` reported both tracks restored (`solo_restored: true`), and `cubase_list_tracks` showed the state from before again. `POC-TEST`'s solo was then cleared to leave the project as found.

## 2026-11-15 — TW-1606: a render imported back, against a known signal

- `cubase_workspace init` on the test project created the missing `previews/`, `analysis/` and `reports/`.
- `cubase_render` on `tw1605-a.wav` (`TW1507` alone, 0–5 s, peak −16.07 dBFS), `gain_db` −6.0206, `track` `TW1507`: `renders/TW1507-gain.wav` (32-bit float, 48 kHz, stereo, peak −22.09 dBFS) and its provenance; the render equals the source × 0.5 within 8e-10.
- The user created a stereo audio track, `TW1606 render`. `cubase_import_audio` refused the render on `TW1507` (`BAD_REQUEST`) and at 1 s (`MISALIGNED`); at 0 s the user imported it with "Copiar archivo a carpeta del proyecto" unticked.
- The first confirm found only the end edge (5.000 s): **an edge at the project start cannot be probed**, because Locate Next Event never stops at 0, and Locate Previous Event went to 0 from 2 s on a track whose only event starts at 2 s. Fixed: at position 0 the new end edge stands for the start (an import places the whole file). After the server was reloaded, the confirm returned `done`, `owned: true` (`verified: null`, since the server had lost its snapshot of the track from before the import; the track had just been created empty), and `state.json` recorded the render and the track as `tw1606-test`'s.
- Cubase left a 0-byte `Audio/TW1606 render_01.wav` (named after the track, not a copy of the render); `copied_to_project` now ignores empty files.
- `TW1507` muted; the user exported `TW1606 render` alone, 0–5 s (`solo`, restored afterwards): it equals the source × 0.5 to −182 dB (the largest difference, 4.7e-10 against the render), with no offset (cross-correlation lag 0) and the RMS ratio 0.5000. `cubase_render list` shows the render on that track, present, without problems.

## 2026-11-15 — TW-1607: profiles read and written live

- With the server reloaded and the test project open: `resolve` found no episode profile and no show, and gave the built-in silence criteria (2 s, 0.25 s padding); `shows` found none in `~/.config/trackwright/shows`; `delivery` listed Apple, iVoox, Spotify and YouTube with their sources.
- `write_episode` on the test project: the dry run showed the TOML and wrote nothing; applied, it wrote `Trackwright/profile.toml` (roles of `POC-TEST`, `TW1507` and `TW1606 render`, a pan, padding 0.3 s, targets Apple and Spotify, a protected range at 40–43 s). `resolve` then gave padding from `episode` and the minimum silence from `built-in`, the protected range, and the two delivery profiles with their sources.
- `write_show` as a dry run only (nothing written in the user's configuration): its TOML carried an empty `notes = ""`, now left out.

## 2026-11-15 — TW-1608: analyses with their source, cached

- `cubase_analyze_audio` on `X0001.test/Mixdown/tw1606-render.wav`: `cache: stored`, `source.sha256` equal to `shasum -a 256` of the file, range 0–5 s, `project_saved_after: false` (the newest `.cpr` was saved at 15:03, the export at 19:39); `Trackwright/analysis/` got `hashes.json` and one `silences-….json`. The same call again with `offset` 1: `cache: hit`, the same source, the page applied to the cached list.
- Two identical calls sent in parallel both answered `stored` (both missed before either stored); harmless, since writes are atomic and the second wrote the same result.
- `cubase_measure_loudness` on the 46-minute episode export of another project (`E0004…/Mixdown/tw1604-podmic.wav`, read-only): `cache: off`, `project_saved_after: null`, nothing written anywhere. On that 1.07 GB file the SHA-256 takes 0.39 s and the loudness measurement 12.25 s, so a hit saves almost all of it.

## 2026-11-15 — TW-1610 and TW-1609: the session audit and ownership records, live

- The audit's reads on the test project: `cubase_get_project` (folder, transport stopped), `cubase_list_tracks` (six channels; `TW1507` muted), `cubase_list_inserts` (Brickwall Limiter on Stereo Out, Compressor on `POC-TEST` and `TW1501`, Gate on `TW1507`, none on `TW1606 render`) and `cubase_track_edges` on the four audio tracks: `POC-TEST` 2.0 … 139.976 s (7 edges), `TW1501` 4–34 s, `TW1507` 30, 40, 43 s, `TW1606 render` 5 s. After the probes, `POC-INSTR` was still selected and the cursor where it was.
- `TW1507` has an odd number of edges: its event from 0 s is not seen (only its end at 30 s), as `TW1606 render` (0–5 s, only the end). The skill now points out an odd number of edges as a probable event at 0 s.
- `cubase_list_inserts` does not say that `TW1501`'s Compressor is bypassed: added to the skill's capability report.
- The episode profile's dry run, built from `resolve`'s new `episode` field, added only the new role line; the built-in `min_silence_seconds` was not copied into the episode. Not applied (the role was an example, not the user's).
- `cubase_workspace` `record` (the Gate on `TW1507` as a `noise-gate` plugin item), `status` (three items) and `forget` worked; `state.json` is back as it was. Their answers left `owned` and `items` empty; they now carry the state after the change.

## 2026-11-15 — TW-1611: the final QC through the server

- `cubase_final_qc` on the test project's `Mixdown/X0001.mp3` (140 s, MP3 128 kbps, 44.1 kHz) with the episode profile's targets (Apple, Spotify) and `expected_seconds` 140: verdict `fail`, one failure: Apple's loudness, −21.13 LUFS against −16 ± 1 (with Apple's page as the source); codec, channels, sample rate, bit rate (127.7 kbps measured from size and duration), true peak (−9.47 dBTP) and duration (140.042 s, within the 0.1 s allowed for MP3) pass. Spotify's loudness and true peak came out as `info`, "not published by the platform".
- Warnings: two pauses of 32.1 s and 35.2 s (23.26 s and 76.58 s) and a level change of −10.8 LU at 2:10. `project_saved_after: true` (the MP3 is from 13 November, the project was saved on the 15th), with its note.
- The cursor moved to the longest pause with `cubase_set_position`. With `report: true` the JSON and Markdown reports were written to `Trackwright/reports/`, and the Markdown one recorded with `cubase_workspace` as a `report` item of `podcast-final-qc`.
- Fixed after the run: a title said "1 level changes"; the end (2:10.042) and the level change (2:10.000) were two moments 42 ms apart, now joined; the report's notes now have their own heading.

## 2026-11-16 — TW-1612: reaching a loudness target in Elements, on a whole episode

- The 46-minute export of episode E0004 (`Pod Mic` alone), imported without copying into the test project and exported alone five times by the user: details and table in `experiments/tw1612/`. Fader −5.25 dB took it from −10.75 to −16.00 LUFS in one round; MP3 128 kbps raised the true peak by 0.78–0.82 dB; the Brickwall Limiter in slot 1 acts before the fader and the one in slot 7 after it; with DIC on, 0.24 dB of intersample peaks pass the −1 dB threshold.
- `cubase_export_mix` confirmed the two MP3 exports as 6.3 s short, from afinfo's estimated duration (2767.55 s against 2773.92 s decoded); durations now come from soundfile, afinfo only for AAC.
- Left in the test project: the track `TW1612 episode`, a second Brickwall Limiter in Stereo Out's slot 7 (bypassed; plugins cannot be removed through the API), the five exports `tw1612-r0` … `r4` in `Mixdown`. The Stereo Out fader is back at 0.00 dB.

## 2026-11-16 — TW-1613: `podcast-delivery` end to end on the test project

- The test project's mix, 0–140 s (`TW1612 episode` muted for the test), target Apple, MP3. Master 1 (WAV): −17.56 LUFS, −0.99 dBTP. `cubase_delivery_plan`: fader 0 → +1.56 dB, predicted MP3 true peak +1.39 dBTP, so a limiter in slot 7 with threshold −2.1 dB (2.67 dB of peak reduction), and a note that the Brickwall Limiter in slot 1 is before the fader. Slot 7 already held the Brickwall Limiter of TW-1612 (bypassed): its threshold set to −2.1 dB, Bypass off, the fader to +1.56 dB, all read back; recorded as a `plugin` item of `podcast-delivery` with the fader's value before and after.
- Master 2: −16.01 LUFS, −2.08 dBTP; the plan asked for +0.01 dB more and no limiter change: one round was enough.
- The delivery file, `delivery-apple.mp3` (128 kbps, 44.1 kHz): `cubase_final_qc` against Apple **passed**: −16.05 LUFS, −2.50 dBTP, 140.069 s (the exact duration since TW-1612's fix).
- The encoding **lowered** the true peak here by 0.42 dB (master 2 −2.08, MP3 −2.50), where TW-1612's episode rose 0.82 dB: the plan's +0.82 dB is a cautious margin, not a constant, and the delivered file is always measured.
- Put back afterwards: Stereo Out fader 0.00 dB, slot 7 limiter bypassed (still recorded as `podcast-delivery`'s), `TW1612 episode` unmuted. Left in `Mixdown`: `delivery-master-1.wav`, `delivery-master-2.wav`, `delivery-apple.mp3`.

## 2026-11-16 — TW-1615: `podcast-music-ducking` on the test project

- Roles in the test project's profile: `POC-TEST` music (the 141 s stock track), `TW1612 episode`, `TW1507` and `TW1606 render` voices. The user exported the voices soloed together and the music alone, 0–140 s (every solo restored). `cubase_ducking_plan`: 6 speech regions, 4 ducked spans, 117 of 140 s ducked (84 %), the protected range 40–43 s kept up (the second span's recovery ends at 40.0 s).
- The ducked render (`POC-TEST-duck.wav`, −10 dB, provenance with the specification and the voice's SHA-256) and three previews. The user heard only the voice in the first two: **the music track is silent from about 28 to 52 s and from 80 to 108 s** (−140 dBFS), and both previews fell in the first gap; the third (64–80 s) had the music 10 dB down under the voice (−31.5 against −21.8 dBFS) and back up after it (−23.7 dBFS), which the user heard as the level rising when the voice stopped. A before/after pair at 56–74 s (voice with the original music, then with the ducked one) made the difference clear; the user approved.
- New stereo track `POC-TEST ducked`, the render imported at 0 s without copying (end edge 2:20.000, `verified: true`, recorded as `podcast-music-ducking`'s), `POC-TEST` muted.
- Fixed after the run: `cubase_preview` reports each source's level and warns when one is silent in the range; `cubase_ducking_plan` takes `music_file` and proposes only moments where the music has sound (on these exports it kept 0, 67.6, 74.7 and 140 s and left out the four in the gap); the skill asks for a before/after pair.

## 2026-11-16 — TW-1616: ducking inside Cubase, part (b): real-time automation

- Details in `experiments/tw1616/`. Two bugs found and fixed: the automation controls are bound to a new selection a moment later (the tools now wait, or stop with `CONTROLS_NOT_BOUND`), and Read was put back off after recording (now left on; an export had played the last value instead of the curve).
- On `POC-TEST`, PreGain at −10 dB exported at −7 to −9 dB: its Compressor sits after PreGain.
- On `TW1616 signal`, created during the session, nothing was recorded (the export equalled the source) although the control moved its PreGain; on `TW1501` the same curve recorded; after the user restarted Cubase, `TW1616 signal` recorded too.
- With pink noise on `TW1616 signal`, 13 cycles: constant delay +0.22 s (0.135–0.335 s), flat parts exact, 0.35 dB RMS after the shift, smooth ramps, a 10 ms step smoothed to 0.08–0.09 s. Offline rendering stays the ducking skill's mode.

## 2026-11-16 — TW-1616: part (a), a side-chained compressor, and two findings

- Compressor on `TW1616 signal` (pink noise), −30 dB, 8:1, 10 ms, 300 ms, no make-up, set through the API; the side-chain turned on and fed with `TW1612 episode` by the user in Cubase. From the mix minus the voice: −17.9 dB median under the voice, 0.0 dB in its silences, the drop with the first syllable (no pre-roll), the return within 0.3–0.8 s, 1.8 dB median movement per 100 ms inside speech. No second ducking mode.
- Cubase exported the voice's silence as −166 dBFS residue, not zeros: the speech detector found speech everywhere (floor −1082 dB); after the fix (frames under −120 dBFS are digital silence) the floor is −54 dB and the regions follow the voice.
- `TW1507`, muted, exported with solo had its audio (−20.92 dBFS, as in TW-1615's voice export): a solo overrides a mute in Cubase; `cubase_export_mix` now leaves muted tracks out of `solo` unless `include_muted`. TW-1615's ducked music was planned with that track in the voices at 20–28 s and around 40 s.

## 2026-11-16 — TW-1617: loops and a bed from a real music file, judged by ear

- The user's intro music, a 36 s march (MP3, read-only; renders written to the session's scratch folder, not to the user's folders).
- First version: 64 BPM, a beat grid a median 202 ms off the strong onsets (which come every 0.232 s: ≈129 BPM, eighths), loops chosen by per-beat features on that grid, a jump to a separate ending: the user heard the seams clearly.
- The march does not truly repeat: its best self-similarity, 15.02 s apart (8 bars at 129 BPM), agrees 0.69. Rebuilt: loops found by self-similarity at whole-bar lags, the seam where the passes agree best within 1 s, the end lined up by correlation (envelopes, then waveforms), half a beat of crossfade, and the bed carrying on naturally to the end of the file after the last pass. The user: "now it is hardly noticeable, more than acceptable"; two seams generated by the module (15.0 s and 11.3 s loops) were both "well connected".
- The tempo stays at 64 BPM even with a prior toward 120: the onsets correlate 0.69 at 64 and 0.32 at 129 (a march's half-time accent); the loops are whole bars either way. Loops are ranked by the agreement over a bar on each side of the seam, which puts the approved 15.02 s loop first and keeps a synthetic progression from being cut between two equal chords.

## 2026-11-16 — TW-1618: `podcast-music-bed` on the test project

- The user's 36 s march (44.1 kHz MP3, read-only), a 60 s target at 0:00. `cubase_music_analysis`: 64.05 BPM, best loop 5.457 → 20.477 s (4 bars, score 0.594). The `bed` render: one repeat, 50.703 s (9.297 s short, never stretched nor exceeded), one seam at 20.009 s of the bed, seam score 0.645.
- The project runs at 48 kHz and the music at 44.1 kHz: Cubase would have converted it on import by copying it into `Audio/`. Added `sample_rate` to the bed (polyphase resampling); the bed was rendered at 48 kHz, its peak +0.23 dBFS (the MP3 is close to full scale).
- `cubase_preview` of the seam (17–23 s, music at −15.3 dBFS): the user: "the seam sounds good". New stereo track `Music bed`, the bed imported at 0 s without a copy and without a rate conversion (end edge 0:00:50.702, `verified: true`, recorded as the skill's). No markers: the user had no doubt about the seam and its score is over 0.5. The cursor at 0:17 to hear it in the mix.
