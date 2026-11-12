"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from loguru import logger


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def log_records() -> Iterator[list[str]]:
    """Capture loguru messages emitted during a test."""
    records: list[str] = []
    sink_id = logger.add(lambda message: records.append(str(message)), level="TRACE", format="{level}|{message}")
    yield records
    logger.remove(sink_id)


@pytest.fixture(autouse=True)
def _isolated_config(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Never read the developer's real configuration or socket directory during tests."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("TRACKWRIGHT_CONFIG", raising=False)
    monkeypatch.setenv("TMPDIR", str(tmp_path_factory.mktemp("tmp")))
