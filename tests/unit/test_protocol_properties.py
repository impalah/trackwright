"""T-02: property-based tests of the SysEx framing (Hypothesis).

Whatever bytes arrive, parsing and reassembly either work or raise ``ProtocolError``; any payload that fits
survives the round trip whatever the fragment order, duplicates or the sequence number.
"""

from __future__ import annotations

import random

from hypothesis import given, settings
from hypothesis import strategies as st

from trackwright import protocol
from trackwright.coremidi import SysExAssembler
from trackwright.errors import ProtocolError

payloads = st.binary(min_size=1, max_size=protocol.MAX_FRAGMENT_PAYLOAD * 6).map(
    lambda raw: bytes(b & 0x7F for b in raw)  # SysEx data bytes are 7-bit
)
sequences = st.integers(min_value=0, max_value=protocol.SEQ_MODULO - 1)


@given(payload=payloads, seq=sequences, seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=300, deadline=None)
def test_round_trip_in_any_order_with_duplicates(payload: bytes, seq: int, seed: int) -> None:
    frames = protocol.build_frames(payload, seq)
    rng = random.Random(seed)
    delivered = frames + rng.sample(frames, k=min(2, len(frames)))  # some duplicates
    rng.shuffle(delivered)
    reassembler = protocol.Reassembler()
    results = []
    for raw in delivered:
        frame = protocol.parse_frame(raw)
        assert frame is not None
        assert frame.seq == seq
        done = reassembler.feed(frame)
        if done is not None:
            results.append(done)
    assert results[0] == payload


@given(data=st.lists(st.integers(min_value=0, max_value=255), max_size=300))
@settings(max_examples=500, deadline=None)
def test_arbitrary_bytes_never_crash_the_parser(data: list[int]) -> None:
    reassembler = protocol.Reassembler()
    try:
        frame = protocol.parse_frame(data)
        if frame is not None:
            reassembler.feed(frame)
    except ProtocolError:
        pass


@given(chunks=st.lists(st.binary(max_size=64), max_size=40))
@settings(max_examples=300, deadline=None)
def test_the_sysex_stream_never_grows_without_bound(chunks: list[bytes]) -> None:
    assembler = SysExAssembler()
    for chunk in chunks:
        for message in assembler.feed(chunk):
            assert all(b < 0x80 for b in message)
    buffered = assembler._buffer or []
    assert len(buffered) <= 4096
