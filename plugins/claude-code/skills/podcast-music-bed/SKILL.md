---
name: podcast-music-bed
description: Make a music bed of a given length for a podcast in Cubase from a piece of music that is too short - repeat a loop (a file made to loop, a region the user marks, or one the analysis proposes) and let the music end naturally, never time-stretched - let the user listen to every seam, and import it on a new track at the right place, with markers at doubtful seams. Use when the user asks for background music, a music bed, to extend or loop music under the voice or a segment, or to make a piece of music last a given time.
license: AGPL-3.0-or-later
compatibility: Needs the Trackwright MCP server with Cubase open, [writes] enabled = true, [analysis] enabled = true and [workspace] enabled = true in ~/.config/trackwright/config.toml, and the project's Trackwright/ folder (cubase_workspace init).
metadata:
  author: impalah
  project: https://github.com/impalah/trackwright
---

# Podcast music bed

A bed has to last as long as the segment under it, and the music is often shorter. Duplicating the event until it fills the gap is not enough: a jump in the middle of a phrase, or off the beat, is heard. This skill repeats a **loop** whose two ends sound alike, lines the jump up to the sample, joins it with a short crossfade, and lets the music **end on its own** after the last pass. It never stretches the music: the bed is the nearest length that fits without going over, and it says how much shorter that is.

Musical judgement is the user's: the analysis proposes, the user listens to every seam and decides.

Speak to the user in their language and keep them informed; they are in front of Cubase.

## Requires

`cubase_status`:

- `connected` false: ask the user to open Cubase and check the Trackwright surface in the MIDI Remote tab.
- `writes_enabled`, `analysis_enabled` or `workspace_enabled` false: say which key is needed in `~/.config/trackwright/config.toml` and stop.
- `cubase_workspace` (action `status`): the workspace must exist; if not, offer `action: "init"` (dry run, then apply).

## Inputs

- **The music file:** an absolute path the user gives (WAV, MP3, M4A…). Only files the user points to are read.
- **Where and how long:** where the bed starts in the project (seconds) and where it must end (or its length). Ask; the length is `target_seconds`.
- **The mode** (ask which, briefly):
  - **a prepared loop:** the file was made to loop; the whole file repeats (`loop_start` 0, `loop_end` its length, `crossfade` 0 unless the user hears a click);
  - **a region the user marks:** start and end in the music file, in seconds; the end is lined up with the start (`align: true`);
  - **proposed by the analysis:** `cubase_music_analysis` gives candidates; the user chooses after listening.
- **The ending:** by default the music, after the last pass of the loop, plays on to its own end. If the user prefers another ending section, `ending_start` makes the last pass jump there (one more artificial seam).

## Workflow

### 1. Inspect

- `cubase_list_tracks`: is there already a music track at that place? The bed goes on a **new** track; say what is already there.
- `cubase_render` (action `list`) and `cubase_workspace` (`status`): an earlier bed of this skill for the same place is the one to replace.

### 2. Analyze

`cubase_music_analysis` on the file: tempo (and how sure it is), loop candidates (bars, seconds, `score`, `crossfade`) and the ending. Say it in plain words: "about 129 BPM; the best loop is 15 s (5.5 → 20.5 s), score 0.59: the piece changes as it goes, so listen to the seam". A score under about 0.5 means the seams will probably be heard; no beat means the loop lengths are not in bars.

For a prepared loop or a region the user marks, skip the candidates; the render (step 4) scores the seam the same way.

### 3. Propose

The plan: the loop (start, end, length), how many times it repeats, the bed's length against the target (`short_by`: it is never longer and never stretched), where the seams fall in the bed, and the crossfade. If the bed falls well short, offer a shorter loop (finer steps), a longer target, or a fade instead of a loop.

### 4. Preview

1. Render the bed: `cubase_render` with `file`, `process: "bed"`, `bed` = `{loop_start, loop_end, target_seconds, crossfade, align, ending_start, sample_rate}`, `skill: "podcast-music-bed"`, a `run_id`; dry run first (it gives `seams`, `seam_score` and the notes), then `dry_run: false`. It writes only to `Trackwright/renders/`. Set `sample_rate` to the project's rate (an export of the project shows it, for example the `sample_rate` of `cubase_measure_loudness` on a recent mixdown, or ask the user): music at another rate (44.1 kHz in a 48 kHz project) would be copied by Cubase on import to convert it.
2. A preview of **every seam** (up to five; with more, the first, a middle one and the last): `cubase_preview` with `sources` = the bed render at `start` = where the bed goes in the project, a range of about 3 s before to 3 s after the seam (project time = bed start + seam). Name them `bed-seam-1`, `bed-seam-2`…
3. Ask the user to listen to them (Quick Look in the Finder). A seam they hear: try the next candidate loop, a longer crossfade (up to half a bar), or mark a region by ear.

### 5. Approve

An explicit yes to the bed (name the render) after the previews.

### 6. Apply

1. A new audio track: `cubase_add_track_interactive` (`kind: "audio"`, a name like `Music bed`); stereo if the music is stereo.
2. `cubase_import_audio` on it at the bed's project start, `file` = the approved render: start (dry run, then `dry_run: false`), the user **unticks "Copy file to project folder"**, then confirm.
3. Markers at the seams the user doubted (or all of them if the score is under 0.5): `cubase_set_position` (cursor, seconds = bed start + seam), then `cubase_markers` with `action: "insert_at_cursor"` (if the project has no marker track, `add_marker_track` first); dry run, then apply. Record each marker (`cubase_workspace`, `action: "record"`, `kind: "marker"`, `key: "bed-seam-<n>@<seconds>"`).

### 7. Verify

The import's `verified` (and the end edge for a bed at 0 s). Offer to play from a seam in Cubase (`cubase_set_position`, cursor) so the user hears it in the mix. If voices go over the bed, offer `podcast-music-ducking`.

## Safety

- Never stretch the music in time, and never go over the target length.
- Do not change the project before the user approves the bed; renders and previews go only to `Trackwright/`.
- Do not read music files the user did not point to.
- Do not remove or overwrite an existing track; a re-run offers to remove only the earlier bed track recorded as this skill's, after the user confirms.
- Do not retry a write after a timeout; do not save the project unless asked.

## Outputs

- The bed on a new track at its place, with markers at the doubtful seams.
- The render and its provenance (the loop, the alignment, the seam score, the seams' places) in `Trackwright/renders/`, the seam previews in `Trackwright/previews/`.
- How long the bed is against the target, and how to undo: mute or remove the bed track; Edit > Undo.

## Ownership

The render, the track it is imported on (recorded by `cubase_import_audio`) and the markers are this skill's (`state.json`). A re-run imports a new bed on a new track and offers to remove only the earlier bed track recorded as this skill's. Every other track and marker is the user's.
