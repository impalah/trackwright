from __future__ import annotations

import json
import tempfile
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.support import ScriptedTransport, ok
from trackwright.bridge import BridgeClient, run_bridge
from trackwright.cli import main
from trackwright.config import BridgeConfig

JsonObject = dict[str, Any]


def script(req: JsonObject) -> JsonObject:
    if req["op"] == "hello":
        return ok(req, {"sessionId": "s1", "scriptVersion": "1.0.0"})
    return ok(req, {"pong": True, "echo": (req.get("p") or {}).get("echo")})


@pytest.fixture
def socket_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="tw-") as d:
        yield Path(d) / "s"


@pytest.fixture
def bridge(socket_dir: Path) -> Iterator[tuple[BridgeConfig, ScriptedTransport]]:
    config = BridgeConfig(socket_dir=socket_dir, request_timeout=1.0)
    transport = ScriptedTransport(script)
    stop = threading.Event()
    thread = threading.Thread(target=run_bridge, args=(config,), kwargs={"transport": transport, "stop": stop})
    thread.start()
    deadline = time.monotonic() + 3
    while not config.socket_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    yield config, transport
    stop.set()
    thread.join(timeout=3)
    assert transport.closed
    assert not config.socket_path.exists()


def write_config(tmp_path: Path, socket_dir: Path) -> Path:
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'[bridge]\nsocket_dir = "{socket_dir}"\nrequest_timeout = 1.0\n', encoding="utf-8")
    return cfg


def test_run_bridge_serves_requests(bridge: tuple[BridgeConfig, ScriptedTransport]) -> None:
    config, transport = bridge
    client = BridgeClient(config.socket_path)
    assert client.call("ping", {"echo": "x"})["echo"] == "x"
    assert [r["op"] for r in transport.requests] == ["hello", "ping"]


def test_cli_ping_and_status(
    bridge: tuple[BridgeConfig, ScriptedTransport], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config, _ = bridge
    cfg = write_config(tmp_path, config.socket_dir)
    assert main(["--config", str(cfg), "ping", "--echo", "ñ"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["ping"]["result"]["echo"] == "ñ"
    assert out["hello"]["sessionId"] == "s1"

    assert main(["--config", str(cfg), "bridge-status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["host"]["session_id"] == "s1"


def test_cli_reports_bridge_down(tmp_path: Path, socket_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = write_config(tmp_path, socket_dir)
    assert main(["--config", str(cfg), "bridge-status"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "BRIDGE_UNAVAILABLE"


def test_cli_bridge_command_runs_daemon(
    tmp_path: Path, socket_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[BridgeConfig] = []
    monkeypatch.setattr("trackwright.bridge.run_bridge", seen.append)
    assert main(["--config", str(write_config(tmp_path, socket_dir)), "bridge"]) == 0
    assert seen[0].socket_dir == socket_dir
