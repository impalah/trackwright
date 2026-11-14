# Architecture

**English** · [Español](architecture.es.md)

## Components

```text
┌──────────────┐  stdio (MCP)   ┌────────────────────┐  Unix socket 0600   ┌─────────────────────┐
│ MCP client   │ ─────────────► │ trackwright serve  │ ──────────────────► │ trackwright bridge  │
│ (Claude)     │ ◄───────────── │ MCPServer          │ ◄────────────────── │ HostClient          │
└──────────────┘                │ CubaseService      │  JSON per line      │ MidiTransport       │
                                │ WritePolicy        │                     └─────────┬───────────┘
                                └────────────────────┘                               │ SysEx "TW"
                                                                                     │ CoreMIDI virtual ports
                                                                           ┌─────────▼───────────┐
                                                                           │ Cubase              │
                                                                           │ Trackwright_Bridge.js│
                                                                           │ DirectAccess, Plugin│
                                                                           │ Manager, commands   │
                                                                           └─────────────────────┘
```

| Component | Responsibility |
|---|---|
| `trackwright serve` | MCP server over stdio. One per client session. Contains the tool logic (`core/`) and the write policy. |
| `trackwright bridge` | Long-lived process and **sole owner** of the MIDI ports. Correlates requests and responses, manages the script session and never retries writes. |
| `Trackwright_Bridge.js` | ES5 script inside Cubase. Answers operations that do not need DirectAccess in `mOnSysex` and queues the rest for `page.mOnIdle`, which is where `activeMapping` is available. |

## Flow of a request

Example: `cubase_set_track_mix(track="POC-TEST", mute=true, dry_run=false)`.

1. `server.py` receives the call and runs it in a worker thread, because the request is blocking.
2. `CubaseService.set_track_mix` resolves the track with `da.channels` over the full, deduplicated mixer. It then reads the current value (`da.param.get`), checks the policy (`WritePolicy.check_track`) and writes with `da.param.set`.
3. `BridgeHost` sends each operation to the bridge over the socket. The bridge hands it to the `HostClient`, which fragments it into SysEx frames and waits for the response with the same `rid`.
4. The script queues the write, runs it on the next idle cycle (about 112 ms), reads the value back and responds.
5. The service compares the read-back value with the requested one and returns `WriteOut(verified=true)`.

## Decisions and the evidence behind them

The evidence is in `cubase-mcp-poc/docs/findings.md` and `progress.md`.

| Decision | Reason |
|---|---|
| Bridge separate from the MCP server | The virtual ports have fixed names and there can be only one owner; several MCP sessions share them through the bridge. Cubase reconnects on its own if the bridge restarts (verified). |
| Session pinned for the duration of each tool | The bridge renegotiates the session transparently on reads; without pinning, a write after a reload could carry an old identifier that now names a different object (finding TW-1001). Since TW-1402 every write carries the pinned session through the bridge to the script, which refuses it with `STALE_SESSION` if it reloaded, even when another client renegotiated the bridge's session in between. |
| Opaque references with session and fingerprint | Internal identifiers are reused for other objects after the script reloads (verified: ID 550 went from Compressor to Input Filter). |
| `uid:` selectors for tracks | The channel's `getObjectUniqueIDString` stayed the same across restarts (verified). |
| DirectAccess over `mMixConsole` | Gives access to all tracks without selecting them. The identifiers are valid in both instances (verified). |
| Mixer deduplication | The last child of "VST Mixer" repeats the last channel (verified twice). |
| Writes without retry and a single deadline | After a timeout, the write may have been executed (verified with late responses). The wait for the write lock and the renegotiation count toward the deadline; if the lock is not released in time, `BUSY` without sending. |
| Suppression of in-flight duplicates, in the script | A duplicate in a burst was executed twice; fixed and verified. |
| Rejection of writes outside [0, 1] | Cubase clamps them to that range; the routing (22) cannot be written back (verified, with an incident). |
| Automation with "touched" surface controls | Writing the parameter through DirectAccess moves the value but does not record. A surface fader bound to the parameter, with its touch state controlled by the script, does record in Touch mode, like a physical controller (TW-1206 and TW-1207, verified in Elements). |
| CoreMIDI transport with `ctypes` | `python-rtmidi` is only distributed as source for macOS and requires compiling it (Xcode). With `ctypes` over CoreMIDI, the package is pure Python. The mido + rtmidi transport is kept as an alternative (`[bridge] backend`). Verified with Cubase (TW-1302). |
| Command classes | Commands return no result; some open dialogs and others act on the UI selection (verified). |
| Write policy with read-only by default | The model can make mistakes: the user decides what may be touched. |
| `FakeCubase` simulator | Fast, reproducible tests; a `--simulate` mode for learning without risk. It never counts as evidence about Cubase. |

## Performance

Measured in the POC:

| Operation | Cost |
|---|---|
| Responding in `mOnSysex` (`hello`, `status`, `transport.get`) | 3–18 ms |
| One DirectAccess operation | One idle cycle: about 110 ms in series |
| `da.channels` (up to 32 channels with their main parameters) | A single cycle, 134 ms |
| `cubase_list_inserts` | About 10 cycles, around 1.1 s |

Batching operations inside the script is the main avenue for improvement.

## Security

- No network port is opened. The socket lives in a private directory (0700) under `$TMPDIR`, with permissions 0600.
- The bridge only accepts operations from an allowlist, lines of at most 64 KiB, and bounded timeouts.
- By default the server is read-only. Writes require explicit configuration and can always be rehearsed first.
- The script only saves the project on explicit request and with its own permission (`[writes] save`). It only starts playback to record automation, and never records audio.

## Extension to other DAWs (possible, not implemented)

**Decision (2026-11-13):** for now Trackwright only controls Cubase and **no DAW abstraction is introduced** (YAGNI). An interface derived from a single DAW would end up shaped like that DAW. It will be designed when there is a concrete second DAW, with a prototype against its real API, as was done with Cubase in the proof of concept. When that happens, breaking internal interfaces is acceptable.

### What can be reused today

| Layer | Modules | Reusable |
|---|---|---|
| MIDI transport and SysEx frames | `coremidi.py`, `transport.py`, `protocol.py` | Yes, for any DAW scriptable over MIDI |
| Bridge and local channel | `bridge.py`, automatic startup, sessions | Almost entirely; the allowlist (`ops.py`) is Cubase-specific |
| Port to the DAW | `HostPort.call(op, params)` | The shape, yes; the vocabulary (`da.*`, `pm.*`, `cmd.run`) is Cubase's MIDI Remote API |
| Domain | `core/` (`CubaseService` and its mixins) | No: DirectAccess *tags*, `Inserts` and `Strips` sections, Cubase commands and workarounds for its behavior (ranges with the Range tool, edge probing…) |
| MCP tools | `server.py` | No: it takes a `CubaseService` and the tools are named `cubase_*` |
| Cross-cutting | `policy.py`, `errors.py`, `core/models.py` | Largely: write policy, errors with codes, track and parameter models |
| Installation | `launcher.py`, `installer.py`, `doctor.py`, `[cubase]` and `[script]` sections | The structure; the content is Cubase-specific |

The most transferable parts are the **principles**: rehearsal before writing (`dry_run`), verification by reading back, no retrying of writes with an uncertain outcome, session pinned for the duration of each operation, and classification of each command by its observed behavior.

### Planned path

1. Move the Cubase-specific parts to `trackwright/daws/cubase/`: service, operations, script, launcher, simulator and `doctor` checks.
2. Keep the transport, the bridge, the policy, the errors and the common models in the core.
3. One `HostPort` per DAW, with whatever transport its API allows.
4. `server.py` registers the tools of the configured DAW (for example, `[daw] kind = "cubase"`).
5. **Tool names prefixed by DAW** (`cubase_*`, `ableton_*`, `protools_*`), reflecting what each one really does. A small common set (tracks, transport, markers, basic mixing) can be added later, with capability flags.

### Candidates (not verified in this project)

- **Ableton Live:** Python *Remote Scripts* inside Live, over its object model (tracks, devices, parameters, clips).
  - It could reuse the SysEx transport. The usual OSC/UDP alternatives open a network port, which conflicts with the security rule.
  - It is strong in mixing and devices and more limited in timeline editing (*Arrangement*).
- **Pro Tools:** it has no MIDI scripts; it offers **PTSL** (Pro Tools Scripting Library), a local gRPC API.
  - It would need a different `HostPort` and would not use the MIDI bridge.
  - It is strong in session, tracks, clips, editing, import and export, and more limited in plugin parameter control.

Before designing anything, each candidate needs its own proof of concept that measures what it really exposes, as `cubase-mcp-poc` did with Cubase.
