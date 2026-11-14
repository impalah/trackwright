"""TW-1405: bridge and IPC robustness (quality review I-01 … I-19)."""

from __future__ import annotations

import socket
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.support import ScriptedTransport
from tests.unit.test_bridge import FakeHost
from trackwright import bridge as bridge_module
from trackwright import exports, launcher
from trackwright.bridge import Bridge, BridgeClient, BridgeServer, prepare_socket_dir, run_bridge
from trackwright.cli import main
from trackwright.config import BridgeConfig
from trackwright.coremidi import MAX_SYSEX_BYTES, SysExAssembler
from trackwright.cubase import SCRIPT_NAME, install_script
from trackwright.errors import BridgeUnavailableError, PreconditionFailedError
from trackwright.launcher import BridgeLauncher

JsonObject = dict[str, Any]


@pytest.fixture
def sock_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="tw-") as d:
        yield Path(d) / "s"


@pytest.fixture
def live(sock_dir: Path) -> Iterator[BridgeServer]:
    server = BridgeServer(Bridge(FakeHost()), sock_dir / "bridge.sock")
    server.serve_in_thread()
    yield server
    server.stop()


# ---------------------------------------------------------------- I-01
def test_a_refused_bridge_leaves_the_live_socket_alone(live: BridgeServer) -> None:
    second = BridgeServer(Bridge(FakeHost()), live.socket_path)
    with pytest.raises(BridgeUnavailableError, match="already listening"):
        second.start()
    second.stop()
    assert live.socket_path.exists()
    assert BridgeClient(live.socket_path).call("ping", timeout=1.0) == {"echo": {}}  # still reachable


def test_run_bridge_is_refused_before_creating_midi_ports(live: BridgeServer) -> None:
    transport = ScriptedTransport(lambda _req: None)
    config = BridgeConfig(socket_dir=live.socket_path.parent)
    with pytest.raises(BridgeUnavailableError):
        run_bridge(config, transport=transport, stop=threading.Event())
    assert transport.receiver is None  # never opened
    assert live.socket_path.exists()


# ---------------------------------------------------------------- I-04
def test_a_burst_of_clients_is_not_refused(live: BridgeServer) -> None:
    errors: list[Exception] = []

    def ping() -> None:
        try:
            BridgeClient(live.socket_path).call("ping", timeout=2.0)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=ping) for _ in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_autostart_probes_a_busy_socket_again(sock_dir: Path) -> None:
    sock_dir.mkdir(parents=True)
    (sock_dir / "bridge.sock").touch()
    answers = iter([False, True])
    spawned: list[object] = []
    starter = BridgeLauncher(
        BridgeConfig(socket_dir=sock_dir),
        spawn=lambda argv, log: spawned.append(argv),
        alive=lambda _p: next(answers),
        sleep=lambda _s: None,
    )
    assert starter.ensure() is False
    assert spawned == []


# ---------------------------------------------------------------- I-05
def test_a_client_that_never_finishes_its_line_is_released(sock_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge_module._Handler, "timeout", 0.2)
    server = BridgeServer(Bridge(FakeHost()), sock_dir / "bridge.sock")
    server.serve_in_thread()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3.0)
            client.connect(str(server.socket_path))
            client.sendall(b'{"op": "ping"')  # no newline
            started = time.monotonic()
            assert client.recv(10) == b""  # the server closed the connection
            assert time.monotonic() - started < 2.0
    finally:
        server.stop()


# ---------------------------------------------------------------- I-06
def test_unterminated_sysex_has_bounded_memory() -> None:
    assembler = SysExAssembler()
    assert list(assembler.feed([0xF0] + [0x01] * (MAX_SYSEX_BYTES + 10))) == []
    assert assembler.oversized == 1
    assert list(assembler.feed([0xF0, 0x7D, 0x02, 0xF7])) == [[0x7D, 0x02]]


# ---------------------------------------------------------------- I-08
def test_unexpected_socket_errors_become_bridge_errors(tmp_path: Path) -> None:
    class Resetting:
        def __enter__(self) -> Resetting:
            return self

        def __exit__(self, *_: object) -> None: ...

        def settimeout(self, _t: float) -> None: ...

        def connect(self, _p: str) -> None:
            raise ConnectionResetError("reset by peer")

    client = BridgeClient(tmp_path / "x.sock", connect=Resetting)  # type: ignore[arg-type]
    with pytest.raises(BridgeUnavailableError) as exc:
        client.request("da.param.set", {})
    assert exc.value.details["sent"] == "unknown"  # never retried as "not sent"


def test_a_socket_path_too_long_is_explained(tmp_path: Path) -> None:
    long_dir = tmp_path / ("d" * 120)
    with pytest.raises(BridgeUnavailableError, match="too long"):
        BridgeServer(Bridge(FakeHost()), long_dir / "bridge.sock").start()


# ---------------------------------------------------------------- I-09
def test_subprocess_timeouts_do_not_escape(monkeypatch: pytest.MonkeyPatch) -> None:
    def hang(*_a: object, **_k: object) -> object:
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(subprocess, "run", hang)
    assert launcher._run(["/usr/bin/open", "-a", "X"]) == launcher.TIMED_OUT
    assert launcher._output(["/usr/sbin/lsof"]) == ""
    assert exports._afinfo(["/usr/bin/afinfo", "x.wav"]) == ""


# ---------------------------------------------------------------- I-11
def test_a_symlinked_socket_directory_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    target.mkdir(mode=0o755)
    link = tmp_path / "socks"
    link.symlink_to(target)
    with pytest.raises(BridgeUnavailableError, match="symbolic link"):
        prepare_socket_dir(link)
    assert target.stat().st_mode & 0o777 == 0o755  # not chmodded


# ---------------------------------------------------------------- I-12
def test_script_install_is_atomic_and_refuses_symlinked_folders(tmp_path: Path) -> None:
    folder = tmp_path / "bridge"
    status, written = install_script(folder, apply=True)
    assert written and status.state == "up_to_date"
    assert sorted(p.name for p in folder.iterdir()) == [SCRIPT_NAME]  # no temporary file left behind
    linked = tmp_path / "linked"
    linked.symlink_to(tmp_path / "real", target_is_directory=True)
    (tmp_path / "real").mkdir()
    with pytest.raises(PreconditionFailedError, match="symbolic link"):
        install_script(linked, apply=True)


# ---------------------------------------------------------------- I-19
def test_bad_log_level_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--log-level", "loud", "version"])
    assert exc.value.code == 2


def test_log_level_is_case_insensitive(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--log-level", "debug", "version"]) == 0
