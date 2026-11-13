# E02 — Communication with Cubase

**English** · [Español](E02-communication.es.md)

Goal: carry requests and responses between Python and the MIDI Remote script reliably, with the robustness verified in milestone H of the POC.

POC evidence: `docs/protocol.md` and `findings.md`, sections 8 to 10 (reconnection, timeouts, duplicates, sessions, Identity Request).

## TW-0201 SysEx protocol

- **Status:** done
- **Scope:** `trackwright.protocol`.
  - Frame `F0 7D 54 57 <ver> <seq_hi> <seq_lo> <idx> <count> <payload ASCII> F7`, with the **`TW`** marker (0x54 0x57). It differs from the POC's (`CP`), so they cannot be confused.
  - Fragments of at most 240 bytes, and 64 fragments per message.
  - Out-of-order reassembly, with duplicates ignored, at most 16 pending messages and a 5 s expiry.
  - JSON payload in ASCII, with `\uXXXX` for non-ASCII characters.
- **Acceptance:**
  - Round-trip tests (including Unicode and the maximum size).
  - Rejection tests: bytes > 127, short header, version, indices, counts and foreign frames such as the Identity Request `F0 7E 7F 06 01 F7`.
  - Tests for expiry and the pending limit.

## TW-0202 Virtual MIDI transport

- **Status:** done
- **Scope:**
  - `trackwright.transport.MidiTransport`: mido + rtmidi, with two CoreMIDI virtual ports, `Trackwright To Cubase` and `Trackwright From Cubase`.
  - Counters for sent, received and foreign frames.
  - Refuses to open if ports with those names already exist (another bridge running).
- **Acceptance:**
  - Tests with a mocked mido: opening, sending, receiving, filtering of non-SysEx messages and name conflict.
  - A manual test with real CoreMIDI is documented in the troubleshooting manual.

## TW-0203 Host client

- **Status:** done
- **Scope:** `trackwright.host.HostClient`.
  - Correlation by `rid`.
  - Per-request timeout; writes have an unknown outcome and are **not retried**.
  - Logging of late and unsolicited responses.
  - Session negotiation (`hello`) and automatic renegotiation on `STALE_SESSION` **for reads only**.
  - Serialized writes.
- **Acceptance:** tests with a mocked transport that reproduces:
  - concurrent correlation;
  - read and write timeout;
  - late response without misattribution;
  - stale session;
  - duplicates.

## TW-0204 Bridge (daemon) and local IPC

- **Status:** done
- **Scope:**
  - `trackwright.bridge`: long-lived process that owns the ports and the `HostClient`.
  - Unix socket server at `$TMPDIR/trackwright-<uid>/bridge.sock`, with directory 0700 and socket 0600. **No network port.**
  - Request: one JSON line of at most 64 KiB.
  - Operation allowlist and timeout validation (0.05–30 s).
  - Local operation `bridge.status`.
  - `BridgeClient` client, which the MCP server uses to talk to the bridge.
- **Acceptance:** tests with a real socket in a temporary directory and a mocked host:
  - permissions;
  - allowlist;
  - line too long;
  - invalid JSON;
  - bridge unavailable;
  - second bridge on the same socket.
