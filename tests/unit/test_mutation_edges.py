"""TW-1410: tests written to kill the mutants that survived the first mutation run of the safety modules
(``protocol``, ``core/policy``, ``core/refs``). Each test names the change it guards against."""

from __future__ import annotations

import math

import pytest

from trackwright import protocol
from trackwright.core.policy import WritePolicy
from trackwright.core.refs import TrackSelector
from trackwright.errors import PolicyError, ProtocolError


# ---------------------------------------------------------------- policy
def test_save_needs_its_own_switch() -> None:
    """`if not self.save` inverted, or the SAVE_DISABLED code lost."""
    with pytest.raises(PolicyError) as exc:
        WritePolicy(enabled=True, save=False).check_save()
    assert exc.value.code == "SAVE_DISABLED"
    WritePolicy(enabled=True, save=True).check_save()  # allowed: no exception
    with pytest.raises(PolicyError) as disabled:
        WritePolicy(enabled=False, save=True).check_save()
    assert disabled.value.code == "WRITES_DISABLED"


def test_not_allowed_details_name_the_track_and_the_list() -> None:
    with pytest.raises(PolicyError) as exc:
        WritePolicy(enabled=True, allowed_tracks=("A",)).check_track("B")
    assert exc.value.details == {"track": "B", "allowed_tracks": ["A"]}
    assert "'B'" in exc.value.message


def test_all_tracks_refusal_says_why() -> None:
    with pytest.raises(PolicyError) as exc:
        WritePolicy(enabled=True, allowed_tracks=("A",)).check_all_tracks("Split Loop")
    assert exc.value.details == {"allowed_tracks": ["A"]}
    assert exc.value.message.startswith("Split Loop can change any track")
    WritePolicy(enabled=True).check_all_tracks("Split Loop")  # no allowed_tracks: allowed


def test_writes_disabled_message_says_how_to_enable_them() -> None:
    with pytest.raises(PolicyError) as exc:
        WritePolicy().check_project_write()
    assert "[writes] enabled = true" in exc.value.message


# ---------------------------------------------------------------- selectors
def test_name_prefix_with_a_one_letter_name() -> None:
    """`raw[5:]` changed to `raw[6:]`: 'name:A' would become the literal name 'name:A'."""
    assert TrackSelector.parse("name:A") == TrackSelector("name", "A")


# ---------------------------------------------------------------- payload encoding
def test_payload_is_compact_ascii_json() -> None:
    """separators, ensure_ascii and allow_nan are part of the wire format."""
    assert protocol.encode_payload({"a": 1, "b": [1, 2]}) == b'{"a":1,"b":[1,2]}'
    assert protocol.encode_payload({"e": "ñ"}) == b'{"e":"\\u00f1"}'
    with pytest.raises(ProtocolError):
        protocol.encode_payload({"x": math.nan})


def test_payload_size_limit_is_inclusive() -> None:
    """`>` changed to `>=`: a payload of exactly MAX_MESSAGE_BYTES must still fit."""
    overhead = len(protocol.encode_payload({"s": ""}))
    exact = {"s": "x" * (protocol.MAX_MESSAGE_BYTES - overhead)}
    assert len(protocol.encode_payload(exact)) == protocol.MAX_MESSAGE_BYTES
    with pytest.raises(ProtocolError):
        protocol.encode_payload({"s": "x" * (protocol.MAX_MESSAGE_BYTES - overhead + 1)})


def test_decode_errors_are_protocol_errors_with_a_reason() -> None:
    with pytest.raises(ProtocolError, match="invalid JSON payload"):
        protocol.decode_payload(b"{nope")
    with pytest.raises(ProtocolError, match="not a JSON object"):
        protocol.decode_payload(b"[1]")


# ---------------------------------------------------------------- frames
def test_byte_128_is_not_a_data_byte() -> None:
    """`> 127` / `<= 127` loosened to 128."""
    with pytest.raises(ProtocolError, match="bytes > 127"):
        protocol.build_frames(bytes([128]), 1)
    frame = protocol.build_frames(b"ok", 1)[0]
    with pytest.raises(ProtocolError, match=r"outside 0\.\.127"):
        protocol.parse_frame([*frame[:-1], 128])


def test_the_shortest_tag_is_ours() -> None:
    """`len(body) >= 3` changed to `> 3` or `>= 4`."""
    assert protocol.is_ours([protocol.MANUFACTURER_ID, *protocol.MAGIC]) is True
    assert protocol.is_ours([protocol.MANUFACTURER_ID, protocol.MAGIC[0]]) is False


def test_an_empty_payload_is_one_empty_fragment() -> None:
    frames = protocol.build_frames(b"", 3)
    assert len(frames) == 1
    parsed = protocol.parse_frame(frames[0])
    assert parsed is not None and parsed.data == b""


# ---------------------------------------------------------------- reassembly
def test_reassembler_defaults() -> None:
    reassembler = protocol.Reassembler()
    assert (reassembler.max_pending, reassembler.max_age_s) == (16, 5.0)


def test_eviction_drops_the_oldest_assembly_not_the_lowest_sequence() -> None:
    now = [0.0]
    reassembler = protocol.Reassembler(max_pending=2, clock=lambda: now[0])
    reassembler.feed(protocol.Frame(seq=9, index=0, count=2, data=b"a"))  # oldest, highest seq
    now[0] = 1.0
    reassembler.feed(protocol.Frame(seq=1, index=0, count=2, data=b"a"))
    now[0] = 2.0
    reassembler.feed(protocol.Frame(seq=5, index=0, count=2, data=b"a"))  # evicts seq 9
    assert reassembler.feed(protocol.Frame(seq=1, index=1, count=2, data=b"b")) == b"ab"
    assert reassembler.feed(protocol.Frame(seq=9, index=1, count=2, data=b"b")) is None


def test_dropped_counts_every_drop() -> None:
    """`dropped += 1` changed to `dropped = 1`."""
    reassembler = protocol.Reassembler(max_pending=1)
    reassembler.feed(protocol.Frame(seq=1, index=0, count=2, data=b"a"))
    for _ in range(2):
        with pytest.raises(ProtocolError):
            reassembler.feed(protocol.Frame(seq=1, index=0, count=3, data=b"x"))
    reassembler.feed(protocol.Frame(seq=2, index=0, count=2, data=b"a"))  # evicts seq 1
    reassembler.feed(protocol.Frame(seq=3, index=0, count=2, data=b"a"))  # evicts seq 2
    assert reassembler.dropped == 4


def test_an_assembly_exactly_at_the_age_limit_is_kept() -> None:
    """`>` changed to `>=` in expire."""
    now = [0.0]
    reassembler = protocol.Reassembler(max_age_s=5.0, clock=lambda: now[0])
    reassembler.feed(protocol.Frame(seq=1, index=0, count=2, data=b"a"))
    now[0] = 5.0
    assert reassembler.expire() == 0
    now[0] = 5.01
    assert reassembler.expire() == 1
