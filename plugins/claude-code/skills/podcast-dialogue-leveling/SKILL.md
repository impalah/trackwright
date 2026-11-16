---
name: podcast-dialogue-leveling
description: Level the voices of a podcast in Cubase so people sound equally loud and no answer drops away, without flattening the performance - speech-gated loudness per voice and per intervention, bounded gains that ramp in the pauses, whispers, laughs and emphasis kept - rendered offline onto new tracks after comparing fragments before and after. Use when the user says one voice is louder than another, the guest is too quiet, the levels jump between people or takes, or asks to balance, even out or level the dialogue.
license: AGPL-3.0-or-later
compatibility: Needs the Trackwright MCP server with Cubase open, [writes] enabled = true, [analysis] enabled = true and [workspace] enabled = true in ~/.config/trackwright/config.toml, and the project's Trackwright/ folder (cubase_workspace init).
metadata:
  author: impalah
  project: https://github.com/impalah/trackwright
---

# Podcast dialogue leveling

Uneven voices are one of the most noticeable faults of a podcast. The goal is **consistency, not equal values**: the host and the guest at the same level, an answer recorded further from the microphone brought back, but a whisper, a laugh or an emphasis left as it was performed. The skill measures the voices over their speech only, proposes bounded gains per voice and per intervention, lets the user compare fragments before and after, and renders the leveled voices onto new tracks (the API cannot write clip gain or automation points, so it is done offline, as for ducking).

Speak to the user in their language and keep them informed; they are in front of Cubase.

## Requires

`cubase_status`:

- `connected` false: ask the user to open Cubase and check the Trackwright surface in the MIDI Remote tab.
- `writes_enabled`, `analysis_enabled` or `workspace_enabled` false: say which key is needed in `~/.config/trackwright/config.toml` and stop.
- `cubase_workspace` (action `status`): the workspace must exist; if not, offer `action: "init"` (dry run, then apply).

## Inputs

- **The voices:** which tracks are voices (`cubase_list_tracks`; the episode profile's roles when there are any: `cubase_profile` `resolve`). One person per track; a track with two people cannot be leveled between them (say so).
- **The range:** the whole episode by default.
- **The target:** by default the voices meet at the median voice (nobody moves much); a speech loudness the user gives (`target_lufs`) instead. The episode's final loudness is the delivery's job (`podcast-delivery`), not this one's.
- **The limits:** `max_gain_db` 6 dB, `tolerance_db` 2 dB (deviations left alone), `min_segment` 3 s (shorter interventions get only their voice's gain), `join_gap` 1.5 s. Say they are starting values; "more natural" means a wider tolerance, "more even" a narrower one.

## Workflow

### 1. Inspect

- `cubase_list_tracks`: the voice tracks, their mute state, and tracks this skill created earlier (`cubase_workspace` `status`, items of `podcast-dialogue-leveling`): a re-run levels the original tracks again and replaces its own leveled tracks.
- Inserts on the voice tracks (`cubase_list_inserts`): the export includes them, so the leveled render carries them; tell the user the original's inserts must be bypassed or the render's track left without them, so they are not applied twice.

### 2. Analyze

1. Export **each voice track alone**: `cubase_export_mix` with `phase: "start"`, the range, `solo` = that one track, `dry_run: false`. Ask for WAV, 32-bit float, the project's sample rate, a name like `leveling-<track>`. Confirm (or cancel); check `solo_restored`. One export per voice.
2. `cubase_leveling_plan` with `voices` = `[{file, start: <range start>, name: <track>}, …]` and the limits.

### 3. Propose

In plain words, per voice: its speech loudness against the target and its gain ("the guest is 6 dB below the host: +3 dB to the guest, −3 dB to the host"); how many interventions get their own correction and the range of gains; the ones bounded by `max_gain_db` (a voice that needs more than that has a recording problem: say so); and that inside an intervention nothing changes. Never present it as making every phrase equal.

### 4. Preview

1. Render each voice: `cubase_render` with `file` = its export, `start` = the range start, `process: "level"`, `level` = that voice's `level` object from the plan, `track` = the voice track (the render replaces it), `skill: "podcast-dialogue-leveling"`, a `run_id`; dry run, then `dry_run: false`.
2. Compare: for each fragment in the voices' `compare` (the most raised, the most lowered, a typical one), two previews with `cubase_preview` over that range: **before** with `sources` = every voice's export, and **after** with `sources` = every voice's render, named `leveling-<n>-before` and `leveling-<n>-after`. Their `levels_db` show the change.
3. The user listens (Quick Look in the Finder). Too much: a wider `tolerance_db` or a lower `max_gain_db`; a segment that should stay as it was: plan again and leave that range out of the render by editing its gain to the voice's gain.

### 5. Approve

An explicit yes to the leveled voices (name each render) after the comparison.

### 6. Apply

For each voice:

1. A new audio track: `cubase_add_track_interactive` (`kind: "audio"`, a name like `<track> leveled`), mono or stereo like the original.
2. `cubase_import_audio` on it at the range start, `file` = the approved render: start (dry run, then `dry_run: false`), the user **unticks "Copy file to project folder"**, then confirm.
3. Mute the original: `cubase_set_track_mix` (`mute: true`; dry run, then apply). Never delete it.

Optional, only if the user asks for it after hearing the leveled voices: moderate compression on the new tracks with Compressor (`cubase_insert_plugin`, a gentle ratio and threshold, dry run first), recorded with `cubase_workspace` (`kind: "plugin"`).

### 7. Verify

Each import's `verified` and each original muted. Offer to play the compared fragments in Cubase (`cubase_set_position`, cursor). If the episode will be delivered, offer `podcast-delivery` afterwards: the overall loudness may have changed.

## Safety

- Consistency, not equal values: never level phrase by phrase, never more than `max_gain_db`, never inside an intervention.
- Do not change the project before the user approves; renders and previews go only to `Trackwright/`.
- Mute originals, never delete them; do not retry a write after a timeout; do not save the project unless asked.
- Exports include the tracks' inserts: never let them be applied twice without saying so.

## Outputs

- The leveled voices on new tracks at their place, the originals muted.
- The renders and their provenance (every gain, the ramp) in `Trackwright/renders/`, the before/after previews in `Trackwright/previews/`.
- How to undo: unmute the originals and mute or remove the leveled tracks; Edit > Undo.

## Ownership

The renders and the leveled tracks (recorded by `cubase_import_audio`, with the track each replaces) and any compressor added are this skill's (`state.json`). A re-run levels the originals again and offers to replace only its own leveled tracks. The original voice tracks and every other track are the user's.
