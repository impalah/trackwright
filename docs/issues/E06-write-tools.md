# E06 — Write tools

**English** · [Español](E06-write-tools.es.md)

All of them apply the write policy (TW-0403): `dry_run` by default, no retries and verification by read-back.

| Issue | Tool | Design | Evidence (POC) | Status |
|---|---|---|---|---|
| TW-0601 | `cubase_set_parameter` | no. 8 | findings 11–12 | done |
| TW-0602 | `cubase_insert_plugin` | no. 5 | findings 8 | done |
| TW-0603 | `cubase_set_track_mix` | no. 11 | findings 30 | done |
| TW-0604 | `cubase_rename_track` | no. 12 | findings 31 | done |
| TW-0605 | `cubase_select_track` | no. 13 | findings 32 | done |
| TW-0606 | `cubase_set_position` | no. 15 | findings 34 | done |
| TW-0607 | `cubase_set_tempo` | no. 19 | findings 43 | done |

## Common acceptance criteria

- With `dry_run=true`, the output contains the plan (current value, requested value and resolved target) and no write operation is called.
- With `dry_run=false`:
  - the value is written;
  - it is read back;
  - the output includes `before`, `after` and `verified`.
- Errors:
  - `WRITES_DISABLED` and `NOT_ALLOWED`, from the policy;
  - `PRECONDITION_FAILED`, `VERIFY_FAILED` and `STALE_REF`;
  - `TIMEOUT`, with `outcome: unknown`.
- There are tests for each error and for the success case, against `FakeCubase`.

## Per-tool notes

- **`cubase_set_parameter`:**
  - value in process units [0, 1], or `plain` via `da.convert`;
  - tolerance of 1e-3.
- **`cubase_insert_plugin`:**
  - the slot must be empty;
  - verified by the child's `uniqueName`, which is `<UID>-0`.
- **`cubase_set_track_mix`:**
  - tags 1025 (volume, process), 1027 (mute), 1028 (solo) and 4002 (record enable);
  - volume in dB is **not** offered: it is not verified.
- **`cubase_rename_track`:**
  - `setParameterDisplayValue(1024)`;
  - beforehand, it rejects names already used by another track (`NAME_CONFLICT`).
- **`cubase_select_track`:**
  - tag 4000 = 1, or the next/previous action;
  - verified with `da.base`.
- **`cubase_set_position`:**
  - bars through the primary display and seconds through the secondary one;
  - the read-back always comes in bars;
  - with seconds, it is verified using the tempo.
- **`cubase_set_tempo`:**
  - 20–300 BPM;
  - the read-back is float32, with a tolerance of 0.01.
