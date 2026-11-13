# E13 — Distribution

**English** · [Español](E13-distribution.es.md)

Origin: the user's question of 2026-11-13. Today Trackwright is used from the source code (`uv --directory … run trackwright`); the goal is to install it with **uv as the only requirement**.

**Status:** closed (2026-11-13). TW-1301, TW-1302 and TW-1303 done; Trackwright 0.3.0 is published on PyPI (tag `v0.3.0`).

**Checked before opening the epic** (2026-11-13, without publishing anything; tests in a temporary directory, since deleted):
- `uv build` produces `trackwright_mcp-0.2.0-py3-none-any.whl`, with `trackwright/cubase/Trackwright_Bridge.js` inside and the `trackwright` executable;
- `uvx --from <wheel> trackwright version` and `script status` work outside the repository;
- `uv tool install <wheel>`, in an isolated directory: `trackwright version` and `doctor` correct against the running bridge;
- **obstacle:** the lock only has **source code** for `python-rtmidi` 1.5.8. On a clean Mac it would have to be compiled, and that requires the Xcode tools. It works on the user's Mac because uv already has it compiled in its cache.

## TW-1301 Guided installation: `trackwright setup`

- **Status:** done (2026-11-13). Verified on the user's Mac; details in [verification.md](../verification.md)
- **Implementation:** `trackwright/installer.py` (steps, questions on stderr and a JSON summary on stdout) and `trackwright/doctor.py` (the diagnostics, shared with `doctor`). The command it registers in Claude Code depends on how it is run: from the repository, `uv --directory <repo> run trackwright serve`; installed with `uv tool`, the absolute path of `trackwright`.
- **Goal:** after installing the package, a single command leaves everything ready.
- **Steps**, each one with what is going to be done (destination, content and file that would be replaced) and **confirmation** before applying it:
  1. install or update the script in Cubase's MIDI Remote folder (what `script install --apply` does today);
  2. create `~/.config/trackwright/config.toml` if it does not exist, asking whether writes and saving are enabled (by default, no);
  3. register the server in Claude Code (`claude mcp add --scope user trackwright -- trackwright serve`), only if `claude` is on the PATH, and otherwise show the command;
  4. final check with `doctor`.
- **Non-interactive mode:** `--yes` for each step separately; never by default.
- **Does not:** install or change anything in Cubase other than the script; enable IAC or Accessibility; use `sudo`.
- **Tests:** unit tests with the destinations in temporary directories and the answers mocked.

## TW-1302 MIDI transport with CoreMIDI via `ctypes` (no compilation)

- **Status:** done (2026-11-13). Verified with Cubase; details in [verification.md](../verification.md)
- **Goal:** nothing needs to be compiled on macOS: the package becomes pure Python.
- **Scope:**
  1. a new transport, `CoreMidiTransport`, with `ctypes` over `CoreMIDI.framework` and `CoreFoundation.framework`:
     - a virtual output port (`MIDISourceCreate`) and an input one (`MIDIDestinationCreate`, with a callback);
     - sending SysEx;
     - checking for duplicate names, as now;
  2. the same `Transport` interface as the current one; `run_bridge` uses the new one on macOS.
- **User requirement: «conservar el código de `rtmidi`»** (*keep the `rtmidi` code*).
  - `MidiTransport` (mido + python-rtmidi) **is not deleted**: it remains as an alternative (for example, for testing on Windows) and can be chosen through configuration (`[bridge] backend = "coremidi" | "rtmidi"`);
  - only the necessary imports are changed: the `mido` import remains lazy, inside `MidiTransport`;
  - in `pyproject.toml`, the `mido` and `python-rtmidi` dependencies are **commented out**, not deleted, with a note on how to re-enable them;
  - the `MidiTransport` tests, with the mocked backend, are kept.
- **Verification in Cubase**, mandatory before closing:
  - Cubase sees the «Trackwright To/From Cubase» ports and the script connects;
  - `ping`, `doctor`, and one read and one write with the tools;
  - large messages (SysEx fragmentation), as in E02.
- **Risks:** the input callback on a CoreMIDI thread (do not block and do not raise exceptions outward) and the lifetime of the `ctypes` objects (prevent the garbage collector from freeing the callback).

## TW-1303 Distribution channel

- **Status:** done (2026-11-13). The user published 0.3.0 on PyPI with `make publish`; tag `v0.3.0`. Details in [verification.md](../verification.md)
- **User decision (2026-11-13):** publish on **PyPI** under the name **`trackwright`** (available on PyPI and TestPyPI that day), license **AGPL-3.0-or-later** (`-only` was chosen first; changed before publishing), author «impalah» with their email.
- **Done:**
  - package renamed (`trackwright-mcp` → `trackwright`), version 0.3.0, `LICENSE` with the official text, and classifiers;
  - the `trackwright-mcp` alias from item 3 is no longer needed: `uvx trackwright serve` works with the new name;
  - `setup` chooses the registration command: the `uv tool` path, the repository, or `uvx` pinned to the version;
  - README for the end user, installation manual with PyPI as the main route, and tutorial 1 updated;
  - `twine check --strict` passes; isolated installation of the wheel with `uv tool install` (`version`, `doctor`, `setup`) and `uvx` checked.
- **Published (2026-11-13):** https://pypi.org/project/trackwright/ — the uploaded files are identical (SHA-256) to the local build of the tagged commit.
- **Lesson about credentials:** the first upload failed with `403 Invalid or non-existent authentication information` because the interactive prompt of `security add-generic-password -w` keeps only 128 characters, and PyPI tokens are longer. The token must be stored from the clipboard (`-w "$(pbpaste)"`); see the release procedure in [development.md](../development.md).
- **Goal:** document and implement the way to install without the repository.
- **Scope:**
  1. **local wheel:** `uv build` and `uv tool install dist/trackwright_mcp-<version>-py3-none-any.whl`; update with `--reinstall`;
  2. **`uvx`:** register the server as `uvx --from <source> trackwright serve`;
  3. a `trackwright-mcp` executable alias, so that `uvx trackwright-mcp serve` works if it is published;
  4. **user decision,** without which nothing is done: publish on PyPI (public), in a *release* of a remote repository (there is none today) or only with the local wheel. Before publishing, review the metadata (author, links) so as not to expose personal data;
  5. installation manual rewritten for the end user, plus a tutorial.
