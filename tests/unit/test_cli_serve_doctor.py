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
from trackwright.bridge import run_bridge
from trackwright.cli import main, make_service
from trackwright.config import BridgeConfig, Settings, load_settings
from trackwright.cubase import install_script
from trackwright.fake import FakeCubase
from trackwright.hostport import BridgeHost

JsonObject = dict[str, Any]


@pytest.fixture
def socket_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="tw-") as d:
        yield Path(d) / "s"


def write_config(tmp_path: Path, socket_dir: Path, script_dir: Path) -> Path:
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        f'[bridge]\nsocket_dir = "{socket_dir}"\nrequest_timeout = 1.0\n\n[script]\ninstall_dir = "{script_dir}"\n',
        encoding="utf-8",
    )
    return cfg


def test_make_service_backends() -> None:
    assert isinstance(make_service(Settings(), simulate=True).host, FakeCubase)
    assert isinstance(make_service(Settings(), simulate=False).host, BridgeHost)


def test_serve_runs_stdio_server(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr("mcp.server.mcpserver.MCPServer.run", lambda self, transport: seen.append(transport))
    assert main(["serve", "--simulate"]) == 0
    assert seen == ["stdio"]


def test_doctor_reports_what_to_fix(tmp_path: Path, socket_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = write_config(tmp_path, socket_dir, tmp_path / "scripts")
    assert main(["--config", str(cfg), "doctor"]) == 1
    report = json.loads(capsys.readouterr().out)
    failing = {c["check"]: c.get("fix") for c in report["checks"] if not c["ok"]}
    assert "script install --apply" in failing["script installed"]
    assert "trackwright bridge" in failing["bridge running"]
    assert "Cubase answers" not in failing


def script(req: JsonObject) -> JsonObject | None:
    if req["op"] == "hello":
        return ok(req, {"sessionId": "s1", "scriptVersion": "1.0.0", "host": {"appName": "Cubase"}})
    return None  # Cubase never answers anything else


@pytest.fixture
def bridge(socket_dir: Path) -> Iterator[BridgeConfig]:
    config = BridgeConfig(socket_dir=socket_dir, request_timeout=0.3)
    stop = threading.Event()
    thread = threading.Thread(
        target=run_bridge, args=(config,), kwargs={"transport": ScriptedTransport(script), "stop": stop}
    )
    thread.start()
    while not config.socket_path.exists():
        time.sleep(0.01)
    yield config
    stop.set()
    thread.join(timeout=3)


def test_doctor_all_green(bridge: BridgeConfig, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    script_dir = tmp_path / "scripts"
    cfg = write_config(tmp_path, bridge.socket_dir, script_dir)
    install_script(load_settings(cfg).script.install_dir, apply=True)
    assert main(["--config", str(cfg), "doctor"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert all(c["ok"] for c in report["checks"])
    answers = next(c for c in report["checks"] if c["check"] == "Cubase answers")
    assert answers["detail"]["script"] == "1.0.0"


def test_doctor_when_cubase_is_silent(socket_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = BridgeConfig(socket_dir=socket_dir, request_timeout=0.2)
    stop = threading.Event()
    silent = ScriptedTransport(lambda req: None)
    thread = threading.Thread(target=run_bridge, args=(config,), kwargs={"transport": silent, "stop": stop})
    thread.start()
    while not config.socket_path.exists():
        time.sleep(0.01)
    try:
        cfg = tmp_path / "c.toml"
        cfg.write_text(f'[bridge]\nsocket_dir = "{socket_dir}"\nrequest_timeout = 0.2\n', encoding="utf-8")
        assert main(["--config", str(cfg), "doctor"]) == 1
        report = json.loads(capsys.readouterr().out)
        answers = next(c for c in report["checks"] if c["check"] == "Cubase answers")
        assert answers["ok"] is False
        assert "MIDI Remote" in answers["fix"]
    finally:
        stop.set()
        thread.join(timeout=3)
