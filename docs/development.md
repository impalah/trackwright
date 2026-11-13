# Development guide

**English** · [Español](development.es.md)

## Rules

- **uv only.**
  - Dependencies: `uv add <package>`, or `uv add --dev <package>` for development ones.
  - Running: `uv run <command>`.
  - Forbidden: `pip`, `uv pip`, `python -m venv`, `virtualenv`, `pipx`, `conda`, `poetry` and `requirements.txt`.
- **Logging with loguru** (`from loguru import logger`).
  - The `logging` module is only touched in `trackwright/logs.py`, to redirect the dependencies' logging.
  - Nothing is ever written to stdout, which belongs to the MCP protocol under `serve`.
- **Mandatory quality:** ruff (lint and format), mypy `strict` and coverage ≥ 85%.
- **Issues:** every change starts from an issue in [`docs/issues/`](issues/README.md), which is closed by its commit.

## Commands

The `Makefile` wraps the usual tasks, always through uv; `make help` lists them:

| Target | Does |
|---|---|
| `make sync` | `uv sync` |
| `make check` | lint, format check, mypy and tests with coverage (same as `scripts/check.sh`) |
| `make lint`, `make format`, `make typecheck` | ruff check, ruff fix + format, mypy |
| `make test`, `make test-cov`, `make test-node` | tests, with coverage, only the Cubase script tests |
| `make test-integration`, `make test-integration-write TEST_TRACK=…` | against the real Cubase (opt-in; writes are reversible, default track `POC-TEST`) |
| `make build`, `make dist-check` | `uv build` into a clean `dist/`, and `uvx twine check --strict` |
| `make publish-test`, `make publish` | upload to TestPyPI or PyPI with `uv publish` (needs `UV_PUBLISH_TOKEN`) |
| `make doctor`, `make ping`, `make bridge`, `make bridge-status`, `make serve-sim` | run Trackwright |
| `make script-status`, `make script-install`, `make script-install-apply`, `make setup` | the Cubase script and the guided installation |
| `make clean` | remove `dist/`, caches and coverage files |

The underlying commands:

```sh
uv sync                         # environment
scripts/check.sh                # everything: lint, format, types and tests with coverage
uv run ruff check src tests     # lint
uv run ruff format src tests    # format
uv run mypy                     # types (strict)
uv run pytest                   # tests (integration tests skip themselves)
uv run pytest --cov             # with coverage (fails below 85%)
uv run pytest -m node           # only the Cubase script tests (needs node)
uv build                        # wheel and sdist in dist/
```

## Structure

```text
src/trackwright/
  cli.py            # commands: bridge, serve, setup, doctor, script, ping, config...
  installer.py      # trackwright setup: guided installation with per-step confirmation (TW-1301)
  doctor.py         # diagnostics of the chain (doctor and the last step of setup)
  config.py         # configuration (TOML + environment, pydantic)
  logs.py           # loguru, stderr, interception of logging
  errors.py         # error hierarchy with stable codes
  protocol.py       # "TW" SysEx frames and reassembly
  coremidi.py       # CoreMIDI virtual ports with ctypes (default on macOS; no compiling)
  transport.py      # Transport interface and alternative mido + python-rtmidi transport
  host.py           # script client: correlation, sessions, timeouts
  ops.py            # script operations (reads, writes)
  bridge.py         # daemon with Unix socket, and its client
  hostport.py       # port to Cubase used by the server (BridgeHost)
  fake.py           # FakeCubase: simulator for tests and --simulate
  commands.py       # Cubase commands with their observed class
  core/             # domain: references, policy, models, service
  server.py         # MCP server: registration of the 21 tools
  cubase/           # Trackwright_Bridge.js and installer
tests/
  unit/             # unit tests (simulator, real sockets in /tmp)
  contract/         # in-memory MCP client against the server
  script/           # the real script run with Node.js and an emulated API
  e2e/              # real process over stdio and package build
  integration/      # against real Cubase, opt-in
```

## Test types

| Type | Where | What it demonstrates | When it runs |
|---|---|---|---|
| Unit | `tests/unit` | Each module; the service against `FakeCubase` | Always |
| MCP contract | `tests/contract` | Tools, schemas, annotations and errors as seen by an MCP client | Always |
| Script | `tests/script` | The real ES5 script speaks the same protocol as Python | If `node` is available |
| End-to-end | `tests/e2e` | The executable starts over stdio; the wheel includes the script | Always (`slow`) |
| Integration | `tests/integration` | Behavior with real Cubase | `TRACKWRIGHT_INTEGRATION=1` |

`FakeCubase` reproduces the behaviors verified in the POC. A test that passes against the simulator proves **nothing** about real Cubase: that is what the integration tests are for.

## Integration tests

They need the bridge running and Cubase open with a disposable project.

```sh
TRACKWRIGHT_INTEGRATION=1 uv run pytest tests/integration -v
TRACKWRIGHT_INTEGRATION=1 TRACKWRIGHT_ALLOW_WRITES=1 TRACKWRIGHT_TEST_TRACK="POC-TEST" uv run pytest tests/integration -v
```

Writes are restored at the end. These tests use your real configuration: they do not apply the isolation from `tests/conftest.py`.

## Adding a tool

1. **Issue** in the corresponding epic, with the runtime evidence it relies on.
2. If it needs a new script operation:
   - add it in `cubase/Trackwright_Bridge.js`;
   - add it in `ops.py`;
   - implement it in `fake.py`, with the same result shape;
   - cover it in `tests/script/test_script_node.py`. The test `test_script_ops_match_python_ops` fails if the lists do not match.
3. **Logic** in the appropriate mixin in `core/`: `reading.py`, `writing.py` or `commanding.py`.
   - Writes use `dry_run`, the policy and verification by reading back.
4. **Output model** in `core/models.py`.
5. **Registration** in `server.py`, with a description and annotations (`READ`, `NAVIGATE`, `WRITE` or `DESTRUCTIVE`).
6. **Tests:** service unit tests and contract tests.
7. **Documentation:** a section in `docs/manual/04-tools.md` and the same in its Spanish translation, `docs/manual/04-tools.es.md`. `tests/unit/test_docs.py` fails if it is missing. Every document is written in English (`X.md`) with its Spanish translation (`X.es.md`), updated together.
8. `scripts/check.sh` green and a commit that cites the issue.

## Releasing a version

1. Update `version` in `pyproject.toml` and the changelog (`CHANGELOG.md` and `CHANGELOG.es.md`); `uv sync` updates `uv.lock`.
2. `make check`, then commit.
3. Publish (the user does it, with their own token):
   ```sh
   UV_PUBLISH_TOKEN="$(security find-generic-password -a "$USER" -s pypi-token -w)" make publish
   ```
   `make publish-test` does the same against TestPyPI (Keychain entry `testpypi-token`).
4. Tag the published commit: `git tag -a vX.Y.Z -m "Trackwright X.Y.Z"`.

A version can never be uploaded twice, even if it is deleted from PyPI.

**Storing the token in the macOS Keychain.** Copy the token from the PyPI page and run:

```sh
security add-generic-password -U -a "$USER" -s pypi-token -w "$(pbpaste)"
pbcopy < /dev/null
```

Do not use the interactive prompt (`-w` with no value): it keeps only 128 characters and PyPI tokens are longer, so the upload fails with `403 Invalid or non-existent authentication information`. After the first release, use a token scoped to the `trackwright` project.

## Changing the Cubase script

- Bump `SCRIPT_VERSION` in the script; the tests check the version.
- Cubase does not reload scripts on its own: install with `uv run trackwright script install --apply` and restart Cubase.
- Validate with the integration tests before considering the change good.
