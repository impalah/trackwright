from __future__ import annotations

import pytest

from trackwright import protocol
from trackwright.errors import ProtocolError


def roundtrip(obj: dict[str, object], seq: int = 1) -> dict[str, object]:
    reassembler = protocol.Reassembler()
    result = None
    for raw in protocol.build_frames(protocol.encode_payload(obj), seq):
        frame = protocol.parse_frame(raw)
        assert frame is not None
        result = reassembler.feed(frame)
    assert result is not None
    return protocol.decode_payload(result)


def test_roundtrip_unicode_is_ascii_on_the_wire() -> None:
    obj = {"op": "ping", "p": {"echo": "hola-ñ-✓"}}
    assert all(b < 128 for b in protocol.encode_payload(obj))
    assert roundtrip(obj) == obj


def test_roundtrip_largest_message() -> None:
    filler = "x" * (protocol.MAX_MESSAGE_BYTES - 20)
    assert roundtrip({"d": filler}, seq=protocol.SEQ_MODULO - 1)["d"] == filler


def test_too_large_payload() -> None:
    with pytest.raises(ProtocolError, match="exceeds"):
        protocol.encode_payload({"d": "x" * protocol.MAX_MESSAGE_BYTES})


def test_not_serializable() -> None:
    with pytest.raises(ProtocolError, match="serializable"):
        protocol.encode_payload({"x": float("nan")})


@pytest.mark.parametrize("data", [b"\xff", b"[1, 2]", b"{not json"])
def test_decode_rejects(data: bytes) -> None:
    with pytest.raises(ProtocolError):
        protocol.decode_payload(data)


def test_build_rejects_high_bytes_and_bad_seq() -> None:
    with pytest.raises(ProtocolError, match="> 127"):
        protocol.build_frames(bytes([200]), 1)
    with pytest.raises(ProtocolError, match="seq"):
        protocol.build_frames(b"{}", protocol.SEQ_MODULO)
    with pytest.raises(ProtocolError, match="fragments"):
        protocol.build_frames(b"x" * (protocol.MAX_MESSAGE_BYTES + 1), 1)


def test_empty_payload_is_one_frame() -> None:
    assert len(protocol.build_frames(b"", 3)) == 1


def test_header_layout() -> None:
    frame = protocol.build_frames(b"{}", (5 << 7) | 9)[0]
    assert frame[:8] == [0x7D, 0x54, 0x57, 1, 5, 9, 0, 1]


def test_foreign_frames_are_not_errors() -> None:
    identity_request = [0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7]
    assert protocol.parse_frame(identity_request) is None
    assert protocol.is_ours(identity_request) is False
    poc_frame = [0x7D, 0x43, 0x50, 1, 0, 1, 0, 1]
    assert protocol.parse_frame(poc_frame) is None


def test_delimiters_are_accepted() -> None:
    raw = protocol.build_frames(b"{}", 1)[0]
    frame = protocol.parse_frame([0xF0, *raw, 0xF7])
    assert frame is not None
    assert frame.data == b"{}"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ([0x7D, 0x54, 0x57, 1, 0], "truncated"),
        ([0x7D, 0x54, 0x57, 1, 0, 1, 0, 1, 200], "outside"),
        ([0x7D, 0x54, 0x57, 2, 0, 1, 0, 1], "version"),
        ([0x7D, 0x54, 0x57, 1, 0, 1, 1, 1], "fragment"),
        ([0x7D, 0x54, 0x57, 1, 0, 1, 0, 0], "fragment"),
        ([0x7D, 0x54, 0x57, 1, 0, 1, 0, 65], "fragment"),
        ([0x7D, 0x54, 0x57, 1, 0, 1, 0, 1, *([65] * 241)], "too large"),
    ],
)
def test_invalid_own_frames(data: list[int], message: str) -> None:
    with pytest.raises(ProtocolError, match=message):
        protocol.parse_frame(data)


def test_reassembly_out_of_order_and_duplicates() -> None:
    frames = [protocol.parse_frame(f) for f in protocol.build_frames(b"a" * 500, 7)]
    reassembler = protocol.Reassembler()
    assert frames[2] is not None
    assert frames[0] is not None
    assert frames[1] is not None
    assert reassembler.feed(frames[2]) is None
    assert reassembler.feed(frames[2]) is None  # duplicate ignored
    assert reassembler.feed(frames[0]) is None
    assert reassembler.pending == 1
    assert reassembler.feed(frames[1]) == b"a" * 500
    assert reassembler.pending == 0


def test_reassembly_count_mismatch() -> None:
    reassembler = protocol.Reassembler()
    reassembler.feed(protocol.Frame(seq=1, index=0, count=3, data=b"a"))
    with pytest.raises(ProtocolError, match="mismatch"):
        reassembler.feed(protocol.Frame(seq=1, index=1, count=2, data=b"b"))
    assert reassembler.dropped == 1


def test_reassembly_limits_and_expiry() -> None:
    now = [0.0]
    reassembler = protocol.Reassembler(max_pending=2, max_age_s=5.0, clock=lambda: now[0])
    reassembler.feed(protocol.Frame(seq=1, index=0, count=2, data=b"a"))
    reassembler.feed(protocol.Frame(seq=2, index=0, count=2, data=b"a"))
    with pytest.raises(ProtocolError, match="too many"):
        reassembler.feed(protocol.Frame(seq=3, index=0, count=2, data=b"a"))
    now[0] = 6.0
    assert reassembler.expire() == 2
    assert reassembler.pending == 0
    assert reassembler.dropped == 3


def test_make_request() -> None:
    assert protocol.make_request("ping", "1-a", None) == {"v": 1, "rid": "1-a", "op": "ping", "sid": ""}
    assert protocol.make_request("da.object", "2-b", "s", {"id": 3})["p"] == {"id": 3}
