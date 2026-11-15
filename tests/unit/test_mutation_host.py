"""TW-1410: tests that kill the mutants which survived in ``host.py`` and ``hostport.py``.

The most important ones guard the "never retry a write whose outcome is unknown" rule and the session that
writes carry; the rest pin down the diagnostics (history bounds, counters, error texts the client reads).
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from tests.support import FakeScript, ScriptedTransport, fail, make_host, ok
from trackwright import protocol
from trackwright.errors import BridgeUnavailableError, RequestTimeoutError, StaleSessionError, TrackwrightError
from trackwright.host import _HISTORY, HostClient
from trackwright.hostport import BridgeHost

JsonObject = dict[str, Any]


# ---------------------------------------------------------------- BridgeHost (hostport.py)
class Client:
    """A BridgeClient double: records each request and fails the first ones on demand."""

    def __init__(self, failures: list[Exception] | None = None) -> None:
        self.failures = list(failures or [])
        self.requests: list[tuple[str, JsonObject | None, float, str | None]] = []

    def request(
        self, op: str, params: JsonObject | None = None, *, timeout: float = 3.0, session: str | None = None
    ) -> JsonObject:
        self.requests.append((op, params, timeout, session))
        if self.failures:
            raise self.failures.pop(0)
        return {"ok": True, "result": {"done": op}, "meta": {"session_id": "s1"}}


def bridge_host(client: Client, ensured: list[bool] | None = None) -> BridgeHost:
    def ensure() -> bool:
        assert ensured is not None
        ensured.append(True)
        return True

    return BridgeHost(
        client,  # type: ignore[arg-type]
        read_timeout=1.5,
        write_timeout=4.5,
        ensure_bridge=ensure if ensured is not None else None,
    )


def test_writes_carry_the_session_and_reads_do_not() -> None:
    client = Client()
    host = bridge_host(client)
    assert host.call("da.param.set", {"v": 1}, session="s1") == {"done": "da.param.set"}
    host.call("da.param.get", {"v": 2}, session="s1")
    assert client.requests == [("da.param.set", {"v": 1}, 4.5, "s1"), ("da.param.get", {"v": 2}, 1.5, None)]
    assert host.session_id == "s1"


def test_retry_only_when_nothing_was_sent() -> None:
    client = Client([BridgeUnavailableError("no socket", details={"sent": False})])
    ensured: list[bool] = []
    host = bridge_host(client, ensured)
    host.call("da.param.set", {"v": 1}, session="s1")
    assert ensured == [True]
    write = ("da.param.set", {"v": 1}, 4.5, "s1")
    assert client.requests == [write, ("hello", None, 1.5, None), write]  # TW-1509: Cubase first, then once more


@pytest.mark.parametrize("sent", ["unknown", True, None])
def test_no_retry_when_the_request_may_have_been_sent(sent: object) -> None:
    client = Client([BridgeUnavailableError("reset", details={"sent": sent})])
    ensured: list[bool] = []
    with pytest.raises(BridgeUnavailableError):
        bridge_host(client, ensured).call("da.param.set", {"v": 1}, session="s1")
    assert ensured == []
    assert len(client.requests) == 1


def test_no_retry_without_autostart() -> None:
    client = Client([BridgeUnavailableError("no socket", details={"sent": False})])
    with pytest.raises(BridgeUnavailableError):
        bridge_host(client).call("ping")
    assert len(client.requests) == 1


# ---------------------------------------------------------------- HostClient.call (host.py)
def test_a_call_with_no_time_left_sends_nothing() -> None:
    client, transport, _ = make_host()
    with pytest.raises(RequestTimeoutError) as exc:
        client.call("ping", timeout=0.0)
    assert exc.value.outcome_unknown is False
    assert exc.value.details == {"op": "ping", "outcome": "not_executed"}
    assert transport.requests == []


def test_the_callers_timeout_wins_over_the_default() -> None:
    script = FakeScript()
    transport = ScriptedTransport(script)
    client = HostClient(transport, default_timeout=5.0)
    client.open()
    client.hello()
    started = time.monotonic()
    with pytest.raises(RequestTimeoutError):
        client.call("silent", timeout=0.3)
    assert time.monotonic() - started < 1.0


def test_a_write_without_a_pinned_session_negotiates_first() -> None:
    client, transport, _ = make_host()
    client.call("da.param.set", {"value": 0.9})
    assert [r["op"] for r in transport.requests] == ["hello", "da.param.set"]


def test_a_stale_read_is_retried_with_its_parameters() -> None:
    client, transport, script = make_host()
    client.hello()
    script.session = "s2"  # the script reloaded
    assert client.call("da.param.get", {"id": 7}).result == {"process": 0.5}
    assert [(r["op"], r.get("p")) for r in transport.requests[-3:]] == [
        ("da.param.get", {"id": 7}),
        ("hello", None),
        ("da.param.get", {"id": 7}),
    ]


def test_a_stale_write_is_not_retried() -> None:
    client, transport, script = make_host()
    client.hello()
    script.session = "s2"
    with pytest.raises(StaleSessionError):
        client.call("da.param.set", {"value": 0.9})
    assert [r["op"] for r in transport.requests] == ["hello", "da.param.set"]


def test_hello_ignores_values_of_the_wrong_type() -> None:
    client = HostClient(ScriptedTransport(lambda req: ok(req, {"sessionId": 7, "host": [], "scriptVersion": 1})))
    client.open()
    client.hello()
    assert (client.session_id, client.host_info, client.script_version) == (None, None, None)


# ---------------------------------------------------------------- errors and replies
def test_timeout_texts_tell_whether_to_retry() -> None:
    client, _, _ = make_host(delay=0.6)
    client.session_id = "s1"
    with pytest.raises(RequestTimeoutError, match="do not retry"):
        client.request("da.param.set", {"value": 0.9}, timeout=0.3)
    with pytest.raises(RequestTimeoutError, match="no response"):
        client.request("ping", timeout=0.1)


def test_host_errors_keep_code_and_message() -> None:
    client = HostClient(ScriptedTransport(lambda req: fail(req, "PRECONDITION_FAILED", "title differs")))
    client.open()
    with pytest.raises(TrackwrightError) as exc:
        client.request("ping")
    assert (exc.value.code, exc.value.message) == ("PRECONDITION_FAILED", "title differs")
    bare = HostClient(ScriptedTransport(lambda req: {"v": 1, "rid": req["rid"], "ok": False, "err": {}}))
    bare.open()
    with pytest.raises(TrackwrightError) as unknown:
        bare.request("ping")
    assert (unknown.value.code, unknown.value.message) == ("HOST_ERROR", "")


def test_reply_fields() -> None:
    client, _, _ = make_host()
    reply = client.request("hello", rid="r-7")
    assert (reply.op, reply.rid, reply.via) == ("hello", "r-7", None)
    assert 0 <= reply.duration_ms < 1000


# ---------------------------------------------------------------- diagnostics
def test_unsolicited_and_late_messages_are_kept_and_bounded() -> None:
    client, transport, _ = make_host()
    for i in range(_HISTORY + 5):
        transport.push({"v": 1, "rid": f"gone-{i}", "ok": True})
    transport.push({"v": 1, "ok": True, "note": "no rid"})
    assert len(client.late_responses) == _HISTORY
    assert client.late_responses[-1]["message"]["rid"] == f"gone-{_HISTORY + 4}"
    assert client.unsolicited[-1]["message"]["note"] == "no rid"
    stats = client.stats()
    assert [e["message"]["rid"] for e in stats["late_responses"]] == [
        f"gone-{i}" for i in range(_HISTORY - 5, _HISTORY + 5)
    ]


def test_protocol_errors_are_recorded_with_their_text() -> None:
    client, transport, _ = make_host()
    for _ in range(12):
        transport.push_raw(protocol.build_frames(b"[1]", 2)[0])
    assert "not a JSON object" in client.protocol_errors[-1]
    assert len(client.stats()["protocol_errors"]) == 10


def test_non_string_rids_do_not_break_the_receiver() -> None:
    client, transport, _ = make_host()
    transport.push({"v": 1, "rid": ["x"], "ok": True})
    assert client.late_responses[-1]["message"]["rid"] == ["x"]


def test_duplicate_answers_are_counted_one_by_one() -> None:
    script = FakeScript()

    def twice(req: JsonObject) -> list[JsonObject] | JsonObject | None:
        answer = script(req)
        return [answer, answer] if isinstance(answer, dict) else answer

    client = HostClient(ScriptedTransport(twice), default_timeout=0.5)
    client.open()
    client.hello()
    client.request("ping")
    assert client.duplicate_responses == 2
    assert client.stats()["duplicate_responses"] == 2


def test_session_changes_are_recorded() -> None:
    client, _, script = make_host()
    client.hello()
    script.session = "s2"
    client.hello()
    assert [(c["old"], c["new"]) for c in client.stats()["session_changes"]] == [("s1", "s2")]


# ---------------------------------------------------------------- the caller's deadline reaches every step
def slow_client(delay: float = 2.0) -> tuple[HostClient, ScriptedTransport]:
    transport = ScriptedTransport(FakeScript(), delay=delay)
    client = HostClient(transport, default_timeout=5.0)
    client.open()
    return client, transport


@pytest.mark.parametrize(
    ("op", "kwargs"),
    [
        ("hello", {}),
        ("da.param.get", {}),
        ("da.param.set", {"session": "s1"}),
    ],
)
def test_every_path_uses_the_remaining_time(op: str, kwargs: dict[str, Any]) -> None:
    client, _ = slow_client()
    client.session_id = "s1"
    started = time.monotonic()
    with pytest.raises(RequestTimeoutError):
        client.call(op, {"value": 0.1} if op == "da.param.set" else None, timeout=0.4, **kwargs)
    assert time.monotonic() - started < 1.5  # not the 5 s default


def test_negotiation_uses_the_remaining_time() -> None:
    client, _ = slow_client()
    started = time.monotonic()
    with pytest.raises(RequestTimeoutError):
        client.call("ping", timeout=0.4)  # no session yet: hello first
    assert time.monotonic() - started < 1.5


def test_hello_honours_its_timeout() -> None:
    client, _ = slow_client()
    started = time.monotonic()
    with pytest.raises(RequestTimeoutError):
        client.hello(timeout=0.3)
    assert time.monotonic() - started < 1.5


def test_a_busy_write_gives_up_before_its_deadline() -> None:
    """The lock wait leaves MIN_WRITE_BUDGET for the answer: it never waits the whole timeout or more."""
    client, transport, _ = make_host()
    client.session_id = "s1"
    client._write_lock.acquire()
    try:
        started = time.monotonic()
        with pytest.raises(TrackwrightError) as exc:
            client.request("da.param.set", {"value": 0.9}, timeout=0.6)
        assert time.monotonic() - started < 0.5
        assert exc.value.details == {"op": "da.param.set", "outcome": "not_executed"}
        assert "da.param.set was not sent" in exc.value.message
    finally:
        client._write_lock.release()
    assert transport.requests == []


def test_reply_reports_how_it_was_answered() -> None:
    client, _, _ = make_host(delay=0.2)
    client.hello()
    reply = client.request("da.param.set", {"value": 0.3})
    assert reply.via == "idle"
    assert 150 <= reply.duration_ms < 1500


def test_unsolicited_and_protocol_error_histories_are_bounded() -> None:
    client, transport, _ = make_host()
    for _ in range(_HISTORY + 5):
        transport.push({"v": 1, "ok": True})
        transport.push_raw(protocol.build_frames(b"[1]", 2)[0])
    assert len(client.unsolicited) == _HISTORY
    assert len(client.protocol_errors) == _HISTORY
