from __future__ import annotations

import json
import os
import socket
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from trackwright.bridge import (
    MAX_LINE,
    Bridge,
    BridgeClient,
    BridgeServer,
    prepare_socket_dir,
    validate_request,
)
from trackwright.errors import (
    BridgeUnavailableError,
    HostError,
    ProtocolError,
    RequestTimeoutError,
    StaleSessionError,
    TrackwrightError,
)
from trackwright.host import Reply

JsonObject = dict[str, Any]


class FakeHost:
    session_id: str | None = "s1"

    def __init__(self) -> None:
        self.calls: list[tuple[str, JsonObject | None, float | None]] = []

    def call(self, op: str, params: JsonObject | None = None, *, timeout: float | None = None) -> Reply:
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


@pytest.fixture
def short_tmp() -> Iterator[Path]:
    """Unix socket paths are limited to ~104 bytes: use a short directory."""
    import tempfile

    with tempfile.TemporaryDirectory(dir="/tmp", prefix="tw-") as d:
        yield Path(d)


@pytest.fixture
def running(short_tmp: Path) -> Iterator[tuple[BridgeClient, FakeHost, BridgeServer]]:
    host = FakeHost()
    server = BridgeServer(Bridge(host), short_tmp / "sock" / "bridge.sock")
    server.serve_in_thread()
    yield BridgeClient(server.socket_path), host, server
    server.stop()


# ---------------------------------------------------------------- validation
@pytest.mark.parametrize(
    "request_obj",
    [
        [],
        {"op": "rm -rf"},
        {"op": 3},
        {"op": "ping", "p": [1]},
        {"op": "ping", "timeout": 0.01},
        {"op": "ping", "timeout": 31},
        {"op": "ping", "timeout": True},
        {"op": "ping", "timeout": "1"},
    ],
)
def test_validate_rejects(request_obj: object) -> None:
    with pytest.raises(ProtocolError):
        validate_request(request_obj)


def test_validate_accepts_defaults() -> None:
    assert validate_request({"op": "ping"}) == ("ping", {}, 3.0)
    assert validate_request({"op": "bridge.status", "timeout": 1}) == ("bridge.status", {}, 1.0)


# ---------------------------------------------------------------- dispatcher
def test_handle_success_and_meta() -> None:
    host = FakeHost()
    out = Bridge(host).handle({"op": "ping", "p": {"echo": "x"}, "timeout": 2})
    assert out["ok"] is True
    assert out["result"] == {"echo": {"echo": "x"}}
    assert out["meta"]["rid"] == "1-a"
    assert out["meta"]["session_id"] == "s1"
    assert host.calls == [("ping", {"echo": "x"}, 2.0)]


def test_handle_errors_are_reported() -> None:
    bridge = Bridge(FakeHost())
    out = bridge.handle({"op": "da.object", "p": {"id": -1}})
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_OBJECT"
    assert bridge.handle({"op": "nope"})["error"]["code"] == "PROTOCOL_ERROR"
    assert bridge.errors == 2


def test_status() -> None:
    out = Bridge(FakeHost()).handle({"op": "bridge.status"})
    assert out["ok"] is True
    assert out["result"]["pid"] == os.getpid()
    assert out["result"]["host"] == {"session_id": "s1"}


# ---------------------------------------------------------------- socket
def test_socket_permissions(running: tuple[BridgeClient, FakeHost, BridgeServer]) -> None:
    _, _, server = running
    assert stat.S_IMODE(server.socket_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(server.socket_path.parent.stat().st_mode) == 0o700


def test_client_roundtrip(running: tuple[BridgeClient, FakeHost, BridgeServer]) -> None:
    client, host, _ = running
    assert client.call("ping", {"echo": "ñ"}) == {"echo": {"echo": "ñ"}}
    assert host.calls[0][0] == "ping"
    full = client.request("bridge.status")
    assert full["ok"] is True


def test_client_maps_errors(running: tuple[BridgeClient, FakeHost, BridgeServer]) -> None:
    client, _, _ = running
    with pytest.raises(TrackwrightError) as exc:
        client.call("da.object", {"id": -1})
    assert exc.value.code == "INVALID_OBJECT"
    with pytest.raises(RequestTimeoutError) as timeout:
        client.call("da.param.set", {"value": "late"})
    assert timeout.value.outcome_unknown is True
    with pytest.raises(StaleSessionError):
        client.call("da.params", {"stale": True})


def test_line_too_long_and_invalid_json(running: tuple[BridgeClient, FakeHost, BridgeServer]) -> None:
    _, _, server = running

    def raw(payload: bytes) -> JsonObject:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(str(server.socket_path))
            s.sendall(payload)
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
        result: JsonObject = json.loads(data)
        return result

    assert "too long" in raw(b"x" * (MAX_LINE + 10) + b"\n")["error"]["message"]
    assert "invalid JSON" in raw(b"{nope\n")["error"]["message"]


def test_second_bridge_on_same_socket_is_refused(running: tuple[BridgeClient, FakeHost, BridgeServer]) -> None:
    _, _, server = running
    with pytest.raises(BridgeUnavailableError, match="already listening"):
        BridgeServer(Bridge(FakeHost()), server.socket_path).start()


def test_stale_socket_file_is_replaced(short_tmp: Path) -> None:
    path = short_tmp / "bridge.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.bind(str(path))  # bound but never listening: a leftover from a crashed bridge
    server = BridgeServer(Bridge(FakeHost()), path)
    server.serve_in_thread()
    try:
        assert BridgeClient(path).call("ping") == {"echo": {}}
    finally:
        server.stop()


def test_client_when_bridge_is_down(short_tmp: Path) -> None:
    with pytest.raises(BridgeUnavailableError, match="trackwright bridge"):
        BridgeClient(short_tmp / "missing.sock").call("ping")


def test_client_connection_refused(short_tmp: Path) -> None:
    path = short_tmp / "dead.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.bind(str(path))
    with pytest.raises(BridgeUnavailableError, match="not accepting"):
        BridgeClient(path).call("ping")


class _FakeSocket:
    def __init__(self, chunks: list[bytes] | None = None, exc: Exception | None = None) -> None:
        self.chunks = list(chunks or [])
        self.exc = exc

    def __enter__(self) -> _FakeSocket:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def settimeout(self, _t: float) -> None:
        return None

    def connect(self, _path: str) -> None:
        if self.exc:
            raise self.exc

    def sendall(self, _data: bytes) -> None:
        return None

    def recv(self, _n: int) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""


@pytest.mark.parametrize(
    ("fake", "error", "match"),
    [
        (_FakeSocket(exc=TimeoutError()), RequestTimeoutError, "no answer"),
        (_FakeSocket(chunks=[]), BridgeUnavailableError, "without answering"),
        (_FakeSocket(chunks=[b"{bad\n"]), ProtocolError, "invalid response"),
        (_FakeSocket(chunks=[b"[1]\n"]), ProtocolError, "not a JSON object"),
    ],
)
def test_client_failure_modes(fake: _FakeSocket, error: type[Exception], match: str) -> None:
    client = BridgeClient(Path("/nowhere"), connect=lambda: fake)  # type: ignore[arg-type,return-value]
    with pytest.raises(error, match=match):
        client.call("ping")


def test_client_error_without_payload() -> None:
    fake = _FakeSocket(chunks=[b'{"ok": false, "error": "weird"}\n'])
    client = BridgeClient(Path("/nowhere"), connect=lambda: fake)  # type: ignore[arg-type,return-value]
    with pytest.raises(TrackwrightError) as exc:
        client.call("ping")
    assert exc.value.code == "BRIDGE_ERROR"


def test_client_non_dict_result() -> None:
    fake = _FakeSocket(chunks=[b'{"ok": true, "result": [1]}\n'])
    client = BridgeClient(Path("/nowhere"), connect=lambda: fake)  # type: ignore[arg-type,return-value]
    assert client.call("ping") == {}


def test_prepare_socket_dir_fixes_permissions(short_tmp: Path) -> None:
    directory = short_tmp / "open"
    directory.mkdir(mode=0o755)
    directory.chmod(0o755)
    prepare_socket_dir(directory)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700


def test_prepare_socket_dir_refuses_foreign_owner(short_tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "getuid", lambda: 12345)
    with pytest.raises(BridgeUnavailableError, match="another user"):
        prepare_socket_dir(short_tmp)


def test_prepare_socket_dir_cannot_fix(short_tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = short_tmp / "stuck"
    directory.mkdir()
    directory.chmod(0o755)
    monkeypatch.setattr(Path, "chmod", lambda self, mode: None)
    with pytest.raises(BridgeUnavailableError, match="private"):
        prepare_socket_dir(directory)


def test_unexpected_exception_is_reported_with_unknown_outcome() -> None:
    class Exploding(FakeHost):
        def call(self, op: str, params: JsonObject | None = None, *, timeout: float | None = None) -> Reply:
            raise OSError("rtmidi send failed")

    bridge = Bridge(Exploding())
    out = bridge.handle({"op": "da.param.set", "p": {}})
    assert out["error"]["code"] == "INTERNAL_ERROR"
    assert out["error"]["details"]["outcome"] == "unknown"
    read = bridge.handle({"op": "da.object", "p": {}})
    assert read["error"]["details"]["outcome"] == "not_executed_or_lost"
