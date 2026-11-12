#!/usr/bin/env bash
# Run every quality gate: lint, format, types, tests with coverage (>= 85 %).
# Usage: scripts/check.sh            (from the repository root)
set -euo pipefail
cd "$(dirname "$0")/.."
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
uv run pytest --cov --cov-report=term-missing
