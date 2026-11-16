---
name: podcast-sound-effects
description: Place sound effects in a podcast in Cubase from the user's licensed library - at the exact point the user approves, with a level that sits against the voice, fades, and a check of the speech and other effects it lands on - with a preview first, the licence recorded and the episode's credits gathered. Use when the user asks to add a sound effect, a door, a click, a whoosh, a laugh track, an ambience or a sound under a moment, or to collect the credits of the sounds used in an episode.
license: AGPL-3.0-or-later
compatibility: Needs the Trackwright MCP server with Cubase open, [writes] enabled = true, [analysis] enabled = true and [workspace] enabled = true in ~/.config/trackwright/config.toml, the project's Trackwright/ folder (cubase_workspace init) and [library] folders with the user's licensed sounds.
metadata:
  author: impalah
  project: https://github.com/impalah/trackwright
---

# Podcast sound effects

An effect supports the story: a door when someone arrives, a click on a demo, a laugh. Where it goes and which one is the user's decision; this skill finds licensed candidates, says what the effect lands on (speech, another effect), proposes a level against the voice, renders it with fades at the project's rate, lets the user listen, places it and records its licence so the episode's credits can be gathered.

Speak to the user in their language and keep them informed; they are in front of Cubase.

## Requires

`cubase_status`:

- `connected` false: ask the user to open Cubase and check the Trackwright surface in the MIDI Remote tab.
- `writes_enabled`, `analysis_enabled` or `workspace_enabled` false: say which key is needed in `~/.config/trackwright/config.toml` and stop.
- `cubase_workspace` (action `status`): the workspace must exist; if not, offer `action: "init"` (dry run, then apply).
- `cubase_library`: `NO_LIBRARY` means no `[library] folders`: ask the user to set them; never take sounds from anywhere else (no downloads, no files without a licence).

## Inputs

- **What and where:** the effect the user wants (words for the search) and the exact project time (read from their marker or cursor with `cubase_get_transport`). Several effects: a list of (sound, time).
- **The sound:** `cubase_library` (`kind: "effect"` or `ambience`, the user's words, `use: "podcast"` when the sidecars list uses, `max_seconds` for short sounds). Show a few with title, length, licence and credit; the user chooses.
- **The level:** against the voice. By default `cubase_effect_plan` proposes −12 dB under the voice when it lands on speech and −3 dB in a pause; the user may say "subtle" (lower) or "clear" (higher).
- **Fades:** a fade in for a sound that starts abruptly and should not; a fade out for one cut short or with a long tail (`clip.trim_end`, `fade_out`).

## Workflow

### 1. Inspect

- `cubase_list_tracks`: the voice tracks (not muted) and whether there is an effects track this skill created (`cubase_workspace` `status`, items of `podcast-sound-effects`). Effects go on such a track, or a new one.
- `cubase_workspace` (`status`): effects this skill placed earlier, to replace one at the same place on a re-run.

### 2. Analyze

1. Export the voices around the points (or the whole episode): `cubase_export_mix` with `phase: "start"`, the range, `solo` = the uids of **all the voice tracks that are not muted**, `dry_run: false`. Ask for WAV, 32-bit float, the project's sample rate, a name like `effects-voices`. Confirm (or cancel); check `solo_restored`.
2. For each effect: `cubase_effect_plan` with `effect_file`, `at`, `voice_file`, `voice_start` (the range start) and `relative_db` if the user gave a level.

### 3. Propose

For each effect, in plain words: where it goes and where its sound ends; whether it lands on speech (`under_speech`, how long) or in a pause; the proposed `suggested_gain_db` (and that it is a starting value); the fades; and `overlaps` with earlier effects (on the same track the events would overlap: a second effects track, or move it). Never move the point on your own: the place is the user's.

### 4. Preview

1. Render each effect: `cubase_render` with `file` = the sound, `process: "clip"`, `clip` = `{sample_rate: <the project's>, fade_in, fade_out, trim_end}` (only what is needed), `gain_db` = the suggested or chosen gain, `start` = `at`, `skill: "podcast-sound-effects"`, a `run_id`; dry run, then `dry_run: false`.
2. `cubase_preview` with `sources` = the voice export at `voice_start` and the render at `at`, over the plan's `preview` range, named `effect-<n>`.
3. The user listens (Quick Look in the Finder). Too loud or too quiet: render again with another `gain_db`; abrupt: add a fade.

### 5. Approve

An explicit yes to each effect (name the render, the time and the level) after its preview.

### 6. Apply

1. The track: the effects track this skill created, or a new one with `cubase_add_track_interactive` (`kind: "audio"`, a name like `Effects`; stereo if the sound is stereo). If the effect overlaps an earlier one on that track, a second effects track.
2. `cubase_import_audio` on it at `at`, `file` = the approved render: start (dry run, then `dry_run: false`), the user **unticks "Copy file to project folder"**, then confirm.
3. Record the licence: `cubase_workspace` (`action: "record"`, `kind: "render"`, `key` = `renders/<the render's file name>`, the same `skill` and `run_id`, `details` = `{title, license, source, attribution, at, audible_seconds}`). It is merged into the record the import made (track and position).
4. The credits: `cubase_workspace` with `action: "credits"` (dry run shows them, then `dry_run: false`) writes `Trackwright/credits.md`: the credits the licences ask for, to paste into the episode notes, and every licensed sound used and where.

### 7. Verify

Each import's `verified`. Offer to play from 3 s before an effect in Cubase (`cubase_set_position`, cursor). Show the credits the licences ask for (or that none asks for one).

## Safety

- Only sounds from the licensed library; nothing is downloaded; a sound whose licence is unknown is never used.
- The point is the user's: never move an effect, and never place one over speech without saying so.
- Do not change the project before the user approves; renders and previews go only to `Trackwright/`.
- Do not remove or overwrite an existing track or event; do not retry a write after a timeout; do not save the project unless asked.

## Outputs

- Each effect on an effects track at its point, at its level, with its fades.
- The renders and their provenance in `Trackwright/renders/`, the previews in `Trackwright/previews/`, the licences in `state.json`, and `Trackwright/credits.md`.
- How to undo: Edit > Undo, or remove the event; `cubase_workspace` `forget` removes a licence record, and `credits` writes the file again.

## Ownership

The clip renders, the effects tracks this skill created (recorded by `cubase_import_audio`), the licence records and `credits.md` (shared: it gathers every skill's licences) are this skill's. A re-run at the same point offers to replace only the earlier effect recorded as this skill's. Every other track, event and marker is the user's.
