# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

**Trackwright** is an independent MCP server for controlling DAWs. The only implementation today is **Cubase** (15.0.20+, verified on Cubase Elements 15.0.30, macOS 27.2 Apple Silicon). Package and executable: `trackwright` (published on PyPI: 0.3.0, tag `v0.3.0`; 0.4.0 prepared, requires Cubase script 1.6.0; release procedure in `docs/development.md`). License AGPL-3.0-or-later. Author: impalah.

Chain: `MCP client ──stdio──► trackwright serve ──Unix socket──► trackwright bridge ──virtual MIDI (SysEx "TW")──► Cubase MIDI Remote script (Trackwright_Bridge.js)`.

- `serve` autostarts the bridge if it is not running (`[bridge] autostart`, flock lock).
- The bridge owns the two virtual ports `Trackwright To Cubase` / `Trackwright From Cubase`, created with CoreMIDI through `ctypes` (`coremidi.py`, pure Python, nothing to compile). The mido + python-rtmidi transport (`transport.py`) is kept on purpose for Windows or as a fallback (`[bridge] backend = "rtmidi"`); its dependencies are commented out in `pyproject.toml`. **Do not delete the rtmidi code.**
- The Cubase script is ES5 JavaScript shipped inside the package (`src/trackwright/cubase/Trackwright_Bridge.js`).

## Commands

The `Makefile` wraps the usual tasks through uv (`make help`): `make check`, `make test`, `make build`, `make dist-check`, `make doctor`, `make clean`… The underlying commands:

```sh
uv sync
scripts/check.sh                 # ruff check + ruff format --check + mypy strict + pytest with coverage (>= 95 %)
uv run pytest tests/unit/test_docs.py   # documentation consistency
uv run trackwright doctor        # read-only check of the whole chain against the real Cubase
uv build                         # dist/ (wheel + sdist); check with: uvx twine check --strict dist/*
```

CI: `.github/workflows/ci.yml` (GitHub Actions, macOS) runs the same gates on every push and PR.

Integration tests against the real Cubase are opt-in: `TRACKWRIGHT_INTEGRATION=1` (reads), plus `TRACKWRIGHT_ALLOW_WRITES=1 TRACKWRIGHT_TEST_TRACK="POC-TEST"` (reversible writes). See `docs/development.md`.

## Code map

- `cli.py` (commands), `installer.py` (`trackwright setup`), `doctor.py`, `config.py` (TOML + pydantic, `~/.config/trackwright/config.toml`), `launcher.py` (bridge and Cubase launchers).
- `protocol.py` (SysEx framing), `coremidi.py` / `transport.py`, `bridge.py` (daemon + client), `host.py`, `hostport.py`, `ops.py` (script operations: read vs write allowlist).
- `core/`: `CubaseService` built from mixins (reading, writing, commanding, automation, project, settings, ranges, exporting, importing, saving, presets, lifecycle), `policy.py` (write policy), `models.py`, `refs.py`.
- `server.py`: registers the 32 `cubase_*` MCP tools. `commands.py`: Cubase commands with their observed class (`direct`, `dialog`, `confirm`, `ui_selection`, `unknown`); keys must match `COMMANDS` in the script.
- `fake.py`: `FakeCubase` simulator (tests and `serve --simulate`). Passing against it proves nothing about real Cubase.
- `experiments/twNNNN/`: throwaway probes against real Cubase, each with a README of what was observed.

## Project rules (from the user)

- **Toolchain: uv only.** Never pip, `uv pip`, venv, virtualenv, pipx, conda, poetry or requirements.txt. Never install anything globally; never use `sudo`.
- **Logging with loguru, to stderr.** Never write to stdout from `serve` (it is the MCP channel); CLI commands print JSON on stdout.
- **Quality:** ruff, mypy strict, coverage ≥ 95 % (currently ~98 %). Code identifiers, logs and CLI messages in English.
- **Documentation is bilingual:** every document is English `X.md` plus Spanish `X.es.md`, updated together, each linking to its counterpart near the top; links stay in their language. `README.md` is also the PyPI page: no relative links there. `tests/unit/test_docs.py` enforces this, and that every tool, command key and config key is documented.
- **Issues** live in `docs/issues/` (epics E01–E13, issues TW-NNNN); every change starts from an issue and its commit cites it. Results observed in real Cubase go to `docs/verification.md` (+ `.es.md`).
- **Git:** remote `origin` = `git@github.com:impalah/trackwright.git` (branch `main`, tags `vX.Y.Z`). Commit and push only when asked; never force-push. Commit with
  `git -c user.name="impalah" -c user.email="impalah@gmail.com" commit`. **Never add `Co-Authored-By` lines (or any AI attribution) to commits or PRs.** Commit messages in English (since 2026-11-13; older ones are in Spanish).
- **Never invent results.** Do not claim a test ran, a Cubase behavior, a version or a measurement that was not observed. Keep "tested with Claude Code and Cubase" statements truthful; untested things (e.g. GitHub Copilot) are marked as such.
- **YAGNI on multi-DAW:** no DAW abstraction until a second DAW is real; the planned route is in `docs/architecture.md` ("Extension to other DAWs").

## Safety with the user's Cubase

- **Ask before** copying a script into `~/Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/...`: show destination, content/version and the file it replaces. After installing, **Cubase must be restarted** (it does not reload scripts).
- Bump `SCRIPT_VERSION` in the script on every script change.
- Do not change Cubase or system settings, enable IAC or Accessibility, close/force-quit Cubase, inject into its process, open network ports, create MIDI loops, or send to "All MIDI Inputs" or physical devices.
- Do not save or overwrite projects unless the user asks (`cubase_save_project` needs `[writes] save`). Do not modify the user's project files on disk; the user cleans the test project. Use the disposable test project and its `POC-TEST` track for write experiments.
- **Never retry a write whose outcome is uncertain after a timeout.** A request is retried (after autostarting the bridge) only if it never reached the bridge (`details.sent=False`).
- Do not read personal projects or audio content beyond what the task needs; do not dump environment variables or credentials.
- Publishing (PyPI, any remote) is the user's decision and is done by the user with their own token.

## Cubase / MIDI Remote facts learned the hard way

- DirectAccess object ids are only valid within one script session; tools pin the session (`@operation`) and stop with `STALE_SESSION` if the script reloads mid-operation.
- Commands return no result: only `canPerform` and state read afterwards. Many act on the GUI selection/focus, which the API cannot see.
- DirectAccess operations run in the idle tick (~110 ms each); `hello`/`status`/`transport.get` answer in `mOnSysex` (ms).
- Dialog-opening tools (import audio, export mix, add track) are two-phase (`start` → user completes the dialog → `confirm`). The macOS file selector blocks Cubase, so requests time out while it is open.
- Cubase's display strings follow its UI language (the user's Cubase is in Spanish: `Activ.`/`Desact.`, "Edición" = slot param tag 4101 that opens the plugin editor).
- Locators cannot be set via the seconds display: move the cursor and use Set Left/Right Locator. Range edits use the Range tool + Select in Loop; single-track edits must handle the "auto-select events under cursor" preference.
- CoreMIDI delivers universal SysEx (`F0 7E …`) twice; Trackwright frames (`7D`) arrive once. Harmless.
- What the API cannot do: routing, reading track contents (events/audio/automation), completing dialogs, preset names.
