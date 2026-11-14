from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from tests.support import ScriptedTransport, fail, ok
from trackwright import protocol
from trackwright.errors import HostError, ProtocolError, RequestTimeoutError, StaleSessionError, TrackwrightError
from trackwright.host import HostClient

JsonObject = dict[str, Any]


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


def make(script: FakeScript | None = None, **kw: Any) -> tuple[HostClient, ScriptedTransport, FakeScript]:
    script = script or FakeScript()
    transport = ScriptedTransport(script, **kw)
    client = HostClient(transport, default_timeout=0.5)
    client.open()
    return client, transport, script


def test_hello_negotiates_session() -> None:
    client, _, _ = make()
    reply = client.hello()
    assert client.session_id == "s1"
    assert client.script_version == "1.0.0"
    assert client.host_info == {"appName": "Cubase"}
    assert reply.result["sessionId"] == "s1"


def test_call_negotiates_lazily_and_echoes_unicode() -> None:
    client, transport, _ = make()
    reply = client.call("ping", {"echo": "hola-ñ-✓"})
    assert reply.result["echo"] == "hola-ñ-✓"
    assert [r["op"] for r in transport.requests] == ["hello", "ping"]


def test_call_hello_directly() -> None:
    client, _, _ = make()
    assert client.call("hello").result["sessionId"] == "s1"


def test_large_fragmented_response_is_reassembled() -> None:
    def handler(req: JsonObject) -> JsonObject:
        return ok(req, {"blob": "z" * 3000, "sessionId": "s1"})

    client = HostClient(ScriptedTransport(handler), default_timeout=0.5)
    client.open()
    assert len(client.request("hello").result["blob"]) == 3000


def test_concurrent_requests_are_correlated() -> None:
    client, _, _ = make(delay=0.05)
    client.hello()
    results: dict[int, str] = {}

    def worker(i: int) -> None:
        results[i] = client.call("ping", {"echo": f"n{i}"}).result["echo"]

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == {i: f"n{i}" for i in range(8)}


def test_read_timeout() -> None:
    client, _, _ = make()
    client.hello()
    with pytest.raises(RequestTimeoutError) as exc:
        client.request("silent", timeout=0.05)
    assert exc.value.outcome_unknown is False
    assert exc.value.details["outcome"] == "not_executed_or_lost"


def test_write_timeout_reports_unknown_outcome_and_is_not_retried() -> None:
    script = FakeScript()
    client, transport, _ = make(script, delay=0.6)
    client.session_id = "s1"
    with pytest.raises(RequestTimeoutError) as exc:
        client.call("da.param.set", {"value": 0.9}, timeout=0.3)
    assert exc.value.outcome_unknown is True
    assert [r["op"] for r in transport.requests] == ["da.param.set"]
    time.sleep(0.5)
    assert script.value == 0.9  # it did run: the outcome really was unknown
    assert len(client.late_responses) == 1


def test_late_response_is_not_misattributed() -> None:
    client, transport, _ = make()
    client.hello()
    transport.push(ok({"rid": "old-1", "op": "ping"}, {"echo": "stale"}))
    reply = client.call("ping", {"echo": "fresh"})
    assert reply.result["echo"] == "fresh"
    assert client.late_responses[0]["message"]["rid"] == "old-1"


def test_unsolicited_message_without_rid() -> None:
    client, transport, _ = make()
    transport.push({"v": 1, "rid": "", "ok": True})
    assert len(client.unsolicited) == 1


def test_stale_session_renegotiates_reads_once() -> None:
    client, transport, script = make()
    client.hello()
    script.session = "s2"  # script reloaded
    assert client.call("da.param.get", {"id": 1}).result["process"] == 0.5
    assert client.session_id == "s2"
    assert client.session_changes[0]["old"] == "s1"
    assert [r["op"] for r in transport.requests] == ["hello", "da.param.get", "hello", "da.param.get"]


def test_stale_session_is_not_retried_for_writes() -> None:
    client, transport, script = make()
    client.hello()
    script.session = "s2"
    with pytest.raises(StaleSessionError):
        client.call("da.param.set", {"value": 0.1})
    assert script.value == 0.5
    assert [r["op"] for r in transport.requests] == ["hello", "da.param.set"]


def test_duplicate_rid_returns_cached_response_without_reexecution() -> None:
    client, _, script = make()
    client.hello()
    first = client.request("da.param.set", {"value": 0.3}, rid="fixed")
    second = client.request("da.param.set", {"value": 0.9}, rid="fixed")
    assert second.duplicate is True
    assert second.result == first.result
    assert script.value == 0.3
    assert script.executed.count("da.param.set") == 1


def test_host_error_carries_script_code() -> None:
    client, _, _ = make()
    client.hello()
    with pytest.raises(HostError) as exc:
        client.call("da.unknown")
    assert exc.value.code == "UNKNOWN_OP"
    assert exc.value.details["op"] == "da.unknown"


def test_pending_rid_collision() -> None:
    client, _, _ = make(delay=0.2)
    client.session_id = "s1"
    thread = threading.Thread(target=lambda: client.request("ping", rid="same", timeout=0.4))
    thread.start()
    time.sleep(0.05)
    with pytest.raises(ProtocolError, match="already pending"):
        client.request("ping", rid="same")
    thread.join()


def test_protocol_errors_are_recorded_not_raised() -> None:
    client, transport, _ = make()
    transport.push_raw([0x7D, 0x54, 0x57, 9, 0, 1, 0, 1])  # bad version
    transport.push_raw([0x7E, 0x7F, 0x06, 0x01])  # foreign: ignored silently
    transport.push_raw(protocol.build_frames(b"[1]", 2)[0])  # not an object
    assert len(client.protocol_errors) == 2


def test_stats_and_close() -> None:
    client, transport, _ = make()
    client.hello()
    stats = client.stats()
    assert stats["session_id"] == "s1"
    assert stats["transport"] == {"sent_frames": 1}
    client.close()
    assert transport.closed


def test_non_dict_result_becomes_empty() -> None:
    client = HostClient(ScriptedTransport(lambda req: {**ok(req), "r": [1, 2]}), default_timeout=0.5)
    client.open()
    assert client.request("ping").result == {}


def test_write_lock_busy_is_not_sent() -> None:
    client, transport, _ = make(delay=0.3)
    client.session_id = "s1"
    thread = threading.Thread(target=lambda: client.request("da.param.set", {"value": 0.2}, timeout=1.0))
    thread.start()
    time.sleep(0.05)
    with pytest.raises(TrackwrightError) as exc:
        client.request("da.param.set", {"value": 0.7}, timeout=0.05)
    assert exc.value.code == "BUSY"
    assert exc.value.details["outcome"] == "not_executed"
    thread.join()
    assert [r["p"]["value"] for r in transport.requests] == [0.2]


def test_call_shares_one_deadline() -> None:
    client, _, script = make(delay=0.2)
    script.session = "s1"
    with pytest.raises(RequestTimeoutError) as exc:
        client.call("silent", timeout=0.25)  # hello uses most of the budget, nothing is left for the request
    assert exc.value.details["op"] in ("silent", "hello")


def test_response_arriving_at_the_deadline_is_used() -> None:
    client, _, _ = make()
    client.hello()
    original = client._arrived

    def arrived_late(pending: Any) -> bool:
        pending.response = ok({"rid": "x", "op": "ping"}, {"echo": "just in time"})
        return original(pending)

    client._arrived = arrived_late  # type: ignore[method-assign]
    assert client.request("silent", timeout=0.01).result["echo"] == "just in time"
