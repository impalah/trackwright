"""MIDI transport: two CoreMIDI virtual ports created with mido + python-rtmidi.

Port names are written from Cubase's point of view:

- ``to_cubase`` ("Trackwright To Cubase") is a Python *virtual output*. CoreMIDI publishes it as a
  source, so Cubase sees it as a MIDI **input**: the script reads from it.
- ``from_cubase`` ("Trackwright From Cubase") is a Python *virtual input*. CoreMIDI publishes it as
  a destination, so Cubase sees it as a MIDI **output**: the script writes to it.

The ports exist only while the process that created them is alive. Cubase reconnects by itself
when they reappear (verified in the POC, milestone H).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from loguru import logger

from trackwright.errors import TransportError
from trackwright.protocol import is_ours

Receiver = Callable[[list[int]], None]


class Transport(Protocol):
    """What the host client needs from a transport."""

    name: str

    def open(self, receiver: Receiver) -> None: ...

    def send_sysex(self, data: Sequence[int]) -> None: ...

    def close(self) -> None: ...

    def stats(self) -> dict[str, int]: ...


@dataclass
class TransportStats:
    sent_frames: int = 0
    received_frames: int = 0
    foreign_frames: int = 0
    non_sysex_messages: int = 0


class MidiTransport:
    """Real transport. ``backend`` is the ``mido`` module (injectable for tests)."""

    name = "coremidi-virtual"

    def __init__(self, to_cubase: str, from_cubase: str, *, backend: Any | None = None) -> None:
        self.to_cubase = to_cubase
        self.from_cubase = from_cubase
        self._backend = backend
        self._out: Any = None
        self._in: Any = None
        self._send_lock = threading.Lock()
        self._stats = TransportStats()

    def _mido(self) -> Any:
        if self._backend is None:
            import mido  # noqa: PLC0415 - imported lazily: loading rtmidi is slow and not needed by --help

            mido.set_backend("mido.backends.rtmidi")
            self._backend = mido
        return self._backend

    def open(self, receiver: Receiver) -> None:
        mido = self._mido()
        existing_in = set(mido.get_input_names())
        existing_out = set(mido.get_output_names())
        if self.to_cubase in existing_in or self.from_cubase in existing_out:
            raise TransportError(
                "virtual ports with these names already exist: is another bridge running?",
                details={"to_cubase": self.to_cubase, "from_cubase": self.from_cubase},
            )

        def on_message(message: Any) -> None:
            if message.type != "sysex":
                self._stats.non_sysex_messages += 1
                return
            data = list(message.data)
            if not is_ours(data):
                self._stats.foreign_frames += 1
                logger.trace("ignoring foreign SysEx {}", data[:8])
                return
            self._stats.received_frames += 1
            try:
                receiver(data)
            except Exception:
                logger.exception("receiver failed")

        try:
            self._out = mido.open_output(self.to_cubase, virtual=True)
            self._in = mido.open_input(self.from_cubase, virtual=True, callback=on_message)
        except Exception as exc:
            self.close()
            raise TransportError(f"cannot create virtual ports: {exc}") from exc
        logger.info("virtual MIDI ports open: '{}' (to Cubase), '{}' (from Cubase)", self.to_cubase, self.from_cubase)

    def send_sysex(self, data: Sequence[int]) -> None:
        if self._out is None:
            raise TransportError("transport is not open")
        message = self._mido().Message("sysex", data=list(data))
        with self._send_lock:
            self._out.send(message)
            self._stats.sent_frames += 1

    def close(self) -> None:
        for port in (self._in, self._out):
            if port is None:
                continue
            try:
                port.close()
            except Exception:
                logger.exception("error closing MIDI port")
        self._in = self._out = None

    def stats(self) -> dict[str, int]:
        return {
            "sent_frames": self._stats.sent_frames,
            "received_frames": self._stats.received_frames,
            "foreign_frames": self._stats.foreign_frames,
            "non_sysex_messages": self._stats.non_sysex_messages,
        }
