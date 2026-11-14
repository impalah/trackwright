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
    return CubaseService(
        live.host, WritePolicy(enabled=True, allowed_tracks=(TEST_TRACK,))
    )  # T-08: only the test track


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


# ---------------------------------------------------------------- TW-1411: more tools against the real Cubase
@pytest.fixture
def track(live: CubaseService) -> str:
    """The test track when given, otherwise the last track with a mixer channel (reads only)."""
    tracks = live.list_tracks().tracks
    chosen = next((t for t in tracks if TEST_TRACK in (t.name, t.track)), None) if TEST_TRACK else None
    return (chosen or tracks[-1]).track


@pytest.fixture
def keep_selection(live: CubaseService) -> Iterator[None]:
    """Some reads select a track (automation targets follow the selection): put the selection back."""
    before = live.get_selected_channel().track
    yield
    if before is not None:
        live.select_track(before.track)


def test_selected_channel(live: CubaseService) -> None:
    out = live.get_selected_channel()
    assert isinstance(out.sections, list)
    if out.track is not None:
        assert out.track.uid


def test_plugin_catalog(live: CubaseService, track: str) -> None:
    catalog = live.list_available_plugins(track, limit=5)
    assert catalog.items, "the active plugin collection is empty"
    assert all(p.uid for p in catalog.items)


def test_parameters_of_a_channel(live: CubaseService, track: str) -> None:
    listing = live.list_parameters(track, "channel", limit=5)
    assert listing.total > 0
    assert len(listing.items) == 5
    volume = live.get_parameter(track, "channel", 1025)
    assert volume.parameter.title
    assert 0.0 <= float(volume.parameter.process or 0) <= 1.0


def test_project_properties(live: CubaseService) -> None:
    project = live.get_project()
    assert project.tempo_bpm is not None and 20 <= project.tempo_bpm <= 300
    assert project.signature is not None


def test_poll_changes(live: CubaseService) -> None:
    assert isinstance(live.poll_changes().events, list)


@pytest.mark.usefixtures("keep_selection")
def test_automation_targets_and_exact_conversion(live: CubaseService, track: str) -> None:
    targets = {t.parameter for t in live.list_automation_targets(track).targets}
    assert {"volume", "pan"} <= targets
    converted = live.convert_value(track, "volume", plain=0.0)
    assert converted.value == pytest.approx(0.7891, abs=1e-3)  # 0 dB (verified in TW-1208)


def test_marker_navigation_puts_the_cursor_back(live: CubaseService) -> None:
    original = live.get_transport().cursor.time
    live.markers("locate_prev", dry_run=False)
    assert live.set_position("cursor", original).verified


@pytest.mark.integration_write
def test_parameter_roundtrip(writer: CubaseService, track: str) -> None:
    before = float(writer.get_parameter(track, "channel", 1025).parameter.process or 0)
    try:
        assert writer.set_parameter(track, "channel", 1025, 0.5, dry_run=False).verified
    finally:
        assert writer.set_parameter(track, "channel", 1025, before, dry_run=False).verified


@pytest.mark.integration_write
def test_rename_roundtrip(writer: CubaseService, track: str) -> None:
    temporary = "TW-RENAME-TEST"
    original = next(t.name for t in writer.list_tracks().tracks if t.track == track)
    # The restore renames a track called `temporary`: allow both names, or the policy would block it
    # (found the first time this test ran: the track stayed renamed).
    renamer = CubaseService(writer.host, WritePolicy(enabled=True, allowed_tracks=(original, temporary)))
    try:
        assert renamer.rename_track(track, temporary, dry_run=False).verified
    finally:
        assert renamer.rename_track(track, original, dry_run=False).verified


@pytest.mark.integration_write
@pytest.mark.usefixtures("keep_selection")
def test_select_roundtrip(writer: CubaseService, track: str) -> None:
    assert writer.select_track(track).verified


@pytest.mark.integration_write
def test_tempo_roundtrip(writer: CubaseService) -> None:
    before = writer.get_project().tempo_bpm
    assert before is not None
    try:
        assert writer.set_tempo(before + 1, dry_run=False).verified
    finally:
        assert writer.set_tempo(before, dry_run=False).verified


@pytest.mark.integration_write
def test_project_setting_roundtrip(writer: CubaseService) -> None:
    before = writer.set_project({"metronome": True}).changes[0].before
    assert isinstance(before, bool)
    try:
        assert writer.set_project({"metronome": not before}, dry_run=False).verified
    finally:
        assert writer.set_project({"metronome": before}, dry_run=False).verified
