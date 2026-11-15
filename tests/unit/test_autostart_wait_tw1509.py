"""TW-1509: after autostarting the bridge, wait for Cubase (``hello``) before sending the request once."""

from __future__ import annotations

from typing import Any

import pytest

from trackwright.errors import BridgeUnavailableError, RequestTimeoutError
from trackwright.hostport import BridgeHost

JsonObject = dict[str, Any]
TIMEOUT = {"ok": False, "error": {"code": "TIMEOUT", "message": "hello timed out", "details": {"outcome": "lost"}}}


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class Bridge:
    """A BridgeClient double: no socket at first, then Cubase answers ``hello`` after ``silent`` attempts."""

    def __init__(self, clock: Clock, silent: int, hello_cost: float = 3.0) -> None:
        self.clock = clock
        self.silent = silent
        self.hello_cost = hello_cost
        self.started = False
        self.requests: list[tuple[str, float, str | None]] = []

    def ensure(self) -> bool:
        self.started = True
        return True

    def request(
        self, op: str, params: JsonObject | None = None, *, timeout: float = 3.0, session: str | None = None
    ) -> JsonObject:
        self.requests.append((op, timeout, session))
        if not self.started:
            raise BridgeUnavailableError("no socket", details={"sent": False})
        if op == "hello" and self.silent > 0:
            self.silent -= 1
            self.clock.now += min(timeout, self.hello_cost)  # the bridge waits for its own timeout
            return TIMEOUT
        return {"ok": True, "result": {"op": op}, "meta": {"session_id": "s1"}}


def host(bridge: Bridge, clock: Clock, wait: float = 10.0) -> BridgeHost:
    return BridgeHost(
        bridge,  # type: ignore[arg-type]
        read_timeout=3.0,
        write_timeout=5.0,
        ensure_bridge=bridge.ensure,
        script_wait=wait,
        sleep=clock.sleep,
        clock=clock,
    )


def test_waits_for_cubase_then_sends_once() -> None:
    clock = Clock()
    bridge = Bridge(clock, silent=2)
    assert host(bridge, clock).call("status") == {"op": "status"}
    assert [op for op, _, _ in bridge.requests] == ["status", "hello", "hello", "hello", "status"]


def test_a_write_is_sent_exactly_once_with_its_session() -> None:
    clock = Clock()
    bridge = Bridge(clock, silent=1)
    host(bridge, clock).call("da.param.set", {"v": 1}, session="s1")
    writes = [r for r in bridge.requests if r[0] == "da.param.set"]
    assert writes == [("da.param.set", 5.0, "s1")] * 2  # the refused attempt (no bridge) and the real one
    assert bridge.requests[0] == ("da.param.set", 5.0, "s1")  # the first never reached a bridge


def test_cubase_never_answers_and_nothing_is_sent() -> None:
    clock = Clock()
    bridge = Bridge(clock, silent=100)
    with pytest.raises(RequestTimeoutError) as exc:
        host(bridge, clock, wait=10.0).call("da.param.set", {"v": 1}, session="s1")
    assert exc.value.outcome_unknown is False
    assert exc.value.details == {"op": "da.param.set", "outcome": "not_executed"}
    assert "MIDI Remote" in exc.value.message
    assert "da.param.set was not sent" in exc.value.message
    assert [op for op, _, _ in bridge.requests].count("da.param.set") == 1  # only the refused first attempt
    assert 10.0 <= clock.now < 14.0  # gave up at the deadline, not much later


def test_the_last_hello_only_uses_the_time_left() -> None:
    clock = Clock()
    bridge = Bridge(clock, silent=100)
    with pytest.raises(RequestTimeoutError):
        host(bridge, clock, wait=4.0).call("status")
    hello_timeouts = [t for op, t, _ in bridge.requests if op == "hello"]
    assert hello_timeouts[0] == 3.0
    assert hello_timeouts[1] == pytest.approx(0.5)  # 4 s - 3 s spent - 0.5 s pause


def test_other_errors_are_not_retried() -> None:
    clock = Clock()
    bridge = Bridge(clock, silent=0)

    def broken(op: str, params: JsonObject | None = None, **_: Any) -> JsonObject:
        bridge.requests.append((op, 0.0, None))
        if not bridge.started:
            raise BridgeUnavailableError("no socket", details={"sent": False})
        raise BridgeUnavailableError("reset", details={"sent": "unknown"})

    bridge.request = broken  # type: ignore[method-assign]
    with pytest.raises(BridgeUnavailableError):
        host(bridge, clock).call("status")
    assert [op for op, _, _ in bridge.requests] == ["status", "hello"]
