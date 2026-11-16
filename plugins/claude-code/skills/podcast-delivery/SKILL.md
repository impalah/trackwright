---
name: podcast-delivery
description: Bring a finished podcast episode to a platform's delivery spec in Cubase - measure the mix, set the Stereo Out fader to reach the target loudness (Apple Podcasts -16 LUFS, or the show's own target), add a limiter after the fader only when the true-peak ceiling needs it, then export the delivery file (MP3 or AAC) with the user and check that file itself. Use when the user asks to master, normalize, deliver, prepare or export an episode for Apple Podcasts, Spotify, YouTube, iVoox or another platform, or to fix the loudness or peaks that podcast-final-qc reported. At most three measure-and-adjust rounds; nothing is changed without approval.
license: AGPL-3.0-or-later
compatibility: Needs the Trackwright MCP server with Cubase open, [writes] enabled = true and [analysis] enabled = true in ~/.config/trackwright/config.toml. Recording what it inserted needs [workspace] enabled = true.
metadata:
  author: impalah
  project: https://github.com/impalah/trackwright
---

# Podcast delivery

Take the episode's mix to what a platform asks: an integrated loudness (for example Apple's −16 LUFS ± 1) and a true-peak ceiling (Apple's −1 dBTP), in the format it accepts. The level is set with the **Stereo Out fader**, which moves the loudness by exactly its gain; a **limiter after the fader** (Stereo Out slot 7 or 8) is added only when the peaks would pass the ceiling. `cubase_delivery_plan` computes both from a master export; the delivered file is always measured itself, because the MP3 encoding raises the peaks (about 0.8 dB in TW-1612).

Speak to the user in their language and keep them informed; they are in front of Cubase.

## Requires

`cubase_status`:

- `connected` false: ask the user to open Cubase and check the Trackwright surface in the MIDI Remote tab.
- `writes_enabled` false or `analysis_enabled` false: the fader cannot be set or nothing can be measured. Explain which key is needed in `~/.config/trackwright/config.toml` and stop.
- `allowed_tracks` not empty: Stereo Out must be in it, since the fader and the limiter are on it.
- `workspace_enabled` false: the job can be done, but the limiter cannot be recorded as this skill's and the report cannot be saved; say so.

## Inputs

- **The target:** one delivery profile (`cubase_profile`, action `resolve`, gives the episode's `delivery.targets` and their values with sources). With several targets, deliver for the one that publishes a loudness and a ceiling (today Apple), and say which values the others do not publish. Without targets, ask (`cubase_profile`, action `delivery`, lists them).
- **The format:** MP3 unless the user wants another the target accepts; the bit rate inside what the profile publishes (for Apple's RSS feed, 128 kbps for stereo is inside its 128–256 range), chosen by the user in Cubase's dialog.
- **The range:** the whole episode, from its start to its end (the user's word, or the extent `podcast-session-audit` found).
- **If `podcast-final-qc` already ran:** its failures are the reason for this job; start from them.

## Workflow

### 1. Inspect

- `cubase_list_tracks`: nothing must be **soloed** (a solo would leave tracks out of the master) and the muted tracks must be the intended ones (roles from the profile help: a muted `voice` is suspicious).
- `cubase_list_inserts` on Stereo Out: what is in slots 1–6 (before the fader) and 7–8 (after it).
- `cubase_workspace` (action `status`): a `plugin` item of `podcast-delivery` on Stereo Out is a limiter this skill inserted before: reuse it.
- `cubase_list_parameters` on Stereo Out with `target: "channel"` and `filter` set to the volume's title: the fader's tag (1025) and its title in Cubase's language (for example `Volumen`).

### 2. Analyze

1. Export the master: `cubase_export_mix` with `phase: "start"`, the range, no `solo`, `dry_run: false`. Ask for **WAV, 32-bit float**, the project's sample rate, a name like `delivery-master-1`. Confirm with `phase: "confirm"` (or `cancel`).
2. `cubase_delivery_plan` with the master's `file`, the `target` and the `codec` to deliver.
3. Name the master the numbers come from; if a note says the project was saved after it, ask whether the mix changed.

### 3. Propose

Explain the plan in plain words, with its numbers:

- the master's loudness and true peak, and the target's values with their source;
- the fader: from `fader_now_db` to `fader_db` (`gain_db`);
- whether a limiter is needed: when `limiter` is true, a Brickwall Limiter (or the limiter the user prefers) in slot `limiter_slot` with its threshold at `threshold_db`, which keeps the delivered file's true peak under the ceiling after the encoding raises it;
- every warning: a target the fader cannot reach (`reachable` false: the tracks or the voices' level must come up first, for example with dialogue leveling), heavy limiting (better compression or leveling upstream), the loudness the limiting will take (a second round).

If `reachable` is false or the limiting is heavy, recommend fixing that first and ask whether to go on anyway.

### 4. Preview

Nothing can be heard before the change, and the change is the fader and a limiter, both easy to undo. After applying (step 6) offer to play from the loudest moment of the master (`cubase_final_qc` on the master gives it in `moments`; `cubase_set_position` puts the cursor there) so the user hears whether the limiter is audible.

### 5. Approve

Ask for an explicit yes to the plan: the fader value, and the limiter with its slot and threshold.

### 6. Apply

1. The fader: `cubase_set_parameter` on Stereo Out, `target: "channel"`, tag 1025, `unit: "plain"`, `value` = `fader_db`, `expect_title` = the title found in step 1; dry run, then `dry_run: false`. Note the value before (`before`).
2. Only if `limiter` is true:
   - if `limiter_in_slot` is empty, find the limiter plugin installed (`cubase_list_available_plugins` on Stereo Out, slot `limiter_slot`, `filter: "limiter"`; do not assume its uid) and `cubase_insert_plugin` it in `limiter_slot` (dry run, then apply);
   - if a limiter is already there and is not recorded as this skill's, it is the user's: ask before changing it;
   - `cubase_list_parameters` on `insert:<slot>`: find the threshold (or ceiling) by title, check it is in dB, and `cubase_set_parameter` it to `threshold_db` with `unit: "plain"` and `expect_title`; check that the plugin is not bypassed.
3. Record what was inserted (`cubase_workspace`, `action: "record"`, `kind: "plugin"`, `key: "<Stereo Out uid>/slot:<slot>"`, `skill: "podcast-delivery"`, a `run_id`, `details` with the plugin, the threshold, the target, and the fader's value before and after).

### 7. Verify

Round by round, **three rounds at most**:

1. Export the master again (WAV, a new name such as `delivery-master-2`) and `cubase_delivery_plan` on it. If its loudness is within the tolerance and its `predicted_true_peak` is under the ceiling, go on; otherwise propose the new fader (and threshold), apply after a yes, and repeat. The plan reads the fader as it is now, so its `gain_db` is the correction.
2. Export the **delivery file** with the user: `cubase_export_mix` with the same range; the user picks the format and bit rate (for example MP3 128 kbps). Confirm.
3. `cubase_final_qc` on the delivered file with `targets` = the target, `expected_seconds` = the range length. If the true peak passes the ceiling, lower the limiter's threshold by the excess plus 0.1 dB (a limiter is needed now even if the plan had none) and export the delivery file again: this counts as a round.
4. After three rounds without meeting the spec, **stop**: say what each round measured and why it does not converge (heavy limiting eating loudness, a ceiling the encoder keeps passing), and what to do instead.

When it passes, offer to save the report (`cubase_final_qc` with `report: true`, then record it as in `podcast-final-qc`).

## Safety

- Do not change anything before the user approves the plan; do not change the fader or the limiter beyond the approved values without asking again.
- Do not put a ceiling in slots 1–6 of Stereo Out: they are before the fader (TW-1612).
- Do not change a limiter or plugin that is not recorded as this skill's without asking.
- Do not run more than three rounds.
- Do not retry a write after a timeout: read the parameter back.
- Do not save the project unless asked.
- Do not report a value the platform does not publish as met.

## Outputs

- The delivered file (in `Mixdown`), measured, with the verdict per target.
- What changed in the project: the Stereo Out fader (from and to) and, if any, the limiter (slot, plugin, threshold). How to undo: put the fader back, Bypass the limiter or remove it in Cubase (Trackwright cannot remove plugins), or Edit > Undo.
- The master exports in `Mixdown` (the user may delete them) and, if approved, the report in `Trackwright/reports/`.
- The project is **not** saved.

## Ownership

The limiter this skill inserts on Stereo Out is its own, recorded as a `plugin` item keyed `<Stereo Out uid>/slot:<slot>`; a later run adjusts that one instead of inserting another. The Stereo Out fader is the user's control: the skill sets it only with approval and records the value it found in the item's `details`, so it can be put back. Any other plugin on Stereo Out, including a limiter in slots 1–6, is the user's.
