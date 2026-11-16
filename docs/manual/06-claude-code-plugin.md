# Claude Code plugin and producer skills

**English** · [Español](06-claude-code-plugin.es.md)

The tools of the [tool reference](04-tools.md) are building blocks. The Trackwright plugin for Claude Code adds **skills**: instructions that teach the model to chain those tools into a producer's job, ask the right questions and stop where your judgment is needed. You ask in plain words ("cut the silences longer than 3 seconds"), and the skill does the rest with you.

## Installing

1. **Cubase side, once:** `uv tool install trackwright` and `trackwright setup`. Install the script and create the configuration; when it offers to register the MCP server in Claude Code, answer **no** (the plugin does it). Restart Cubase.
2. **Permissions** in `~/.config/trackwright/config.toml`:
   ```toml
   [writes]
   enabled = true

   [analysis]
   enabled = true
   ```
   `[writes]` lets the skills change the project; `[analysis]` lets them read the audio you export (see the [configuration chapter](03-configuration.md)).
3. **In Claude Code:**
   ```text
   /plugin marketplace add impalah/trackwright
   /plugin install trackwright@trackwright
   ```
   In Claude Code's VS Code extension, the same from `/plugins`.

The plugin starts its own server with `uvx trackwright==<version> serve`, so its skills always run against the server version they were written for.

**If you registered the server by hand before** (`claude mcp add` or `trackwright setup`), remove that registration: with both, Claude Code shows every tool twice, which confuses the model.

```sh
claude mcp remove trackwright --scope user
```

## How the skills work with you

Every skill follows the same rules, on top of the server's own safety (dry runs, write policy, verification by reading back):

- **It asks before changing anything.** It shows the plan (the cuts, the plugin and its values) and waits for your yes.
- **You do the dialogs.** Cubase's API cannot read audio, so the skills measure an **export**: the skill sets the range and opens "Export Audio Mixdown", and you choose the format and click Export. Cubase Elements exports only Stereo Out, so the skill solos the track first and undoes the solo right after.
- **It never saves the project** unless you ask.
- **Everything can be undone** with Edit > Undo in Cubase, and the skill tells you how many times.

Every skill has the same sections and phases, and records what it creates so a re-run updates its own items and never yours: see [the skill contract](07-skill-contract.md).

When it asks you to export, choose: Stereo Out, Wave, **32 bit float**, the project's sample rate, the name it suggests, and real-time export off.

## `podcast-session-audit`

Takes stock of the session before working on it, and records what you confirm in the episode profile.

- **Ask for it like this:** "audit this episode", "check the project before I mix it", "set up the episode profile".
- **What it looks at:** every track (type, output, fader, mute, solo, plugins) and where each audio track's events start and end, the episode's extent, and what Trackwright already knows (the show and episode profiles, the tracks other skills created). It measures no audio and needs no export.
- **What it points out:** a forgotten solo, a muted track that has audio, a track routed nowhere, a silent fader, an empty track, a render and the track it replaces; as questions, since you decide what is intended.
- **What it asks:** the show the episode belongs to, the role of each track (voice, music, effects, reference, other; it never guesses one from a name), and the ranges no skill may touch (you give the times; markers cannot be read).
- **What it cannot see** (it says so every time): automation, clip gain and fades, markers, an event starting exactly at 0 s, plugin presets, sends and side-chains.
- **What it writes:** only `Trackwright/profile.toml`, after showing it to you; nothing in the Cubase project changes.

## `podcast-final-qc`

The last look before publishing: does the file meet the platforms' specs, and is there anything a listener would notice?

- **Ask for it like this:** "is the episode ready for Apple and Spotify?", "check this MP3 before I publish it".
- **What it checks:** format, channels, sample rate, bit rate, size, loudness and true peak against each target, with the platform's own page as the source; a value the platform does not publish is said to be "not published", never passed. Duration against the approved range.
- **What it warns about:** long pauses, silence at the start or end, sudden level changes between sections, clipping; and before a fresh export, a soloed track, a reference track that is not muted or a muted voice.
- **Where to listen:** the start, the end, the longest pauses, the level changes and the loudest moment; it can move the cursor to each one.
- **What it changes:** nothing. Fixing loudness or peaks is the job of `podcast-delivery`. It can save the report (JSON and Markdown) in `Trackwright/reports/`.

## `podcast-delivery`

Brings the finished episode to a platform's spec: the loudness with the Stereo Out fader, and a limiter after the fader only when the peaks need it; then the delivery file, exported by you and measured itself.

- **Ask for it like this:** "prepare the episode for Apple Podcasts", "normalize it to −16 LUFS", "fix the loudness the QC reported".
- **How it decides:** it measures a WAV master and asks `cubase_delivery_plan` for the fader value and whether a limiter is needed, with its threshold. The numbers behind it were measured on a whole episode (TW-1612): the fader moves the loudness by exactly its gain; Stereo Out's slots 1–6 are before the fader and 7–8 after it, so a ceiling goes in 7 or 8; MP3 raises the peaks about 0.8 dB, so the limiter's threshold sits that much lower.
- **What it warns about:** a target the fader cannot reach (+6 dB at most) and heavy limiting: both mean the voices should come up or be leveled first.
- **How it checks:** a new master after the change, then the delivery file you export (MP3, for example) measured with `cubase_final_qc`. At most three rounds; if it does not converge it stops and explains.
- **What it changes:** the Stereo Out fader and, only if needed, a limiter in slot 7 or 8, after your yes. It records the limiter as its own and the fader's previous value, so it can be put back.

## `podcast-music-ducking`

Lowers the music under the voices: down just before someone speaks, down through short pauses, gently back up after a block of speech.

- **Ask for it like this:** "duck the music under the voices", "make the ducking less obvious", "do not bring the music up between 12:30 and 13:10".
- **How:** the Cubase API cannot write automation points or route a side-chain, so it is done offline. You export the voices together and the music (the skill solos and restores); the skill plans the envelope from the speech, renders the ducked music into `Trackwright/renders/`, and makes short previews (voice plus ducked music at the first word, a recovery, a pause, the end) for you to listen to before anything changes.
- **Edits in plain words** change the plan; only the spans an edit changes are rendered and previewed again.
- **What it changes, after your yes:** a new track with the ducked music at the right place, and the original music track muted (never deleted). A later run replaces its own ducked track and nothing else.
- **What it warns about:** a voice with short pauses everywhere (a monologue) keeps the music low almost all the time; it offers to keep it up at the intro, the outro or a transition.

## `podcast-music-bed`

Makes a music bed of a given length from music that is too short: a loop repeated, the music ending on its own, never stretched.

- **Ask for it like this:** "make this music last 3 minutes under the interview", "loop the intro music from 0:30 to 4:00".
- **Three ways:** a file made to loop (it repeats whole), a region you mark (its end is lined up to the sample with its start), or a loop the analysis proposes (tempo, bars, and how well its seam matches in timbre and harmony).
- **How it sounds:** the jump is placed where the music matches itself best, lined up by correlation, with a half-beat crossfade; after the last pass the music plays on to its own end. On a real march (TW-1617) the seams were "hardly noticeable".
- **You listen first:** a short preview of every seam, before anything changes in the project. The bed is never longer than asked and never stretched: it tells you how much shorter it is.
- **What it changes, after your yes:** a new track with the bed at its place, and markers at the seams you doubted.

## `podcast-section-transitions`

Places a transition (a stinger, a short music in or out) between two sections, in the pause between them.

- **Ask for it like this:** "put the usual transition between the interview and the news, without covering the last phrase", "a stinger at 12:30".
- **How:** you give about where (the time of your marker) and choose the stinger from your licensed library (title, length, licence, credit). The skill exports the voices around that place, finds the pause, starts the stinger just after the last phrase and checks that its sound (not the silence the file may carry) ends before the next phrase. It renders it at the project's rate and makes a preview with the voices.
- **When it does not fit:** it says by how much and offers to open the pause (insert silence: every track moves later), fade its tail out, or a shorter stinger. Nothing is cut or moved without your choice.
- **What it changes, after your yes:** the transition on a transitions track at its place; its licence and credit recorded in the project's `Trackwright/` folder.

## `podcast-sound-effects`

Places sound effects from your licensed library at the points you choose, and gathers the episode's credits.

- **Ask for it like this:** "a door closing at 12:04", "a keyboard click under the demo at 3:10, subtle", "collect the credits of the sounds in this episode".
- **How:** it searches your library (title, length, licence, credit) and you choose. It exports the voices and says what each effect lands on (speech or a pause, other effects). It proposes a level against the voice: well under it over speech, close to it in a pause. Then it renders the effect with fades at the project's rate and makes a preview with the voices.
- **The point is yours:** it never moves an effect. Over speech or over another effect, it tells you so.
- **What it changes, after your yes:** each effect on an effects track at its point; its licence recorded, and `Trackwright/credits.md` with the credits to paste into the episode notes.

## `podcast-silence-trim`

Finds the silences longer than a duration and removes them, closing the gaps so the episode gets shorter.

- **Ask for it like this:** "remove the silences longer than 3 seconds", "cut the pauses over 2 s between minute 5 and minute 20".
- **What it asks:** the minimum duration (2 s if you do not say), the range (the whole project by default), and what to analyze.
- **Why it analyzes the whole mix by default:** the cut removes the span from **every track**, so a span is only safe to cut when it is silent on all of them. If you name one track and others have sound there (another voice, a music bed), it explains the options: the whole mix, that track alone knowing the cuts affect the others, or deleting only on that track without closing the gaps.
- **What it shows:** each proposed cut (start, end, duration) and the total time removed. You choose all, some or none.
- **How it cuts:** from the last to the first, so the earlier positions do not move; each cut is verified on a track's event edges.
- **Margins:** 0.25 s of each silence is kept at both ends so words are not clipped (a 3 s silence becomes a 2.5 s cut). Ask for tighter or looser edits if you want.

## `noise-gate`

Adds and sets a noise gate on a track, so the background noise between phrases disappears while soft speech is kept.

- **Ask for it like this:** "put a noise gate on the Voice track", "remove the room noise in the pauses of the guest's track".
- **Which gate:** it does not assume one. It searches your plugins for gates (Cubase's `Gate`, or third-party ones), leaves out the ones that are not audio-level gates (MIDI-triggered, spectral denoisers), and lets you choose if there are several. Once loaded, it checks that the plugin really has a threshold in dB.
- **How it chooses the threshold:** it measures the **noise floor** and the **quietest speech** on an export and puts the threshold in the middle. The gate hears the track before its fader and panning, while the export comes after them, so it translates the value (a centered mono track exports 3 dB lower). If noise and soft speech are less than 12 dB apart, it warns you that a gate cannot separate them cleanly.
- **What it proposes:** threshold, range (how much it attenuates; about −30 dB sounds natural for speech, −∞ removes everything), hold and release (so word endings are not chopped). You approve or change them.
- **How it checks the result:** optionally, a second export with the gate active: the pauses must be quieter by about the range, and the soft speech must keep its level. Then listen: no measurement replaces your ears.
- **Removing it:** the plugin's Bypass switch, or remove it from the insert slot in Cubase (Trackwright cannot remove plugins).

Measured on a test signal (noise at −55 dBFS, speech at −16 and −36 dBFS): the noise in the pauses went down 30 dB and both the loud and the soft phrases kept their level exactly (see the verification log).

## Other MCP clients

The skills use only the fields of the open [Agent Skills](https://agentskills.io) standard, so the same files may work in other clients that read that format. This has **not** been tested yet; for now the plugin is for Claude Code (terminal and VS Code extension).
