# E07 — Tools based on Cubase commands

**English** · [Español](E07-command-tools.es.md)

Commands are triggered from the script and **return no result**. Each command has an observed class, which the tool exposes:

| Class | Behavior |
|---|---|
| `direct` | acts directly |
| `dialog` | opens a dialog; the user must complete it |
| `confirm` | may ask for confirmation |
| `unknown` | no evidence |

| Issue | Tool | Design | Evidence (POC) | Status |
|---|---|---|---|---|
| TW-0701 | Command registry with classes | principles 10–11 | phase 4 and 2b | done |
| TW-0702 | `cubase_run_command` | no. 18 | findings 35 | done |
| TW-0703 | `cubase_markers` | no. 16 | findings 37 | done |
| TW-0704 | `cubase_remove_selected_tracks` | no. 17 | findings 38 | done |
| TW-0705 | `cubase_split_at_locators` | no. 20 | findings 45 | done |
| TW-0706 | `cubase_add_track_interactive` | no. 21 | findings 42 | done |

## Common acceptance criteria

- Write policy and `dry_run` as in E06.
- **A `dialog`-class command is never presented as completed.** The tool returns `awaiting_user` and an instruction for the user.
- If the effect can be read, it is verified (tracks, selection, transport). If not, `verified: "not_observable"`, explicitly.
- `canPerform = false` becomes `CANNOT_PERFORM`, except with `force`, which only `cubase_run_command` accepts.

## Notes

- **`cubase_remove_selected_tracks`:**
  - requires `expect_selected` and checks that it matches the selection **exactly** (`SELECTION_MISMATCH`);
  - if the track is still listed after the command, it returns `pending_confirmation`, because Cubase asks for confirmation when there are events.
- **`cubase_add_track_interactive`:**
  - in two phases: `start` triggers the command and returns `awaiting_user`; `confirm` looks for the new track by name;
  - folders have no mixer channel, so in that case verification is visual.
- **`cubase_split_at_locators`:**
  - writes and reads back the locators before triggering `Split Loop`;
  - warns that it affects **all** tracks with events in the range.
