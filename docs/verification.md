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

- **Registration:** `claude mcp add --scope user trackwright -- uv --directory /Volumes/Data/projects/sound/trackwright run trackwright serve`. `claude mcp list` → `✔ Connected`.
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
  - project folder: `/Volumes/Data/Produccion/Cubase/X0001.test`.
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
  - the dialog opens and exports between the locators: `X0001.mp3` lasts 27.99 s for a 2–30 s range;
  - Select All + Locators to Selection put the locators at 0 → 2:19.976 s.
- **`cubase_export_mix`, against Cubase:**
  - the `start` dry run proposes the folder `…/X0001.test/Mixdown`, deduced with `lsof`;
  - `confirm` found `X0001.mp3` (27.99 s), with `verified: true`.
- **User test, full episode in MP3:** 139.721 s for 139.976 s. The tolerance is widened for compressed formats.

## 2026-11-13 — TW-1202: saving

- **Experiment,** with the user's authorization: `File / Save` rewrote `X0001.cpr` and `Save New Version` created `X0001-01.cpr`, both without a dialog. Details in [experiments/tw1202](../experiments/tw1202/README.md).
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
