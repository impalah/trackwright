"""Wire protocol between Python and the Trackwright MIDI Remote script.

Frame (SysEx). ``mido`` strips F0/F7, so ``data`` below excludes them::

    7D 54 57 <ver> <seq_hi> <seq_lo> <frag_idx> <frag_count> <ascii payload...>

- ``0x7D`` is the SysEx ID reserved for non-commercial use.
- ``0x54 0x57`` ("TW") tags Trackwright traffic. Frames with another tag (for example Cubase's
  universal Identity Request ``7E 7F 06 01``, sent every ~5 s) are *foreign*, not errors.
- ``seq`` is a 14-bit message number chosen by the sender.
- The payload is JSON encoded as ASCII (non-ASCII escaped as ``\\uXXXX``), so every byte is 0..127.

Envelope::

    request:  {"v": 1, "sid": str, "rid": str, "op": str, "p": {...}}
    response: {"v": 1, "sid": str, "rid": str, "op": str, "ok": bool,
               "r": {...} | "err": {"code": str, "msg": str}, "via": "sysex" | "idle", "dup": bool?}
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from trackwright.errors import ProtocolError

PROTOCOL_VERSION = 1
MANUFACTURER_ID = 0x7D
MAGIC = (0x54, 0x57)
HEADER_LEN = 8
MAX_FRAGMENT_PAYLOAD = 240
MAX_FRAGMENTS = 64
MAX_MESSAGE_BYTES = MAX_FRAGMENT_PAYLOAD * MAX_FRAGMENTS
SEQ_MODULO = 1 << 14

JsonObject = dict[str, Any]


def encode_payload(obj: JsonObject) -> bytes:
    """Serialize to compact ASCII JSON; raise :class:`ProtocolError` if it does not fit in one message."""
    try:
        text = json.dumps(obj, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"payload is not JSON serializable: {exc}") from exc
    data = text.encode("ascii")
    if len(data) > MAX_MESSAGE_BYTES:
        raise ProtocolError(f"payload of {len(data)} bytes exceeds {MAX_MESSAGE_BYTES}")
    return data


def decode_payload(data: bytes) -> JsonObject:
    try:
        obj = json.loads(data.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"invalid JSON payload: {exc}") from exc
    if not isinstance(obj, dict):
        raise ProtocolError("payload is not a JSON object")
    return obj


def build_frames(payload: bytes, seq: int) -> list[list[int]]:
    """Split an ASCII payload into SysEx data lists (without F0/F7)."""
    if any(b > 127 for b in payload):
        raise ProtocolError("payload contains bytes > 127")
    if not 0 <= seq < SEQ_MODULO:
        raise ProtocolError(f"seq {seq} out of range")
    chunks = [payload[i : i + MAX_FRAGMENT_PAYLOAD] for i in range(0, len(payload), MAX_FRAGMENT_PAYLOAD)] or [b""]
    if len(chunks) > MAX_FRAGMENTS:
        raise ProtocolError(f"payload needs {len(chunks)} fragments (max {MAX_FRAGMENTS})")
    count = len(chunks)
    header = [MANUFACTURER_ID, *MAGIC, PROTOCOL_VERSION, (seq >> 7) & 0x7F, seq & 0x7F]
    return [[*header, idx, count, *chunk] for idx, chunk in enumerate(chunks)]


@dataclass(frozen=True, slots=True)
class Frame:
    seq: int
    index: int
    count: int
    data: bytes


def is_ours(data: Sequence[int]) -> bool:
    """Whether SysEx data (with or without F0/F7) carries the Trackwright tag."""
    body = _strip_delimiters(data)
    return len(body) >= 3 and body[0] == MANUFACTURER_ID and (body[1], body[2]) == MAGIC


def parse_frame(data: Sequence[int]) -> Frame | None:
    """Parse SysEx data. Return ``None`` for foreign frames; raise :class:`ProtocolError` for invalid own frames."""
    if not is_ours(data):
        return None
    body = _strip_delimiters(data)
    if len(body) < HEADER_LEN:
        raise ProtocolError("truncated header")
    if any(not 0 <= b <= 127 for b in body):
        raise ProtocolError("data byte outside 0..127")
    ver, seq_hi, seq_lo, idx, count = body[3:8]
    if ver != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol version {ver}")
    if not 1 <= count <= MAX_FRAGMENTS or idx >= count:
        raise ProtocolError(f"invalid fragment {idx}/{count}")
    payload = bytes(body[8:])
    if len(payload) > MAX_FRAGMENT_PAYLOAD:
        raise ProtocolError("fragment payload too large")
    return Frame(seq=(seq_hi << 7) | seq_lo, index=idx, count=count, data=payload)


def _strip_delimiters(data: Sequence[int]) -> list[int]:
    body = list(data)
    if body and body[0] == 0xF0:
        body = body[1:]
    if body and body[-1] == 0xF7:
        body = body[:-1]
    return body


@dataclass(slots=True)
class _Assembly:
    count: int
    started: float
    parts: dict[int, bytes] = field(default_factory=dict)


class Reassembler:
    """Reassemble fragments with bounded memory and time.

    Out-of-order fragments are accepted, duplicates ignored and stale assemblies expired.
    """

    def __init__(
        self, *, max_pending: int = 16, max_age_s: float = 5.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.max_pending = max_pending
        self.max_age_s = max_age_s
        self._clock = clock
        self._pending: dict[int, _Assembly] = {}
        self.dropped = 0

    @property
    def pending(self) -> int:
        return len(self._pending)

    def feed(self, frame: Frame) -> bytes | None:
        """Add a fragment; return the full payload when the message is complete."""
        self.expire()
        assembly = self._pending.get(frame.seq)
        if assembly is None:
            if len(self._pending) >= self.max_pending:  # I-07: make room by dropping the oldest, not the new one
                oldest = min(self._pending, key=lambda seq: self._pending[seq].started)
                del self._pending[oldest]
                self.dropped += 1
            assembly = _Assembly(count=frame.count, started=self._clock())
            self._pending[frame.seq] = assembly
        if assembly.count != frame.count:  # I-07: a stray frame must not destroy a legitimate assembly
            self.dropped += 1
            raise ProtocolError("fragment count mismatch")
        if frame.index in assembly.parts:
            return None
        assembly.parts[frame.index] = frame.data
        if len(assembly.parts) < assembly.count:
            return None
        del self._pending[frame.seq]
        return b"".join(assembly.parts[i] for i in range(assembly.count))

    def expire(self) -> int:
        now = self._clock()
        stale = [seq for seq, a in self._pending.items() if now - a.started > self.max_age_s]
        for seq in stale:
            del self._pending[seq]
        self.dropped += len(stale)
        return len(stale)


def make_request(op: str, rid: str, sid: str | None, params: JsonObject | None = None) -> JsonObject:
    request: JsonObject = {"v": PROTOCOL_VERSION, "rid": rid, "op": op, "sid": sid or ""}
    if params:
        request["p"] = params
    return request
