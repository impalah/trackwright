# E01 — Project foundations

**English** · [Español](E01-foundations.es.md)

Goal: provide a reproducible project skeleton, with automated quality checks, logs, configuration and common errors, on which to build the rest.

## TW-0101 Project skeleton with uv

- **Status:** done
- **Scope:**
  - Git repository `trackwright` (branch `main`, no remote).
  - Distribution package `trackwright-mcp`, module `trackwright` and executable `trackwright`.
  - `pyproject.toml` with the `uv_build` backend and Python ≥ 3.14.
  - Dependencies: `mcp`, `mido`, `python-rtmidi`, `loguru` and `pydantic`.
  - Development dependencies: `pytest`, `pytest-cov`, `ruff`, `mypy` and `anyio`.
  - `.gitignore`.
- **Acceptance:**
  - `uv sync` creates `.venv`.
  - `uv run trackwright --help` works.
  - There is no `requirements.txt`.

## TW-0102 Automated quality checks

- **Status:** done
- **Scope:**
  - Configuration of ruff (lint and format), mypy `strict` and coverage with `fail_under = 85`.
  - Script `scripts/check.sh`, run with `uv run`, to launch everything at once.
- **Acceptance:** `scripts/check.sh` exits with code 0 on a clean tree.

## TW-0103 Logs with loguru

- **Status:** done
- **Scope:** module `trackwright.logging`.
  - Configures loguru with level, optional file and format.
  - **Never writes to stdout**, because with the stdio transport stdout belongs to the MCP protocol.
  - Redirects `logging` logs from dependencies (`mcp`, `anyio`) to loguru, through an *intercept handler*.
- **Acceptance:**
  - A test shows that a log from a dependency ends up in the loguru sink.
  - A test shows that after `configure_logging` nothing is written to stdout.

## TW-0104 Configuration

- **Status:** done
- **Scope:** `trackwright.config`, with pydantic models.
  - Source: TOML file at `~/.config/trackwright/config.toml`, or the path in `TRACKWRIGHT_CONFIG`.
  - Sections:
    - `[bridge]`: port names, socket directory and timeout;
    - `[writes]`: `enabled` (default `false`) and `allowed_tracks`;
    - `[logging]`.
  - Safe defaults: **read-only** until writes are enabled.
- **Acceptance:**
  - Tests for defaults, loading from file, environment variable and rejection of invalid values (timeout out of range, unknown keys).

## TW-0105 Error hierarchy

- **Status:** done
- **Scope:** `trackwright.errors`, with `TrackwrightError(code, message, details)` and its subclasses:
  - transport: `TransportError`;
  - protocol: `ProtocolError`;
  - timeout: `RequestTimeoutError`, which indicates whether the outcome is unknown;
  - session: `StaleSessionError`;
  - host: `HostError`, with the script's code;
  - bridge: `BridgeUnavailableError`;
  - policy and references: `PolicyError`, `NotFoundError`, `StaleReferenceError`, `PreconditionFailedError`.
- **Acceptance:**
  - Each error serializes to a stable dictionary.
  - The MCP server turns it into a readable tool error (E04).
