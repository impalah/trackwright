# Trackwright issues and epics

**English** · [Español](README.es.md)

Issues document each unit of work **before** it is implemented. When an issue is closed, its status is updated and the commit is linked.

- **Source of requirements:** `docs/mcp-design.md` and `docs/findings.md` from the POC (`../cubase-mcp-poc/`). Each tool issue cites the runtime evidence it relies on.
- **Statuses:** `pending` → `in progress` → `done` (with commit) · `blocked` (with reason).
- **Identifiers:** `TW-<epic><number>`, for example `TW-0203` (epic 02, issue 03).

## Epics

| Epic | Title | File |
|---|---|---|
| E01 | Project foundations | [E01-foundations.md](E01-foundations.md) |
| E02 | Communication with Cubase (protocol, transport, client, bridge) | [E02-communication.md](E02-communication.md) |
| E03 | Trackwright MIDI Remote script | [E03-midi-remote-script.md](E03-midi-remote-script.md) |
| E04 | MCP server core | [E04-mcp-core.md](E04-mcp-core.md) |
| E05 | Read tools | [E05-read-tools.md](E05-read-tools.md) |
| E06 | Write tools | [E06-write-tools.md](E06-write-tools.md) |
| E07 | Tools based on Cubase commands | [E07-command-tools.md](E07-command-tools.md) |
| E08 | User documentation: manuals and tutorials | [E08-documentation.md](E08-documentation.md) |
| E09 | Quality and testing | [E09-quality-testing.md](E09-quality-testing.md) |
| E10 | Hardening after the independent review | [E10-hardening.md](E10-hardening.md) |
| E11 | Status panel on the MIDI Remote surface | [E11-status-panel.md](E11-status-panel.md) |
| E12 | Extended features (startup, save, import and export, presets, automation, project properties, range editing). **Closed** (TW-1201 to TW-1212) | [E12-extended-features.md](E12-extended-features.md) |
| E13 | Distribution: guided installation, CoreMIDI transport without compilation, and distribution channel | [E13-distribution.md](E13-distribution.md) |
| E14 | Quality remediation (from the code-quality review of 2026-11-14) | [E14-quality-remediation.md](E14-quality-remediation.md) |

## Criteria common to all issues

- **Tooling:** `uv` only.
  - Dependencies with `uv add`; execution with `uv run`.
  - `pip`, `uv pip`, `venv`, `virtualenv`, `pipx`, `conda`, `poetry` and `requirements.txt` are forbidden.
- **Logs:** with `loguru`. The standard library `logging` module is only touched to redirect dependency logs to loguru (E01).
- **Quality:**
  - `uv run ruff check` and `uv run ruff format --check` with no errors;
  - `uv run mypy` in `strict` mode with no errors;
  - unit test coverage ≥ 85 % (`fail_under` in `pyproject.toml`).
- **Documentation:** every user-visible feature is reflected in the manuals (E08).
- **Honesty of evidence:** anything tested only with the simulator is marked as such; nothing is declared verified against Cubase without a recorded real run.
