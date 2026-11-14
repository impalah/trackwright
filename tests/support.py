"""Test doubles shared by the unit tests."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from trackwright import protocol
from trackwright.errors import HostError, RequestTimeoutError, StaleSessionError
from trackwright.host import HostClient, Reply
from trackwright.transport import Receiver

JsonObject = dict[str, Any]
Handler = Callable[[JsonObject], JsonObject | list[JsonObject] | None]


def ok(request: JsonObject, result: JsonObject | None = None, **extra: Any) -> JsonObject:
    return {
        "v": 1,
        "sid": request.get("sid"),
        "rid": request["rid"],
        "op": request["op"],
        "ok": True,
        "r": result or {},
        **extra,
    }


def fail(request: JsonObject, code: str, msg: str = "") -> JsonObject:
    return {"v": 1, "rid": request["rid"], "op": request["op"], "ok": False, "err": {"code": code, "msg": msg}}


class ScriptedTransport:
    """Speaks the real wire protocol; ``handler`` plays the Cubase script.

    The handler receives the decoded request and returns a response, a list of responses
    (sent in order) or ``None`` (no answer). ``delay`` answers from another thread after a pause.
    """

    name = "scripted"

    def __init__(self, handler: Handler, *, delay: float = 0.0, fragment_size: int | None = None) -> None:
        self.handler = handler
        self.delay = delay
        self.fragment_size = fragment_size
        self.receiver: Receiver | None = None
        self.requests: list[JsonObject] = []
        self._reassembler = protocol.Reassembler()
        self._seq = 0
        self.closed = False

    def open(self, receiver: Receiver) -> None:
        self.receiver = receiver

    def close(self) -> None:
        self.closed = True

    def stats(self) -> dict[str, int]:
        return {"sent_frames": len(self.requests)}

    def send_sysex(self, data: Sequence[int]) -> None:
        frame = protocol.parse_frame(list(data))
        assert frame is not None
        payload = self._reassembler.feed(frame)
        if payload is None:
            return
        request = protocol.decode_payload(payload)
        self.requests.append(request)
        answer = self.handler(request)
        responses = [] if answer is None else answer if isinstance(answer, list) else [answer]
        if self.delay:
            threading.Timer(self.delay, self._deliver, args=(responses,)).start()
        else:
            self._deliver(responses)

    def push(self, message: JsonObject) -> None:
        """Deliver an arbitrary message (late response, unsolicited...)."""
        self._deliver([message])

    def push_raw(self, data: list[int]) -> None:
        assert self.receiver is not None
        self.receiver(data)

    def _deliver(self, responses: list[JsonObject]) -> None:
        assert self.receiver is not None
        for response in responses:
            self._seq = (self._seq + 1) % protocol.SEQ_MODULO
            frames = protocol.build_frames(protocol.encode_payload(response), self._seq)
            for frame in reversed(frames) if len(frames) > 1 else frames:  # out of order on purpose
                self.receiver(frame)


@dataclass
class FakeMessage:
    type: str
    data: tuple[int, ...] = ()


@dataclass
class FakePort:
    name: str
    callback: Callable[[FakeMessage], None] | None = None
    sent: list[FakeMessage] = field(default_factory=list)
    closed: bool = False
    fail_on_close: bool = False

    def send(self, message: FakeMessage) -> None:
        self.sent.append(message)

    def close(self) -> None:
        if self.fail_on_close:
            raise OSError("close failed")
        self.closed = True


class FakeMido:
    """Minimal stand-in for the ``mido`` module."""

    def __init__(self, inputs: Sequence[str] = (), outputs: Sequence[str] = (), *, fail_open: bool = False) -> None:
        self.inputs = list(inputs)
        self.outputs = list(outputs)
        self.fail_open = fail_open
        self.out_port: FakePort | None = None
        self.in_port: FakePort | None = None

    def get_input_names(self) -> list[str]:
        return self.inputs

    def get_output_names(self) -> list[str]:
        return self.outputs

    def open_output(self, name: str, virtual: bool) -> FakePort:
        assert virtual
        self.out_port = FakePort(name)
        return self.out_port

    def open_input(self, name: str, virtual: bool, callback: Callable[[FakeMessage], None]) -> FakePort:
        assert virtual
        if self.fail_open:
            raise OSError("CoreMIDI refused")
        self.in_port = FakePort(name, callback=callback)
        return self.in_port

    @staticmethod
    def Message(kind: str, data: list[int]) -> FakeMessage:  # noqa: N802 - mirrors mido.Message
        return FakeMessage(kind, tuple(data))


# ---------------------------------------------------------------- shared doubles (T-06)
class FakeScript:
    """A tiny script: sessions, a parameter store and duplicate cache."""

    def __init__(self) -> None:
        self.session = "s1"
        self.value = 0.5
        self.executed: list[str] = []
        self.cache: dict[str, JsonObject] = {}

    def __call__(self, req: JsonObject) -> JsonObject | list[JsonObject] | None:
        key = f"{req.get('sid')}/{req['rid']}"
        if key in self.cache:
            return {**self.cache[key], "dup": True}
        op = req["op"]
        if op not in ("hello", "ping") and req.get("sid") != self.session:
            return fail(req, "STALE_SESSION", f"expected session {self.session}")
        self.executed.append(op)
        if op == "hello":
            resp = ok(req, {"sessionId": self.session, "scriptVersion": "1.0.0", "host": {"appName": "Cubase"}})
        elif op == "ping":
            resp = ok(req, {"pong": True, "echo": (req.get("p") or {}).get("echo")})
        elif op == "da.param.get":
            resp = ok(req, {"process": self.value})
        elif op == "da.param.set":
            self.value = req["p"]["value"]
            resp = ok(req, {"after": {"process": self.value}}, via="idle")
        elif op == "silent":
            return None
        else:
            resp = fail(req, "UNKNOWN_OP", op)
        self.cache[key] = resp
        return resp


def wait_for(condition: Callable[[], bool], timeout: float = 3.0) -> None:
    """Poll until ``condition`` holds (T-04: no fixed sleeps that a slow CI machine could outrun)."""
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition not met in time"
        time.sleep(0.005)


def make_host(script: FakeScript | None = None, **kw: Any) -> tuple[HostClient, ScriptedTransport, FakeScript]:
    script = script or FakeScript()
    transport = ScriptedTransport(script, **kw)
    client = HostClient(transport, default_timeout=0.5)
    client.open()
    return client, transport, script


class FakeHost:
    session_id: str | None = "s1"

    def __init__(self) -> None:
        self.calls: list[tuple[str, JsonObject | None, float | None]] = []

    def call(
        self, op: str, params: JsonObject | None = None, *, timeout: float | None = None, session: str | None = None
    ) -> Reply:
        self.calls.append((op, params, timeout))
        if op == "da.object" and (params or {}).get("id") == -1:
            raise HostError("object -1 is not valid", code="INVALID_OBJECT")
        if op == "da.param.set" and (params or {}).get("value") == "late":
            raise RequestTimeoutError("da.param.set timed out", outcome_unknown=True, details={"op": op})
        if op == "da.params" and (params or {}).get("stale"):
            raise StaleSessionError("expected session s2")
        return Reply(op=op, rid="1-a", result={"echo": params}, via="sysex", duplicate=False, duration_ms=1.5)

    def stats(self) -> JsonObject:
        return {"session_id": self.session_id}
