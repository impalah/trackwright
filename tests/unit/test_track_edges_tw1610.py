"""TW-1610: the event edges of one track, probed and with the cursor and the selection put back."""

from __future__ import annotations

import pytest

from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import PreconditionFailedError
from trackwright.fake import FakeCubase


@pytest.fixture
def svc(fake: FakeCubase) -> CubaseService:
    fake.track_events[fake.channel_by_title("POC-TEST").id] = [(10.0, 20.0), (30.0, 40.0)]
    return CubaseService(fake, WritePolicy(), sleep=lambda _s: None, settle_timeout=0.0)


def test_edges_and_extent(svc: CubaseService, fake: FakeCubase) -> None:
    fake.selected = fake.channel_by_title("POC-INSTR").id
    cursor = fake.transport["locator"]
    out = svc.track_edges("POC-TEST")
    assert out.edges_seconds == [10.0, 20.0, 30.0, 40.0]
    assert (out.first, out.last, out.complete) == ("0:00:10.000", "0:00:40.000", True)
    assert out.track_uid == f"uid:{fake.channel_by_title('POC-TEST').uid}"
    assert any("exactly at 0 s" in n for n in out.notes)
    assert fake.selected == fake.channel_by_title("POC-INSTR").id  # put back
    assert fake.transport["locator"] == cursor


def test_a_window_and_a_limit(svc: CubaseService) -> None:
    window = svc.track_edges("POC-TEST", start="15", end="35")
    assert (window.edges_seconds, window.end, window.complete) == ([20.0, 30.0], "0:00:35.000", True)
    assert not any("exactly at 0 s" in n for n in window.notes)
    capped = svc.track_edges("POC-TEST", limit=2)
    assert (capped.edges_seconds, capped.complete) == ([10.0, 20.0], False)
    assert any("stopped after 2 edges" in n for n in capped.notes)
    empty = svc.track_edges("POC-TEST", start="45")
    assert (empty.edges, empty.first) == ([], None)
    assert any("no event edge" in n for n in empty.notes)


def test_refusals(svc: CubaseService, fake: FakeCubase) -> None:
    with pytest.raises(PreconditionFailedError):
        svc.track_edges("POC-TEST", limit=0)
    with pytest.raises(PreconditionFailedError):
        svc.track_edges("POC-TEST", start="soon")
    fake.studio_param("transport", "start").value = 1
    with pytest.raises(PreconditionFailedError) as running:
        svc.track_edges("POC-TEST")
    assert running.value.code == "TRANSPORT_RUNNING"
