"""Fixtures of the Cubase script tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.script.node_harness import Harness


@pytest.fixture
def h() -> Iterator[Harness]:
    harness = Harness()
    hello = harness.call("hello")
    assert hello["ok"], hello
    harness.sid = hello["r"]["sessionId"]
    yield harness
    harness.close()
