"""Request/response client for the Cubase script over a :class:`~trackwright.transport.Transport`.

Responsibilities (all verified against Cubase in the POC, milestone H):

- correlate responses by ``rid``; responses that arrive after their timeout are kept as *late*
  and never attributed to another request;
- negotiate the script session with ``hello``; after a script reload, reads that fail with
  ``STALE_SESSION`` renegotiate once and are retried; **writes are never retried**;
- serialize writes so that at most one is in flight.
"""

from __future__ import annotations

import itertools
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from trackwright import protocol
from trackwright.errors import ProtocolError, RequestTimeoutError, StaleSessionError, TrackwrightError, host_error
from trackwright.ops import WRITE_OPS
from trackwright.transport import Transport

JsonObject = dict[str, Any]
MIN_WRITE_BUDGET = 0.25
"""Seconds a write needs left to be worth sending (one idle tick is ~110 ms)."""
_HISTORY = 50


@dataclass(slots=True)
class _Pending:
    op: str
    sent_at: float
    event: threading.Event = field(default_factory=threading.Event)
    response: JsonObject | None = None


@dataclass(frozen=True, slots=True)
class Reply:
    """A successful response from the script."""

    op: str
    rid: str
    result: JsonObject
    via: str | None
    duplicate: bool
    duration_ms: float


class HostClient:
    def __init__(self, transport: Transport, *, default_timeout: float = 3.0) -> None:
        self.transport = transport
        self.default_timeout = default_timeout
        self.session_id: str | None = None
        self.host_info: JsonObject | None = None
        self.script_version: str | None = None
        self._pending: dict[str, _Pending] = {}
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._rid_counter = itertools.count(1)
        self._seq_counter = itertools.count(1)
        self._reassembler = protocol.Reassembler()
        self.late_responses: deque[JsonObject] = deque(maxlen=_HISTORY)
        self.unsolicited: deque[JsonObject] = deque(maxlen=_HISTORY)
        self.protocol_errors: deque[str] = deque(maxlen=_HISTORY)
        self.session_changes: list[JsonObject] = []

    # ------------------------------------------------------------------ lifecycle
    def open(self) -> None:
        self.transport.open(self._on_sysex)

    def close(self) -> None:
        self.transport.close()

    # ------------------------------------------------------------------ receive path (transport thread)
    def _on_sysex(self, data: list[int]) -> None:
        try:
            frame = protocol.parse_frame(data)
            if frame is None:
                return
            payload = self._reassembler.feed(frame)
            if payload is None:
                return
            message = protocol.decode_payload(payload)
        except ProtocolError as exc:
            self.protocol_errors.append(str(exc))
            logger.warning("protocol error: {}", exc)
            return
        rid = message.get("rid", "")
        with self._lock:
            pending = self._pending.get(rid) if isinstance(rid, str) else None
            if pending is not None and pending.response is None:
                pending.response = message
                pending.event.set()
                return
        entry = {"received_at": time.time(), "message": message}
        if pending is None and rid:
            self.late_responses.append(entry)
            logger.warning("late or unknown response rid={} op={}", rid, message.get("op"))
        else:
            self.unsolicited.append(entry)

    # ------------------------------------------------------------------ requests
    def new_rid(self) -> str:
        return f"{next(self._rid_counter):x}-{secrets.token_hex(3)}"

    def request(
        self,
        op: str,
        params: JsonObject | None = None,
        *,
        timeout: float | None = None,
        rid: str | None = None,
        session: str | None = None,
    ) -> Reply:
        """Send one request and wait for its response. Writes are serialized and never retried.

        The whole call, including waiting for another write to finish, fits in ``timeout``: if the
        write lock is not free in time, or too little time is left to wait for the answer, the write
        fails with ``BUSY`` without being sent (TW-1402). ``session`` overrides the negotiated session.
        """
        wait = self.default_timeout if timeout is None else timeout
        if op not in WRITE_OPS:
            return self._request(op, params, wait, rid, session)
        started = time.monotonic()
        if not self._write_lock.acquire(timeout=max(wait - MIN_WRITE_BUDGET, 0.0)):
            raise self._busy(op, "another write is still running")
        try:
            left = wait - (time.monotonic() - started)
            if left < MIN_WRITE_BUDGET:
                raise self._busy(op, f"only {left:.2f}s left to wait for the answer")
            return self._request(op, params, left, rid, session)
        finally:
            self._write_lock.release()

    @staticmethod
    def _busy(op: str, reason: str) -> TrackwrightError:
        return TrackwrightError(
            f"{reason}; {op} was not sent", code="BUSY", details={"op": op, "outcome": "not_executed"}
        )

    def _request(
        self, op: str, params: JsonObject | None, wait: float, rid: str | None, session: str | None = None
    ) -> Reply:
        rid = rid or self.new_rid()
        sid = session or self.session_id
        payload = protocol.encode_payload(protocol.make_request(op, rid, sid, params))
        pending = _Pending(op=op, sent_at=time.monotonic())
        with self._lock:
            if rid in self._pending:
                raise ProtocolError(f"rid {rid!r} is already pending")
            self._pending[rid] = pending
        try:
            seq = next(self._seq_counter) % protocol.SEQ_MODULO
            for frame in protocol.build_frames(payload, seq):
                self.transport.send_sysex(frame)
            if not pending.event.wait(max(wait, 0.0)) and not self._arrived(pending):
                is_write = op in WRITE_OPS
                outcome = "unknown: read the state back, do not retry" if is_write else "no response"
                raise RequestTimeoutError(
                    f"{op} timed out after {wait:.2f}s ({outcome})",
                    outcome_unknown=is_write,
                    details={"rid": rid, "op": op},
                )
        finally:
            with self._lock:
                self._pending.pop(rid, None)
        message = pending.response or {}
        duration_ms = (time.monotonic() - pending.sent_at) * 1000
        if not message.get("ok"):
            error = message.get("err") or {}
            raise host_error(
                str(error.get("code", "HOST_ERROR")),
                str(error.get("msg", "")),
                {"rid": rid, "op": op, "via": message.get("via")},
            )
        result = message.get("r")
        return Reply(
            op=op,
            rid=rid,
            result=result if isinstance(result, dict) else {},
            via=message.get("via"),
            duplicate=bool(message.get("dup")),
            duration_ms=duration_ms,
        )

    def _arrived(self, pending: _Pending) -> bool:
        """A response may land between the end of the wait and the removal of the pending entry."""
        with self._lock:
            return pending.response is not None

    # ------------------------------------------------------------------ session
    def hello(self, timeout: float | None = None) -> Reply:
        reply = self.request("hello", timeout=timeout)
        new_session = reply.result.get("sessionId")
        if self.session_id and new_session != self.session_id:
            self.session_changes.append({"old": self.session_id, "new": new_session, "at": time.time()})
            logger.info("script session changed: {} -> {}", self.session_id, new_session)
        self.session_id = new_session if isinstance(new_session, str) else None
        host = reply.result.get("host")
        self.host_info = host if isinstance(host, dict) else None
        version = reply.result.get("scriptVersion")
        self.script_version = version if isinstance(version, str) else None
        return reply

    def call(
        self, op: str, params: JsonObject | None = None, *, timeout: float | None = None, session: str | None = None
    ) -> Reply:
        """Request with session negotiation; a stale session is renegotiated and retried for reads only.

        Every step (``hello``, request, retry) shares one deadline, so the caller's timeout holds.
        Callers that gathered object ids before a renegotiation must not reuse them: the MCP layer
        pins the session per tool call (see ``trackwright.core.base``) and sends writes with that
        ``session``, which is used as is: no ``hello`` first, so the script refuses a stale write.
        """
        deadline = time.monotonic() + (self.default_timeout if timeout is None else timeout)

        def remaining() -> float:
            left = deadline - time.monotonic()
            if left <= 0:
                raise RequestTimeoutError(
                    f"{op}: no time left", outcome_unknown=False, details={"op": op, "outcome": "not_executed"}
                )
            return left

        if op == "hello":
            return self.hello(remaining())
        if session is not None and op in WRITE_OPS:
            return self.request(op, params, timeout=remaining(), session=session)
        if not self.session_id:
            self.hello(remaining())
        try:
            return self.request(op, params, timeout=remaining())
        except StaleSessionError:
            if op in WRITE_OPS:
                raise
            self.hello(remaining())
            return self.request(op, params, timeout=remaining())

    def stats(self) -> JsonObject:
        return {
            "session_id": self.session_id,
            "script_version": self.script_version,
            "pending": len(self._pending),
            "late_responses": list(self.late_responses)[-10:],
            "unsolicited": len(self.unsolicited),
            "protocol_errors": list(self.protocol_errors)[-10:],
            "session_changes": self.session_changes[-10:],
            "transport": self.transport.stats(),
        }
