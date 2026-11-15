---
name: podcast-final-qc
description: Check a finished podcast episode before publishing - format, channels, sample rate, bit rate, size, loudness and true peak against the delivery targets (Apple Podcasts, Spotify, YouTube, iVoox or the show's own), plus long pauses, silence at the ends, sudden level changes between sections and clipping - and say where to listen. Use when the user asks for a final check, QC, quality control, or whether an episode or file is ready to publish or meets a platform's specs. Read-only; it fixes nothing (that is podcast-delivery) and can save the report in the project.
license: AGPL-3.0-or-later
compatibility: Needs the Trackwright MCP server with [analysis] enabled = true in ~/.config/trackwright/config.toml; Cubase open to export a fresh mix. Saving the report needs [workspace] enabled = true.
metadata:
  author: impalah
  project: https://github.com/impalah/trackwright
---

# Podcast final QC

The last look before publishing: does the file meet what the platforms ask, and is there anything a listener would notice? The measuring is done by `cubase_final_qc` on the file itself; this skill decides which file, which targets, explains the result in plain words and says where to listen. It changes nothing: fixing the loudness or the peaks is the job of `podcast-delivery`.

Speak to the user in their language and keep them informed; they are in front of Cubase.

## Requires

`cubase_status`:

- `analysis_enabled` false: nothing can be measured. Explain that `[analysis] enabled = true` is needed in `~/.config/trackwright/config.toml`, then reconnect the MCP server.
- `connected` false: a file the user already has can still be checked; a fresh export needs Cubase open.
- `workspace_enabled` false: the check runs, but the report cannot be saved in the project; say so.

## Inputs

- **The file:** the one the user will publish (an MP3 or M4A they exported, often), or a fresh export of the whole episode (step 2). Ask which.
- **The targets:** `cubase_profile` (action `resolve`) gives the profile's `delivery.targets` and their published values. If there are none, ask which platforms the episode goes to (`cubase_profile`, action `delivery`, lists them) and pass them as `targets`; offer to save them in the episode or show profile afterwards.
- **The approved range:** for a fresh export, the episode's start and end (from the user, or the extent found by `podcast-session-audit`); its length is `expected_seconds`.
- **The thresholds:** pauses of 3 s or more and level changes of 6 LU or more are flagged by default; the user can ask for others (`long_pause_seconds`, `jump_lu`).

## Workflow

### 1. Inspect

- `cubase_profile` (action `resolve`): targets, track roles.
- If Cubase is connected: `cubase_list_tracks`. A track **soloed** would leave the others out of a fresh export; a track whose role is `reference` (a guide, a backup recording) should be muted; a track `muted` that has a `voice` or `music` role may be a mistake. Point these out before exporting: the file cannot show which tracks are in it.

### 2. Analyze

1. **A fresh export** (if the user did not give a file): `cubase_export_mix` with `phase: "start"`, the approved range (`start`, `end`), no `solo` (the whole mix), `dry_run: false`. Ask the user to export what they will publish (for example MP3 at the bit rate of the target, or WAV 32-bit float to check the master); wait; `phase: "confirm"` with `since` and `expected_seconds` (or `phase: "cancel"`).
2. `cubase_final_qc` with `file`, `start` (the export's range start, or 0 for a whole file), `expected_seconds` when known, and `targets` if the profile has none. Leave `report` false here.
3. Name the file measured (`source.file`). If `source.project_saved_after` is true, the project was saved after this file: ask whether it changed; if so, export again.

### 3. Propose

Explain the result in three groups, in plain words:

- **Checks:** a table per target: item, measured, expected, pass or fail. Give each expected value's source (the platform's page). `info` items mean the platform publishes no number for that: say "not published", never "passes".
- **Warnings:** what is worth a listen and why (a 12 s pause at 23:40, a section 8 LU quieter from 31:10, silence at the start).
- **To check by hand:** the manual items, plus anything found in step 1.

Then the verdict: ready for each target, or what fails. A failed loudness or true peak is fixed with `podcast-delivery`; a failed format is chosen again in the export dialog.

### 4. Preview

List the `moments` (project time and why). Offer to move the cursor to each one in turn (`cubase_set_position` with `which: "cursor"`, `unit: "seconds"`) so the user plays from there in Cubase; the cursor does not change the project.

### 5. Approve

Ask whether to save the report in the project (`Trackwright/reports/`). Nothing else is written.

### 6. Apply

If the user wants the report: `cubase_final_qc` again with the same values and `report: true` (it measures again and writes `qc-<file>-<time>.json` and `.md`). Then record it: `cubase_workspace` with `action: "record"`, `kind: "report"`, `key` set to the Markdown path relative to `Trackwright/` (for example `reports/qc-episode-20261115T193000Z.md`), `skill: "podcast-final-qc"`, a `run_id`, and `details` with the verdict and targets; dry run, then `dry_run: false`.

### 7. Verify

The answer's `report` lists the files written: tell the user where they are. If something was fixed after this check (with `podcast-delivery` or by hand), offer to check the new file again: a report is about one file (its SHA-256 is in it).

## Safety

- Do not change anything in the Cubase project: no fader, limiter, mute or solo, even to fix a failure; propose `podcast-delivery` instead.
- Do not report a value the platform does not publish as passing or failing.
- Do not mark a manual item as checked: only the user can.
- Do not export or measure files the user did not point to.
- Do not save the project.

## Outputs

- The verdict per target, the checks with their sources, the warnings and the moments to listen to, in the conversation.
- If approved, the report in `Trackwright/reports/` (JSON for other tools, Markdown to read).
- The export, if one was made, stays in `Mixdown`.

## Ownership

The reports this skill writes are its own: each recorded in `state.json` as a `report` item. A new check writes a new report and never overwrites an old one (they are dated); old reports are deleted only if the user asks. Nothing in the Cubase project is created or changed.
