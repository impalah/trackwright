# E03 — Trackwright MIDI Remote script

**English** · [Español](E03-midi-remote-script.es.md)

Goal: the ES5 script that runs inside Cubase and exposes the operations verified in the POC (script 0.2.2), with its own identity.

## TW-0301 Port of the POC script

- **Status:** done
- **Scope:** `src/trackwright/cubase/Trackwright_Bridge.js`, shipped as package data.
  - Vendor `Trackwright` and device `Bridge`.
  - Ports `Trackwright To Cubase` and `Trackwright From Cubase`.
  - SysEx marker `TW`.
  - Same operations as version 0.2.2:
    - reads: `hello`, `ping`, `status`, `capabilities`, `events`, `transport.get` and `cmd.list`;
    - DirectAccess: `da.*`;
    - Plugin Manager: `pm.*`;
    - selection: `sel.step`;
    - transport: `transport.setTime` and `transport.setTempo`;
    - commands: `cmd.canPerform` and `cmd.run`.
  - Suppression of in-flight duplicates and mixer deduplication.
  - The `raw` option is removed; it was verified to have no useful effect (`findings` 41).
  - The `da.param.probe` probe is removed: no tool uses it and it was the source of the routing incident in the POC. Writes outside [0, 1] are rejected with `BAD_REQUEST`.
- **Acceptance:**
  - `node --check` passes with no errors.
  - Loads without exceptions with a mocked API (TW-0302).

## TW-0302 Script tests with Node.js

- **Status:** done
- **Scope:**
  - Harness in `tests/script/` that emulates the MIDI Remote API: page, `mOnIdle`, DirectAccess with an in-memory tree, Plugin Manager, transport and commands.
  - Runs the real script without Cubase.
  - A pytest test (marker `node`) launches the harness and validates the protocol end to end with the Python encoder.
- **Acceptance:**
  - Covers `hello`, parameter read, write and read-back, `INVALID_OBJECT`, `STALE_SESSION`, sequential and in-flight duplicate, mixer deduplication, rejection of values outside [0, 1], selection, transport, commands, plugin insertion and consistency of the operation list with `trackwright.ops`.
  - Verified that the tests detect an altered SysEx marker: 16 of 17 fail.
  - Skipped, with a clear reason, if `node` is not installed.

## TW-0303 Script installation

- **Status:** done
- **Scope:** command `trackwright script install`.
  - By default, a **dry run**: shows the destination (`~/Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/trackwright/bridge/Trackwright_Bridge.js`), whether it exists and whether it matches.
  - With `--apply`, copies the script.
  - `trackwright script status` compares the installed script with the packaged one.
- **Acceptance:**
  - Tests with a temporary destination directory: dry run, copy, already up to date and different version.
  - Never writes outside the destination.
