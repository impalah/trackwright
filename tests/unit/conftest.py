from __future__ import annotations

import pytest

from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.fake import FakeCubase


@pytest.fixture
def fake() -> FakeCubase:
    return FakeCubase()


@pytest.fixture
def service(fake: FakeCubase) -> CubaseService:
    """Service over the simulator with writes enabled and no waiting."""
    return CubaseService(fake, WritePolicy(enabled=True), sleep=lambda _s: None, settle_timeout=0.0)


@pytest.fixture
def readonly(fake: FakeCubase) -> CubaseService:
    """Service with the default policy (writes disabled)."""
    return CubaseService(fake, WritePolicy(), sleep=lambda _s: None, settle_timeout=0.0)
