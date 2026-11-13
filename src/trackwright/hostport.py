"""The port through which the MCP layer reaches Cubase.

Two implementations:

- :class:`BridgeHost`, the real one, over the bridge IPC;
- :class:`trackwright.fake.FakeCubase`, an in-memory simulator for tests and demos.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from trackwright.bridge import BridgeClient, error_from_dict
from trackwright.errors import BridgeUnavailableError
from trackwright.ops import WRITE_OPS

JsonObject = dict[str, Any]


class HostPort(Protocol):
    @property
    def session_id(self) -> str | None:
        """Session of the Cubase script that answered last (changes when the script reloads)."""

    @property
    def simulated(self) -> bool:
        """``True`` only for the simulator."""

    def call(self, op: str, params: JsonObject | None = None) -> JsonObject:
        """Run one operation; return its result or raise a :class:`~trackwright.errors.TrackwrightError`."""


class BridgeHost:
    """Reach Cubase through the bridge daemon."""

    simulated = False

    def __init__(
        self,
        client: BridgeClient,
        *,
        read_timeout: float,
        write_timeout: float,
        ensure_bridge: Callable[[], bool] | None = None,
    ) -> None:
        self._client = client
        self._ensure_bridge = ensure_bridge
        self._read_timeout = read_timeout
        self._write_timeout = write_timeout
        self._session_id: str | None = None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def call(self, op: str, params: JsonObject | None = None) -> JsonObject:
        timeout = self._write_timeout if op in WRITE_OPS else self._read_timeout
        try:
            response = self._client.request(op, params, timeout=timeout)
        except BridgeUnavailableError as exc:
            # Retrying is safe only when nothing reached the bridge (no socket / refused connection).
            if self._ensure_bridge is None or exc.details.get("sent") is not False:
                raise
            self._ensure_bridge()
            response = self._client.request(op, params, timeout=timeout)
        meta = response.get("meta")
        if isinstance(meta, dict) and isinstance(meta.get("session_id"), str):
            self._session_id = meta["session_id"]
        if not response.get("ok"):
            error = response.get("error")
            raise error_from_dict(error if isinstance(error, dict) else {})
        result = response.get("result")
        return result if isinstance(result, dict) else {}
