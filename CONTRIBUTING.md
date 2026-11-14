# Contributing to Trackwright

**English** · [Español](CONTRIBUTING.es.md)

Thank you for helping. Trackwright controls a real Cubase, so the rules below are about not breaking the user's work as much as about code style.

## Before you start

- Open or pick an issue. Every change starts from one (`docs/issues/`) and its commit cites it (`TW-NNNN: ...`).
- Read the [development guide](docs/development.md): structure, test types and how to add a tool.

## Setting up

Trackwright uses [uv](https://docs.astral.sh/uv/) only: no pip, venv, pipx, conda or poetry.

```sh
uv sync
uvx pre-commit install   # optional: ruff and mypy before every commit
make check               # lint, format, mypy strict, tests with coverage >= 95 %
```

## Rules

- **Logs** with loguru, to stderr. `trackwright serve` never writes to stdout: it is the MCP channel.
- **Tests** assert the error code, wait for events instead of sleeping, and use the simulator (`trackwright.fake`). A test that passes against the simulator proves nothing about Cubase: behaviors of the real Cubase go to `docs/verification.md` with what was observed.
- **Writes** keep `dry_run`, the write policy and verification by reading back. A write whose outcome is unknown after a timeout is never retried.
- **Documentation** is bilingual: English `X.md` and Spanish `X.es.md`, updated in the same change. `tests/unit/test_docs.py` checks it.
- **Cubase script**: bump `SCRIPT_VERSION` on every change; Cubase only loads it after a restart.
- **Commits** in English. No AI attribution lines.

## Pull requests

Fill in the template. CI (`.github/workflows/ci.yml`) must be green. Say plainly what you checked in a real Cubase and what you did not.

## License

By contributing you agree that your contribution is licensed under the AGPL-3.0-or-later, like the rest of the project.
