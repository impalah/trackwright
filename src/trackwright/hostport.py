"""The port through which the MCP layer reaches Cubase.

Two implementations:

- :class:`BridgeHost`, the real one, over the bridge IPC;
- :class:`trackwright.fake.FakeCubase`, an in-memory simulator for tests and demos.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from trackwright.bridge import BridgeClient, unwrap
from trackwright.errors import BridgeUnavailableError, RequestTimeoutError
from trackwright.jsontypes import JsonObject
from trackwright.ops import WRITE_OPS


class HostPort(Protocol):
    @property
    def session_id(self) -> str | None:
        """Session of the Cubase script that answered last (changes when the script reloads)."""

    @property
    def simulated(self) -> bool:
        """``True`` only for the simulator."""

    def call(self, op: str, params: JsonObject | None = None, *, session: str | None = None) -> JsonObject:
        """Run one operation; return its result or raise a :class:`~trackwright.errors.TrackwrightError`.

        ``session`` (writes only): the script session the caller's object ids belong to. The write is sent
        with exactly that session, so a script reloaded in between refuses it with ``STALE_SESSION``.
        """


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
        script_wait: float = 10.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._ensure_bridge = ensure_bridge
        self._script_wait = script_wait
        self._sleep = sleep
        self._clock = clock
        self._read_timeout = read_timeout
        self._write_timeout = write_timeout
        self._session_id: str | None = None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def call(self, op: str, params: JsonObject | None = None, *, session: str | None = None) -> JsonObject:
        timeout = self._write_timeout if op in WRITE_OPS else self._read_timeout
        session = session if op in WRITE_OPS else None
        try:
            response = self._client.request(op, params, timeout=timeout, session=session)
        except BridgeUnavailableError as exc:
            # Retrying is safe only when nothing reached the bridge (no socket / refused connection).
            if self._ensure_bridge is None or exc.details.get("sent") is not False:
                raise
            self._ensure_bridge()
            self._wait_for_script(op)
            response = self._client.request(op, params, timeout=timeout, session=session)
        meta = response.get("meta")
        if isinstance(meta, dict) and isinstance(meta.get("session_id"), str):
            self._session_id = meta["session_id"]
        return unwrap(response)

    def _wait_for_script(self, op: str) -> None:
        """TW-1509: after starting the bridge, Cubase needs a moment to bind to the new virtual ports.

        ``hello`` only reads, so it is repeated until the script answers or ``script_wait`` runs out; the
        caller's request (which never reached the bridge) is sent once afterwards, or not at all.
        """
        deadline = self._clock() + self._script_wait
        while True:
            remaining = deadline - self._clock()
            try:
                unwrap(self._client.request("hello", timeout=max(0.05, min(self._read_timeout, remaining))))
            except RequestTimeoutError as exc:
                if self._clock() >= deadline:
                    raise RequestTimeoutError(
                        f"the bridge started but Cubase did not answer within {self._script_wait:g} s: check "
                        f"that Cubase is open and the 'Trackwright - Bridge' surface is active in the MIDI "
                        f"Remote tab; {op} was not sent",
                        outcome_unknown=False,
                        details={"op": op, "outcome": "not_executed"},
                    ) from exc
                self._sleep(0.5)
            else:
                return
