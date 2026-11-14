"""Bridge daemon and its local IPC client.

The bridge is a long-running process that owns the virtual MIDI ports and the
:class:`~trackwright.host.HostClient`. MCP servers (one per client session) talk to it over a
Unix domain socket in a private per-user directory (mode 0700, socket 0600). No network port is
ever opened.

IPC: one JSON line per connection, at most 64 KiB::

    request:  {"op": str, "p": {...}, "timeout": 0.05..30}
    response: {"ok": true, "result": {...}, "meta": {...}}
              {"ok": false, "error": {"code": str, "message": str, "details": {...}}}
"""

from __future__ import annotations

import json
import os
import platform
import socket
import socketserver
import stat
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from loguru import logger

from trackwright.config import BridgeConfig
from trackwright.errors import (
    BridgeUnavailableError,
    ProtocolError,
    RequestTimeoutError,
    TrackwrightError,
)
from trackwright.host import Reply
from trackwright.ops import ALL_OPS, WRITE_OPS
from trackwright.transport import Transport

MAX_LINE = 64 * 1024
MIN_TIMEOUT = 0.05
MAX_TIMEOUT = 30.0
MAX_SESSION_LEN = 64
LOCAL_OPS = frozenset({"bridge.status"})
JsonObject = dict[str, Any]


class HostBackend(Protocol):
    """The part of :class:`~trackwright.host.HostClient` the bridge needs (a fake in tests)."""

    session_id: str | None

    def call(
        self, op: str, params: JsonObject | None = None, *, timeout: float | None = None, session: str | None = None
    ) -> Reply: ...

    def stats(self) -> JsonObject: ...


# ---------------------------------------------------------------------------- validation
def validate_request(obj: object) -> tuple[str, JsonObject, float, str | None]:
    """Validate one IPC request; return ``(op, params, timeout, session)``.

    ``session`` is optional and only used for writes: the script session the caller pinned (TW-1402).
    """
    if not isinstance(obj, dict):
        raise ProtocolError("IPC request must be a JSON object")
    op = obj.get("op")
    if not isinstance(op, str) or (op not in ALL_OPS and op not in LOCAL_OPS):
        raise ProtocolError(f"operation not allowed: {op!r}")
    params = obj.get("p") or {}
    if not isinstance(params, dict):
        raise ProtocolError("'p' must be a JSON object")
    timeout = obj.get("timeout", 3.0)
    if isinstance(timeout, bool) or not isinstance(timeout, int | float) or not MIN_TIMEOUT <= timeout <= MAX_TIMEOUT:
        raise ProtocolError(f"timeout must be a number within [{MIN_TIMEOUT}, {MAX_TIMEOUT}] seconds")
    session = obj.get("session")
    if session is not None and (not isinstance(session, str) or not session or len(session) > MAX_SESSION_LEN):
        raise ProtocolError("'session' must be a non-empty string")
    return op, params, float(timeout), session if op in WRITE_OPS else None


# ---------------------------------------------------------------------------- socket directory
def prepare_socket_dir(directory: Path) -> Path:
    """Create the private socket directory (0700) and refuse it if another user could use it."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.stat()
    if info.st_uid != os.getuid():
        raise BridgeUnavailableError(f"socket directory {directory} belongs to another user")
    if stat.S_IMODE(info.st_mode) & 0o077:
        directory.chmod(0o700)
        if stat.S_IMODE(directory.stat().st_mode) & 0o077:
            raise BridgeUnavailableError(f"cannot make {directory} private (mode 0700)")
    return directory


def _socket_is_alive(path: Path) -> bool:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            probe.connect(str(path))
    except ConnectionRefusedError, FileNotFoundError, TimeoutError, OSError:
        return False
    return True


# ---------------------------------------------------------------------------- daemon
class Bridge:
    """Request dispatcher, independent of sockets so it can be unit tested."""

    def __init__(self, host: HostBackend) -> None:
        self.host = host
        self.started_at = time.time()
        self.requests = 0
        self.errors = 0

    def status(self) -> JsonObject:
        return {
            "pid": os.getpid(),
            "uptime_s": round(time.time() - self.started_at, 1),
            "requests": self.requests,
            "errors": self.errors,
            "host": self.host.stats(),
        }

    def handle(self, obj: object) -> JsonObject:
        self.requests += 1
        started = time.monotonic()
        try:
            op, params, timeout, session = validate_request(obj)
            if op == "bridge.status":
                return {"ok": True, "result": self.status()}
            reply = self.host.call(op, params, timeout=timeout, session=session)
        except TrackwrightError as exc:
            self.errors += 1
            logger.debug("request failed: {}", exc)
            return {"ok": False, "error": exc.to_dict(), "meta": self._meta(started)}
        except Exception as exc:
            self.errors += 1
            logger.exception("unexpected error handling {}", obj)
            op_name = obj.get("op") if isinstance(obj, dict) else None
            outcome = "unknown" if op_name in WRITE_OPS else "not_executed_or_lost"
            error = TrackwrightError(
                f"internal bridge error: {exc}", code="INTERNAL_ERROR", details={"op": op_name, "outcome": outcome}
            )
            return {"ok": False, "error": error.to_dict(), "meta": self._meta(started)}
        logger.debug("{} ok in {:.1f} ms (via {})", op, reply.duration_ms, reply.via)
        meta = self._meta(started) | {"rid": reply.rid, "via": reply.via, "duplicate": reply.duplicate}
        return {"ok": True, "result": reply.result, "meta": meta}

    def _meta(self, started: float) -> JsonObject:
        return {"duration_ms": round((time.monotonic() - started) * 1000, 2), "session_id": self.host.session_id}


class _Handler(socketserver.StreamRequestHandler):
    bridge: Bridge

    def handle(self) -> None:
        line = self.rfile.readline(MAX_LINE + 1)
        if not line:
            return  # a liveness probe: connected and closed without a request
        if len(line) > MAX_LINE:
            response: JsonObject = {"ok": False, "error": ProtocolError("IPC line too long").to_dict()}
        else:
            try:
                response = self.bridge.handle(json.loads(line))
            except ValueError as exc:
                response = {"ok": False, "error": ProtocolError(f"invalid JSON: {exc}").to_dict()}
        try:
            self.wfile.write((json.dumps(response) + "\n").encode())
        except BrokenPipeError:
            logger.warning("IPC client disconnected before the response")


class BridgeServer:
    """Unix socket server around a :class:`Bridge`."""

    def __init__(self, bridge: Bridge, socket_path: Path) -> None:
        self.bridge = bridge
        self.socket_path = socket_path
        self._server: socketserver.ThreadingUnixStreamServer | None = None

    def start(self) -> None:
        prepare_socket_dir(self.socket_path.parent)
        if self.socket_path.exists():
            if _socket_is_alive(self.socket_path):
                raise BridgeUnavailableError(f"another bridge is already listening on {self.socket_path}")
            self.socket_path.unlink()
        handler = type("BoundHandler", (_Handler,), {"bridge": self.bridge})
        previous = os.umask(0o077)
        try:
            self._server = socketserver.ThreadingUnixStreamServer(str(self.socket_path), handler)
        finally:
            os.umask(previous)
        self._server.daemon_threads = True
        self.socket_path.chmod(0o600)
        logger.info("bridge listening on {}", self.socket_path)

    def serve_forever(self) -> None:
        if self._server is None:
            self.start()
        assert self._server is not None
        self._server.serve_forever(poll_interval=0.2)

    def serve_in_thread(self) -> threading.Thread:
        """Start serving in a daemon thread (used by tests)."""
        if self._server is None:
            self.start()
        thread = threading.Thread(target=self.serve_forever, name="trackwright-bridge", daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        self.socket_path.unlink(missing_ok=True)
        logger.info("bridge stopped")


# ---------------------------------------------------------------------------- client
def error_from_dict(error: JsonObject) -> TrackwrightError:
    from trackwright import errors as module  # noqa: PLC0415 - small local lookup table

    code = str(error.get("code", "BRIDGE_ERROR"))
    message = str(error.get("message", ""))
    details = error.get("details") if isinstance(error.get("details"), dict) else None
    if code == "TIMEOUT":
        outcome_unknown = bool(details and details.get("outcome") == "unknown")
        return RequestTimeoutError(message, outcome_unknown=outcome_unknown, details=details)
    if code == "STALE_SESSION":
        return module.StaleSessionError(message, details=details)
    return TrackwrightError(message, code=code, details=details)


class BridgeClient:
    """Client used by the MCP server and the CLI to reach the bridge."""

    def __init__(self, socket_path: Path, *, connect: Callable[[], socket.socket] | None = None) -> None:
        self.socket_path = socket_path
        self._connect = connect or (lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM))

    def request(
        self, op: str, params: JsonObject | None = None, *, timeout: float = 3.0, session: str | None = None
    ) -> JsonObject:
        """Send one request; return the full response (``ok``, ``result`` or ``error``, ``meta``)."""
        request: JsonObject = {"op": op, "p": params or {}, "timeout": timeout}
        if session is not None:
            request["session"] = session
        line = json.dumps(request) + "\n"
        buffer = b""
        try:
            with self._connect() as sock:
                sock.settimeout(timeout + 2.0)
                sock.connect(str(self.socket_path))
                sock.sendall(line.encode())
                while not buffer.endswith(b"\n"):
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    buffer += chunk
        except FileNotFoundError as exc:
            raise BridgeUnavailableError(
                f"bridge socket not found at {self.socket_path}: start it with 'trackwright bridge'",
                details={"sent": False},
            ) from exc
        except ConnectionRefusedError as exc:
            raise BridgeUnavailableError(
                f"bridge is not accepting connections at {self.socket_path}", details={"sent": False}
            ) from exc
        except TimeoutError as exc:
            raise RequestTimeoutError(
                f"no answer from the bridge for {op}", outcome_unknown=True, details={"op": op}
            ) from exc
        if not buffer:
            raise BridgeUnavailableError("the bridge closed the connection without answering")
        try:
            response = json.loads(buffer)
        except ValueError as exc:
            raise ProtocolError(f"invalid response from the bridge: {exc}") from exc
        if not isinstance(response, dict):
            raise ProtocolError("the bridge response is not a JSON object")
        return response

    def call(self, op: str, params: JsonObject | None = None, *, timeout: float = 3.0) -> JsonObject:
        """Like :meth:`request` but return ``result`` or raise the error it carries."""
        response = self.request(op, params, timeout=timeout)
        if not response.get("ok"):
            error = response.get("error")
            raise error_from_dict(error if isinstance(error, dict) else {})
        result = response.get("result")
        return result if isinstance(result, dict) else {}


# ---------------------------------------------------------------------------- entry point
def make_transport(settings: BridgeConfig, *, system: str | None = None) -> Transport:
    """The configured MIDI transport (TW-1302): CoreMIDI through ctypes on macOS by default."""
    backend = settings.backend
    if backend == "auto":
        backend = "coremidi" if (system or platform.system()) == "Darwin" else "rtmidi"
    if backend == "coremidi":
        from trackwright.coremidi import CoreMidiTransport  # noqa: PLC0415

        return CoreMidiTransport(settings.to_cubase_port, settings.from_cubase_port)
    from trackwright.transport import MidiTransport  # noqa: PLC0415 - needs mido + python-rtmidi installed

    return MidiTransport(settings.to_cubase_port, settings.from_cubase_port)


def run_bridge(
    settings: BridgeConfig, *, transport: Transport | None = None, stop: threading.Event | None = None
) -> None:
    """Run the bridge until ``stop`` is set or SIGINT/SIGTERM arrives."""
    import signal  # noqa: PLC0415 - only needed by the daemon

    from trackwright.host import HostClient  # noqa: PLC0415

    stop_event = stop or threading.Event()
    host = HostClient(
        transport or make_transport(settings),
        default_timeout=settings.request_timeout,
    )
    host.open()
    server = BridgeServer(Bridge(host), settings.socket_path)
    try:
        server.serve_in_thread()
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGINT, signal.SIGTERM):
                signal.signal(signum, lambda *_: stop_event.set())
        logger.info("bridge ready; waiting for Cubase on '{}'", settings.to_cubase_port)
        stop_event.wait()
    finally:
        server.stop()
        host.close()
