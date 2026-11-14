# Code quality review (2026-11-14)

**English** · [Español](quality-review.es.md)

Review of Trackwright 0.3.0 (commit `3d715e4`): code organization, MCP API, code smells, tests, documentation, an adversarial analysis of the infrastructure and a mutation-testing plan. The remediation plan is epic [E14](issues/E14-quality-remediation.md).

## Method

- **Three independent read-only reviews** of the code, each with a defined scope:
  - domain service and MCP API (`core/`, `server.py`, `commands.py`, `errors.py`);
  - adversarial review of the infrastructure (`protocol`, `coremidi`, `transport`, `host`, `bridge`, `launcher`, `config`, `cli`, `installer`, `doctor`), with probes;
  - Cubase script, simulator, test suite, repository tooling and a mutation-testing pilot.
- **Tools,** all run through `uv`/`uvx`, nothing installed in the project:
  - radon (complexity and maintainability), vulture (dead code), pylint `duplicate-code`, interrogate (docstrings);
  - pip-audit (known vulnerabilities in `uv.lock`), `uv tree --outdated`;
  - pytest with branch coverage, V8 coverage for the script, mutmut 3.8.1 (pilot).
- **Safety:** nothing touched the user's Cubase or the running bridge. Probes used isolated `TMPDIR`/`HOME`, port names other than the production ones, and a clone of the repository for mutation testing.
- **Evidence:** every finding cites `file:line` and is marked **confirmed** (read in the code, reproduced or measured) or **suspected** (plausible, not reproduced). The three most serious policy findings were reproduced again against the simulator by the coordinator.

## Summary

Trackwright is in good shape for an alpha: 98 % branch coverage, strict mypy, a broad ruff rule set, a fast suite (~9 s), well-designed session pinning, no automatic retry of writes, careful IPC hardening and documentation enforced by tests. No known vulnerabilities in its dependencies.

The review found **three policy holes that let a write bypass the user's configuration**, a **session-pinning gap** in the bridge, and several places where a tool can **report success without evidence**. These go first in the plan. The rest is robustness of the bridge and the script, drift risk between the simulator and the real script, weak assertions found by mutation testing, missing CI, and maintainability work.

| Severity | Count | Examples |
|---|---|---|
| High | 6 | `run_command` bypasses `[writes] save`; `allowed_tracks` ignored by range edits; routing writable through `set_parameter`; writes can carry a renegotiated session; simulator and script not checked against each other; no CI |
| Medium | 30 | `track="selected"` default on write tools; import/save/automation reported as done without proof; refused bridge deletes the live socket; script version not checked at runtime; weak tests |
| Low | 40+ | duplication, magic numbers, naming, error classes, small robustness gaps |

## Metrics

| Metric | Value | Comment |
|---|---|---|
| Size | `src/` ≈ 7 800 lines of Python + 1 130 lines of ES5 script; tests ≈ 5 750 lines | `fake.py` (1 112) and the script are the largest files |
| Tests | 458 passed, 6 skipped, ~9 s | integration tests are opt-in |
| Branch coverage | 98.1 % (`fail_under = 85`) | only `coremidi.py` below 95 % (94 %) |
| Script coverage (node tests) | ≈ 85 % of lines | not measured by the normal suite |
| Cyclomatic complexity | average A (3.45); nothing worse than C outside the simulator | worst: `split_at_locators` C(18), `edit_range`, `set_track_mix`, `set_project` C(16); `FakeCubase._apply_transport_move` D(22) |
| Maintainability index | A everywhere except `fake.py` (C) | |
| Duplication (pylint, ≥ 5 lines) | 1 block | SysEx receive path in `coremidi.py` and `transport.py` |
| Dead code (vulture) | `ServiceBase.is_host_code`; also see C-25 | other reports are pydantic fields (false positives) |
| Docstrings (interrogate) | 26.8 % | tool behavior is documented in the tool descriptions and the manual; low priority |
| Vulnerabilities (pip-audit) | none in 33 runtime and 17 dev pinned packages | |
| Outdated direct dependencies | ruff 0.17.4 → 0.17.5 | |
| Live integration tests | 6 of 32 tools | the rest are verified by hand (verification log) and against the simulator |

**Tool compatibility:** `bridge.py:95` uses the Python 3.14 unparenthesized `except A, B, C:` form (PEP 758). It is valid, but radon, vulture, pylint and interrogate fail to parse the file, so it was excluded from their metrics. All the listed exceptions are subclasses of `OSError` anyway (I-18).

## Findings

IDs: **C** domain and API, **I** infrastructure, **S** Cubase script, **F** simulator, **T** tests, **R** repository and tooling. Effort: S (hours), M (a day or two), L (more).

### 1. Policy and write safety

| ID | Sev | Finding | Location | Status | Fix | Effort |
|---|---|---|---|---|---|---|
| C-01 | high | `cubase_run_command` only checks `check_project_write()`: `file.save`/`file.save_new_version` save with `[writes] save = false`; `project.remove_selected_tracks` skips the selection guard and `allowed_tracks`; range commands skip `allowed_tracks` | `core/commanding.py:101-103` | confirmed, reproduced | per-key policy: `file.*` → `check_save()`; refuse keys that have a dedicated guarded tool, or require `allowed_tracks` to be empty | S |
| C-02 | high | `edit_range` (also with `track=`) and `split_at_locators` ignore `allowed_tracks` | `core/ranges.py:150`, `core/commanding.py:209` | confirmed, reproduced | `check_track` for single-track edits; refuse all-track edits when `allowed_tracks` is set | S |
| C-03 | high | `set_parameter` on target `channel` accepts the input/output routing tags (4101/4102); the simulator records that writing routing leaves "Sin bus" (*No Bus*) | `core/writing.py:103-136`, script `:801-807` | confirmed, reproduced in the simulator | refuse routing, name and selection tags with `READ_ONLY_PARAM`, in Python and in the script | S |
| I-02 | high | a write pinned to session S1 can be sent with session S2: the bridge's `HostClient` substitutes its own current session id (and may `hello` first), so the script's `STALE_SESSION` check passes and the write can hit another object after a script reload; the client notices only afterwards | `host.py:140, 205-226`; `core/base.py:124-133`; `bridge.py:60-73` | confirmed with probes | send the pinned session id in the IPC request for writes; the bridge forwards it as is, without implicit `hello` | M |
| C-08 | medium | `set_position` changes the cycle locators (saved in the project) with no policy check and `dry_run` default false | `core/writing.py:312-374`, `server.py:230-235` | confirmed | treat locators as a project write, or document the exception | S |
| C-04 | medium | `cubase_set_parameter` and `cubase_insert_plugin` default to `track="selected"`: the apply call can hit a different track than the dry run showed | `server.py:182, 197` | confirmed | make `track` required on write tools; dry runs return the `uid:` selector | S |
| C-10 | medium | `remove_selected_tracks` fires even when Cubase reports it cannot | `core/commanding.py:166-170` | confirmed | raise `CANNOT_PERFORM` | S |
| C-09 | medium | the all-track range path does not clear a previous selection before *Select in Loop*; a leftover selection could make `edit.delete` act on it | `core/ranges.py:265-280` | suspected | `edit.select_none` first | S |
| I-03 | medium | a write that gets the lock (or finishes `hello`) right at its deadline is still sent with a few ms left, so it ends as `TIMEOUT outcome: unknown` although it probably runs | `host.py:127-134, 218-221` | confirmed with a probe | minimum remaining budget for writes; below it, `BUSY` without sending | S |
| C-12 | low | some dry runs send write operations (cursor moves for bar conversion, track selection); `edit_range` does not restore the cursor if parsing `end` fails | `core/ranges.py:118-121`, `core/exporting.py:85-87`, `core/automation.py:200` | confirmed | `try/finally`; document side effects | S |

### 2. Truthful results

| ID | Sev | Finding | Location | Status | Fix | Effort |
|---|---|---|---|---|---|---|
| C-05 | medium | `import_audio` confirm can report `verified: true` for a cancelled import when an existing event already has an edge at the target position | `core/importing.py:106-113` | confirmed (logic) | probe edges before opening the dialog; require new edges, each matched once | M |
| C-06 | medium | `save_project` reports `status: "saved"` with no evidence when the project folder is unknown (a never-saved project shows *Save As*) | `core/saving.py:53-55` | confirmed | status `fired`/`unverified` | S |
| C-07 | medium | an automation recording cut short (transport stopped) is returned as if complete | `core/automation.py:352-380` | confirmed | compare with the curve end; `complete: false` or `NOT_RECORDED` | S |
| C-11 | medium | `set_project` lacks the timeout read-back and the `applied` list of `set_track_mix` (`_write` lives in `WritingMixin`) | `core/settings.py:64-68` | confirmed | move `_write` to `ServiceBase` | S |
| C-13 | low | save, export and import use `folders[0]` when several projects are open | `core/saving.py:33-35`, `core/exporting.py:58-60`, `core/importing.py:125-127` | suspected | `verified: null` and a note when there are several folders | S |
| C-14 | low | `select_track(step=…)` reports verified when nothing moved | `core/writing.py:303-305` | confirmed | also require `after != before` | S |
| C-15 | low | some `IndexError`/`KeyError` escape as generic errors without a code | `core/automation.py:166, 185`, `core/writing.py:113` | confirmed | guard them; map unexpected exceptions to `INTERNAL_ERROR` in `server.run` | S |
| C-16 | low | events without an object id are reported as `still_valid: false` | `core/reading.py:204-220` | suspected | skip the lookup | S |

### 3. Bridge and IPC robustness (adversarial)

| ID | Sev | Finding | Location | Status | Fix | Effort |
|---|---|---|---|---|---|---|
| I-01 | medium | a second bridge refused because a live one is listening deletes the live bridge's socket in `finally: server.stop()`; clients can no longer reach the live bridge. Not reached with the default CoreMIDI backend, where the port-name check fails earlier; reachable with other port names, rtmidi or a race | `bridge.py:205-211, 314-322` | confirmed with a probe | unlink only a socket this instance bound; open MIDI after the liveness check | S |
| I-04 | medium | listen backlog 5: a burst of concurrent clients gets `ECONNREFUSED` (16 of 40 in a probe); under load `ensure()` may decide the bridge is dead | `bridge.py:185` | confirmed (autostart part suspected) | `request_queue_size = 128`; treat "refused but file exists" as busy | S |
| I-07 | low | one stray frame with the same sequence number destroys a legitimate assembly; 16 junk sequences fill the pending table for 5 s | `protocol.py:152-160` | confirmed with fuzzing | drop only the new frame; evict the oldest assembly | S |
| I-06 | low | `SysExAssembler` grows without bound until `F7` | `coremidi.py:62-63` | confirmed (10 MB buffered) | cap at the maximum frame size | S |
| I-08 | low | raw `OSError`s escape (socket path too long, reset, broken pipe): the CLI prints a traceback instead of JSON; the socket path length is not validated | `bridge.py:241-263`, `cli.py:194-199`, `config.py` | confirmed | map to `BridgeUnavailableError` with `sent` unknown; validate the path length (< 104) | S |
| I-05 | low | no server read timeout: a client that never sends a newline holds a thread forever (same user only) | `bridge.py:152` | confirmed | socket timeout in `setup()` | S |
| I-09 | low | `open -a`/`pgrep` have no timeout; `lsof`/`afinfo` timeouts raise a raw `TimeoutExpired` | `launcher.py:45-51`, `exports.py:20-22` | suspected | timeouts mapped to tool errors | S |
| I-10 | low | a duplicated response is counted as `unsolicited` | `host.py:93-104` | confirmed | separate `duplicates` counter | S |

### 4. Security

No high-impact issue: the socket lives in a 0700 directory with an owner check, is created 0600 under umask 077, requests are capped at 64 KiB, the op allowlist is exact, timeouts reject NaN/inf, subprocesses use absolute binaries without a shell, and setup never overwrites existing files.

| ID | Sev | Finding | Location | Status | Fix | Effort |
|---|---|---|---|---|---|---|
| I-11 | low | `stat`/`chmod` on the socket directory follow symlinks; if `TMPDIR` is unset the directory falls back to the shared `/tmp`, where another user could pre-create a symlink (denial of service, no privilege gain) | `bridge.py:79-86`, `config.py:29` | confirmed with a probe | `lstat` and refuse symlinks (or `O_NOFOLLOW`); consider `~/Library/Caches` | S |
| I-12 | low | script install: time-of-check/time-of-use between the symlink check and `copyfile`, and the copy is not atomic | `cubase/__init__.py:79-82` | suspected | temp file + `os.replace` | S |
| I-13 | low | a relative export folder starting with `-` reaches `afinfo` as an option | `exports.py:38`, `core/exporting.py:121` | suspected | resolve the path | S |
| I-15 | low | unexpected errors log the full request (up to 64 KiB, including track names) | `bridge.py:133` | confirmed | log op and size only | S |

### 5. Cubase script

| ID | Sev | Finding | Location | Status | Fix | Effort |
|---|---|---|---|---|---|---|
| S-01 | medium | every parameter write walks up to 3 000 mixer nodes (two DirectAccess calls each) only to build a `guard.path` that Python never reads | script `:712-736` | confirmed in code; latency suspected | drop the walk | S |
| S-02 | medium | the idle queue checks `daActive` for both scopes: mixer requests may run on an inactive mixer instance, or be refused when only the selection instance failed | script `:1018-1025` | confirmed | check the active flag of the request's scope | S |
| S-04 | medium | nothing compares the **running** script version with the packaged one: after an upgrade without restarting Cubase, `doctor` passes and new operations fail with `UNKNOWN_OP` | `doctor.py:51`, `core/reading.py:42` | confirmed | `doctor` check and `script_outdated` in `cubase_status` | S |
| S-03 | low | `da.channels` accepts an unbounded tag list (work done before `RESPONSE_TOO_LARGE`) | script `:834, 850-855` | confirmed with the harness | cap at 16 tags | S |
| S-05 | low | `mOnDeactivate` drops queued requests without replying: callers wait for the timeout and writes look "unknown" | script `:1080-1092` | confirmed | reply `NOT_ACTIVE` before clearing | S |
| S-06 | low | `mOnIdle` has no top-level `try/catch` | script `:1094-1108` | confirmed | wrap it | S |
| S-07 | low | op lookups on plain objects accept inherited names (`toString`); blocked by the bridge allowlist in production | script `:501, 540, 548` | confirmed | `hasOwnProperty` | S |
| S-08 | low | assemblies expire after 2 000 idle ticks (~225 s) against 5 s in Python | script `:488-498` | confirmed | ~50 ticks | S |
| S-09 | low | some error envelopes lack `op`/`via`; bad-JSON replies carry an empty `rid` | script `:373-379, 509, 513` | confirmed | one envelope helper | S |
| S-10 | low | duplicated blocks and a global mutable `da` swapped per request | script, several | confirmed | extract helpers; pass `da` explicitly | M |
| S-11 | low | paging caps and the default tag list are literals, copied in `fake.py` and `core/base.py` | script, several | confirmed | named constants checked by a test | S |
| S-12 | low | nothing checks ES5: Node accepts ES6 that Cubase would reject | `tests/script` | confirmed | ES5 parse test (`vm.Script` + forbidden tokens, or acorn) | S |
| S-13 | medium | node tests cover ≈ 85 % of the script; untested: `da.params`, `da.param.get`, `da.convert`, `pm.collections`, protocol errors, frame rejection and expiry, `mOnDeactivate`, edit-lock preconditions, multi-fragment requests | `tests/script` | confirmed (V8 coverage) | node tests per item; JS coverage in `make test-node` | M |

### 6. Simulator

| ID | Sev | Finding | Location | Status | Fix | Effort |
|---|---|---|---|---|---|---|
| F-01 | high | nothing checks that `FakeCubase` and the script return the same shapes; a probe found differences in `status`, `capabilities`, `da.param.set`, `da.children` with `limit=0` and missing tags in `da.channels` | `fake.py`, `tests/script` | confirmed | conformance test: the same operations against the node harness and the simulator, comparing keys, clamping and error codes | M |
| F-02 | medium | missing channel tags are `None` in the simulator and sentinel dicts in the script, so `track_info` differs | `fake.py:575-583`, `core/base.py:189-199` | confirmed vs harness; suspected vs Cubase | verify in Cubase; treat `process == -1` as absent | S |
| F-03 | medium | `expectChannelTitle` means different things in the simulator and the script (and nothing in `src` uses it) | `fake.py:426-432`, script `:712-719` | confirmed | remove it from both (with S-01) | S |
| F-04 | medium | three copies of the automation-control key list (only the script's is tested); plugin list copied in the node harness; nothing enforces that every op has a simulator handler | `fake.py:705-716`, script `:158-187` | confirmed | tests comparing the lists; `ALL_OPS` ↔ `_op_*` test | S |
| F-05 | low | one ~980-line class mixes protocol emulation, an editing model and test helpers | `fake.py:79-1060` | confirmed | `fake/` package (`ops`, `model`, `doubles`) | M |
| F-06 | low | tests monkeypatch private `fake._op_*` methods | several tests | confirmed | public `override(op, fn)` hook | S |

### 7. Tests

| ID | Sev | Finding | Location | Status | Fix | Effort |
|---|---|---|---|---|---|---|
| T-01 | medium | the suite does not catch: `WritePolicy.from_config` dropping `save`; removing `code="NOT_ALLOWED"`; `check_fingerprint` `or` → `and`. Some tests use bare `pytest.raises(PolicyError)` | tests for `core/policy.py`, `core/refs.py` | confirmed (mutants applied by hand) | assert error codes; single-field fingerprint tests; `from_config` round trip | S |
| T-02 | medium | protocol round trips do not cover sequence numbers > 127 or 0, nor the 15 360-byte fragment boundary | tests for `protocol.py:49, 68, 109` | confirmed (mutants survived) | parametrize seq {0, 127, 128, 16383} and sizes {15360, 15361}; property-based fuzzing | S |
| T-03 | medium | a parametrized test shares mutable fake sockets, so it fails when run twice in one process (it broke the mutmut baseline) | `tests/unit/test_bridge.py:226-238` | confirmed | build the fakes inside the test | S |
| T-07 | medium | range editing, export/import, presets and automation are tested only against the simulator's own model of Cubase; real behavior is only in the verification log | `tests/unit/test_service_*` | confirmed | mark them as simulator-modelled and link each rule to its experiment; more live tests (TW-1411) | S |
| T-04 | low | timing-based synchronization (`sleep`) in host tests | `tests/unit/test_host.py:122, 187, 222` | suspected flaky on CI | events or polling | S |
| T-05 | low | the node harness reads with no timeout; no `pytest-timeout` | `tests/script/test_script_node.py:50` | confirmed | timeout | S |
| T-06 | low | fixtures re-declared in several places; a test module imports from another | `tests/contract`, `tests/script` | confirmed | shared `conftest.py` | S |
| T-08 | low | the live write fixture allows every track | `tests/integration/test_live_cubase.py:43` | confirmed | `allowed_tracks=(TEST_TRACK,)` | S |
| T-09 | low | `commandsBound >= 30` while 57 are bound | `tests/script/test_script_node.py` | confirmed | `== len(COMMANDS)` | S |
| T-10 | low | tests are not type-checked | `pyproject.toml` | confirmed | add `tests` to mypy | S |

**Policy tests missing** (from the domain review): refusals by `allowed_tracks` for `set_track_mix`, `rename_track`, `insert_plugin`, `plugin_preset`, `record_automation` and `import_audio`; `WRITES_DISABLED` for `rename_track`, `insert_plugin` and `split_at_locators`; the selection guard of `remove_selected_tracks` with only one mismatching condition; `edit_range` with equal bounds; partial failures in `set_track_mix` and `set_project`; a contract test asserting that every tool that modifies the project defaults to `dry_run=true`.

**Live integration coverage:** 6 of 32 tools (`status`, `list_tracks`, `list_inserts`, `get_transport`, `set_track_mix`, `set_position`). The other 26 were verified by hand (verification log) but have no repeatable live test.

### 8. MCP API design

| ID | Sev | Finding | Location | Status | Fix | Effort |
|---|---|---|---|---|---|---|
| C-17 | medium | tool and model descriptions still say "positions assume 4/4", but the code reads the time signature | `server.py:460`, `core/models.py:236` | confirmed | fix the texts the client model reads | S |
| C-18 | low | same idea, different spelling: `step: "prev"` vs `direction: "previous"`; `split_at_locators` bars only while other tools accept seconds or bars; `remove_selected_tracks` is plural but removes one track; several status vocabularies (`fired`, `done`, `saved`) | `server.py`, models | confirmed | align in a minor version (breaking for clients) | M |
| C-19 | low | slot numbering: descriptions say 8 slots, schemas allow 16, automation keys accept 1–8 | `server.py:124-131, 195, 327` | confirmed | one source of truth | S |
| C-20 | low | exception classes do not match their codes (`PreconditionFailedError` with `VERIFY_FAILED` or `NOT_FOUND`; `VerificationFailedError` unused) | `core/commanding.py:223`, `core/importing.py:44`, `core/project.py:85` | confirmed | use the matching class | S |
| C-24 | low | `"Compases+Tiempos"` (Spanish Cubase UI) hard-coded as a time format | `core/writing.py:358` | confirmed | read it from `transport.get` | S |

### 9. Code smells and organization

| ID | Sev | Finding | Location | Fix | Effort |
|---|---|---|---|---|---|
| C-21 | medium | the same offset/limit pagination loop written 5 times | `core/base.py:247-253`, `core/project.py:87-110`, `core/presets.py:27-38`, `core/automation.py:148-157` | one `_paged()` helper | S |
| C-22 | medium | track selection, project-folder and cursor helpers copied across mixins; bar helpers live in `writing.py` but are used by mixins that do not inherit it | `core/automation.py:93`, `core/ranges.py:70`, `core/writing.py:307`, … | `core/timefmt.py`; helpers on `ServiceBase` | S |
| C-23 | low | Cubase tag constants scattered and colliding (4101 means input, seconds display and plugin editor) | `core/base.py:55-65`, `core/project.py:21`, `core/presets.py:20` | `core/tags.py` with namespaces | S |
| C-25 | low | unused code: `ObjectRef.decode`/`check_session`/`check_fingerprint` (tests only; the docstring claims tools use them), `is_host_code`, `VerificationFailedError` | `core/refs.py:62-88`, `core/base.py:311`, `errors.py:106` | delete or document as reserved | S |
| C-26 | low | the time signature travels in thread-local state | `core/automation.py:131, 260` | pass it explicitly | S |
| C-27 | low | `_seconds_of` runs twice on the export apply path (extra cursor moves) | `core/exporting.py:86, 104-106` | compute once | S |
| I-14 | low | bridge counters updated from several threads without a lock | `bridge.py:107-132` | lock | S |
| I-16 | low | `launcher.py` imports a private helper from `bridge.py`; `JsonObject` redefined in ~6 modules | `launcher.py:22` | small `ipc`/`types` module | S |
| I-17 | low | response unwrapping duplicated | `hostport.py:70-74`, `bridge.py:277-281` | shared helper | S |
| I-18 | low | redundant `except ConnectionRefusedError, FileNotFoundError, TimeoutError, OSError:` (PEP 758 form that breaks radon/vulture/pylint/interrogate) | `bridge.py:95` | `except OSError:` | S |
| I-19 | low | an invalid `--log-level` raises a raw `ValueError` | `cli.py:192` | argparse `choices` | S |

**Organization proposals** (no change of architecture; YAGNI on multi-DAW still applies): `core/tags.py` and `core/timefmt.py`; a small `ipc.py` for the socket-directory and liveness helpers; a `fake/` package; shared test fixtures in `conftest.py`. The current mixin layout is sound: no two mixins define the same method name.

### 10. Repository and tooling

| ID | Sev | Finding | Fix | Effort |
|---|---|---|---|---|
| R-01 | high | the public GitHub repository has **no CI**: every gate runs only on the author's Mac | GitHub Actions on `macos-latest` with `astral-sh/setup-uv`: `make check`, node tests, build and `twine check` | S |
| R-02 | medium | no pre-commit, no dependency update policy (Dependabot/Renovate), no CONTRIBUTING, SECURITY or issue/PR templates | add them (bilingual where they are documents) | S |
| R-03 | low | `fail_under = 85` while coverage is 98 % | raise to 95 | S |
| R-04 | low | ruff lacks `PT`, `PERF`, `FURB`, `ERA`, `TRY`, `ASYNC`; pytest lacks `xfail_strict`, `filterwarnings = error` and a timeout | add gradually | S |
| R-05 | low | runtime dependencies have only lower bounds; PyPI users do not get `uv.lock` | upper bounds on majors (`mcp>=2.3,<3`) | S |
| R-06 | low | `experiments/` is not linted (one stale `__pycache__`) | accept as throwaway, or relaxed lint | S |

## Mutation testing plan

**Pilot** (clone of the repository, mutmut 3.8.1 through `uv run --with`, nothing added to the project): `protocol.py`, `core/policy.py` and `core/refs.py`, 416 mutants in 27 s with 4 workers, **70 % killed**. About 74 of the 124 survivors only change message strings. The meaningful survivors became T-01 and T-02, and were re-checked against the full suite.

**Tool:** mutmut 3 (works with Python 3.14 and uv, fast, no extra dependency). cosmic-ray works too but is slower to set up. For the JavaScript script, StrykerJS would need npm, a toolchain the project does not use today: a decision for the user, not part of this plan.

**How to run it:**

```sh
uv run --with mutmut==3.8.1 mutmut run --max-children 4
uv run --with mutmut==3.8.1 mutmut results
```

Configuration in `[tool.mutmut]` of `pyproject.toml` (configuration only, no dependency): `source_paths` with the targets, a narrowed `pytest_add_cli_args_test_selection`, and `also_copy` with `docs/`, the README and CHANGELOG files, `CLAUDE.md` and `LICENSE` (the documentation tests read them). A `make mutation` target wraps it.

**Pitfalls found:** T-03 broke the clean baseline, and with the whole `tests/unit` selection mutmut crashed in its fork workers (suspected: tests that start subprocesses, sockets or CoreMIDI ports). Narrow the selection per target.

**Targets, in order:** `protocol.py`, `core/policy.py`, `core/refs.py`, `ops.py`, `host.py`; then `core/writing.py`, `core/base.py`, `core/ranges.py`, `core/automation.py`; then `bridge.py`. **Excluded:** `fake.py` (a test double), `coremidi.py` and `transport.py` (ctypes/rtmidi), `cli.py`, `launcher.py`, `installer.py`, `logs.py`, `server.py` (declarative) and `__main__.py`.

**Cadence and goals:** on demand and before each release, not on every push (estimated 5–15 min for the whole target set; extrapolated, not measured). Goal: at least 85 % killed on the safety modules (`policy`, `refs`, `protocol`, `host`, the write paths of `core/`) once string-only mutants are excluded; every surviving mutant is either killed by a new test or recorded as equivalent.

**Concrete mutants to kill first:** `from_config` without `save`; `NOT_ALLOWED` removed; fingerprint `or` → `and`; protocol sequence `<< 8` and the `>` → `>=` fragment boundary; `remove_selected_tracks` selection guard `or` → `and`; `edit_range` `<` → `<=`; `set_track_mix` `all` → `any`; deletion of `check_track` in `set_track_mix`, `rename_track` and `insert_plugin`; deletion of `check_project_write` in `split_at_locators`; group-writable socket directory (`& 0o077` → `& 0o007`); `open("x")` → `open("w")` in setup.

## Adversarial analysis: what was tried

- **IPC:** a 30 000-level nested JSON (handled), 50 idle half-line clients (I-05), a burst of 40 clients (I-04), a second bridge against a live one (I-01), a 120-character socket path (I-08), a symlinked socket directory (I-11).
- **Protocol:** 200 000 random and near-valid frames through the parser, reassembler and decoder (only `ProtocolError`, never a crash; the pending table ended saturated, I-07), a stray frame inside an assembly (I-07), 10 MB of SysEx without `F7` (I-06).
- **Host:** a write at its deadline (I-03), renegotiated sessions (I-02), duplicated responses (I-10), non-string request ids (handled).
- **Script, in the node harness:** inherited op names (S-07), 2 000 tags (S-03).
- **The "never retry a write" invariant held** on every path tried; its tests kill the relevant mutants.

## Strengths

- Session pinning, no automatic retry of writes, and read-back verification with honest `unknown` outcomes.
- Commands report their class (`dialog`, `ui_selection`), so a dialog is never reported as done.
- Careful IPC hardening; exact op allowlist; bounded resources in the script (caches, queues, assemblies).
- Fast suite with 98 % branch coverage, strict mypy, contract tests through a real MCP client, opt-in live tests that revert their writes.
- Protocol agreement between Python and the script tested with the real script under Node.
- Documentation enforced by tests (bilingual pairs, every tool, command key and configuration key documented).
