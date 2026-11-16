# E16 — Podcast production skills

**English** · [Español](E16-podcast-production.es.md)

**Epic status: pending.** Origin: the brainstorm in `01.podcast.production.ideas.md` (outside the repository, 2026-11-15), assessed against what Trackwright and Cubase Elements can really do. Goal: a set of Claude Code skills that each complete a production job (analyze, propose, apply within limits, verify), first for podcasts and later for other spoken-word productions (audiobooks, voice-over, video dialogue).

## Decisions (2026-11-15, with the user)

- **Cubase Elements 15 only.** The brainstorm assumed Artist 15 (SuperVision, sidechain, time stretch, VocalChain). Everything is designed and verified on Elements; Artist or Pro features may appear only as optional paths marked untested.
- **Offline render first, then Cubase.** The API cannot write automation points, change event gain, read audio or change routing. Ducking, dialogue leveling, music beds, room tone and fades are therefore done **offline**: export the stem (solo + Stereo Out, aligned to the sample, TW-1501), process it in Python, **import the result as a new track** and mute the original. Doing it inside Cubase (real-time automation recording, sidechain set up by the user) comes later, where editability is worth the playback time.
- **Files in a `Trackwright/` subfolder of each project.** Renders, analyses, previews, the episode profile and the record of what each skill created live there; show profiles shared by several episodes go to `~/.config/trackwright/shows/`. Writing there is a new permission (TW-1602).
- **Local transcription, late.** Editorial review (repetitions, false starts, filler words, recording cues) uses a local Whisper model installed with uv, in the last phase. Audio never leaves the machine.
- **Delivery targets:** Apple Podcasts (RSS), Spotify, YouTube, iVoox; other hosts when the user names them. Every number in a delivery profile is taken from the platform's published specification, cited with its URL and retrieval date; without a source, no profile.
- **Test material:** whole episodes the user points to, read-only; results recorded without the audio. Synthetic signals for unit tests (the gate test showed how they can hide bugs, so never only synthetic).
- **Order:** the brainstorm's (final QC, delivery, ducking, music bed, dialogue leveling, edit smoothing, voice tone, edit review), with session audit early because it feeds the rest; foundations first.
- **Library:** the user has none yet; the epic defines its format (TW-1620).

## What Trackwright can and cannot do (facts this epic builds on)

- **Can:** list tracks, inserts and plugins; read and set any plugin or channel parameter in real units (with read-back); insert plugins; mute, solo, volume, pan; markers (create, jump); range edits in seconds on all tracks (`delete_time`…) or delete on one track; event edges of a track (probing); export Stereo Out between locators with the user (dialog); import a file at a position with the user (dialog); play and stop; record automation by playing (volume, pan, sends 1–4, channel EQ, pre-filter, insert slots 1–2); analyze an exported file (noise floor, levels, silences; TW-1503).
- **Cannot (verified):** read audio, events, event gain, fades, automation curves or markers as data; change routing (including sidechain sources); complete dialogs; remove plugins; export more than Stereo Out in Elements (no per-channel or batch export: one dialog per stem); Cubase commands for fades, repeating or duplicating events are not bound by the script today.

## Viability of the brainstorm's ideas

✅ viable with what exists · 🧪 needs an experiment first · 🔧 needs new server capability · 👤 a step only the user can do · ⛔ not possible through the API (the alternative is given)

| Idea | Verdict | How |
|---|---|---|
| `podcast-final-qc` | ✅🔧 | Read-only: export, then measure (loudness and true peak are new, TW-1603). "Excluded tracks are not in the render" cannot be proven from a mixdown: it becomes a checklist item, or a comparison of stems. |
| `podcast-delivery` | ✅🧪👤 | Loudness measured in Python (BS.1770, no SuperVision or FFmpeg needed); gain on Stereo Out's fader; limiter on Stereo Out if the true peak would exceed the ceiling (Brickwall Limiter, Maximizer exist in Elements; inserting on Stereo Out to be verified); the user exports MP3 in the dialog; the delivered file is decoded and measured again (MP3 by soundfile; AAC by macOS `afconvert`). |
| Ducking by sidechain (option 1) | ⛔👤🧪 | Routing a sidechain is not reachable by the API. At most a guided setup the user completes, if Elements' Compressor even offers a side-chain input (TW-1601). |
| Ducking by envelope (option 2) | ✅🔧 | Offline: voice activity on the voice stem, envelope planner (pre-roll, hold, merged gaps, recovery, protected zones, per-region overrides), rendered ducked music imported as a new track. "Make it less obvious / don't bring it up between those two phrases" edits the stored plan, not the whole mix. |
| Respect existing automation | ⛔ → ✅ | Automation cannot be read. The offline path never touches it; a later Cubase-side mode writes only a parameter the skill owns. |
| `podcast-music-bed` (loop region, extend, ending) | ✅🔧🧪 | Offline: beat and repetition analysis proposes loop regions, the user approves one, Python renders the bed to the length needed with seams on beats and short crossfades, keeps the ending, renders previews of each seam and leaves markers at doubtful ones. |
| Time stretch | ⛔ | Not reachable through the API; offline stretching is out of this epic (`allow_time_stretch: false`). |
| `podcast-session-audit` | ✅ partial | Tracks, types, mute/solo, outputs, inserts, event edges per track, capability report. Cannot see automation, event gain or the user's markers; roles are confirmed by the user and stored in the episode profile; protected ranges are stored there too (markers cannot be read). |
| `podcast-edit-review` | ✅🔧 late | Pauses and level jumps without transcription; repetitions, false starts, filler words and recording cues need the local transcript (TW-1630). Output: a decision list; nothing is cut without approval; approved cuts through `cubase_edit_range` on all tracks, latest first. |
| `podcast-edit-smoothing` | ✅🧪 | Room tone extracted from quiet passages of the same voice and imported to fill gaps; fades at cut points only if the needed Cubase commands can be bound (TW-1626), otherwise rendered offline; a single preview file of all cuts. |
| `podcast-sync-sources` | ✅ diagnostic | Cross-correlation of two stems at several points: fixed offset versus drift. Moving events is not possible through the API: the correction is a manual instruction (or an offline render, later). Audio Alignment (Pro) is not used. |
| `podcast-dialogue-leveling` | ✅🔧 | Speech-gated loudness per region and per voice, bounded gains (no per-phrase normalization), leveled stem rendered and imported. Event gain cannot be set through the API. |
| `podcast-voice-cleanup` | ✅🔧 diagnostic first | Hum, broadband noise, plosives, mouth clicks, sibilance and reverb measured offline; treated only with plugins found installed (StudioEQ notches for hum, Gate, DeEsser, channel high-pass); otherwise "detected, needs review or another tool". |
| `podcast-voice-tone` | ✅🧪 | Objectives, not presets: rumble, resonances, body, dynamics, sibilance, with StudioEQ, Compressor and DeEsser; A/B by playing a cycle range in Cubase with Bypass toggled and loudness matched. VocalChain is not in Elements. |
| `podcast-section-transitions` | ✅👤 | An approved stinger placed at a marker or time (import at a position), never over the last phrase (voice activity), fades rendered offline. |
| `podcast-sound-effects` | ✅🔧👤 | From a local licensed library only (TW-1620); placement and gain as above; provenance and license recorded per episode. No downloads. |
| `podcast-spatial-balance` | ✅ | Pan read and set per channel; voice placement policy in the show profile; mono check from an export folded down in Python, with a mono preview file. |
| Analysis services (loudness, voice activity, regions, render comparison, previews) | 🔧 | New modules in `trackwright.analysis` (pure, tested), reached through MCP tools. |
| Transcription with timestamps | 🔧 late | Local Whisper, optional extra. |
| Analysis tied to an audio version | 🔧 | Every analysis records the file and its hash; a cache in `Trackwright/analysis/`. |
| Skill contract (requires, inputs, workflow, safety, outputs) and ownership | 🔧 | A common contract checked by the plugin tests; ownership recorded in `Trackwright/state.json` so a re-run updates its own tracks and plugins instead of piling them up. |
| Show profile | 🔧 | `~/.config/trackwright/shows/<show>.toml` plus `Trackwright/profile.toml` per episode. |
| "Produce a whole podcast" | ⛔ | Out of scope, as the brainstorm itself says. |

## Architecture shared by the skills

```text
analysis (trackwright.analysis, Python, pure)   → measurements, voice regions, candidate problems, renders
skills (plugins/claude-code/skills/podcast-*)   → goals, questions, plan, approval, report
MCP tools (Trackwright → Cubase)                 → inspect, export/import with the user, apply, verify
```

- **Stems:** one export per stem (Elements has no per-channel or batch export), with the track or tracks soloed and the solo restored afterwards. Skills reuse cached analyses to avoid asking for the same export twice.
- **Render and re-import:** processed audio is written to `Trackwright/renders/` as 32-bit float WAV at the project's rate, with a provenance file (source export and its hash, processing, parameters, skill and run). It is imported on a new track at the range start; the original is muted, never deleted. Alignment is checked with the event edges.
- **`Trackwright/` layout:** `renders/`, `previews/`, `analysis/` (cache keyed by file hash and parameters), `profile.toml` (episode: track roles, protected ranges, overrides), `state.json` (what each skill created: tracks, plugins and their slots, renders), `reports/` (QC and delivery reports).
- **Ownership:** a skill only updates or replaces what `state.json` says it created; anything else is the user's.
- **Previews:** short files rendered offline (seams, first words, cut points) and, for processing done in Cubase, a cycle range played with Bypass toggled.
- **Safety, as in E15:** dry run and approval before every change, no saving unless asked, no retry after a timeout, solo always restored, nothing read beyond the exports and episodes the user points to.

## Rules for the whole epic

The same as E14 and E15: a failing test before each fix; documentation in English and Spanish; results observed in Cubase in the verification log; experiments in `experiments/twNNNN/` with a README in both languages. Real episodes are read only where the user points, and only measurements are recorded. Platform numbers are cited, never remembered.

## Phase 1 — Foundations

### TW-1601 Experiment: what Cubase Elements offers for these skills

- **Status:** done (2026-11-15): see `experiments/tw1601/` and the verification log. Limiter on Stereo Out: yes; side-chain: the button exists, the source is the user's; automation ~0.1 s late, quantized to ~110 ms; PreGain automatable; fade commands found ("Ajustar fundidos al rango", crossfade, duplicate, repeat), none bound yet; MP3 decodable, no AAC export; renders import in place; cycle playback with Bypass for A/B works without clicks
- **Questions:**
  1. Can plugins be inserted on Stereo Out and their parameters set (Brickwall Limiter, Maximizer: ceiling, threshold)?
  2. Does Elements' Compressor (or VSTDynamics) offer a side-chain input at all, and which parameters show through the API? (Routing stays the user's.)
  3. Automation recording precision: offset between the requested and the written start and end of a curve (for a later Cubase-side ducking mode).
  4. Which channel parameters are automatable besides volume and pan (pre-gain?), to give a Cubase-side mode a parameter it owns.
  5. Which Cubase key commands would give fades at the cursor, event fades and repeating events, and what binding them would need (a script change: permission, install, Cubase restart). Findings only; no script change here.
  6. MP3 options in the export dialog; whether soundfile decodes the MP3 Cubase writes, and `afconvert` an AAC.
  7. Importing a WAV written by Trackwright into `Trackwright/renders/`: does Cubase copy it into `Audio/`, and is it placed to the sample?
  8. `transport.start`/`stop` with a cycle range while toggling a plugin's Bypass, for A/B listening.
- **Result:** verification log; decisions recorded in the issues that depend on each answer.

### TW-1602 The `Trackwright/` project workspace

- **Status:** done (2026-11-15): `trackwright/workspace.py` (layout, paths that cannot escape, atomic writes, `State`/`OwnedItem` for `state.json`, `EpisodeProfile` for `profile.toml`, written with the new dependency `tomli-w`), `[workspace] enabled` (default off, `WORKSPACE_DISABLED`, checked before anything else in `init`), tool `cubase_workspace` (`status`, `init`), `setup --workspace`, `cubase_status.workspace_enabled`, `doctor`; configuration chapter, tools chapter and SECURITY. Tests in `tests/unit/test_workspace.py` and the contract test. Live: `status` found the test project's folder and the incomplete `Trackwright/` left by TW-1601; `init` refused with the user's configuration (writing not enabled), so creating it live is still to be seen
- **Scope:** the layout above; a `[workspace] enabled` switch (off by default, like `[writes]` and `[analysis]`), shown in `cubase_status` and `doctor`; Trackwright creates only `Trackwright/` inside the project folder found by `project_folder()`, never another file; a tool to report and create it (`cubase_workspace`); `state.json` (ownership) and `profile.toml` (episode) with pydantic models; SECURITY and the configuration chapter updated.
- **Tests:** policy, layout, ownership records, refusal outside the project folder.

### TW-1603 Loudness and true peak

- **Status:** done (2026-11-15): `trackwright/analysis/loudness.py` (K-weighting for any rate, gated integrated loudness, momentary and short-term maxima, LRA, sample and 4x true peak, read in blocks) with scipy as a new dependency (`lfilter`, `resample_poly`; pure numpy would need a per-sample loop); tool `cubase_measure_loudness`; AAC decoded through macOS `afconvert` (`decoded()`, also used by `cubase_analyze_audio`). Tests: BS.1770 coefficient tables at 48 kHz, EBU Tech 3341 cases 1-4 (±0.1 LU), Tech 3342 cases 1-3 (±1 LU), true peak between samples, mono, silence, pyloudnorm at 44.1 and 48 kHz (±0.1 LU), MP3 and AAC. On nine real exports of the test project it agrees with pyloudnorm within 0.07 LU; 140 s measured in 0.6 s
- **Scope:** ITU-R BS.1770 / EBU R128 measurements in `trackwright.analysis`: integrated loudness (gated), short-term and momentary maxima, loudness range, sample peak and true peak (4× oversampling). Exposed through the analysis tool or a new `cubase_measure_loudness`.
- **Validation:** conformance signals generated in the tests (as described in EBU Tech 3341 and 3342; the documents cited) and comparison with `pyloudnorm` as a development dependency only; MP3 and AAC deliveries decoded (soundfile, `afconvert`) and measured.

### TW-1604 Voice activity detection

- **Status:** done (2026-11-15): `trackwright/analysis/speech.py` and tool `cubase_detect_speech`. Validated on a real episode (46 min, one voice, `Pod Mic` exported alone): 2.5 s for the whole episode; floor −61.8 dB, typical speech −13.1 dB. A 0.37 s noise at −52 dB inside a pause was taken for speech and split the pause; fixed with `faint_db` (fragments 30 dB below the typical speech level dropped **before** joining: dropping them after was not enough, they had already bridged pauses), which dropped 108 such fragments and revealed 35 pauses over 1 s instead of hiding them. The user listened to the first 10 minutes with a tone marking detected speech: starts and ends correct. Breaths and false positives were not commented on
- **Scope:** speech regions on a voice stem: energy against the noise floor plus a speech-band criterion, hysteresis, minimum region and gap; regions with level and confidence. Each voice is on its own track, so no speaker separation is needed; one track with several voices is out of scope.
- **Validation:** on whole episodes the user points to, compared with a few minutes they mark by hand (cycle ranges or a list of times); the synthetic syllable signal of TW-1507 in the unit tests.

### TW-1605 Stem export with the solo restored

- **Status:** done (2026-11-15): `cubase_export_mix` gained `solo` (track selectors, `allowed_tracks` respected) and a `cancel` phase; `start` remembers every solo, clears the others and solos the given tracks; `confirm` and `cancel` put every solo back, and any failure before the dialog opens restores them at once. Both skills use it. Tests in `tests/unit/test_export_solo_tw1605.py`. Live on the test project: an export with `confirm` and a closed dialog with `cancel`, both with the solos back as before
- **Scope:** one step to export a stem: solo the given tracks (remembering the previous solo state), set the range, open the dialog; on confirm, restore the solo state exactly, even if the export failed. Today each skill does this by hand and could leave a track soloed. Either new parameters of `cubase_export_mix` or a new tool.
- **Tests:** solo state restored in every path; verified in Cubase.

### TW-1606 Render and re-import

- **Status:** done (2026-11-15), verified in Cubase (a −6.02 dB render of a track imported on a new track and exported alone equals the source × 0.5 to −182 dB, no offset; see the verification log): `trackwright/renders.py` (32-bit float WAV written block by block through a temporary file, provenance `<name>.json` with the source's and the render's SHA-256, names never reused), tool `cubase_render` (`render` with the process `gain`, `list` with the problems found and the track each render went to), and `cubase_import_audio` aware of renders (position checked against the provenance, the replaced track and a changed render refused, ownership of the render and its track recorded in `state.json`, an earlier render track of the same skill pointed out; an import at position 0 proved by its new end edge, since the probe cannot see an edge at the project start). Tests in `tests/unit/test_render_tw1606.py`
- **Scope:** write processed audio to `Trackwright/renders/` with its provenance file; import it on a new track at the range start with the user (`cubase_import_audio`); mute the original; check alignment with the event edges; record ownership. A re-run replaces only its own render track (removing it needs the user's confirmation, as with `cubase_remove_selected_track`).
- **Tests:** provenance, alignment checks; verified in Cubase with a known signal.

### TW-1607 Show and delivery profiles

- **Status:** done (2026-11-15), checked live on the test project (see the verification log); a show profile for the user's podcast waits for the user's roles and targets: `trackwright/profiles.py` (settings for show and episode, `resolve` with the origin of every value, `DeliveryProfile` refusing a value no source covers), `delivery.toml` (Apple, Spotify, YouTube, iVoox, read on 2026-11-15 from the platforms' pages: Apple −16 LUFS ±1 and −1 dBTP; Spotify, YouTube and iVoox publish no loudness or true peak for podcasts, Spotify's −14 LUFS being for music; iVoox only from a 2022 blog, its help centre unreadable), `EpisodeProfile` with the same sections, tool `cubase_profile` (`resolve`, `shows`, `delivery`, `write_show`, `write_episode`). Tests in `tests/unit/test_profiles_tw1607.py`
- **Scope:** pydantic schema for a show profile (`~/.config/trackwright/shows/<show>.toml`: track roles by name, voices, approved music, ducking style, editing criteria, delivery profiles) and an episode profile (`Trackwright/profile.toml`), resolved built-in < show < episode; tools to read them and to write them after approval.
- **Track identity (seen in TW-1604):** track uids are not unique across projects made from the same template (the user's episode and the test project share one), so a show profile names tracks by name; uids only within one project (`state.json`).
- **Delivery profiles (research):** Apple Podcasts (RSS), Spotify, YouTube and iVoox, each with loudness target and tolerance, true peak ceiling, codec, channels, sample rate and bitrate **only as published by the platform**, with the URL and the date read. A platform without a published number gets none (for example, a platform that normalizes on its own may only get a ceiling). Other hosts when the user names them.

### TW-1608 Analyses tied to an audio version

- **Status:** done (2026-11-15), checked live (see the verification log; on a 1.07 GB episode the hash takes 0.39 s and the loudness 12.25 s): `trackwright/analysis/cache.py` (file identity with SHA-256 remembered in `hashes.json` by path, size and mtime; one JSON per result keyed by analysis, hash and parameters) and the three analysis tools returning `source` (file, hash, project range, `project_saved_after` from the folder's `.cpr` times) and `cache` (`hit`, `stored`, `off`); both skills name the export and ask for a new one when the project was saved after it. Tests in `tests/unit/test_analysis_cache_tw1608.py`
- **Scope:** every analysis result records the file, its hash, its project range and the parameters; cached in `Trackwright/analysis/`; a skill states which export its numbers come from and asks for a new export when the project changed after it (cuts, processing, automation).

### TW-1609 Common skill contract

- **Status:** done (2026-11-15): the contract in `docs/manual/07-skill-contract.md` (sections Requires, Inputs, Workflow with the seven phases, Safety, Outputs, Ownership), checked by `contract_problems` in `tests/unit/test_plugin.py`; `cubase_workspace` gained `record` and `forget` (and `status` lists the items) so skills can own what they create; `podcast-silence-trim` (now using the profile's editing values and never cutting a protected range) and `noise-gate` (recording its gate as a `plugin` item and adjusting it on a re-run) rewritten to the contract
- **Scope:** every podcast skill has the same sections (Requires, Inputs, Workflow: inspect, analyze, propose, preview, approve, apply, verify; Safety; Outputs; Ownership); `tests/unit/test_plugin.py` checks them; a shared conventions document in the manual. Existing skills (`podcast-silence-trim`, `noise-gate`) brought in line.

## Phase 2 — Session, quality control and delivery

### TW-1610 Skill `podcast-session-audit`

- **Status:** done (2026-11-15), tried live on the test project (see the verification log; a run on a real episode with the user's roles is still to come): the skill (contract of TW-1609) and the tool `cubase_track_edges` (a track's event edges and extent, cursor and selection put back); `cubase_profile resolve` now also returns `episode`, the episode layer as stored, so a skill writes the episode profile without copying the show's values into it. Tests in `tests/unit/test_track_edges_tw1610.py`
- **Scope:** inventory of tracks (type, mute, solo, output, inserts, event edges and the episode's extent), roles confirmed by the user and stored in the episode profile (never inferred from a name or from being stereo), protected ranges, and a capability report (what the API cannot see: automation, event gain, the user's markers). Read-only except the profile, after approval.

### TW-1611 Skill `podcast-final-qc`

- **Status:** done (2026-11-15), tried live on the test project (see the verification log; a run on a real episode's published file is still to come): the skill (contract of TW-1609) and the read-only tool `cubase_final_qc` (checks per target with their sources, `info` for unpublished values, warnings for long pauses, silence at the ends, level changes between 10 s sections and full scale, manual items, moments to listen to, optional JSON and Markdown report); `trackwright/analysis/qc.py` (level changes, codec, bit rate) and the short-term series kept by the loudness measurement. On the test project's 140 s MP3: Apple fails on loudness (−21.13 LUFS), Spotify's loudness and true peak are reported as not published, two long pauses and a −10.8 LU change at 2:10 are flagged. Tests in `tests/unit/test_final_qc_tw1611.py`
- **Scope:** read-only checks on the delivered file or a fresh export: opens, format, channels, sample rate, duration against the approved range; loudness and true peak against the chosen profile; long pauses; sudden level changes between sections; a list of moments to listen to. Objective checks separated from warnings; items that cannot be verified from a mixdown (excluded tracks) listed as manual. Report in `Trackwright/reports/`.

### TW-1612 Experiment: reaching a loudness target in Elements

- **Status:** done (2026-11-16): see `experiments/tw1612/` and the verification log. One round of fader gain reaches the target exactly when lowering; slots 1–6 of Stereo Out are before the fader and 7–8 after it, so a ceiling goes in slot 7 or 8; the Brickwall Limiter lets 0.24 dB of intersample peaks through with DIC on; MP3 128 kbps raises the true peak by about 0.8 dB, so a −1 dBTP MP3 needs a threshold near −2.1 dB and a measurement of the MP3 itself. Found and fixed on the way: afinfo's estimated MP3 duration was 6.3 s short on 46 minutes; export durations now come from soundfile
- **Scope:** on a whole episode: gain on Stereo Out's fader (its range), Brickwall Limiter or Maximizer on Stereo Out (ceiling, release), measured after export; how much the MP3 encoding raises the true peak; how many measure-adjust rounds are needed.

### TW-1613 Skill `podcast-delivery`

- **Status:** done (2026-11-16), run end to end on the test project (see the verification log: −17.56 LUFS master, fader +1.56 dB and a limiter at −2.1 dB in slot 7, one round, the MP3 passed Apple at −16.05 LUFS and −2.50 dBTP): the skill (contract of TW-1609, three rounds at most) and the read-only tool `cubase_delivery_plan` (fader gain from a master, predicted true peak of the delivered format, a limiter in a post-fader slot with its threshold only when the ceiling needs it, warnings for the fader's +6.02 dB range and for heavy limiting), on TW-1612's figures in `trackwright/analysis/delivery.py`; the simulator knows the Brickwall Limiter. Seen on the way: `cubase_convert_value` on Stereo Out answered with the selected track's title (added to TW-1635). Tests in `tests/unit/test_delivery_plan_tw1613.py`
- **Scope:** choose a profile, export and measure, compute whether gain alone reaches the target without breaking the ceiling (the brainstorm's −21 → −16 LUFS example), otherwise propose a limiter (and warn when the gain needed calls for dynamics processing upstream instead); apply after approval; export the master and measure; export the delivery format with the user; decode and validate the delivered file; report. At most three rounds, then stop and explain.

## Phase 3 — Music

### TW-1614 Ducking planner

- **Status:** done (2026-11-16): `trackwright/analysis/ducking.py` (pure: join, hold, no pumping, `hold`/`free`/`depth` overrides, protected ranges and `free` spans kept at full level with the whole ramps outside them, an envelope of straight lines in dB), the read-only tool `cubase_ducking_plan`, and the process `duck` of `cubase_render` (the envelope applied in project time, the specification and the voice's SHA-256 in the provenance). Tests: concrete envelopes, a Hypothesis property over random regions, protected ranges and `free` spans (continuity within 1 ms, exact depth, full level in every hole; 3,000 examples passed once), and a render of synthetic music under a synthetic voice (−12 dB exactly under the speech, 0 dB between, no jump larger than the music's own). Live use comes with TW-1615
- **Scope:** pure functions from voice regions to a gain envelope: attenuation, pre-roll before the first word, hold, merging gaps shorter than a threshold, recovery curve, protected ranges and per-region overrides ("do not bring the music up between these two phrases"); render of the ducked music. The brainstorm's values are starting points, not norms.
- **Tests:** envelopes on synthetic regions; continuity (no clicks), exact attenuation.

### TW-1615 Skill `podcast-music-ducking`

- **Status:** pending (needs TW-1605, TW-1606, TW-1614)
- **Scope:** export the voice tracks together and the music; plan; previews at first words, pauses, section changes and ends; apply by importing the ducked music and muting the original; edits in plain words change the stored plan and re-render only the affected spans. Acceptance: the voice stays clear and the recoveries do not distract, judged by the user.

### TW-1616 Experiment: ducking inside Cubase

- **Status:** pending (needs TW-1601)
- **Scope:** (a) a guided sidechain setup the user completes, if Elements' Compressor allows it; (b) the planned envelope written by real-time automation recording on a parameter the skill owns, with the precision measured. Decide whether either becomes a second mode of `podcast-music-ducking`.

### TW-1617 Loop and ending analysis

- **Status:** pending
- **Scope:** tempo and beat estimation, repeated sections (self-similarity), candidate loop regions with seam quality, loop points on beats and near zero crossings, crossfade length; detection of the ending and its tail; render of a bed of a given length that keeps the ending. Validated on real beds the user provides.

### TW-1618 Skill `podcast-music-bed`

- **Status:** pending (needs TW-1606, TW-1617)
- **Scope:** modes: a prepared loop, a region the user approves, or regions proposed by the analysis (the user always approves); no time stretch; previews of each seam; markers at doubtful seams; import of the result. A crossfade is not imposed: a well-made loop may need none.

### TW-1619 Skill `podcast-section-transitions`

- **Status:** pending (needs TW-1604, TW-1606, TW-1620)
- **Scope:** an approved stinger or music in/out at a marker or time, never over the end of the last phrase, its tail respected, fades rendered offline; "the usual transition" comes from the show profile.

### TW-1620 Licensed audio library

- **Status:** pending
- **Scope:** a local folder (or several) with one sidecar file per item: source, license, attribution, allowed uses, tags; an index and search (`trackwright library` and an MCP tool); items without a license note are not offered. Nothing is ever downloaded.

### TW-1621 Skill `podcast-sound-effects`

- **Status:** pending (needs TW-1606, TW-1620)
- **Scope:** search the library, place an effect at an approved point, gain and fades, overlaps; provenance and license recorded in the episode (`Trackwright/credits`).

## Phase 4 — Voice

### TW-1622 Skill `podcast-dialogue-leveling`

- **Status:** pending (needs TW-1603, TW-1604, TW-1606)
- **Scope:** speech-gated loudness per region and per voice, separating differences between people, between takes and within an intervention; bounded gains (±6 dB by default) that keep whispers, laughter and emphasis; leveled stems rendered and imported; optional moderate compression with Compressor; representative fragments compared before and after. Never every phrase to the same value.

### TW-1623 Voice diagnostics

- **Status:** pending
- **Scope:** pure analyses with a confidence each: long-term spectrum, hum (50/60 Hz and harmonics), broadband noise, plosives (low-frequency bursts), mouth clicks (short transients), sibilance (high-band energy), reverberation (decay after phrase ends). Validated on whole episodes.

### TW-1624 Skill `podcast-voice-cleanup`

- **Status:** pending (needs TW-1623)
- **Scope:** a diagnosis per problem; treatment only with plugins found installed (dynamic discovery as in `noise-gate`): StudioEQ notches for hum, high-pass on the channel for rumble and plosives, DeEsser for sibilance, Gate or the `noise-gate` skill for noise in pauses; clicks, reverberation and intrusive sounds reported for review or another tool. Gentle settings and previews; artifacts named as a risk.

### TW-1625 Skill `podcast-voice-tone`

- **Status:** pending (needs TW-1601 item 8, TW-1623)
- **Scope:** goals instead of presets (rumble, harsh resonances, body and intelligibility, dynamics, sibilance) with StudioEQ or the channel EQ, Compressor and DeEsser; each change records which problem it addresses; A/B by playing a cycle range in Cubase with Bypass toggled at matched loudness.

## Phase 5 — Editing

### TW-1626 Experiment: fades and room tone

- **Status:** pending
- **Scope:** whether fades at cut points can be done through key commands bound in the script (and the script version, permission and restart that would need), or must be rendered; room tone extracted from a voice's quiet passages and imported to fill a gap, with how audible the joins are.

### TW-1627 Skill `podcast-edit-smoothing`

- **Status:** pending (needs TW-1606, TW-1626)
- **Scope:** cut points from earlier `podcast-silence-trim` runs (`state.json`) or event edges; ambience changes across each cut; room tone instead of digital silence where the background drops; fades as decided in TW-1626; one preview file with every cut in turn.

### TW-1628 Skill `podcast-sync-sources`

- **Status:** pending (needs TW-1605)
- **Scope:** diagnosis only: offset at several points by cross-correlation of two stems (a local recording and a remote one, or a backup), fixed offset versus drift, and what to correct by hand; beginning and end checked again after the user corrects it.

### TW-1629 Skill `podcast-spatial-balance`

- **Status:** pending
- **Scope:** pan positions reviewed against the show profile (voices, music, effects separately), accidental pans flagged; mono compatibility from an export folded down in Python (loudness difference, correlation) and a mono preview file; creative panning only on explicit request.

### TW-1630 Local transcription

- **Status:** pending
- **Scope:** an optional extra (`trackwright[transcribe]`) with a local Whisper model (whisper.cpp or faster-whisper, chosen by an experiment on whole episodes: speed, word timestamps, Spanish and English); the model downloaded only after the user agrees; transcripts stored in `Trackwright/analysis/` tied to the export they come from.

### TW-1631 Skill `podcast-edit-review`

- **Status:** pending (needs TW-1604, TW-1630)
- **Scope:** a list of decisions with times, reason and confidence: repeated takes, false starts, unusually long pauses, filler words, recording cues, ranges the user marked for removal (given as times or cycle ranges, since markers cannot be read); the default action is "review", never "cut"; approved cuts applied on all tracks, latest first, and the affected analyses invalidated.

### TW-1635 Fix: `cubase_record_automation` after TW-1601

- **Status:** pending
- **Seen in TW-1601:** (1) after a recording reported `complete: true`, the first export was flat and the fader was left at −1.43 dB instead of the last point's value; a later export, with the curve present and R on, had it. (2) The dry run reports the parameter title of the **selected** track (`TW1507 / Volumen`) for another target track (`TW1501`). Seen again in TW-1613: `cubase_convert_value` on Stereo Out answered `TW1612 episode / Volumen`, the title of the selected track (`TW1612 episode`); the value was right, since every volume shares the scale, but a control without an equivalent on the selected track could be converted on the wrong one.
- **Scope:** find the cause of (1) with a test that reproduces it (read mode after recording, the fader's final value); report the track's read state in the output; leave the fader at the last point; take the title in the dry run from the target track. The read-back tolerance should account for the ~110 ms tick (its own readings arrive one tick late).

## Phase 6 — Integration

### TW-1632 Test sessions and live test plan

- **Status:** pending
- **Scope:** a generator of synthetic podcast sessions (voices made of syllables, a music bed, stingers, noise, a drifting second source) for unit and live tests, and a live test plan per skill on the test project and on episodes the user points to.

### TW-1633 Beyond podcasts

- **Status:** pending
- **Scope:** delivery profiles for other spoken-word productions (audiobooks, voice-over, video dialogue), researched with their sources; skills parameterized by profile rather than tied to podcast numbers; whether to keep the `podcast-` prefix or add general names.

### TW-1634 Documentation and release

- **Status:** pending
- **Scope:** a manual chapter "Podcast production skills" in both languages, README, changelog, and a release once each phase's skills are verified (a phase can be released on its own).

## Out of scope

- Producing a whole episode unattended.
- Time stretching, speaker separation on a single track, downloading audio from the Internet.
- Artist and Pro features as requirements (SuperVision, Audio Alignment, per-channel export, VocalChain).
- Any change of routing by Trackwright.
