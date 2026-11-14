# E14 — Quality remediation

**English** · [Español](E14-quality-remediation.es.md)

**Epic status: pending.** Origin: the code-quality review of 2026-11-14, with every finding, its evidence and its location in [`docs/quality-review.md`](../quality-review.md). Finding IDs (C-xx, I-xx, S-xx, F-xx, T-xx, R-xx) refer to that document.

**Order:** four phases, by risk. Phase 1 fixes ways in which a write can bypass the user's configuration or a tool can report something that did not happen; it should be released before new features. Phases 1 and 2 together make version **0.4.0**: some changes alter tool schemas (C-04) and Trackwright is still alpha.

**Rules for the whole epic:**
- Every fix starts with a test that fails before the fix (most findings come with a ready test case).
- Changes to the Cubase script bump `SCRIPT_VERSION` and need the user's permission to install it (destination, content and replaced file), a Cubase restart and verification in Cubase, recorded in the verification log.
- Documentation in English and Spanish, updated together.

## Phase 1 — Safety and truthful results

### TW-1401 Close the write-policy holes

- **Status:** done (2026-11-14); tests in `tests/unit/test_write_policy_tw1401.py`; verified in Cubase (see verification.md)
- **Decisions:**
  - `cubase_run_command` refuses `file.save`, `file.save_new_version` and `project.remove_selected_tracks` with `USE_DEDICATED_TOOL`, even with permission: the dedicated tools check and verify more.
  - New `WritePolicy.check_all_tracks()`: anything that can change any track (Cubase commands acting on the window selection, range edits and splits on every track) is refused with `NOT_ALLOWED` while `allowed_tracks` is set.
  - Cycle locators need writes enabled; `cubase_set_position` keeps `dry_run=false` by default, like the other navigation tools (documented exception).
  - The routing guard inside the Cubase script moves to TW-1406 (script 1.6.0), to batch the script changes; the Python guard already covers every MCP path.
  - `edit.select_none` before *Select in Loop*: checked in Cubase with a range edit on the test project and undone (2026-11-14).
- **Findings:** C-01, C-02, C-03, C-08, C-10, C-09.
- **Scope:**
  1. `run_command`: per-key policy. `file.save` and `file.save_new_version` → `check_save()`. Keys that have a dedicated guarded tool (track removal, range edits) are refused, or allowed only when `allowed_tracks` is empty; document which.
  2. `edit_range` with `track=` → `check_track`; all-track `edit_range` and `split_at_locators` are refused with `NOT_ALLOWED` when `allowed_tracks` is set.
  3. `set_parameter` on target `channel`: refuse the input/output routing, name and selection tags (`READ_ONLY_PARAM`). Same guard in the script.
  4. `set_position` with cycle locators: `check_project_write()` and a dry run, or a documented exception (decision recorded in this issue).
  5. `remove_selected_tracks`: `CANNOT_PERFORM` when Cubase says it cannot.
  6. All-track range edits: `edit.select_none` before *Select in Loop* (verify in Cubase that it does not change the result).
- **Tests:** the policy cases listed in the review ("Policy tests missing"), including a contract test that every tool that modifies the project defaults to `dry_run=true`.
- **Verification in Cubase:** `file.save` refused with `save = false`; a single-track range edit refused outside `allowed_tracks`; routing tags refused.

### TW-1402 Writes always reach the object and session the caller saw

- **Status:** done (2026-11-14); tests in `tests/unit/test_session_pinning_tw1402.py`; verified in Cubase (see verification.md). The IPC request has an optional `session` field, kept for writes only; an older bridge ignores it, so the bridge must be restarted after upgrading. Minimum budget: 0.25 s (`MIN_WRITE_BUDGET`)
- **Findings:** I-02, C-04, I-03.
- **Scope:**
  1. The IPC request of a write carries the pinned session id; the bridge forwards it as is (no implicit `hello`, no substitution), so the script's `STALE_SESSION` check refuses a write after a reload.
  2. `track` becomes required in `cubase_set_parameter` and `cubase_insert_plugin`; dry runs return the `uid:` selector and the server instructions tell the client to reuse it. **Schema change.**
  3. Writes need a minimum remaining time budget; below it, `BUSY` without sending.
- **Tests:** probes H1–H3 from the review turned into unit tests; a test that a write never carries a session id other than the pinned one.

### TW-1403 Results that say only what happened

- **Status:** done in code (2026-11-14), tests next to each tool's tests (`test_service_import`, `_saving`, `_automation`, `_settings`, `_ranges`, `_writing`, `_reading`, contract). Not checked live: import, save without a known folder and a recording cut short need a dialog or playback; the unit tests cover them against the simulator. C-27 (export range converted once) was done here too, and the three project-folder helpers became `ServiceBase.project_folder()`.
- **Findings:** C-05, C-06, C-07, C-11, C-12, C-13, C-14, C-15, C-16, C-17.
- **Scope:**
  1. `import_audio`: probe the edges before opening the dialog; require new edges, each matched once.
  2. `save_project` without a known folder: `status: "fired"` and `verified: null`.
  3. `record_automation`: `complete: false` (or `NOT_RECORDED`) when the transport stopped early.
  4. `_write` (read-back after a timeout, `applied` list) moved to `ServiceBase` and used by `set_project`.
  5. Dry runs: restore the cursor in `finally`; document the cursor and selection side effects.
  6. Several open projects: `verified: null` and a note instead of using the first folder.
  7. `select_track(step)`: verified only if the selection moved.
  8. Unexpected exceptions mapped to `INTERNAL_ERROR`; guard the indexing found in C-15.
  9. Events without an id are not reported as invalid.
  10. Tool and model descriptions: remove "assume 4/4".

### TW-1404 Continuous integration

- **Status:** done in the repository (2026-11-14): `.github/workflows/ci.yml` and `fail_under = 95`; the first run on GitHub is still pending (needs a push).
- **Findings:** R-01, R-03.
- **Scope:** GitHub Actions on `macos-latest` with `astral-sh/setup-uv`: `make check`, `make test-node`, `make build` and `make dist-check`; `fail_under = 95`. Optional, a user decision: trusted publishing to PyPI from tags.

## Phase 2 — Robustness

### TW-1405 Bridge and IPC robustness

- **Status:** done in code (2026-11-14), tests in `tests/unit/test_robustness_tw1405.py` and `test_protocol.py`. I-13 (resolved export folder) was done in TW-1403, and `afinfo` now gets a resolved path. The socket path length is checked by the bridge, not the configuration (commands that do not use the socket must keep working)
- **Findings:** I-01, I-04, I-05, I-06, I-07, I-08, I-09, I-10, I-11, I-12, I-13, I-15, I-18, I-19.
- **Scope:** unlink only a socket this instance bound, and open MIDI after the liveness check; listen backlog 128 and "busy" handling in autostart; server read timeout; caps in `SysExAssembler`; reassembler that drops only the stray frame and evicts the oldest assembly; every `OSError` mapped to `BridgeUnavailableError` (with `sent` unknown) and socket path length validated; subprocess timeouts; duplicate-response counter; no symlinks for the socket directory; atomic script install; resolved export folder; shorter error logs; `except OSError:`; `--log-level` choices.
- **Tests:** the probes P2–P5 and F2–F3 of the review as unit tests.

### TW-1406 Cubase script robustness (script 1.6.0)

- **Status:** pending
- **Findings:** S-01, S-02, S-03, S-05, S-06, S-07, S-08, S-09, F-03.
- **Scope:** drop the guard walk and `expectChannelTitle`; active flag per scope; cap on `da.channels` tags; reply `NOT_ACTIVE` to queued requests on deactivation; `try/catch` in `mOnIdle`; `hasOwnProperty` lookups; assembly expiry ~50 ticks; one error-envelope helper.
- **Verification in Cubase:** install with permission, restart Cubase, `doctor`, the live integration tests and a write latency comparison before/after S-01.

### TW-1407 Check the running script version

- **Status:** done (2026-11-14): `doctor` check "script loaded in Cubase" and `script_outdated` / `packaged_script_version` in `cubase_status` (null in the simulator); tests in `test_cli_serve_doctor.py` and `test_service_reading.py`; `doctor` checked against Cubase (script 1.5.5 = packaged)
- **Findings:** S-04.
- **Scope:** `doctor` compares the script version Cubase is running with the packaged one; `cubase_status` reports `script_outdated`; the hint says to restart Cubase.

## Phase 3 — Tests

### TW-1408 Simulator and script conformance

- **Status:** pending
- **Findings:** F-01, F-02, F-04, F-06, S-11.
- **Scope:** a parametrized test that sends the same operations to the node harness (real script) and to `FakeCubase` and compares keys, clamping and error codes; a decision on missing tags verified in Cubase; tests that the automation-key and plugin lists match; every op in `ALL_OPS` has a simulator handler; a public `override(op, fn)` hook; named script constants checked by a test.

### TW-1409 Test-suite hardening

- **Status:** pending
- **Findings:** T-01, T-02, T-03, T-04, T-05, T-06, T-08, T-09, T-10, S-12, S-13.
- **Scope:** assert error codes; fingerprint and `from_config` tests; protocol round trips over sequence numbers and the fragment boundary, plus property-based fuzzing of the framing; re-entrant parametrized tests; events instead of `sleep`; timeouts in the node harness; shared fixtures; the live write fixture limited to the test track; exact command count; `tests` under mypy; an ES5 check of the script; node tests for the untested script operations and JS coverage in `make test-node`.

### TW-1410 Mutation testing

- **Status:** pending
- **Plan:** section "Mutation testing plan" of the review.
- **Scope:** `[tool.mutmut]` configuration and a `make mutation` target (`uv run --with mutmut==3.8.1`); targets in the order of the plan; kill or record as equivalent every surviving mutant of the safety modules; goal ≥ 85 % killed there, string-only mutants excluded; run before each release and record the score in the verification log.
- **Depends on:** TW-1409 (T-03 breaks the baseline).

### TW-1411 More live integration tests

- **Status:** pending
- **Scope:** opt-in live tests, reversible and limited to the test track, for the read tools that have none (`get_selected_channel`, `list_available_plugins`, `list_parameters`, `get_parameter`, `get_project`, `poll_changes`, `list_automation_targets`, `convert_value`) and, behind `TRACKWRIGHT_ALLOW_WRITES`, for the reversible writes (`set_parameter`, `rename_track`, `select_track`, `set_tempo`, `set_project`, `markers`). Tools with dialogs or audio stay manual and are listed as such.

## Phase 4 — Maintainability and API

### TW-1412 Core refactoring

- **Status:** pending
- **Findings:** C-21, C-22, C-23, C-25, C-26, C-27, I-14, I-16, I-17.
- **Scope:** `_paged()` helper; `core/timefmt.py`; selection, folder and cursor helpers on `ServiceBase`; `core/tags.py` with namespaced Cubase tags; remove or document unused code; explicit time signature; bridge counters under a lock; a small `ipc` module; one response-unwrapping helper. No behavior change: the suite and the mutation score must not drop.

### TW-1413 MCP API consistency

- **Status:** pending
- **Findings:** C-18, C-19, C-20, C-24.
- **Scope:** one spelling for previous/next, seconds or bars wherever a position is accepted, a singular name for the track-removal tool, one status vocabulary, one source of truth for slot numbering, exception classes that match their codes, the time format read from Cubase. **Breaking for clients:** release in a minor version with a changelog note.

### TW-1414 Split the simulator

- **Status:** pending
- **Findings:** F-05.
- **Scope:** `fake/` package with protocol emulation, the editing model and the test doubles; no behavior change.

### TW-1415 Repository hygiene

- **Status:** pending
- **Findings:** R-02, R-04, R-05, R-06.
- **Scope:** pre-commit (ruff, ruff-format, mypy); Dependabot for uv and GitHub Actions; CONTRIBUTING and SECURITY (English and Spanish) and issue/PR templates; more ruff rules and pytest options, gradually; upper bounds on the major versions of runtime dependencies; a decision on linting `experiments/`.
