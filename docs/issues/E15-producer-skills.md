# E15 — Producer skills: Claude Code plugin and audio analysis

**English** · [Español](E15-producer-skills.es.md)

**Epic status: pending.** Goal: practical requests such as "cut the silences longer than 3 seconds in track X" or "add a noise gate to the voice track", built on the MCP server. Two parts: an **audio analyzer** in the server (Cubase's API cannot read track contents, so silences and noise levels must be measured outside Cubase), and a **Claude Code plugin** with skills in the open Agent Skills format, published from this same repository.

**Decisions (2026-11-14):**
- **Same repository.** The skills name the tools and depend on their contracts; in one repository a test catches a renamed tool in the same commit. To be reconsidered only if the skills become independent of Trackwright (several DAWs, other servers) or need another license; until then they are AGPL-3.0-or-later like the rest.
- **Server and skills, each with its job.** The server does the safe, atomic operations and the deterministic analysis, and keeps the safety (dry runs, write policy, verification by reading back): a skill only gives instructions to the model and cannot enforce anything. The skills carry the producer's judgment: order of the steps, thresholds, what to show the user and when to ask.
- **Standard skills.** `SKILL.md` uses only the fields of the Agent Skills standard (`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`), not the Claude Code-only ones, so the same files can be tried later in other clients. Skills name tools by their short name (`cubase_edit_range`): inside a plugin, the full name gets a prefix (`mcp__plugin_<plugin>_<server>__<tool>`).
- **Analysis of an export, not of the project's files.** The file in the project's Audio folder is not what plays on the timeline (offsets, trims, several events, clip gain, fades, plugins), and the API cannot read the events to convert file time to project time. An export between the locators is aligned with the project from the left locator and contains what really plays (verified in TW-1204: Cubase Elements exports between the locators).
- **numpy + soundfile.** soundfile reads WAV, AIFF and FLAC, including 32-bit float (the standard `wave` module does not), and ships libsndfile in its wheel: installed with uv, nothing to compile or install on the system. Ruled out: ffmpeg (a system binary, outside "uv only"), pydub (needs ffmpeg), librosa (heavy for this), neural voice detection (torch, hundreds of MB).
- **VS Code and GitHub Copilot: out of this epic.** Plugins already work in Claude Code's VS Code extension (documented). A test with Copilot and a possible VS Code extension stay for later (see "Out of scope").

**References (checked 2026-11-14):** Claude Code plugins ([overview](https://code.claude.com/docs/en/plugins/overview.md), [manifest](https://code.claude.com/docs/en/plugins/manifest-reference.md), [marketplace](https://code.claude.com/docs/en/plugins/create-marketplace.md), [CLI](https://code.claude.com/docs/en/plugins/cli-reference.md)), [skills](https://code.claude.com/docs/en/skills.md) and [MCP](https://code.claude.com/docs/en/mcp.md).

**Rules for the whole epic:** the same as E14 (a failing test before each fix, bilingual documentation, results seen in Cubase recorded in the verification log). Skills are tried against the disposable test project and its `POC-TEST` track; nothing is applied without the user's confirmation.

## Phase 1 — Audio analysis in the server

### TW-1501 Exporting one track, checked in Cubase

- **Status:** done (2026-11-14), see `experiments/tw1501/` and the verification log: only Stereo Out can be exported, so the track goes in solo; alignment exact to the sample (`project = left locator + file time`); levels shifted by the pan law (−3 dB), so thresholds must be relative to the noise floor; digital silence must be left out of the noise floor estimate. `cubase_export_mix` needs no change; the solo is the skill's step
- **Why first:** the analysis plan depends on it, and it is unknown today.
- **Scope (experiment in `experiments/tw1501/`, with its README):**
  1. Whether the "Export Audio Mixdown" dialog of Cubase Elements 15 can export one track's channel instead of Stereo Out. If not: Stereo Out with the track in solo (and the solo undone afterwards), or the user chooses.
  2. Alignment: sample 0 of the exported file = the left locator (measured with a click or a known edge in the test project).
  3. The format and sample rate Cubase proposes, and whether 32-bit float WAV is available.
  4. Whether insert plugins and the channel fader are included (they would change the levels measured).
- **Result:** recorded in `docs/verification.md`; it decides the export step of TW-1506 and what `cubase_export_mix` needs (perhaps nothing).

### TW-1502 Reading audio: a new capability with its own switch

- **Status:** done (2026-11-14): `[analysis] enabled` (default `false`, `ANALYSIS_DISABLED`) and `max_seconds` (default 14400 s, `TOO_LONG`), checked by `WritePolicy.check_analysis()`; independent of `[writes]`; `setup` asks for it (`--analysis`); `cubase_status.analysis_enabled` and a `doctor` check; configuration chapter and SECURITY. A size limit was not added: the analyzer reads in blocks, so the duration bounds the work. Tests in `tests/unit/test_analysis_policy_tw1502.py`; the contract test for the tool goes with TW-1504
- **Why:** today Trackwright never reads audio (`cubase_export_mix` reads only name, size, date and duration). Reading the samples of a file is a new capability and must be explicit.
- **Scope:**
  1. `[analysis] enabled` in the configuration, `false` by default; `ANALYSIS_DISABLED` when off. `trackwright setup` asks for it as another step.
  2. Only files the user exported and Trackwright confirmed, or a path given explicitly; read-only; never sent anywhere, only the measurements are returned.
  3. Limits: maximum duration and size, refused with a clear code instead of filling memory (reading in blocks).
  4. SECURITY.md (+ `.es`) and the configuration chapter of the manual.
- **Tests:** policy tests like those of `[writes]`; a contract test that the tool is refused when disabled.

### TW-1503 Analyzer module

- **Status:** done (2026-11-14): `trackwright.analysis` (`reader.py`: `probe` and `measure` in blocks of 500 windows; `detect.py`: `noise_floor`, `SilenceCriteria`, `find_silences`). Decisions: the level of a window is the RMS over its samples and all channels (out-of-phase channels do not cancel); the floor is the 10th percentile without digital silence; the relative threshold (floor + 10 dB by default) only applies when it stays below the 90th percentile, otherwise only digital silence counts (a continuous tone or a file of pure noise has no silence to find); padding is not applied at the file's ends. Defaults: 20 ms windows, minimum 2 s, padding 0.25 s, merge gap 0.3 s. Tests in `tests/unit/test_analysis.py` (100 % of the package, Hypothesis properties). Run on the real TW-1501 export: the three silences of 3 s or more found where they are in the project, the 1 s one ignored, noise floor −63 dB
- **Scope:** `trackwright/analysis/`, with no Cubase dependency (pure functions over samples):
  1. Read in blocks with soundfile; mix to mono for the measurement.
  2. RMS in windows of about 20 ms, in dBFS; peak.
  3. Noise floor: a low percentile of the window levels (for example the 10th).
  4. Silences: spans below a threshold (absolute in dBFS, or relative to the noise floor) lasting at least a minimum; padding kept before and after each cut so words are not clipped; spans merged when the gap between them is shorter than a minimum.
  5. Dependencies: `numpy` and `soundfile`, with an upper bound on the next major version like the rest.
- **Tests:** synthetic signals (tone, silence, noise at a known level): exact spans within one window; property tests (Hypothesis): spans ordered, not overlapping, inside the file, all at least the minimum duration; a file with no silence and a file that is all silence.

### TW-1504 Tool `cubase_analyze_audio`

- **Status:** done (2026-11-15): `core/analyzing.py` (`AnalyzingMixin`), `AnalysisOut`/`SilenceOut`, tool registered as `READ`; the duration limit is checked from the header before reading samples. Tests in `tests/unit/test_service_analysis.py` and the contract test. Verified through MCP on the TW-1501 export (see the verification log)
- **Scope:**
  1. **Input:** the file (from the `confirm` phase of `cubase_export_mix`) and the project time of its start (the left locator, which that tool knows); threshold, minimum duration and padding, with documented defaults for spoken voice.
  2. **Output:** silences in **project seconds** (start, end, duration, level), noise floor, peak and RMS of the whole file, and the parameters used. A list capped like the other tools (`clamp_limit`), with the total.
  3. Annotations: `READ` (it changes nothing in Cubase).
  4. Section in `docs/manual/04-tools.md` (+ `.es`); the number of tools in the documentation rises to 33.
- **Tests:** service and contract tests with a WAV generated in the test; live: an export of the test project, with the silences found checked against the timeline.

## Phase 2 — Claude Code plugin

### TW-1505 Plugin and marketplace structure

- **Status:** done (2026-11-15): plugin in `plugins/claude-code/` (`plugin.json` with the package version, README in both languages), marketplace at the root, `.mcp.json` with `uvx --from ${TRACKWRIGHT_FROM:-trackwright==<version>} trackwright serve` (`uvx` works; the variable lets development use a checkout, because the published 0.4.0 refuses a configuration with `[analysis]`). `claude plugin validate --strict` passes for the plugin and the marketplace (warning only about the missing icon, which matters only for Anthropic's catalog); not in CI, which has no `claude` CLI: it is a release step. Duplicate registration: documented in the plugin README with the command to remove the manual one; not detected by `doctor`, because Claude Code does not document where plugins are recorded. Verified: `TRACKWRIGHT_FROM=$PWD claude --plugin-dir plugins/claude-code mcp list` shows `plugin:trackwright:trackwright` connected
- **Scope:**
  1. `plugins/claude-code/` with `.claude-plugin/plugin.json` (`name: "trackwright"`, version, description, author, homepage, repository, license) and `skills/`.
  2. `.mcp.json` of the plugin: the server started as `uvx trackwright==X.Y.Z serve`, with the version that matches the plugin. **To check:** the documentation shows `npx` but says nothing about `uvx`; if it fails, document the alternative.
  3. `.claude-plugin/marketplace.json` at the repository root (the repository is the marketplace), with `"source": "./plugins/claude-code"`. Installation: `claude plugin marketplace add impalah/trackwright` and `claude plugin install trackwright@<marketplace>`.
  4. **Conflict with the current installation:** a user who registered `trackwright` with `claude mcp add` would have two servers with the same tools. Document which one to remove (both share the bridge thanks to its lock, but the client would see duplicated tools) and make `trackwright doctor` warn about it if it can be detected.
  5. **Tests in `tests/unit/test_plugin.py`:** every tool a skill names exists in `server.py`; the frontmatter uses only standard fields; the plugin's version and the `trackwright==` pin in `.mcp.json` match `pyproject.toml`; `plugin.json` and `marketplace.json` are valid JSON with the same name.
  6. `claude plugin validate plugins/claude-code --strict` before each release (documented in the release procedure). Whether CI can run it (it needs the `claude` CLI on the runner) is decided here.
- **Verification:** `claude --plugin-dir plugins/claude-code` in a session against the real Cubase: the skills appear (`/trackwright:<skill>`) and the tools answer.

### TW-1506 Skill `podcast-silence-trim`

- **Status:** done (2026-11-15): `plugins/claude-code/skills/podcast-silence-trim/SKILL.md`. Decisions: analyze the whole mix by default, because `delete_time` cuts every track and only a span silent in the mix is silent everywhere; when the user names one track, explain and offer the mix, that track in solo, or `delete` on that track only (gaps stay); a music bed makes the mix never silent; digital silence at the range's ends is left out of the proposal. The flow was run step by step against the test project (see the verification log): four cuts approved and verified. The user then ran the request through the plugin in a fresh session (`claude --plugin-dir`) and reported that it worked
- **Flow:**
  1. Identify the track and the range (whole project by default) with the read tools; confirm them with the user.
  2. Export (`cubase_export_mix`, two phases: the user completes the dialog) and confirm.
  3. `cubase_analyze_audio` with the user's criteria (for example "longer than 3 s") or the voice defaults.
  4. Show the proposed cuts (list, total time removed) and ask. Nothing is cut without a yes.
  5. Apply with `cubase_edit_range` (`delete_time`) **from the end to the start**, so earlier positions do not move; dry run first, as the server instructions say.
  6. Report what was cut; say how to undo it (Edit > Undo, once per cut).
- **Decisions to record:** whether the cut acts on every track (podcast with several voices in sync, the usual case: `cubase_edit_range` acts on every track in the range) or only on one; what happens with music beds.
- **Verification:** on the test project, with a known number of silences; undone afterwards.

### TW-1507 Skill `noise-gate`

- **Status:** pending (needs TW-1503 to TW-1505)
- **Flow:**
  1. Find a gate among the available plugins (`cubase_list_available_plugins`); which one Cubase Elements ships is **unknown** and is checked here, not assumed.
  2. Measure the noise floor of the track (export and `cubase_analyze_audio`) and propose the threshold a few dB above it.
  3. `cubase_insert_plugin` and `cubase_set_parameter` with dry runs, the threshold in real units; read back.
  4. Explain to the user how to listen and adjust (attack, release), which Trackwright cannot judge.
- **Verification:** on `POC-TEST`; the plugin removed afterwards.

### TW-1508 Documentation and release

- **Status:** pending
- **Scope:** a manual chapter "Claude Code plugin and skills" (+ `.es`): installation, the skills and what they ask, how they relate to the tools; README section; CHANGELOG; CLAUDE.md (code map). Release: the version that includes this epic (it may be 0.5.0 together with the API changes of E14, if they are released at once).

### TW-1509 Wait for Cubase after autostarting the bridge

- **Status:** done (2026-11-15); tests in `tests/unit/test_autostart_wait_tw1509.py`; verified in Cubase (see the verification log)
- **Why:** seen during TW-1504: right after the bridge was autostarted, the first request timed out because Cubase had not yet bound to the new virtual ports; the second one worked. A skill's first step would fail for no real reason.
- **Decision:** after starting the bridge, `BridgeHost` repeats `hello` (read-only, so retrying it is safe) until Cubase answers or `[bridge] autostart_timeout` runs out, pausing 0.5 s between attempts; then the caller's request, which never reached the bridge, is sent once. If Cubase does not answer, `TIMEOUT` with `outcome: not_executed` and a message saying the request was not sent. Other errors are not retried. The rule "never retry a write whose outcome is uncertain" is unchanged.

## Out of scope (possible later epics)

- **GitHub Copilot in VS Code:** try the same skills and the server with `.vscode/mcp.json`, without an extension; record the result and update the "not tested" note.
- **VS Code extension:** only if the above works and one-click installation for other people is worth a TypeScript project with its own releases.
- **MCP prompts** in the server, for workflows that must work in any MCP client.
- **Voice detection** (speech versus breaths), **loudness** (LUFS for podcast, `pyloudnorm`) and other producer skills.
