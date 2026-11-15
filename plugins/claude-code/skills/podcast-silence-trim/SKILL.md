---
name: podcast-silence-trim
description: Find and remove long silences from a podcast or spoken-word recording in the open Cubase project, closing the gaps (all tracks stay in sync). Use when the user asks to cut, trim, shorten or remove silences, pauses or dead air longer than some duration, on the whole project or a range. Exports the audio with the user's help, measures it, shows every proposed cut and only cuts after the user agrees.
license: AGPL-3.0-or-later
compatibility: Needs the Trackwright MCP server with Cubase open, [writes] enabled = true and [analysis] enabled = true in ~/.config/trackwright/config.toml.
metadata:
  author: impalah
  project: https://github.com/impalah/trackwright
---

# Podcast silence trim

Remove silences longer than a duration from a Cubase project, closing the gaps so the episode gets shorter and every track stays in sync. The Cubase API cannot read audio, so the silences are measured on an export: you prepare it, **the user clicks Export in Cubase**, then `cubase_analyze_audio` measures the file. Nothing is cut until the user has seen the list and said yes.

Speak to the user in their language. Keep them informed at each step; they are in front of Cubase.

## What gets cut, and why it matters

`cubase_edit_range` with `delete_time` removes the span from **every track** and moves everything after it earlier. So a span is only safe to cut when it is silent on **all** tracks:

- **Default: analyze the whole mix** (no solo). A silence in the mix is a silence everywhere. This is the right choice for a podcast with several voices recorded in sync.
- **The user names one track** ("the silences of the Voice track"): if other tracks have sound in the range (another voice, a music bed), cutting time would cut them too. Say so and offer:
  1. analyze the whole mix instead (safe, usually what they want);
  2. analyze the named track alone (solo it), knowing the cuts will also remove whatever the other tracks have there;
  3. remove the silences only on that track with `action: "delete"` and `track`, which leaves the gaps (the episode does not get shorter; useful only to remove noise between phrases).
- **A music bed under the voices** makes the mix never silent. Tell the user; they may mute it for the analysis, but the cuts will still cut the music (it will jump).

## Requires

Call `cubase_status`. Stop and explain if:

- `connected` is false: Cubase is not answering; ask the user to open it and check the Trackwright surface in the MIDI Remote tab.
- `analysis_enabled` is false: the user must add `[analysis]` with `enabled = true` to `~/.config/trackwright/config.toml` and reconnect the MCP server.
- `writes_enabled` is false: the analysis can still run, but nothing can be cut; say so before starting.
- `allowed_tracks` is not empty: range edits on every track are refused (`NOT_ALLOWED`); only option 3 above is possible, on an allowed track.

## Inputs

From the user's words, or by asking only what is missing:

- **Minimum silence** (`min_seconds`): "longer than 3 seconds" means 3. If they gave none, propose 2 s and ask.
- **Range:** the whole project (default) or start and end in seconds.
- **What to analyze:** the whole mix (default) or one track; see above. Use `cubase_list_tracks` to see the tracks, their names, `uid`, `solo` and `mute`.
- **Breathing room:** by default 0.25 s of each silence is kept at both ends so words are not clipped (`padding_seconds`). A silence of 3 s becomes a cut of 2.5 s. Mention it; change it if they want tighter or looser edits.
- **Profile:** `cubase_profile` (action `resolve`) gives the show's or episode's `editing.min_silence_seconds` and `editing.padding_seconds`; use them as the defaults to propose, and say where they come from. Its `protected` ranges must never be cut: leave out any silence that overlaps one, and say so.

## Workflow

### 1. Inspect

`cubase_list_tracks`: the tracks, their `uid`, `solo` and `mute`. Note a music bed or other sound under the voices (see above) and anything already soloed or muted, and tell the user before exporting.

### 2. Analyze

Export:

1. `cubase_export_mix` with `phase: "start"`, the range (`start`, `end`) or none for the whole project, `dry_run: false` once the user agreed to the job. If analyzing one track, add `solo` with its `uid`: only that track is exported, and the tool puts every solo back afterwards. Keep `since`, `expected_seconds` and **`start`** from the answer.
2. Tell the user what to choose in the "Export Audio Mixdown" dialog, then wait for them to say it is done:
   - channel: Stereo Out (the only one Cubase Elements offers);
   - file type: Wave, **32 bit float**, the project's sample rate;
   - a name they will recognize, for example `silence-check`;
   - real-time export off.
3. `cubase_export_mix` with `phase: "confirm"`, `since` and `expected_seconds`. It also restores the solos; check `solo_restored` is true (if not, say which track and restore it with `cubase_set_track_mix`). If it reports `not_found`, ask where they saved it and confirm again with `folder`. If the user closed the dialog without exporting, call `phase: "cancel"` with `since` instead.

Measure with `cubase_analyze_audio`:

- `file`: the path from the confirm phase;
- `start`: the `start` returned by the export's start phase (the project time of the file's first sample);
- `min_seconds` and `padding_seconds` as agreed; leave the other values at their defaults unless there is a reason.

Read the answer:

- If `threshold_db` is null and a note says there is no contrast, the audio has no quieter part to call silence (constant music, constant noise). Explain; offer a fixed threshold (`threshold_db`, for example -50) only if the user wants to try.
- `noise_floor_db` and `threshold_db` tell how quiet the "silence" is; mention them in one line.
- `source` says which export the numbers come from (file, range, SHA-256). Name the file when you report. If `source.project_saved_after` is true, the project was saved after this export: ask whether anything changed since (cuts, processing); if so, export again before cutting. `cache: "hit"` means the same export was already analyzed with these values: no need to say more.
- A silence marked `digital: true` at the very start or end of the range is empty project time with no audio (before the first event or after the last). Leave it out of the proposal unless the user wants it: cutting it changes nothing they can hear.

### 3. Propose

Show a short table: number, start and end (project time, `h:mm:ss.mmm`), duration, and the total time that would be removed. Leave out silences that overlap a protected range of the profile, and say which.

### 4. Preview

No preview file: a cut is checked by its dry run (step 6), and the user can listen in Cubase after each one and undo it. Offer to stop after the first cut so they can listen before the rest.

### 5. Approve

Ask whether to cut all of them, some (by number) or none. **Never cut without an explicit yes.** If there are many, show them all anyway (page with `offset` and `limit` if needed); do not decide on the user's behalf.

### 6. Apply

Cut from the end to the start. Cutting a span moves everything after it earlier, so cut the **last** silence first: the earlier positions are then still valid.

1. Do a dry run of the first cut (the latest one): `cubase_edit_range` with `start`, `end` (the `start_seconds` and `end_seconds` of the silence), `action: "delete_time"`, `verify_track` set to a track with audio in the range (the analyzed track, or the main voice), `dry_run: true`. If it reports a problem, stop and explain.
2. Apply the agreed cuts one by one, latest first, with `dry_run: false` and the same `verify_track`. Tell the user the progress ("3 of 7").
3. Stop at the first error and report what was already cut. **Never repeat a cut after a `TIMEOUT`**: its result is unknown; ask the user to look at the project, or read the track's edges again before doing anything else.

### 7. Verify

Every cut was checked by `verify_track` (the edges of that track before and after). If the user wants, export the same range again and analyze it with the same values: the cut silences must be gone and the total shorter by the time removed.

## Safety

- Do not cut anything the user has not approved in this conversation.
- Do not leave a track soloed: use `solo` in `cubase_export_mix`, and `cancel` if the export is abandoned.
- Do not retry a write after a timeout.
- Do not save the project unless asked.
- Do not analyze files the user did not export for this purpose.
- Do not cut a span that overlaps a protected range of the episode profile.

## Outputs

Say how many cuts were made and how much time was removed. Explain how to undo: **Edit > Undo** in Cubase, once per cut (more if a cut reported `undo_steps`). The project is **not** saved; save only if the user asks, with `cubase_save_project`.

The exported file stays in the project's `Mixdown` folder; tell the user its name so they can delete it if they want. If the episode profile has protected ranges after a cut, they are now earlier by the time cut before them: tell the user, since the profile is not updated by this skill.

## Ownership

This skill creates no tracks, plugins or markers, so it records nothing in `state.json`. The cuts change the user's own events; they are undone in Cubase, not by this skill. Its own files are the export in `Mixdown` and the cached analysis in `Trackwright/analysis/` (when the workspace exists).
