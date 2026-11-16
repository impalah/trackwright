"""TW-1616: the automation controls follow a new selection a moment later; nothing acts on the wrong track."""

from __future__ import annotations

import pytest

from trackwright.core import automation
from trackwright.core.models import AutomationPoint
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import PreconditionFailedError
from trackwright.fake import FakeCubase


def make(fake: FakeCubase) -> CubaseService:
    return CubaseService(fake, WritePolicy(enabled=True), sleep=lambda _s: None, settle_timeout=0.0)


def test_the_listing_waits_for_the_controls(fake: FakeCubase) -> None:
    """Live: read right after selecting POC-TEST, the volume was 'POC-TEST ducked / Volumen'."""
    fake.auto_lag = ["Stereo Out", "Stereo Out"]  # two readings still bound to the previous selection
    out = make(fake).list_automation_targets("POC-TEST")
    volume = next(t for t in out.targets if t.parameter == "volume")
    assert volume.title == "POC-TEST / Volumen"
    assert fake.auto_lag == []


def test_conversion_and_recording_wait_too(fake: FakeCubase) -> None:
    fake.auto_lag = ["Stereo Out"]
    converted = make(fake).convert_value("POC-TEST", "volume", value=0.5)
    assert converted.title == "POC-TEST / Volumen"
    fake.auto_lag = ["Stereo Out"]
    plan = make(fake).record_automation(
        "POC-TEST", "volume", [AutomationPoint(position="2. 1. 1. 0", value=0.5)], dry_run=True
    )
    assert plan.title == "POC-TEST / Volumen"  # the dry run's title is the target track's (TW-1635)


def test_controls_that_never_follow_stop_everything(fake: FakeCubase, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(automation, "CONTROLS_TIMEOUT", 0.0)
    fake.auto_lag = ["Stereo Out"] * 50
    with pytest.raises(PreconditionFailedError) as exc:
        make(fake).record_automation(
            "POC-TEST", "volume", [AutomationPoint(position="2. 1. 1. 0", value=0.5)], dry_run=False
        )
    assert exc.value.code == "CONTROLS_NOT_BOUND"
    assert "Stereo Out / Volumen" in exc.value.message
    assert fake.automation == {}  # nothing was written
