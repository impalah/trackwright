---
name: podcast-section-transitions
description: Place a transition (a stinger, a short music in or out) between two sections of a podcast in Cubase - in the pause between them, never over the last phrase, with its tail ending before the next one - from the user's licensed library, at the project's rate, with a preview to listen to first; when it does not fit, offer to open the pause, fade the tail or choose a shorter one. Use when the user asks to put the usual transition, a stinger, a jingle or a separator between the interview and the news, between segments or sections, or to place a sound at a marker without covering speech.
license: AGPL-3.0-or-later
compatibility: Needs the Trackwright MCP server with Cubase open, [writes] enabled = true, [analysis] enabled = true and [workspace] enabled = true in ~/.config/trackwright/config.toml, the project's Trackwright/ folder (cubase_workspace init) and, to search for the stinger, [library] folders.
metadata:
  author: impalah
  project: https://github.com/impalah/trackwright
---

# Podcast section transitions

A transition marks the change from one section to the next. Placed by hand it often covers the last word of the section, or its tail runs into the first phrase of the next one. This skill finds the pause between the two sections from the voices, starts the stinger just after the last phrase, checks that its **audible** tail (not the silence a file may carry) ends before the next phrase, and lets the user listen before anything changes.

Choosing the stinger and the style is the user's: the skill places and executes.

Speak to the user in their language and keep them informed; they are in front of Cubase.

## Requires

`cubase_status`:

- `connected` false: ask the user to open Cubase and check the Trackwright surface in the MIDI Remote tab.
- `writes_enabled`, `analysis_enabled` or `workspace_enabled` false: say which key is needed in `~/.config/trackwright/config.toml` and stop.
- `cubase_workspace` (action `status`): the workspace must exist; if not, offer `action: "init"` (dry run, then apply).
- To search the library, `cubase_library`: `NO_LIBRARY` means no `[library] folders`; the user can still give a file, but only one whose licence they confirm.

## Inputs

- **Where:** about where the transition goes, as a project time (the API cannot read markers: ask the user to read the marker's time, or to put the cursor there and read it with `cubase_get_transport`), and between which sections.
- **The stinger:** `cubase_library` (`kind: "stinger"`, or `music`/`effect`, words from the user, `use: "podcast"` when the sidecars list uses). Show title, length, licence and the credit it asks for; the user chooses. A sound without a licence is never offered.
- **The level:** relative to the voice (by default it is placed as it is; the preview shows its level next to the voice).
- **The margins:** 0.3 s after the last phrase and 0.3 s before the next one, unless the user says otherwise.

## Workflow

### 1. Inspect

- `cubase_list_tracks`: the voice tracks (not muted), and whether there is already a transitions track. The transition goes on a **new** track (or the transitions track this skill created, recorded in `state.json`).
- `cubase_workspace` (`status`): an earlier transition of this skill at the same place is the one to replace.

### 2. Analyze

1. Export the voices around the place (from about 60 s before to 60 s after, or the whole episode if several transitions are planned): `cubase_export_mix` with `phase: "start"`, the range, `solo` = the uids of **all the voice tracks that are not muted**, `dry_run: false`. Ask for WAV, 32-bit float, the project's sample rate, a name like `transitions-voices`. Confirm (or cancel); check `solo_restored`.
2. `cubase_transition_plan` with `voice_file` = that export, `voice_start` = the range start, `at` = the time the user gave, `stinger_file` = the chosen sound, `pre_gap`, `post_gap`.

### 3. Propose

In plain words: the pause found (from the end of the last phrase to the start of the next one), where the stinger starts, where its sound ends, and whether it fits. Read the `notes`: a pause far from the time asked for (check it is the right place), a file with silence after its sound. When it does **not** fit, give the `overlap` and the `options`, and let the user choose:

- **open the pause:** `cubase_edit_range` with `action: "insert_silence"` at the start of the next phrase for the `overlap` (every track moves later from there: say so);
- **fade the tail:** render with `clip.trim_end` = (next phrase − `post_gap` − start) and a `fade_out` of up to 1 s;
- **a shorter stinger** from the library.

Never shorten, move or fade anything the user has not chosen.

### 4. Preview

1. Render the stinger ready to place: `cubase_render` with `file` = the stinger, `process: "clip"`, `clip` = `{sample_rate: <the project's>, trim_end, fade_in, fade_out}` (only what was chosen), `gain_db` (the level), `start` = the plan's `start`, `skill: "podcast-section-transitions"`, a `run_id`; dry run first, then `dry_run: false`. The project's rate keeps Cubase from copying the file on import.
2. `cubase_preview` with `sources` = the voice export at `voice_start` and the clip render at the plan's `start`, over the plan's `preview` range, named `transition-<n>`. Its `levels_db` shows the stinger's level next to the voice.
3. Ask the user to listen (Quick Look in the Finder). Too loud or too quiet: render again with another `gain_db`; too early or too late: change `pre_gap`.

### 5. Approve

An explicit yes to the transition (name the render and where it goes) after the preview. If the pause must be opened, a separate yes to the `insert_silence` (it moves every track).

### 6. Apply

1. If chosen, open the pause first: `cubase_edit_range` (`insert_silence`, dry run, then `dry_run: false`).
2. The track: the transitions track this skill created, or a new one with `cubase_add_track_interactive` (`kind: "audio"`, a name like `Transitions`; stereo if the stinger is stereo).
3. `cubase_import_audio` on it at the plan's `start`, `file` = the approved render: start (dry run, then `dry_run: false`), the user **unticks "Copy file to project folder"**, then confirm.
4. Record the licence: `cubase_workspace` (`action: "record"`, `kind: "render"`, `key` = `renders/<the render's file name>`, the same `skill` and `run_id`, `details` = `{title, license, source, attribution, at}` from the library). The import already recorded that render with its track; the same skill's details are merged into that record, so the credits can be gathered later.

### 7. Verify

The import's `verified`. Offer to play from 3 s before the transition in Cubase (`cubase_set_position`, cursor). If the library asks for a credit (`attribution`), remind the user to add it to the episode notes; `cubase_workspace` with `action: "credits"` gathers every licence of the episode into `Trackwright/credits.md`.

## Safety

- Never cover speech: the stinger starts after the last phrase, and a tail that runs into the next phrase is reported, never cut or moved on its own.
- Only sounds from the licensed library, or a file the user gives and whose licence they confirm; nothing is downloaded.
- Do not change the project before the user approves; renders and previews go only to `Trackwright/`.
- `insert_silence` moves every track after the point: only with its own explicit yes.
- Do not remove or overwrite an existing track or event; do not retry a write after a timeout; do not save the project unless asked.

## Outputs

- The transition on its track at its place (and, if chosen, the pause opened).
- The render and its provenance in `Trackwright/renders/`, the preview in `Trackwright/previews/`, the licence and credit recorded in `state.json`.
- How to undo: Edit > Undo, or remove the event; the opened pause with Edit > Undo or `cubase_edit_range` `delete_time` over the same span.

## Ownership

The clip render, the transitions track it created (recorded by `cubase_import_audio`) and the licence record are this skill's (`state.json`). A re-run at the same place offers to replace only the earlier transition recorded as this skill's. Every other track, event and marker is the user's.
