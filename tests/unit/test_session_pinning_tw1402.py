"""TW-1402: a write reaches Cubase only with the session its object ids belong to, and only when there is
time left to wait for the answer (quality review I-02, I-03, C-04)."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import pytest

from tests.unit.test_host import make
from trackwright.bridge import Bridge, BridgeClient, validate_request
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import ProtocolError, StaleSessionError, TrackwrightError
from trackwright.fake import FakeCubase
from trackwright.host import MIN_WRITE_BUDGET, Reply

JsonObject = dict[str, Any]


# ---------------------------------------------------------------- IPC request
def test_validate_request_keeps_the_session_only_for_writes() -> None:
    assert validate_request({"op": "da.param.set", "session": "s1"})[3] == "s1"
    assert validate_request({"op": "da.param.get", "session": "s1"})[3] is None
    assert validate_request({"op": "da.param.set"})[3] is None


@pytest.mark.parametrize("session", ["", 7, ["s1"], "x" * 65])
def test_validate_request_rejects_bad_sessions(session: object) -> None:
    with pytest.raises(ProtocolError):
        validate_request({"op": "da.param.set", "session": session})


def test_bridge_forwards_the_session_to_the_host() -> None:
    seen: list[str | None] = []

    class Host:
        session_id = "s2"

        def call(self, op: str, params: JsonObject | None = None, *, timeout: float | None = None,
                 session: str | None = None) -> Reply:  # fmt: skip
            seen.append(session)
            return Reply(op=op, rid="r", result={}, via="idle", duplicate=False, duration_ms=1.0)

        def stats(self) -> JsonObject:
            return {}

    bridge = Bridge(Host())
    assert bridge.handle({"op": "da.param.set", "p": {}, "session": "s1"})["ok"] is True
    assert bridge.handle({"op": "da.param.get", "p": {}, "session": "s1"})["ok"] is True
    assert seen == ["s1", None]


def test_client_sends_the_session_in_the_request_line() -> None:
    lines: list[JsonObject] = []

    class Sock:
        def __enter__(self) -> Sock:
            return self

        def __exit__(self, *_: object) -> None: ...

        def settimeout(self, _t: float) -> None: ...

        def connect(self, _p: str) -> None: ...

        def sendall(self, data: bytes) -> None:
            lines.append(json.loads(data))

        def recv(self, _n: int) -> bytes:
            return b'{"ok": true, "result": {}}\n'

    client = BridgeClient(__import__("pathlib").Path("/x"), connect=Sock)  # type: ignore[arg-type]
    client.request("da.param.set", {}, session="s1")
    client.request("da.param.get", {})
    assert lines[0]["session"] == "s1"
    assert "session" not in lines[1]


# ---------------------------------------------------------------- host client
def test_a_pinned_write_is_sent_with_its_session_and_without_hello() -> None:
    client, transport, script = make()
    client.session_id = "s2"  # the bridge renegotiated after the script reloaded
    script.session = "s2"
    with pytest.raises(StaleSessionError):
        client.call("da.param.set", {"value": 0.9}, session="s1")
    assert [(r["op"], r["sid"]) for r in transport.requests] == [("da.param.set", "s1")]
    assert script.value == 0.5  # refused by the script: nothing was written


def test_a_pinned_write_on_the_current_session_runs() -> None:
    client, transport, script = make()
    client.call("da.param.set", {"value": 0.9}, session="s1")
    assert [r["op"] for r in transport.requests] == ["da.param.set"]
    assert script.value == 0.9


def test_a_write_is_not_sent_without_time_to_wait_for_the_answer() -> None:
    client, transport, _ = make()
    client.session_id = "s1"
    with pytest.raises(TrackwrightError) as exc:
        client.request("da.param.set", {"value": 0.9}, timeout=MIN_WRITE_BUDGET / 2)
    assert exc.value.code == "BUSY"
    assert exc.value.details["outcome"] == "not_executed"
    assert transport.requests == []


def test_a_write_that_gets_the_lock_too_late_is_not_sent() -> None:
    client, transport, _ = make()
    client.session_id = "s1"
    client._write_lock.acquire()
    releaser = threading.Timer(0.35, client._write_lock.release)
    releaser.start()
    started = time.monotonic()
    with pytest.raises(TrackwrightError) as exc:
        client.request("da.param.set", {"value": 0.9}, timeout=0.5)
    releaser.join()
    assert exc.value.code == "BUSY"
    assert transport.requests == []
    assert time.monotonic() - started < 0.5


# ---------------------------------------------------------------- service
class LaggingHost:
    """A host that has not noticed a script reload yet (another client renegotiated with the bridge)."""

    simulated = True

    def __init__(self, fake: FakeCubase) -> None:
        self.fake = fake
        self.session_id = fake.session
        self.sessions: list[tuple[str, str | None]] = []

    def call(self, op: str, params: JsonObject | None = None, *, session: str | None = None) -> JsonObject:
        self.sessions.append((op, session))
        return self.fake.call(op, params, session=session)


def test_service_writes_carry_the_pinned_session(fake: FakeCubase) -> None:
    host = LaggingHost(fake)
    service = CubaseService(host, WritePolicy(enabled=True), sleep=lambda _s: None, settle_timeout=0.0)  # type: ignore[arg-type]
    service.set_track_mix("POC-TEST", mute=True, dry_run=False)
    writes = [s for op, s in host.sessions if op == "da.param.set"]
    assert writes == [fake.session]


def test_service_write_after_a_silent_reload_is_refused(fake: FakeCubase) -> None:
    host = LaggingHost(fake)
    service = CubaseService(host, WritePolicy(enabled=True), sleep=lambda _s: None, settle_timeout=0.0)  # type: ignore[arg-type]
    original = fake.call

    def reload_before_writing(op: str, params: JsonObject | None = None, *, session: str | None = None) -> JsonObject:
        if op == "da.param.set" and session == host.session_id and fake.session == host.session_id:
            fake.reload_script()  # ids gathered so far now belong to an old session
        return original(op, params, session=session)

    fake.call = reload_before_writing  # type: ignore[method-assign]
    with pytest.raises(StaleSessionError):
        service.set_track_mix("POC-TEST", mute=True, dry_run=False)
    assert fake.channel_by_title("POC-TEST").params[1027].value == 0
