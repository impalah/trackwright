"""TW-1201: starting the bridge and Cubase on demand (launchers simulated; no process is started)."""

from __future__ import annotations

import socket
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from trackwright.bridge import Bridge, BridgeClient, BridgeServer
from trackwright.config import BridgeConfig, CubaseConfig
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import BridgeUnavailableError, PolicyError, PreconditionFailedError, TrackwrightError
from trackwright.fake import FakeCubase, FakeLauncher
from trackwright.hostport import BridgeHost
from trackwright.launcher import BridgeLauncher, CubaseLauncher, _spawn_detached


@pytest.fixture
def short_dir() -> Any:
    import tempfile

    with tempfile.TemporaryDirectory(dir="/tmp") as directory:  # AF_UNIX paths must be short
        yield Path(directory) / "tw"


# ---------------------------------------------------------------- BridgeLauncher
class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_bridge_already_running_is_not_started_again(short_dir: Path) -> None:
    spawned: list[Any] = []
    launcher = BridgeLauncher(BridgeConfig(socket_dir=short_dir), spawn=lambda a, p: spawned.append(a),
                              alive=lambda _p: True)  # fmt: skip
    assert launcher.ensure() is False
    assert spawned == []


def test_bridge_is_started_and_waited_for(short_dir: Path) -> None:
    clock = Clock()
    spawned: list[Any] = []
    checks = iter([False, False, False, True])
    launcher = BridgeLauncher(
        BridgeConfig(socket_dir=short_dir),
        config_path=Path("/cfg.toml"),
        spawn=lambda argv, log: spawned.append((argv, log)),
        alive=lambda _p: next(checks),
        sleep=clock.sleep,
        clock=clock,
    )
    assert launcher.ensure() is True
    argv, log = spawned[0]
    assert argv == [sys.executable, "-m", "trackwright", "--config", "/cfg.toml", "bridge"]
    assert log == short_dir / "bridge.log"
    assert (short_dir / "autostart.lock").exists()


def test_bridge_started_by_someone_else_while_waiting_for_the_lock(short_dir: Path) -> None:
    checks = iter([False, True])
    spawned: list[Any] = []
    launcher = BridgeLauncher(BridgeConfig(socket_dir=short_dir), spawn=lambda a, p: spawned.append(a),
                              alive=lambda _p: next(checks))  # fmt: skip
    assert launcher.ensure() is False
    assert spawned == []


def test_bridge_that_never_starts(short_dir: Path) -> None:
    clock = Clock()
    launcher = BridgeLauncher(BridgeConfig(socket_dir=short_dir, autostart_timeout=1.0), spawn=lambda a, p: None,
                              alive=lambda _p: False, sleep=clock.sleep, clock=clock)  # fmt: skip
    with pytest.raises(BridgeUnavailableError) as exc:
        launcher.ensure()
    assert exc.value.details["log"].endswith("bridge.log")
    assert launcher.argv()[-1] == "bridge"


def test_spawn_detached_writes_stderr_to_the_log(tmp_path: Path) -> None:
    log = tmp_path / "bridge.log"
    _spawn_detached([sys.executable, "-c", "import sys; sys.stderr.write('hola')"], log)
    deadline = threading.Event()
    for _ in range(50):
        if log.read_text() == "hola":
            break
        deadline.wait(0.1)
    assert log.read_text() == "hola"


# ---------------------------------------------------------------- BridgeHost retry
class Backend:
    session_id = "s1"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def call(self, op: str, params: Any = None, *, timeout: float | None = None) -> Any:
        from trackwright.host import Reply

        self.calls.append(op)
        return Reply(op=op, rid="1-a", result={"op": op}, via="sysex", duplicate=False, duration_ms=1.0)

    def stats(self) -> dict[str, Any]:
        return {}


def test_host_starts_the_bridge_and_retries_once(short_dir: Path) -> None:
    config = BridgeConfig(socket_dir=short_dir)
    backend = Backend()
    server = BridgeServer(Bridge(backend), config.socket_path)

    def ensure() -> bool:
        server.start()
        server.serve_in_thread()
        return True

    host = BridgeHost(BridgeClient(config.socket_path), read_timeout=1, write_timeout=1, ensure_bridge=ensure)
    try:
        assert host.call("da.param.set", {"id": 1})["op"] == "da.param.set"
        assert backend.calls == ["da.param.set"]  # sent exactly once
    finally:
        server.stop()


def test_host_without_autostart_raises(short_dir: Path) -> None:
    host = BridgeHost(BridgeClient(short_dir / "none.sock"), read_timeout=1, write_timeout=1)
    with pytest.raises(BridgeUnavailableError) as exc:
        host.call("hello")
    assert exc.value.details == {"sent": False}


def test_host_never_retries_after_sending(short_dir: Path) -> None:
    """A connection closed after the request was sent may have executed it: no autostart, no retry."""
    short_dir.mkdir(parents=True)
    path = short_dir / "b.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen(1)

    def close_after_reading() -> None:
        conn, _ = listener.accept()
        conn.recv(65536)
        conn.close()

    threading.Thread(target=close_after_reading, daemon=True).start()
    ensured: list[bool] = []
    host = BridgeHost(
        BridgeClient(path), read_timeout=1, write_timeout=1, ensure_bridge=lambda: ensured.append(True) or True
    )
    try:
        with pytest.raises(BridgeUnavailableError):
            host.call("da.param.set", {"id": 1})
        assert ensured == []
    finally:
        listener.close()


# ---------------------------------------------------------------- CubaseLauncher
def test_cubase_launcher_commands() -> None:
    ran: list[list[str]] = []
    codes = iter([0, 1, 0, 0])

    def run(argv: Any) -> int:
        ran.append(list(argv))
        return next(codes)

    launcher = CubaseLauncher(CubaseConfig(app="Cubase 14"), run=run)
    assert (launcher.app, launcher.launch_timeout) == ("Cubase 14", 120.0)
    assert launcher.is_running() is True
    assert launcher.is_running() is False
    launcher.launch()
    launcher.launch(Path("/p/song.cpr"))
    assert ran == [
        ["/usr/bin/pgrep", "-x", "Cubase 14"],
        ["/usr/bin/pgrep", "-x", "Cubase 14"],
        ["/usr/bin/open", "-a", "Cubase 14"],
        ["/usr/bin/open", "-a", "Cubase 14", "/p/song.cpr"],
    ]


def test_cubase_launcher_failure() -> None:
    with pytest.raises(PreconditionFailedError) as exc:
        CubaseLauncher(CubaseConfig(app="Nope"), run=lambda _a: 1).launch()
    assert exc.value.code == "LAUNCH_FAILED"


# ---------------------------------------------------------------- cubase_launch
def make(fake: FakeCubase, launcher: FakeLauncher | None, *, writes: bool = True) -> CubaseService:
    return CubaseService(fake, WritePolicy(enabled=writes), sleep=lambda _s: None, settle_timeout=0.0,
                         launcher=launcher)  # fmt: skip


def test_launch_when_already_running() -> None:
    fake = FakeCubase()
    launcher = FakeLauncher(fake)
    out = make(fake, launcher).launch_cubase(dry_run=False)
    assert (out.status, out.script_version) == ("already_running", fake.call("hello")["scriptVersion"])
    assert launcher.launched == []


def test_running_without_script_never_opens_a_second_instance() -> None:
    fake = FakeCubase()
    fake.online = False
    launcher = FakeLauncher(fake, running=True)
    out = make(fake, launcher).launch_cubase(dry_run=False)
    assert out.status == "running_without_script"
    assert out.instructions and "second instance" in out.instructions
    assert launcher.launched == []


def test_launch_plan_then_open(tmp_path: Path) -> None:
    project = tmp_path / "song.cpr"
    project.write_bytes(b"")
    fake = FakeCubase()
    fake.online = False
    launcher = FakeLauncher(fake, running=False)
    service = make(fake, launcher)
    plan = service.launch_cubase(str(project))
    assert (plan.status, plan.project, launcher.launched) == ("planned", str(project.resolve()), [])
    out = service.launch_cubase(str(project), dry_run=False)
    assert out.status == "ready"
    assert out.process_running is True
    assert launcher.launched == [project.resolve()]


def test_launch_awaiting_user() -> None:
    fake = FakeCubase()
    fake.online = False
    launcher = FakeLauncher(fake, running=False, answers_after=-1)  # Cubase stuck on a dialog
    out = make(fake, launcher).launch_cubase(dry_run=False, timeout=0.0)
    assert out.status == "awaiting_user"
    assert out.process_running is True
    assert out.instructions and "dialog" in out.instructions


def test_launch_errors(tmp_path: Path) -> None:
    fake = FakeCubase()
    fake.online = False
    service = make(fake, FakeLauncher(fake, running=False))
    with pytest.raises(PreconditionFailedError) as bad:
        service.launch_cubase("song.txt")
    assert bad.value.code == "BAD_REQUEST"
    with pytest.raises(PreconditionFailedError) as missing:
        service.launch_cubase(str(tmp_path / "missing.cpr"))
    assert missing.value.code == "NOT_FOUND"
    with pytest.raises(PolicyError):
        make(fake, FakeLauncher(fake, running=False), writes=False).launch_cubase(dry_run=False)
    with pytest.raises(TrackwrightError) as unsupported:
        make(fake, None).launch_cubase()
    assert unsupported.value.code == "UNSUPPORTED"


def test_liveness_probe_gets_no_answer_and_no_warning(short_dir: Path) -> None:
    from trackwright.bridge import _socket_is_alive

    config = BridgeConfig(socket_dir=short_dir)
    server = BridgeServer(Bridge(Backend()), config.socket_path)
    server.serve_in_thread()
    try:
        assert _socket_is_alive(config.socket_path) is True
        assert BridgeClient(config.socket_path).call("hello")["op"] == "hello"
    finally:
        server.stop()
