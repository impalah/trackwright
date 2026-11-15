---
name: podcast-session-audit
description: Take stock of a podcast or spoken-word session in the open Cubase project before working on it - every track with its type, mute, solo, output, fader, inserts and where its audio starts and ends, the episode's extent, leftovers such as a forgotten solo - and record in the episode profile the track roles and protected ranges the user confirms. Use when the user asks to audit, review or inspect a session or episode, to check the project before mixing or delivering, or to set up the episode profile. Read-only; only the profile is written, after the user approves it.
license: AGPL-3.0-or-later
compatibility: Needs the Trackwright MCP server with Cubase open. Writing the episode profile needs [workspace] enabled = true in ~/.config/trackwright/config.toml.
metadata:
  author: impalah
  project: https://github.com/impalah/trackwright
---

# Podcast session audit

Before cutting, mixing or delivering an episode, know what is in the project: which tracks there are, what each one is for, what is muted, soloed or routed nowhere, which plugins are on them, and where the audio starts and ends. The other podcast skills read the result from the **episode profile** (`Trackwright/profile.toml`): the track roles and the ranges they must not touch.

This skill changes nothing in the Cubase project. The only thing it writes is the episode profile, and only what the user confirmed.

Speak to the user in their language and keep them informed; they are in front of Cubase.

## Requires

`cubase_status`:

- `connected` false: ask the user to open Cubase and check the Trackwright surface in the MIDI Remote tab.
- `workspace_enabled` false: the audit still runs, but the profile cannot be written. Say that `[workspace] enabled = true` in `~/.config/trackwright/config.toml` is needed for that, and offer the audit as a report only.
- Writes (`writes_enabled`) and audio analysis are not needed: nothing is changed or measured.
- The transport must be stopped: probing a track's events moves the cursor (it is put back).

## Inputs

- **The project:** the one open in Cubase. `cubase_get_project` gives its folder (`project_folders`); if it is unknown or there are several, say so: the profile cannot be written then.
- **The show:** `cubase_profile` (action `shows`) lists the show profiles; ask which show this episode belongs to, if any. With a show, its `track_roles` (by track name) are proposals to confirm, not facts.
- **The roles:** for each track, the user says whether it is a `voice`, `music`, `effects`, `reference` or `other` track. **Never infer a role** from a track's name, from it being stereo or mono, or from its level: ask, offering the show's role as the default when there is one.
- **Protected ranges:** spans no skill may change (an ad read, a legal disclaimer, a sponsor's segment), in seconds with a short note. The API cannot read markers, so the user gives the times (they can read them from Cubase's marker window).

## Workflow

### 1. Inspect

1. `cubase_get_project`: transport stopped, project folder, cycle.
2. `cubase_list_tracks` (page with `offset` and `limit` if `total` is larger): name, `uid`, type, fader (`volume.display`), `mute`, `solo`, `output`.
3. For each audio track (types `AudioChannel` and similar; not Stereo Out, groups or FX): `cubase_list_inserts` (the plugins in its slots) and `cubase_track_edges` (where its events start and end; with many events, raise `limit` or probe in windows with `start` and `end`).
4. What Trackwright already knows: `cubase_profile` (action `resolve`): the current episode profile (`episode`), the show, the protected ranges; and `cubase_workspace` (action `status`): what skills created (`items`, for example a render track that replaces another).

### 2. Analyze

Build the inventory, without measuring audio:

- **Per track:** type, output, fader, mute, solo, inserts (plugin names, slot), first and last edge, number of edges (two per separate event; adjacent events share an edge).
- **The episode's extent:** from the earliest first edge to the latest last edge over the audio tracks. If some track's probe was not `complete`, the extent is a lower bound: say so.
- **Things to point out** (questions, not faults; the user decides):
  - a track **soloed**: a solo left over from an earlier job silences everything else in an export;
  - a track **muted** that has events: intended (an alternative take, a muted original replaced by a render) or forgotten?
  - a track whose output is no bus (`Sin bus`, "No Bus" in English): it is heard nowhere;
  - a fader at `-oo` (silent) or far from the others;
  - an audio track **with no edges**: empty, or one event covering it all (see the notes of `cubase_track_edges`);
  - an audio track with an **odd number of edges**: probably an event that starts exactly at 0 s, whose start the probe cannot see (its first edge is then that event's end); overlapping or adjacent events can also cause it, so say "probably";
  - a track that `state.json` says a skill created, and the track it replaces;
  - a track whose name in the show profile has a role but which is missing from the project, or the reverse.

### 3. Propose

Show the inventory as a table (one row per track) and the points above. Then the proposed episode profile:

- `show`: the show the user named (or none);
- `track_roles`: one line per track with the role the user gave, or the show's role marked "from the show, confirm";
- `protected`: the ranges the user gave;
- whatever the episode profile already had and the user keeps.

Add the **capability report**: what this audit cannot see, so the user does not take silence for a clean bill of health:

- automation curves (volume, pan, plugin parameters) and whether automation is read;
- event gain (clip gain), fades and crossfades inside events, and silence inside an event;
- the markers themselves (names and positions) and the events' names and source files;
- an event that starts exactly at 0 s (only its end is seen);
- whether a plugin is bypassed or switched off (`cubase_list_inserts` lists what is loaded, not its state), plugin presets by name, and plugins' settings unless asked for (`cubase_list_parameters`);
- routing beyond each track's output (sends' destinations, side-chains).

### 4. Preview

Nothing in the project changes, so there is nothing to hear. The preview is the file itself: `cubase_profile` with `action: "write_episode"`, the proposed `data` and `dry_run: true` returns `before` and `after` (the TOML as it would be written). Show `after` to the user.

Build `data` from `episode` of the `resolve` answer (the episode layer as stored) plus the confirmed changes, **never** from `settings` (the merged result): that would copy the show's and Trackwright's defaults into the episode, and later changes to the show would no longer reach it.

### 5. Approve

Ask for an explicit yes to write the profile as shown. A partial yes ("roles yes, but not the range") means a new dry run with the agreed part.

### 6. Apply

1. If the workspace does not exist (`cubase_workspace` `status` says `absent`): `cubase_workspace` with `action: "init"`, dry run, then `dry_run: false` (it creates only `Trackwright/` and its subfolders).
2. `cubase_profile` with `action: "write_episode"`, the same `data`, `dry_run: false`.

### 7. Verify

`cubase_profile` (action `resolve`) again: every confirmed role must come from `episode` in `origins`, and the protected ranges must be listed. Tell the user where the file is (`episode_path`) and that they can edit it by hand.

## Safety

- Do not change anything in the Cubase project: no mute, solo, fader, insert or edit, even to "fix" a point raised; offer the fix and let the user ask for it (or another skill do it).
- Do not infer a track's role; ask.
- Do not write the profile without an explicit yes to what was shown.
- Do not write `settings` into the episode profile; start from `episode`.
- Do not read or measure audio: the audit needs no export.
- Do not save the project.

## Outputs

- The inventory and the capability report, in the conversation.
- The episode profile `Trackwright/profile.toml`, if the user approved it: track roles, protected ranges, the show. Every other podcast skill reads it through `cubase_profile`.
- The cursor and the track selection are where they were (the edge probe puts them back).

## Ownership

The audit creates nothing in the project and records nothing in `state.json`. The episode profile is the **user's** document: the skill writes it only with their approval and keeps everything already in it that the user did not change. The `Trackwright/` folder, if the skill created it, is shared by every skill.
