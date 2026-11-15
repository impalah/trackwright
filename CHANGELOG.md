# Changelog

**English** · [Español](CHANGELOG.es.md)

## Unreleased

- **Voice activity** (TW-1604): new tool `cubase_detect_speech`: speech regions of a voice track's export in project seconds (speech band with hysteresis, hangover, gaps joined, clicks dropped). The server now has 36 tools.
- **Loudness and true peak** (TW-1603): new tool `cubase_measure_loudness` (ITU-R BS.1770 / EBU R128: integrated, momentary and short-term loudness, loudness range, sample and true peak), checked against the EBU Tech 3341 and 3342 test cases and pyloudnorm; AAC files decoded with macOS `afconvert` (also for `cubase_analyze_audio`). New dependency scipy. The server now has 35 tools.
- **Project workspace** (TW-1602): `[workspace] enabled` (off by default, `WORKSPACE_DISABLED`) and the tool `cubase_workspace` (`status`, `init`), for a `Trackwright/` folder inside the project folder with `renders/`, `previews/`, `analysis/`, `reports/`, `state.json` (what skills created) and `profile.toml` (episode profile). `trackwright setup` asks for it (`--workspace`); `cubase_status` and `doctor` report it. New dependency `tomli-w`. The server now has 34 tools.

## 0.5.0 — 2026-11-15

Producer skills (epic E15) and the rest of the quality remediation (E14, phases 3 and 4). The Cubase script stays at **1.6.1**: no new script, no Cubase restart. **Breaking for MCP clients:** a tool renamed and two values changed (TW-1413, below).

**Upgrading from 0.4.0:**

1. `uv tool upgrade trackwright`, then `trackwright bridge-stop` (the MCP server starts the new bridge when it needs it).
2. If a prompt, script or client of yours calls the tools by name: `cubase_remove_selected_tracks` is now `cubase_remove_selected_track`, `cubase_select_track` takes `step: "previous"` instead of `"prev"`, and `cubase_save_project` answers `status: "done"` instead of `"saved"`.
3. Optional: add `[analysis]` with `enabled = true` to `~/.config/trackwright/config.toml` to use `cubase_analyze_audio` and the skills. **A configuration with `[analysis]` is refused by 0.4.0 and older** (unknown sections are errors), so do not go back to an older version with it.
4. Optional: install the Claude Code plugin (`/plugin marketplace add impalah/trackwright`, `/plugin install trackwright@trackwright`) and then remove the manual registration (`claude mcp remove trackwright --scope user`), so the tools do not appear twice.
5. Restart your MCP client (in Claude Code, `/mcp`).

- **Claude Code plugin and producer skills** (TW-1505 to TW-1508): `plugins/claude-code/`, published from this repository as a marketplace; skills `podcast-silence-trim` and `noise-gate`; manual chapter 6.

- **Skill `noise-gate`** (TW-1507): finds the gate plugins installed (Cubase's or third-party), measures the noise and the quietest speech on an export, translates the threshold to the gate's input (faders, pan law) and sets it with the user's approval. `cubase_analyze_audio` now also returns `quiet_sound_db` and `sound_db`.
- **Fix:** the default `merge_gap_seconds` of `cubase_analyze_audio` drops from 0.3 to 0.05 s. With 0.3 s, syllables of 250 ms were taken for blips and a whole phrase could be reported as silence.
- **Skill `podcast-silence-trim`** (TW-1506): finds and removes silences longer than a duration, closing the gaps on every track; exports with the user, measures with `cubase_analyze_audio`, shows the cuts and only cuts what the user approves, from the end to the start.
- **Claude Code plugin** (TW-1505): `plugins/claude-code/` (manifest, `.mcp.json` that starts `uvx trackwright==<version> serve`, skills folder) and the marketplace in `.claude-plugin/marketplace.json`; `tests/unit/test_plugin.py` keeps versions, names and the tools the skills name consistent.
- **Autostart waits for Cubase** (TW-1509): after starting the bridge, the server repeats `hello` until Cubase answers (within `[bridge] autostart_timeout`) before sending the request, instead of failing the first request with `TIMEOUT`.
- **New tool `cubase_analyze_audio`** (TW-1504): noise floor, levels and silences of an exported file, in project seconds; read-only, needs `[analysis] enabled`. The server now has 33 tools.
- **Audio analyzer** (TW-1503): the `trackwright.analysis` package reads WAV, AIFF, FLAC and Ogg files in blocks (numpy and soundfile, new dependencies) and finds the noise floor and the silences, with a threshold relative to the noise floor or absolute, a minimum duration, padding and merging of short blips.
- **`[analysis]` configuration** (TW-1502): reading audio files is a capability of its own, off by default (`ANALYSIS_DISABLED`) and limited by `max_seconds` (`TOO_LONG`); `trackwright setup` asks for it (`--analysis`), and `cubase_status` and `trackwright doctor` report it.
- **Repository hygiene** (TW-1415): pre-commit (ruff, mypy), Dependabot (uv and GitHub Actions), CONTRIBUTING and SECURITY (English and Spanish), issue and pull request templates; ruff rules PT, PERF, FURB, ASYNC and TRY; pytest fails on warnings and on hung tests; runtime dependencies bounded below their next major version (`mcp<3`, `pydantic<3`, `loguru<1`).
- **Simulator package** (TW-1414): `trackwright.fake` is now a package of layers (core, editing, automation, writes, reads), with the same public names.
- **MCP API consistency** (TW-1413). **Breaking:**
  - `cubase_remove_selected_tracks` is now `cubase_remove_selected_track`: it removes exactly one track;
  - `cubase_select_track` takes `step: "previous"` (was `"prev"`), as `cubase_plugin_preset`;
  - `cubase_save_project` reports `status: "done"` (was `"saved"`), like the other tools.

  Also: `cubase_split_at_locators` accepts `unit: "seconds"`; slot numbering follows `insert_slots` (8 in Cubase Elements) and automation keys accept only the sends (1-4) and insert slots (1-2) the script binds; each error class matches its code (`VERIFY_FAILED`, `NOT_FOUND`, `UNAVAILABLE`); the cursor format is read from Cubase instead of being a hard-coded Spanish text.
- **Core refactoring** (TW-1412), no behavior change: one pagination helper, time formats in `core/timefmt.py`, Cubase tags by object in `core/tags.py`, shared selection and cursor helpers, the time signature passed explicitly, one `JsonObject`. Removed: the reference checks no tool used and the `STALE_REF` error the manuals mentioned.
- **Live integration tests** (TW-1411): 20 of the 32 tools now have repeatable tests against the real Cubase (reads, and reversible writes on the test track).
- **Mutation testing** (TW-1410): `make mutation` runs mutmut on the safety modules (87.3 % of mutants killed); new tests close the gaps it found, the most important being that `BridgeHost` must never retry a request whose sending is uncertain.
- **Test-suite hardening** (TW-1409): policy tests assert the error code; tests for the fingerprint and `from_config`; property-based tests of the framing (Hypothesis, new dev dependency); an ES5 syntax check of the Cubase script; Node tests for script paths that had none (reads, protocol errors, the request queue, fragment expiry); waits on events instead of fixed sleeps; a time limit on the Node harness; shared test doubles instead of tests importing tests; the live write tests limited to the test track; `mypy` also checks the tests. A log race in a test that could print a "logging error" was fixed by logging late responses before recording them.
- **Simulator and script conformance** (TW-1408): a test sends the same operations to the real script and to the simulator and compares their answers; the simulator now matches the script (diagnostic fields, the 16-tag limit, `limit` 0 returning one item) and Cubase (a missing channel parameter reads as `process: -1`, which Trackwright now treats as absent). Tests use `fake.override()` instead of replacing private methods.

## 0.4.0 — 2026-11-14

Phases 1 and 2 of the quality remediation (epic E14): safety and truthful results, bridge and Cubase script robustness. Requires the **Cubase script 1.6.1**.

**Upgrading from 0.3.0:**

1. `uv tool upgrade trackwright`
2. `trackwright bridge-stop`: the bridge started by 0.3.0 ignores the session that writes now carry. The MCP server starts a new one when it needs it.
3. `trackwright setup`: it installs the script 1.6.1 (it shows what it replaces and asks), then **restart Cubase**.
4. Restart your MCP client (in Claude Code, `/mcp`), so it loads the new tools. If you registered the server with `uvx --from trackwright==0.3.0`, that registration keeps running 0.3.0: `setup` now warns about it; replace it with `claude mcp remove trackwright -s user` and `trackwright setup`.
5. `trackwright doctor`: "script loaded in Cubase" must show 1.6.1.

- **Breaking:** `track` is required in `cubase_set_parameter` and `cubase_insert_plugin`; their outputs include `track_uid` to reuse when applying a dry run.
- **Write policy** (TW-1401): `cubase_run_command` refuses save and track removal (use the dedicated tools) and is refused, like range edits and splits on every track, while `[writes] allowed_tracks` is set; single-track range edits honour `allowed_tracks`; `cubase_set_parameter` refuses the channel's routing, name and selection; moving the cycle locators needs writes enabled.
- **Session pinning through the bridge** (TW-1402): writes carry the session the tool pinned, so the script refuses them after a reload; a write with too little time left to wait for its answer is not sent (`BUSY`). **Restart the bridge after upgrading** (`trackwright bridge-stop`): an older bridge ignores the session.
- **Truthful results** (TW-1403): an import is confirmed only by new event edges; a save without a known project folder is `fired`, not `saved`; an automation recording cut short reports `complete: false`; `cubase_set_project` reports what was applied when a write fails; several open projects are never guessed; unexpected errors reach the client as `INTERNAL_ERROR`.
- **Continuous integration** (TW-1404): GitHub Actions on macOS runs `make check`, the Node tests of the Cubase script and the package build on every push and pull request; coverage threshold raised to 95 %.
- **Bridge robustness** (TW-1405): a refused second bridge no longer deletes the live socket (and opens no MIDI ports); listen backlog 128 and a second probe before autostart; per-client read timeout; bounded SysEx buffer; a stray frame no longer destroys a reassembly and a full table drops its oldest entry; every socket error is a `BRIDGE_UNAVAILABLE` error; subprocess timeouts; no symlinked socket directory; atomic script install; `--log-level` is validated.
- **`trackwright bridge-stop`** (and `make bridge-stop`): stops the running bridge through the pid it reports. The documented `pkill -f "trackwright bridge"` did not match an autostarted bridge, which runs as `python -m trackwright --config … bridge`.
- **Running script version** (TW-1407): `doctor` checks that Cubase runs the packaged script (after an upgrade without restarting Cubase it fails with the fix), and `cubase_status` reports `script_outdated`.
- **Cubase script 1.6.0** (TW-1406): parameter writes no longer walk the mixer tree; each DirectAccess scope checks its own activation; `da.channels` accepts at most 16 tags; requests still queued when the page deactivates are answered with `NOT_ACTIVE`; `page.mOnIdle` never throws into Cubase; inherited names (`toString`) are not operations or commands; incomplete requests expire after ~6 s instead of ~225 s; `RESPONSE_TOO_LARGE` keeps `op` and `via`. Install it with `trackwright setup` and restart Cubase.
- **Surface panel** (script 1.6.1): three fixed lines say what the 45 faders are (the automation controls of `cubase_record_automation`) and not to move or map them; the installation manual explains why they are always there.
- **Code quality review** (`docs/quality-review.md`) and its remediation plan, epic E14: policy holes, session pinning in the bridge, truthful results, robustness, simulator/script conformance, mutation testing and CI.
- **Project links:** `Repository` and `Issues` (GitHub) in the package metadata; the README links the Spanish version, the documentation and the license on GitHub, which also work on PyPI.
- **Docs:** the source installation clones the GitHub repository; local paths replaced with generic ones.

## 0.3.0 — 2026-11-13

First release on PyPI: `uv tool install trackwright`.

- **`Makefile`** with the usual tasks (check, tests, build, publish, doctor, Cubase script…), all through uv; `make help` lists them.
- **Publication on PyPI** (TW-1303): the package is renamed **`trackwright`** (formerly `trackwright-mcp`) and is installed with `uv tool install trackwright`.
  - **AGPL-3.0-or-later** license (`LICENSE` file, metadata per PEP 639).
  - README rewritten for end users; the documentation index moves to `docs/README.md`.
  - `setup` registers in Claude Code the absolute path of `trackwright` (installed with `uv tool`), or `uvx --from trackwright==<version> trackwright serve` when run with `uvx`, pinned to the version of the script it installs.
- **Positioning:** Trackwright is presented as an independent MCP server for DAWs whose first implementation is Cubase. The docs speak of MCP clients in general (tested with Claude Code) and explain how to connect GitHub Copilot in VS Code (not tested yet). The tutorials and the tool reference speak of "the assistant" and state that they were tested with Claude Code and Cubase.
- **Documentation in English** with a Spanish translation of every document in a sibling `*.es.md` file. English file and folder names (`docs/tutorials`, `docs/reference`, `docs/manual/01-installation.md`…). `tests/unit/test_docs.py` checks that every document has its translation and that links and anchors stay in their language.
- **Guided installation** (TW-1301): `trackwright setup` installs the Cubase script, creates the configuration if it doesn't exist (writes and saving disabled by default) and registers the server in Claude Code. Each step is shown and confirmed; `--yes STEP` skips the question. It ends with `doctor`.
- `doctor` also shows `[writes] save` and, with `autostart`, explains that the bridge starts with the MCP server.
- **MIDI transport with CoreMIDI via `ctypes`** (TW-1302), the default on macOS:
  - the package is pure Python and needs nothing compiled (no Xcode);
  - `mido` and `python-rtmidi` are commented out in `pyproject.toml`; the transport based on them is kept and is selected with `[bridge] backend = "rtmidi"`.

## 0.2.0 — 2026-11-13

Epic E12 closed (TW-1201 to TW-1212): 32 tools, Cubase script 1.5.5.

- **Plugin presets** (TW-1205):
  - `cubase_plugin_preset` tool (next or previous), verified by the change in parameters; asks for a click in the plugin window the first time;
  - **script 1.5.5**, with `Preset / Next` and `Previous`.
- **Project settings** (TW-1210):
  - `cubase_set_project` tool: cycle, metronome, count-in, punch, use of pre-roll and post-roll, click during playback and recording, and click level, with read-back;
  - `cubase_get_project` reports the click level as 0–127.
- **Import audio** (TW-1203):
  - `cubase_import_audio` tool in two phases: track, position and the Cubase file picker; then confirmation by probing the edges and the copy into the project;
  - **script 1.5.4**, with `File / Import Audio File`.
- **Save the project** (TW-1202):
  - `cubase_save_project` tool (`save` or `new_version`), with its own `[writes] save` permission, disabled by default, and verification by the timestamp of the `.cpr` files;
  - **script 1.5.3**, with `File / Save` and `Save New Version`.
- **Export the mix** (TW-1204):
  - `cubase_export_mix` tool in two phases: the range (or all the audio) and the Cubase dialog; then confirmation of the file and its duration;
  - **script 1.5.2**, with `File / Export Audio Mixdown`.
- **Deletion on a single track** (TW-1212): `cubase_edit_range` with `track` and `action: "delete"`. It splits, deletes the pieces one by one, verifies and reports the undo steps.
- **Range editing in seconds** (TW-1211):
  - `cubase_edit_range` tool (`delete`, `delete_time`, `cut_time`, `insert_silence`, `crop`), with verification by probing the event edges;
  - **script 1.5.1**, with 14 edit, tool and probing commands.
- **`cubase_set_position` in seconds:** verifies with the Cubase seconds display and places the locators via the cursor. **Fixes** locators in seconds, which previously ended up at a different position.
- **Project properties** (TW-1209):
  - `cubase_get_project` tool: time signature, cycle, punch, pre-roll and post-roll, metronome, count-in, transport state, record modes and project folder;
  - `cubase_record_automation` uses the project's time signature instead of assuming 4/4.
- **Autostart** (TW-1201):
  - `trackwright serve` starts the bridge if it isn't running (`[bridge] autostart`, enabled by default), without duplicating it;
  - `cubase_launch` tool, which opens Cubase (optionally with a project) and waits for the script;
  - `[cubase]` configuration section.
- **Real units in automation** (TW-1208):
  - `cubase_record_automation` points accept `plain` (dB, Hz…), which Cubase converts exactly;
  - new read-only tool `cubase_convert_value`;
  - `cubase_list_automation_targets` states whether each parameter supports real units (`converts_units`).
- **Automation** (TW-1207):
  - `cubase_list_automation_targets` and `cubase_record_automation` tools: record volume, pan, send, channel EQ, pre-filter and insert plugin parameter curves by playing the project, with optional verification;
  - **script 1.4.0**, with 45 active automation controls on the surface and the `auto.control` and `auto.list` operations;
  - the simulator plays back and records automation.
- **Script 1.2.2:** `Transport / Start` and `Stop` commands (`transport.start`, `transport.stop`), to play without user intervention. It never records.
- **Script 1.2.1:** experimental automation fader (TW-1206, variant B2), **disabled** (`AUTOMATION_FADER_ENABLED = false`), and the `auto.fader` operation, which answers `UNSUPPORTED` while disabled. The test version is generated with `experiments/tw1206/build.py`.
- **Script 1.2.0:** automation commands (Touch, Auto-Latch and Cross-Over modes, next mode and write on the selected tracks) for the TW-1206 experiment. Class `unknown` until observed.
- **Script 1.1.0:** status panel on the MIDI Remote surface (TW-1101): title with the version, selected track and activity lamp. It only uses mechanisms verified in Cubase 15. The operations don't change.
- **TW-1101 experiment** (`experiments/tw1101/README.md`): protocol and results, in `docs/verification.md`.
- **`trackwright script install --file <script>`:** installs another script, such as the experiment's.
- **Simulator:** "Locate Next Marker" with no next marker goes to the end of the last event, as in Cubase 15.

## 0.1.0 — 2026-11-12

First version, based on the design verified in the `cubase-mcp-poc` proof of concept.

- **`trackwright` MCP server** with 21 tools: 9 read tools, 7 write and navigation tools, and 5 command-based tools.
- **MIDI Remote script** `Trackwright_Bridge.js` 1.0.0, with its installer (`trackwright script install`).
- **Bridge** with CoreMIDI virtual ports and IPC over a private Unix socket.
- **Security:** read-only by default, dry run (`dry_run`) on every write, verification by read-back, no retries and validated opaque references.
- **Simulator** `FakeCubase` and `trackwright serve --simulate` mode.
- **Diagnostics** `trackwright doctor`.
- **Tests:** unit, MCP contract, script tests with Node.js, end-to-end and optional integration tests against Cubase.
- **Documentation:** manuals, tutorials, architecture, development and issues.
- **Hardening** after an independent review (epic E10):
  - session pinned for the duration of each tool;
  - deletion only with a single selection;
  - lossless pagination of the parameter filter;
  - single deadline with `BUSY` in the bridge;
  - `INTERNAL_ERROR` with unknown result;
  - already-applied changes reported in partial errors;
  - `expectTitle` checked in the script.
