# Changelog

**English** · [Español](CHANGELOG.es.md)

## 0.3.0 — prepared, pending publication on PyPI

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
