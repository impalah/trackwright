---
name: noise-gate
description: Add and set a noise gate on a track of the open Cubase project so the background noise between phrases disappears while soft speech is kept. Use when the user asks for a noise gate, or to remove hiss, hum, room or background noise in the pauses of a voice or instrument track. Finds the gate plugins installed (Cubase's own or third-party VSTs), measures the noise and the quietest speech on an export, proposes a threshold and only applies what the user approves.
license: AGPL-3.0-or-later
compatibility: Needs the Trackwright MCP server with Cubase open, [writes] enabled = true, and [analysis] enabled = true to measure the levels.
metadata:
  author: impalah
  project: https://github.com/impalah/trackwright
---

# Noise gate

A gate mutes a track while its level is below a **threshold** and opens when it goes above. Set too low, the noise passes; set too high, it cuts the start of soft words. So the threshold must sit **between the noise floor and the quietest speech**, and both are measured on an export because the Cubase API cannot read audio.

Speak to the user in their language and keep them informed; they are in front of Cubase.

## 1. Check the setup

`cubase_status`:

- `connected` false: ask the user to open Cubase and check the Trackwright surface in the MIDI Remote tab.
- `writes_enabled` false: nothing can be inserted or set; say so.
- `analysis_enabled` false: the levels cannot be measured. Explain that `[analysis] enabled = true` is needed in `~/.config/trackwright/config.toml`; without it you can only insert the gate with its default threshold and let the user set it by ear.
- `allowed_tracks`: if not empty, the track must be in it.

## 2. Pick the track

Use `cubase_list_tracks` to find the track the user means (an audio track); keep its `uid`, its `volume.display` (fader, dB) and whether it is soloed. Note the `volume.display` of **Stereo Out** too. `cubase_list_inserts` on the track: find a free slot and check whether a gate is already loaded (then offer to adjust that one instead of adding another). A gate usually goes **first** in the chain; if slot 1 is taken, say which slot you will use.

## 3. Find the gate plugins installed

Do not assume a plugin name: users have different Cubase editions and third-party plugins.

1. `cubase_list_available_plugins` on the track with `filter` set to `gate`, then `expander`, then `noise`; page with `offset` while `matched` is larger than what you have seen. Also look at the `Dynamics` category (`filter: "Dynamics"`) for multi-module processors.
2. Leave out what is not an audio-level gate: gates opened by MIDI notes (for example Steinberg's MidiGate), spectral noise reduction (denoisers work differently: mention them if the user's noise is constant hiss), and anything whose name says "sidechain only" or similar.
3. Show the candidates (name and vendor). If there is one, propose it; if there are several, let the user choose. Steinberg's `Gate` is a safe default when present.

A plugin is only usable here if, once loaded, it has a parameter titled like **Threshold** whose value is in dB. You check that in step 6; if it has none, remove it from the plan and tell the user.

## 4. Measure the noise and the quietest speech

1. Agree on a range that has both speech and pauses (the whole track, or a few representative minutes).
2. `cubase_export_mix` `phase: "start"` with the range, `solo` set to the track's `uid` (the export only has Stereo Out: only that track sounds, and every solo is put back afterwards), `dry_run: false`; keep `since`, `expected_seconds` and `start`. Ask the user to export Stereo Out as Wave, **32 bit float**, project sample rate, a name like `gate-check`, real-time export off. Wait until they say it is done.
3. `cubase_export_mix` `phase: "confirm"` (or `phase: "cancel"` if they closed the dialog). Check `solo_restored` is true.
4. `cubase_analyze_audio` with the file, `start`, and `min_seconds: 0.5`. Keep `noise_floor_db` (N), `quiet_sound_db` (Q) and `sound_db`.
   Name the export the numbers come from (`source.file`). If `source.project_saved_after` is true, the project was saved after this export: ask whether the track changed since; if so, export again.

If Q is null there is no contrast between noise and sound: a gate cannot help; say so. If `Q - N` is under **12 dB**, the noise is too close to the soft speech for a gate to separate them cleanly: say so and offer a gentle setting (less attenuation, see Range below) or a noise-reduction plugin instead.

## 5. Compute the threshold

The analysis measures the **export**, after the track fader, the panning and Stereo Out; the gate sits in an insert and hears the signal **before** them. Translate:

1. Threshold on the export: `T_export = N + (Q - N) / 2`, the middle point in dB, rounded to 0.5 dB.
2. Threshold for the gate: `T_gate = T_export - track_fader_dB - stereo_out_fader_dB + pan_offset`, where `pan_offset` is **3 dB for a mono track** panned to the center (Cubase's default pan law: a centered mono track reaches Stereo Out 3 dB lower, verified) and 0 for a stereo track. Use the faders' `volume.display` values (dB); `-oo` means the track is silent: stop and ask.
3. Keep `T_gate` at least 6 dB above `N + offsets` and 6 dB below `Q + offsets`; if both cannot hold, use the middle and warn.

Also propose, and explain in one line each:

- **Range** (how much it attenuates when closed): about -30 dB for speech sounds natural; -oo removes everything and can sound abrupt. Ask.
- **Release** around 150-250 ms and **Hold** around 30-60 ms, so word endings are not chopped; **Attack** 1 ms or a little more.

Show the plan as a short table: plugin, slot, threshold (with the numbers it comes from: N, Q, faders), range, hold, release. **Apply nothing until the user agrees.**

## 6. Insert and set

1. `cubase_insert_plugin` with `track` = the `uid`, the free `slot`, the chosen `plugin_uid`: `dry_run: true`, then `dry_run: false`.
2. `cubase_list_parameters` with `target: "insert:<slot>"` (page with `next_offset`). Find the tags by title: Threshold (required), Range, Attack, Hold, Release. Titles may differ in third-party plugins (for example "Thresh", "Floor", "Depth"); match sensibly and tell the user which ones you will set. Check that Threshold's `display` is in dB.
3. For each agreed value: `cubase_set_parameter` with `target: "insert:<slot>"`, the `tag`, `unit: "plain"`, the value in real units (dB, ms), `expect_title` set to the title you found, `dry_run: true` then `false`. Read the `after` value: if Cubase clamped it, say so.

## 7. Check the result

Offer to check it on a new export, with the gate active: export the same range with `solo` (`gate-after`), confirm, and analyze with the same `start` **and `threshold_db` set to the `threshold_db` of the first analysis**. With the default relative threshold the comparison is wrong: once the pauses are quieter, the threshold drops with them and the noise left between syllables (the gate stays open there, by Hold and Release) starts counting as sound.

- The pauses must be quieter: `noise_floor_db` lower by about the Range (with -oo the pauses become exact silence and count as `digital`).
- The soft speech must stay: `quiet_sound_db` within about 1 dB of before, and `sound_db` unchanged. If `quiet_sound_db` dropped, the threshold is too high: propose lowering it 3 dB and check again.

Then ask the user to **listen**: no measurement replaces it, especially for breaths, word endings and room tails. Adjust Hold and Release by ear on request.

## 8. Report

Say what was inserted, where, and the final values. Explain how to undo: the plugin's **Bypass** switch, or remove it from the insert slot in Cubase (Trackwright cannot remove plugins). The project is **not** saved; save only if the user asks (`cubase_save_project`). The export files stay in the project's `Mixdown` folder.

## Do not

- Do not assume which gate is installed: discover it.
- Do not write a parameter whose title you have not checked (`expect_title`).
- Do not leave a track soloed: use `solo` in `cubase_export_mix`, and `cancel` if the export is abandoned.
- Do not apply values the user has not approved.
- Do not retry a write after a timeout: read the parameter back instead.
- Do not save the project unless asked.
