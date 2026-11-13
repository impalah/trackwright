# E05 — Read tools

**English** · [Español](E05-read-tools.es.md)

The tools follow the numbering of `mcp-design.md`. None of them modifies the project.

| Issue | Tool | Design | Evidence (POC) | Status |
|---|---|---|---|---|
| TW-0501 | `cubase_status` | no. 1 | findings 1–3 | done |
| TW-0502 | `cubase_list_tracks` | no. 10 | findings 28–29 | done |
| TW-0503 | `cubase_get_selected_channel` | no. 2 | findings 4–5 | done |
| TW-0504 | `cubase_list_inserts` | no. 3 | findings 6, 8 | done |
| TW-0505 | `cubase_list_available_plugins` | no. 4 | findings 7 | done |
| TW-0506 | `cubase_list_parameters` | no. 6 | findings 9–10 | done |
| TW-0507 | `cubase_get_parameter` | no. 7 | findings 9–10 | done |
| TW-0508 | `cubase_get_transport` | no. 14 | findings 33 | done |
| TW-0509 | `cubase_poll_changes` | no. 9 | findings 16 | done |

## Common acceptance criteria

- Input and output are pydantic models, and the published schema matches the design.
- Tracks are addressed with `TrackRef`. Objects are returned with an opaque `ref`, **never** with bare runtime IDs.
- There are tests against `FakeCubase` for the success case, errors (nonexistent track, empty slot, deleted object, bridge unavailable) and pagination.
- There is a contract test with the in-memory MCP client for each tool.

## Per-tool notes

- **`cubase_list_tracks`:**
  - deduplicates by ID;
  - does not show tracks without a mixer channel (markers, folders), and documents this.
- **`cubase_get_transport`:**
  - uses the **primary** display;
  - warns if no callback has arrived yet (`UNAVAILABLE`).
- **`cubase_list_inserts`:**
  - an empty slot has `children == 0`;
  - the plugin UID is the `uniqueName` without the `-N` suffix.
