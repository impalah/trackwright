# E09 — Quality and testing

**English** · [Español](E09-quality-testing.es.md)

## TW-0901 Unit tests and coverage ≥ 85 %

- **Status:** done
- **Scope:**
  - Tests in `tests/unit/` for each module.
  - `uv run pytest --cov` fails if total coverage drops below 85 %.

## TW-0902 MCP contract tests

- **Status:** done
- **Scope:** `tests/contract/`.
  - In-memory MCP client (`mcp.client.Client`) against the server with `FakeCubase`.
  - Expected list of tools and read-only or destructive annotations.
  - One successful call and one error call per tool.

## TW-0903 Script tests with Node.js

- **Status:** done
- **Scope:** see TW-0302 (marker `node`).

## TW-0904 Optional integration tests against Cubase

- **Status:** done
- **Scope:** `tests/integration/`.
  - **Reads** with `TRACKWRIGHT_INTEGRATION=1`: bridge running and Cubase open.
  - **Reversible writes**, only when `TRACKWRIGHT_ALLOW_WRITES=1` is also set and with a track the user specifies in `TRACKWRIGHT_TEST_TRACK`. Each write is restored.
- **Acceptance:** without those variables they are skipped, with a clear reason.

## TW-0905 Documentation consistency

- **Status:** done
- **Scope:**
  - A test checks that every registered tool appears in `docs/manual/04-tools.md`.
  - A test checks that every configuration key appears in `docs/manual/03-configuration.md`.

## TW-0906 Startup from the package

- **Status:** done
- **Scope:** `tests/e2e/test_package_build.py` builds the wheel with `uv build` and checks that it includes the Cubase script, `py.typed` and the `trackwright` executable (marker `slow`).
- **Added:** `tests/e2e/test_stdio_server.py` starts the real `trackwright serve --simulate` process and an MCP client talks to it over stdio. It shows that logs (even at DEBUG) do not pollute stdout.
