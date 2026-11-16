---
name: podcast-voice-cleanup
description: Diagnose and gently clean a podcast voice track in Cubase - hum, rumble, plosives, sibilance and noise in the pauses - with the plugins actually installed (StudioEQ notches and high-pass, DeEsser, a gate through noise-gate), each change tied to a measured problem, tried with Bypass before it stays, and checked on a new export; mouth clicks, reverb and intrusive sounds are reported with their times for review. Use when the user says a voice has hum, buzz, rumble, pops, harsh esses, background noise or sounds dirty, or asks to clean up, repair or diagnose a voice recording.
license: AGPL-3.0-or-later
compatibility: Needs the Trackwright MCP server with Cubase open, [writes] enabled = true and [analysis] enabled = true in ~/.config/trackwright/config.toml; [workspace] enabled = true to record what it inserts.
metadata:
  author: impalah
  project: https://github.com/impalah/trackwright
---

# Podcast voice cleanup

Cleaning a voice starts with knowing what is wrong with it. This skill measures the problems on an export of the voice (`cubase_voice_diagnostics`), treats only what was found, with gentle settings and with the plugins the user has, and checks the result on a new export. Every change is tied to a problem and to a measure; nothing is treated "just in case". Over-treatment is a real risk: a notch too wide thins the voice, a high-pass too high takes its body, a de-esser too strong makes a lisp, a gate chops word endings. Say so when proposing.

Speak to the user in their language and keep them informed; they are in front of Cubase.

## Requires

`cubase_status`:

- `connected` false: ask the user to open Cubase and check the Trackwright surface in the MIDI Remote tab.
- `writes_enabled` or `analysis_enabled` false: say which key is needed in `~/.config/trackwright/config.toml` and stop.
- `workspace_enabled` false: the cleanup still works, but what it inserts cannot be recorded as this skill's; say so.
- `allowed_tracks`: if not empty, the voice track must be in it.

## Inputs

- **The voice track:** one person per track (`cubase_list_tracks`; roles from `cubase_profile` `resolve` when there are any).
- **The range:** the whole track by default (a 46-minute voice is diagnosed in seconds), or a part the user names.
- **The problems to treat:** the user's complaint ("hum", "harsh esses") or, by default, what the diagnosis finds.

## Workflow

### 1. Inspect

- `cubase_list_tracks`: the track's `uid`, its fader and whether it is muted.
- `cubase_list_inserts` on it: free slots, and what is already there (an EQ, a de-esser or a gate already loaded: offer to adjust that one, it is the user's). Cleanup goes early in the chain: EQ (high-pass and notches) first, then the de-esser; dynamics the user has after them stay after.
- `cubase_workspace` (`status`): plugins this skill inserted before on this track (`plugin` items of `podcast-voice-cleanup`, `<uid>/slot:N`): adjust those instead of inserting more.
- The plugins installed, never assumed: `cubase_list_available_plugins` with `filter` `EQ` and `ess` (and `gate`, `noise`, `denois` for the record). Steinberg's StudioEQ and DeEsser are the known ones (see [references/steinberg-plugins.md](references/steinberg-plugins.md) for their measured parameters); a third-party EQ is usable if, once loaded, it has bands with frequency, gain, Q and a cut type, checked by title.

### 2. Analyze

1. Export the voice alone: `cubase_export_mix` with `phase: "start"`, the range, `solo` = the track, `dry_run: false`. Ask for WAV, 32-bit float, the project's sample rate, a name like `cleanup-before`. Confirm (or cancel); check `solo_restored`.
2. `cubase_voice_diagnostics` with the file and `start` = the range start.

### 3. Propose

Explain each finding in plain words with its severity **and confidence** (a finding with low confidence is "possible, listen first"), and the measure behind it. Offer to make a listening file of its `times` (`cubase_preview` with the export, a few seconds around each) before deciding. Then, per problem:

| Found | Treatment (only if the plugin is there) | Gentle values |
|---|---|---|
| `spectrum` rumble (`rumble_db` > −20), `plosives` detected, or hum whose fundamental is under 80 Hz | StudioEQ LF band type `Cut` (high-pass) | 80 Hz; never above 100 Hz on a voice. It also takes a 50 Hz hum fundamental: decide it first, then the notches |
| `hum` detected | StudioEQ peak bands as notches at `mains_hz` × k, only for a harmonic above the cut with `hK_db` ≥ 10 **and** `hK_dbfs` ≥ −60 (a peak far over near silence is itself inaudible; −60 is a starting value). Up to two: P1, P2 | gain −(hK_db − 3), at most −24 dB, but **at most −6 dB between 80 and 250 Hz**, where the voice's own fundamental lives; Q 10 |
| `sibilance` mild or more | DeEsser | `LowFreq` = `band_low_hz` (at least 4 kHz), `HighFreq` = `band_high_hz` (at least 2 kHz above), Auto Threshold on, `Reduction` 3 for mild, 4 for moderate or strong |
| `noise` moderate or strong | the `noise-gate` skill for the pauses; a spectral denoiser if the user has one (name it, do not set it blindly) | as in noise-gate |
| `clicks`, `reverb`, plosives too strong for a filter | not treated here: the times, for review by ear or another tool (spectral repair, de-reverb) | — |

Show the plan as a table: problem, measure, plugin, slot, values, the risk of each. Prominence (`hK_db`) says a peak stands out; its level (`hK_dbfs`) says whether anyone can hear it: say both. A problem not found is not treated, even if the user expected it: say what was measured.

### 4. Preview

A plugin cannot be heard before it is loaded; loaded **with Bypass on** it changes nothing. So, after a yes to try it:

1. `cubase_insert_plugin` (dry run, then `dry_run: false`) in the free slot; `cubase_set_parameter` its `Bypass` to on first (`expect_title`), then each value of the plan (dry run, then apply, `unit: "plain"`, `expect_title` the title checked with `cubase_list_parameters`; read `after`: Cubase may clamp).
2. A cycle range around the strongest `times` of the problem (`cubase_set_position`), and ask the user to play it in Cubase toggling Bypass. For the de-esser, its `Solo` switch lets the user hear only what it removes.
3. Say what may not be heard: changes under about 150 Hz (a high-pass, hum notches) barely reach laptop speakers and many headphones, and a 3-4 dB de-esser is subtle. If the user hears no difference, that settles nothing: offer to measure instead (turn Bypass off, step 7, and compare).

### 5. Approve

An explicit yes to keep each plugin with its values (or a change: "less", "only the hum").

### 6. Apply

1. `cubase_set_parameter` the approved plugins' `Bypass` to off.
2. Record each one: `cubase_workspace` (`action: "record"`, `kind: "plugin"`, `key: "<track uid>/slot:<N>"`, `skill: "podcast-voice-cleanup"`, a `run_id`, `details` = the plugin, the problem it treats, the values and the measure before).
3. For noise in the pauses, hand over to `noise-gate` with the same export.

### 7. Verify

Export the same range again (`cleanup-after`) and run `cubase_voice_diagnostics` on it. Compare **absolute** levels, not relative ones: the relative bands (`*_db`) and the prominences (`hK_db`) move when the whole moves or when a notch also lowers a peak's surroundings. So:

- the treated problems should fall: the harmonics' `hK_dbfs`, `rumble_dbfs`, and for the de-esser the esses' `peak_dbfs` (2-4 dB down for `Reduction` 3-4; the sibilance rate often does not move, since its threshold follows the voice);
- the voice should keep its body: `low_dbfs` (80-250 Hz), `body_dbfs` and `presence_dbfs` within about 1 dB of before. A notch or a high-pass can take much more than its nominal shape suggests: on TW-1624's test, StudioEQ's 80 Hz cut with notches at 100 Hz (−6 dB) and 150 Hz (Q 10) took 8-15 dB from 80 to 200 Hz, 5-7 dB more than the settings suggest.

Report both, with the numbers. If the voice lost body, propose a gentler value and check again. No measure replaces listening: ask the user to listen once more.

## Safety

- Discover the plugins; do not assume names or parameters. Write only parameters whose title was checked (`expect_title`).
- Treat only measured problems, gently; name the artifacts each treatment can cause.
- Insert with Bypass on and turn it off only after the user's yes; never change a plugin that is not this skill's unless the user asks for that one.
- Do not leave a track soloed (`solo` in `cubase_export_mix`, `cancel` if abandoned); do not retry a write after a timeout; do not save the project unless asked.

## Outputs

- The plugins kept, their slots and values, each with the problem it treats and the measure before and after.
- The problems reported but not treated, with their times.
- How to undo: each plugin's Bypass, or remove it from its slot in Cubase (Trackwright cannot remove plugins). The exports stay in `Mixdown`.

## Ownership

The plugins this skill inserts are its own (`plugin` items keyed `<track uid>/slot:<N>` in `state.json`); a re-run adjusts them instead of inserting more. Plugins already on the track are the user's. If the user removes one in Cubase, forget its item (`cubase_workspace`, `action: "forget"`). The gate, if any, belongs to `noise-gate`.
