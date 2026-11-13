# E10 — Hardening after the independent review

**English** · [Español](E10-hardening.es.md)

Origin: independent code review of 2026-11-12, done by an agent with no prior context. Each finding was checked in the code before its issue was opened. All of them require a test that reproduces the failure.

## TW-1001 Script reload during a tool → write to a different object

- **Status:** done
- **Severity:** high.
- **Problem:** `HostClient.call` renegotiates the session and retries reads after `STALE_SESSION`. A tool gathers IDs across several calls. If the script reloads in between, a later write travels with the new session and an ID from the old one, and IDs are reused.
- **Solution:** each tool pins the session on its first call. If a later response carries a different session, the tool stops with `STALE_SESSION` **before** any write.

## TW-1002 `remove_selected_tracks` with several tracks selected

- **Status:** done
- **Severity:** high.
- **Problem:** it only checks `da.base`. "Remove Selected Tracks" deletes **all** selected tracks.
- **Solution:**
  - require exactly one track with parameter 4000 active, and that it be the expected one;
  - document that selected tracks without a mixer channel are not visible.

## TW-1003 `list_parameters` filter: lost matches and wrong `truncated`

- **Status:** done
- **Problem:** matches on a page beyond `limit` are lost, and `truncated` does not reflect it.
- **Solution:** iterate parameter by parameter, return `next_offset` (the index after the last one consumed) and `truncated` whenever parameters remain.

## TW-1004 Unprotected read-back in `insert_plugin`

- **Status:** done
- **Problem:** if the read-back after a write timeout also times out, the resulting error looks like a read error (`not_executed_or_lost`) and hides the fact that the write outcome is unknown.
- **Solution:** protect the read-back (`read_back_error`) and keep the write error.

## TW-1005 Time budget in the bridge

- **Status:** done
- **Problem:** waiting for the write lock, the `hello` and the retry are not counted within the timeout. The client may give up while the bridge executes the write later.
- **Solution:**
  - a single deadline per request, from which each sub-request uses only what remains;
  - if the write lock is not released in time, respond `BUSY` without executing.

## TW-1006 `set_track_mix` loses the changes already applied if a later one fails

- **Status:** done
- **Solution:** attach `applied` to the error with the changes already made.

## TW-1007 `add_track_interactive` confirms a track that already existed

- **Status:** done
- **Solution:** the `start` phase rejects existing names with `NAME_CONFLICT`.

## TW-1008 `poll_changes` marks unchecked objects as invalid

- **Status:** done
- **Solution:** `still_valid` becomes `null` when it is not checked, and the number of unchecked events is reported (`unchecked`).

## TW-1009 `expect_title` must be checked in the script, atomically

- **Status:** done
- **Solution:** send `expectTitle` in `da.param.set`. The Python check is kept for dry runs.

## TW-1010 Unexpected exceptions in the bridge

- **Status:** done
- **Problem:** `Bridge.handle` only catches `TrackwrightError`. Any other exception closes the connection without a response and the client reports `BRIDGE_UNAVAILABLE`, which suggests nothing was executed.
- **Solution:** respond `INTERNAL_ERROR`, with `outcome: unknown` for writes.

## TW-1011 Response arriving just as the timeout expires

- **Status:** done
- **Problem:** if the response arrives between the end of the wait and the removal of the pending request, it is lost: it is neither returned nor moved to `late_responses`.
- **Solution:** after a failed wait, check for the response under the lock and, if it has arrived, use it.

## TW-1012 Checks too early after triggering a command

- **Status:** done
- **Problem:** `remove_selected_tracks` and `select_track` read the state as soon as they trigger the command, and the effect may arrive a moment later.
- **Solution:** use `wait_until`.

## TW-1013 Consistency between the code and the manual

- **Status:** done
- **Problems:**
  - **References:** no tool accepts `ref`; the manual says they are validated before use, and `resolve_ref` is dead code.
  - **`dry_run`:** the manual says every write has `dry_run`, but `add_track_interactive` does not.
  - **Locators:** `split_at_locators` overwrites the locators without reporting it.
- **Solution:**
  - `ref` values are informational: `resolve_ref` is removed and the manual is corrected;
  - the `add_track_interactive` exception is documented;
  - `split_at_locators` reports the previous locators (`previous_left` and `previous_right`), but does **not** restore them: doing so right after triggering the command could get ahead of it, because Cubase executes it in its own cycle. This decision departs from the review's suggestion.
  - Minor: `offset ≥ 0` in `cubase_list_tracks`.

## TW-1014 The default installation path was not expanded

- **Status:** done
- **Severity:** high. Detected during the first installation on the user's machine (2026-11-12).
- **Problem:** pydantic does not run validators on default values. `[script] install_dir` kept the literal `~`, and `trackwright script install --apply` copied the script to `./~/Documents/…` **inside the repository**, while reporting `up_to_date`. The tests did not catch it because they always passed `--dir` with an absolute path.
- **Solution:**
  - `validate_default=True` on `install_dir` and `socket_dir`;
  - `install_script` rejects relative paths;
  - regression tests: the default paths are absolute and the default destination is under `$HOME`.
- **Cleanup:** the `./~` folder created by mistake, which contained only that file, was deleted, and the script was reinstalled at the correct path.
