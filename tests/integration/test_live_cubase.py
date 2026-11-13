"""Opt-in integration tests against a running bridge and Cubase (TW-0904).

Reads:   TRACKWRIGHT_INTEGRATION=1 uv run pytest tests/integration
Writes:  also TRACKWRIGHT_ALLOW_WRITES=1 and TRACKWRIGHT_TEST_TRACK=<track name or uid:...>
         Every write is reverted. Use a disposable project.

The bridge must be running (``trackwright bridge``) with the default or ``$TRACKWRIGHT_CONFIG`` settings.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from trackwright.cli import make_service
from trackwright.config import load_settings
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.cubase import SCRIPT_VERSION

LIVE = os.environ.get("TRACKWRIGHT_INTEGRATION") == "1"
WRITES = LIVE and os.environ.get("TRACKWRIGHT_ALLOW_WRITES") == "1"
TEST_TRACK = os.environ.get("TRACKWRIGHT_TEST_TRACK", "")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not LIVE, reason="set TRACKWRIGHT_INTEGRATION=1 with the bridge and Cubase running"),
]


@pytest.fixture(scope="module")
def live() -> Iterator[CubaseService]:
    service: CubaseService = make_service(load_settings(), simulate=False)
    yield service


@pytest.fixture(scope="module")
def writer(live: CubaseService) -> CubaseService:
    if not WRITES or not TEST_TRACK:
        pytest.skip("set TRACKWRIGHT_ALLOW_WRITES=1 and TRACKWRIGHT_TEST_TRACK to run write tests")
    return CubaseService(live.host, WritePolicy(enabled=True, allowed_tracks=()))


def test_status(live: CubaseService) -> None:
    status = live.status()
    assert status.connected
    assert status.simulated is False
    assert status.script_version == SCRIPT_VERSION


def test_tracks_and_inserts(live: CubaseService) -> None:
    tracks = live.list_tracks()
    assert tracks.total >= 1
    uids = [t.uid for t in tracks.tracks]
    assert len(uids) == len(set(uids)), "the mixer list must be deduplicated"
    assert len(live.list_inserts(tracks.tracks[-1].track).slots) >= 1


def test_transport(live: CubaseService) -> None:
    assert live.get_transport().cursor.time


@pytest.mark.integration_write
def test_mute_roundtrip(writer: CubaseService) -> None:
    before = next(t for t in writer.list_tracks().tracks if TEST_TRACK in (t.name, t.track))
    target = before.track
    flipped = not bool(before.mute)
    assert writer.set_track_mix(target, mute=flipped, dry_run=False).verified
    assert writer.set_track_mix(target, mute=bool(before.mute), dry_run=False).verified


@pytest.mark.integration_write
def test_cursor_roundtrip(writer: CubaseService) -> None:
    original = writer.get_transport().cursor.time
    assert writer.set_position("cursor", "3.1.1.0").verified
    assert writer.set_position("cursor", original).verified
