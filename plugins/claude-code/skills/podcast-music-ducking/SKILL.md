---
name: podcast-music-ducking
description: Lower the music under the voices of a podcast in Cubase - the music goes down just before someone speaks, stays down through short pauses and comes back up gently after a block of speech - by planning a gain envelope from the voices, rendering the ducked music, letting the user listen to previews, and importing it as a new track with the original muted. Use when the user asks to duck the music, lower or automate the music under the voice, make the music not cover the speech, or change how the music behaves ("make the ducking less obvious", "do not bring the music up between those two phrases"). Nothing in the project changes before the user approves.
license: AGPL-3.0-or-later
compatibility: Needs the Trackwright MCP server with Cubase open, [writes] enabled = true, [analysis] enabled = true and [workspace] enabled = true in ~/.config/trackwright/config.toml, and the project's Trackwright/ folder (cubase_workspace init).
metadata:
  author: impalah
  project: https://github.com/impalah/trackwright
---

# Podcast music ducking

The music under a podcast has to make room for the voice: down a little before the first word, down through the short pauses of a phrase (not back up at every breath), and gently back up when a block of speech ends. The Cubase API cannot write automation points or route a side-chain, so this is done **offline**: the voices and the music are exported, `cubase_ducking_plan` plans the envelope from the voices, `cubase_render` writes the ducked music to `Trackwright/renders/`, the user listens to previews, and the ducked music is imported on a **new track** with the original muted, never deleted.

The default values (−10 dB, pre-roll 0.25 s, hold 0.8 s, recovery 1.2 s, phrases joined over pauses under 0.9 s) are starting points, not rules: the user's ears decide. The acceptance is "the voice stays clear and the recoveries do not distract".

Speak to the user in their language and keep them informed; they are in front of Cubase.

## Requires

`cubase_status`:

- `connected` false: ask the user to open Cubase and check the Trackwright surface in the MIDI Remote tab.
- `writes_enabled`, `analysis_enabled` or `workspace_enabled` false: say which key is needed in `~/.config/trackwright/config.toml` and stop.
- `cubase_workspace` (action `status`): the workspace must exist; if not, offer `action: "init"` (dry run, then apply).
- `allowed_tracks` not empty: the new track and the muting of the music track must be allowed.

## Inputs

- **The voice tracks and the music track:** from the episode profile's `track_roles` (`cubase_profile`, action `resolve`): `voice` and `music`. If the roles are not set, ask (or offer `podcast-session-audit`); never guess from the names.
- **The range:** the part of the episode with music (often the whole episode), in project seconds.
- **The style:** the profile's `ducking` settings if any (`depth_db` is `attenuation_db`, `pre_roll_seconds` is `pre_roll`, `hold_seconds` is `hold`, `release_seconds` is `recovery`), otherwise the defaults; say where each value comes from.
- **Protected ranges:** the profile's are kept at full level (`use_protected`); the user can add spans in plain words ("no ducking under the intro") as overrides.

## Workflow

### 1. Inspect

- `cubase_list_tracks`: the voice and music tracks, their `uid`, mute and solo; nothing must stay soloed after the exports.
- `cubase_render` (action `list`) and `cubase_workspace` (`status`): a render of `podcast-music-ducking` that replaces this music track, and the track it was imported on, mean an earlier run. Its provenance's `parameters` is the earlier ducking specification: start from it, and the earlier ducked track is the one to replace.

### 2. Analyze

1. Export the voices: `cubase_export_mix` with `phase: "start"`, the range, `solo` = the uids of **all the voice tracks that are not muted** (a soloed track sounds even when muted, so `cubase_export_mix` leaves muted ones out and says so: a muted voice track is usually one a render replaced), `dry_run: false`. Ask for WAV, 32-bit float, the project's sample rate, a name like `ducking-voices`. Confirm (or cancel); check `solo_restored`.
2. Export the music the same way, with `solo` = the music track's uid (name it `ducking-music`).
3. `cubase_ducking_plan` with `ducking` = `{voice_file, voice_start: <range start>, attenuation_db, pre_roll, hold, recovery, merge_gap, overrides, use_protected}`, `music_start` = the range start, `music_seconds` = the music export's length, and `music_file` = the music export, so the `moments` it proposes have music to hear.

### 3. Propose

In plain words: how many speech regions, how many ducked spans, how much of the music is ducked and for how long it comes back up; the values and where they come from; the protected ranges kept up. Ducking above about 80 % of the time means the music will be low almost everywhere (a monologue with short pauses): say so and offer to keep it up in chosen places (`free` overrides: the intro, the outro, a transition), a lighter attenuation, or a shorter `hold`.

### 4. Preview

1. Render the ducked music: `cubase_render` with `file` = the music export, `start` = the range start, `process: "duck"`, `ducking` = the same object, `track` = the music track, `skill: "podcast-music-ducking"`, a `run_id`; dry run, then `dry_run: false`. It writes only to `Trackwright/renders/`.
2. Previews with `cubase_preview`: `sources` = the voice export and the ducked render, both at the range start; about 15 s around 3 to 5 `moments` of the plan (a first word, a recovery after a long block, a pause where the music comes up, the end). Only moments where **both** the voice and the music have sound show anything: music tracks often have gaps, and a preview in one only plays the voice (seen live in TW-1615). If a preview's notes say a source is silent, drop it and pick another moment.
3. Make one **before/after pair** of the same stretch: the voice with the original music export, then with the ducked render, named so the user knows which is which (`…-BEFORE-…`, `…-AFTER-…`). Hearing the difference is what lets the user judge the ducking. Ask the user to listen to them (Quick Look in the Finder).

**Edits in plain words** ("less obvious", "deeper", "do not bring it up between 12:30 and 13:10", "no ducking under the intro") change the specification: the parameters, or an override (`hold`, `free`, `depth` with project seconds). Call `cubase_ducking_plan` with the new `ducking` and `previous` = the one before: `changed` lists the spans the edit changes. Render again and preview **only** those spans; say what changed and where.

### 5. Approve

Ask for an explicit yes to the last render (name it) after the previews.

### 6. Apply

1. A new audio track: `cubase_add_track_interactive` (`kind: "audio"`, suggested name `<music track> ducked`); the user chooses **stereo** if the music is stereo.
2. `cubase_import_audio` on that track, `position` = the range start, `file` = the approved render: start (dry run, then `dry_run: false`), the user picks the file and **unticks "Copy file to project folder"**, then confirm. It checks the position against the render's provenance and records the track as this skill's.
3. Mute the original music track (`cubase_set_track_mix`, `mute: true`; dry run, then apply). Never delete it.
4. On a re-run: once the new ducked track is in, offer to remove the earlier ducked track (recorded as this skill's): `cubase_select_track`, then `cubase_remove_selected_track` after the user confirms.

### 7. Verify

- The import's `edges_found` and `verified` (or the end edge for a render at 0 s).
- Offer to play from 2–3 of the moments in Cubase (`cubase_set_position`, cursor) with the original muted, so the user hears it in the mix.
- If the episode will be delivered, offer `podcast-final-qc` on a new export.

## Safety

- Do not change the project before the user approves the render; renders and previews are written only to `Trackwright/`.
- Never delete or overwrite the original music track or its audio: mute it.
- Do not remove a track that is not recorded as this skill's, and not without the user's confirmation.
- Restore every solo (`solo` in `cubase_export_mix`, `cancel` if an export is abandoned).
- Do not retry a write after a timeout; do not save the project unless asked.

## Outputs

- The ducked music track in the project, at the range start, with the original muted.
- The render and its provenance (the whole ducking specification, the voice export's hash) in `Trackwright/renders/`, the previews in `Trackwright/previews/`, the exports in `Mixdown`.
- How to undo: unmute the original and mute or remove the ducked track; Edit > Undo in Cubase.

## Ownership

The render and the track it is imported on are this skill's, recorded in `state.json` by `cubase_import_audio`; the previews too (`cubase_workspace`, `action: "record"`, `kind: "preview"`, if the user wants them kept track of). A re-run starts from the earlier render's specification, imports a new render on a new track and offers to remove only the earlier track recorded as this skill's. The original music track, the voices and every other track are the user's: the skill only mutes the music track, with approval.
