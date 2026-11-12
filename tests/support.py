"""Test doubles shared by the unit tests."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from trackwright import protocol
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
