"""Start the bridge and Cubase on demand (TW-1201).

* :class:`BridgeLauncher` starts ``trackwright bridge`` as a detached process when the MCP server cannot
  reach it. A file lock and a second liveness check make sure two MCP servers starting at the same time
  do not launch two bridges (the bridge itself also refuses to start when the socket is alive).
* :class:`CubaseLauncher` checks the Cubase process and opens the application with ``open -a``. It never
  closes, kills or injects anything into Cubase.
"""

from __future__ import annotations

import fcntl
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from loguru import logger

from trackwright.bridge import _socket_is_alive, prepare_socket_dir
from trackwright.config import BridgeConfig, CubaseConfig
from trackwright.errors import BridgeUnavailableError, PreconditionFailedError

Spawn = Callable[[Sequence[str], Path], None]
Run = Callable[[Sequence[str]], int]


def _spawn_detached(argv: Sequence[str], log_path: Path) -> None:
    """Start ``argv`` in its own session, with no stdin/stdout and stderr appended to ``log_path``."""
    with log_path.open("ab") as log:
        subprocess.Popen(  # noqa: S603 - fixed argv built from sys.executable
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=log,
            start_new_session=True,
            close_fds=True,
        )


def _run(argv: Sequence[str]) -> int:
    return subprocess.run(list(argv), capture_output=True, check=False).returncode  # noqa: S603


class BridgeLauncher:
    """Make sure the bridge is running, starting it if needed."""

    def __init__(
        self,
        config: BridgeConfig,
        *,
        config_path: Path | None = None,
        spawn: Spawn = _spawn_detached,
        alive: Callable[[Path], bool] = _socket_is_alive,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.config_path = config_path
        self._spawn = spawn
        self._alive = alive
        self._sleep = sleep
        self._clock = clock

    @property
    def log_path(self) -> Path:
        return self.config.socket_dir / "bridge.log"

    def argv(self) -> list[str]:
        argv = [sys.executable, "-m", "trackwright"]
        if self.config_path is not None:
            argv += ["--config", str(self.config_path)]
        return [*argv, "bridge"]

    def ensure(self) -> bool:
        """Return ``True`` when this call started the bridge, ``False`` when it was already running."""
        socket_path = self.config.socket_path
        if self._alive(socket_path):
            return False
        directory = prepare_socket_dir(self.config.socket_dir)
        with (directory / "autostart.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)  # another MCP server may be starting it right now
            if self._alive(socket_path):
                return False
            logger.info("starting the bridge (log: {})", self.log_path)
            self._spawn(self.argv(), self.log_path)
            deadline = self._clock() + self.config.autostart_timeout
            while self._clock() < deadline:
                if self._alive(socket_path):
                    logger.info("bridge started")
                    return True
                self._sleep(0.1)
        raise BridgeUnavailableError(
            f"the bridge did not start within {self.config.autostart_timeout:g} s; see {self.log_path}",
            details={"log": str(self.log_path)},
        )


class CubaseLauncher:
    """Check and open the Cubase application (macOS)."""

    def __init__(self, config: CubaseConfig, *, run: Run = _run) -> None:
        self.config = config
        self._run = run

    @property
    def app(self) -> str:
        return self.config.app

    @property
    def launch_timeout(self) -> float:
        return self.config.launch_timeout

    def is_running(self) -> bool:
        return self._run(["/usr/bin/pgrep", "-x", self.config.app]) == 0

    def launch(self, project: Path | None = None) -> None:
        argv = ["/usr/bin/open", "-a", self.config.app]
        if project is not None:
            argv.append(str(project))
        if self._run(argv) != 0:
            raise PreconditionFailedError(
                f"macOS could not open {self.config.app!r}: check [cubase] app in the configuration",
                code="LAUNCH_FAILED",
            )
