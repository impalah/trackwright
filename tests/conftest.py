"""Shared fixtures."""

from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest
from loguru import logger

from tests.support import ScriptedTransport
from trackwright.fake import FakeCubase


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
def _isolated_config(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Never read the developer's real configuration or socket directory, except in integration tests."""
    if request.node.get_closest_marker("integration"):
        return
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("TRACKWRIGHT_CONFIG", raising=False)
    monkeypatch.setenv("TMPDIR", str(tmp_path_factory.mktemp("tmp")))


@pytest.fixture(autouse=True)
def _nothing_logs_into_a_closed_stream() -> Iterator[None]:
    """After each test: cancel the scripted transport's delayed answers, and point loguru at whatever stderr is
    current. ``configure_logging`` (called by ``main()``) binds the sink to the ``sys.stderr`` object of the moment,
    which in a test is pytest's capture of that test and is closed when it ends: a later log line from a
    background thread would print a loguru "logging error"."""
    yield
    ScriptedTransport.cancel_pending()
    logger.remove()
    logger.add(_to_current_stderr, level="INFO")


def _to_current_stderr(message: object) -> None:
    sys.stderr.write(str(message))  # looked up on every call: never a stream that a finished test closed


@pytest.fixture
def fake() -> FakeCubase:
    """A fresh simulated Cubase (shared by the unit and contract tests, T-06)."""
    return FakeCubase()
