# E04 — MCP server core

**English** · [Español](E04-mcp-core.es.md)

Goal: the common layer shared by all tools. It implements the principles of `mcp-design.md`.

## TW-0401 Host port and Cubase simulator

- **Status:** done
- **Scope:**
  - `HostPort` protocol (`call(op, params, timeout) -> dict`), with two implementations:
    - `BridgeHost`, via IPC with the bridge;
    - `FakeCubase`, an in-memory simulator that reproduces the behaviors observed in the POC:
      - mixer tree with the last child duplicated;
      - IDs reused on restart;
      - sentinels for deleted objects;
      - writes limited to [0, 1];
      - single selection;
      - commands of class `direct`, `dialog` and `confirm`;
      - transport with bars format.
- **Acceptance:** the simulator has its own tests. It always declares itself as **simulated**: `capabilities.simulated = true`.

## TW-0402 Opaque references and track resolution

- **Status:** done
- **Scope:**
  - `TrackRef`: `{uid}`, `{name}` or `"selected"`.
  - Resolution against `da.channels` (mixer scope, with deduplication).
  - Errors `TRACK_NOT_FOUND` and `TRACK_AMBIGUOUS`.
  - `ObjectRef`: opaque string with the session, the ID and a fingerprint (`type` and `uniqueName`). It is validated before each use:
    - if the session has changed or the fingerprint does not match, `STALE_REF`;
    - if the object no longer exists (`children == -1`), `INVALID_OBJECT`.
  - Semantic paths within a track: `insert:N`, `strip:eq` and `channel`.
- **Acceptance:**
  - Resolution tests: by uid, by name, ambiguous, nonexistent and selected with no selection.
  - Reference tests: valid, different session, different fingerprint (the ID reuse from `findings` 8) and deleted object.

## TW-0403 Write policy and dry run

- **Status:** done
- **Scope:**
  - `WritePolicy`, built from the configuration:
    - writes disabled → `WRITES_DISABLED`;
    - track outside `allowed_tracks` → `NOT_ALLOWED`.
  - All write tools take `dry_run` (default `true`) and return the plan without touching anything.
  - Writes are **never retried**. A timeout is reported as an unknown outcome and the state is read back if possible.
- **Acceptance:** tests for each branch of the policy and of the dry run, verifying that no write operation is called.

## TW-0404 MCP server

- **Status:** done
- **Scope:** `trackwright.server`.
  - `MCPServer` named `trackwright`, with instructions for the model: dry run first, confirm with the user, and explain dialog commands.
  - Tool registration.
  - Conversion of `TrackwrightError` into `ToolError` with the format `CODE: message`.
  - stdio transport with `trackwright serve`.
- **Acceptance:** tests with an in-memory `mcp.client.Client`:
  - list of tools, with their names and schemas;
  - successful call;
  - tool error with `is_error`.
