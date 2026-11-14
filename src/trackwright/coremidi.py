"""MIDI transport on macOS CoreMIDI through ``ctypes`` (TW-1302): pure Python, nothing to compile.

Same contract as :class:`trackwright.transport.MidiTransport` (mido + python-rtmidi), which is kept as an
alternative (``[bridge] backend = "rtmidi"``), for instance for other platforms:

- ``to_cubase`` is a CoreMIDI *virtual source* (``MIDISourceCreate``): Cubase sees it as an input. Data is
  sent with ``MIDIReceived``.
- ``from_cubase`` is a *virtual destination* (``MIDIDestinationCreate`` with a read callback): Cubase sees
  it as an output.

SysEx may arrive split over several packets or callbacks; :class:`SysExAssembler` rebuilds each message.
The callback runs on a CoreMIDI thread: it never raises, and the ``ctypes`` callback object is kept
alive for the lifetime of the port.
"""

from __future__ import annotations

import ctypes
import platform
import threading
from collections.abc import Callable, Iterator, Sequence
from typing import Any

from loguru import logger

from trackwright.errors import TransportError
from trackwright.protocol import is_ours
from trackwright.transport import Receiver, TransportStats

COREMIDI = "/System/Library/Frameworks/CoreMIDI.framework/CoreMIDI"
COREFOUNDATION = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
UTF8 = 0x08000100  # kCFStringEncodingUTF8
SYSEX_START, SYSEX_END = 0xF0, 0xF7
MAX_SYSEX_BYTES = 4096  # a Trackwright frame is at most ~250 bytes
PACKET_HEADER = 10  # MIDITimeStamp (UInt64) + length (UInt16)

MIDIObjectRef = ctypes.c_uint32
OSStatus = ctypes.c_int32
ReadProc = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)


class SysExAssembler:
    """Rebuild SysEx messages from a MIDI byte stream (``F0 … F7``, which may be split anywhere)."""

    def __init__(self) -> None:
        self._buffer: list[int] | None = None
        self.non_sysex = 0
        self.oversized = 0

    def feed(self, data: bytes | Sequence[int]) -> Iterator[list[int]]:
        """Yield the data bytes (without ``F0``/``F7``) of every message completed by ``data``."""
        for byte in data:
            if byte == SYSEX_START:
                self._buffer = []
            elif byte >= 0xF8:  # real-time bytes may appear anywhere, even inside SysEx
                continue
            elif self._buffer is not None:
                if byte == SYSEX_END:
                    done, self._buffer = self._buffer, None
                    yield done
                elif byte & 0x80:  # another status byte: the SysEx was cut
                    self._buffer = None
                    self.non_sysex += 1
                elif len(self._buffer) >= MAX_SYSEX_BYTES:  # I-06: bounded memory without an F7
                    self._buffer = None
                    self.oversized += 1
                else:
                    self._buffer.append(byte)
            elif byte & 0x80:
                self.non_sysex += 1  # a channel or system message we do not use


def packets(packet_list: int, *, aligned: bool | None = None) -> Iterator[bytes]:
    """The data of each ``MIDIPacket`` in a ``MIDIPacketList`` at address ``packet_list``.

    Layout (``#pragma pack(4)``): ``UInt32 numPackets`` then packets of ``UInt64 timeStamp``, ``UInt16
    length`` and the data. On ARM the next packet starts at a 4-byte boundary (``MIDIPacketNext``).
    """
    align = platform.machine().startswith(("arm", "aarch")) if aligned is None else aligned
    count = ctypes.c_uint32.from_address(packet_list).value
    address = packet_list + 4
    for _ in range(count):
        length = ctypes.c_uint16.from_address(address + 8).value
        yield ctypes.string_at(address + PACKET_HEADER, length)
        address += PACKET_HEADER + length
        if align:
            address = (address + 3) & ~3


class CoreMidiApi:
    """The few CoreMIDI and CoreFoundation calls the transport needs (replaceable in tests)."""

    def __init__(self) -> None:
        self.midi = ctypes.cdll.LoadLibrary(COREMIDI)
        self.cf = ctypes.cdll.LoadLibrary(COREFOUNDATION)
        self.cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        self.cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        self.cf.CFStringGetCString.restype = ctypes.c_bool
        self.cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
        self.cf.CFRelease.argtypes = [ctypes.c_void_p]
        m = self.midi
        m.MIDIClientCreate.restype = OSStatus
        m.MIDIClientCreate.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(MIDIObjectRef)]
        m.MIDISourceCreate.restype = OSStatus
        m.MIDISourceCreate.argtypes = [MIDIObjectRef, ctypes.c_void_p, ctypes.POINTER(MIDIObjectRef)]
        m.MIDIDestinationCreate.restype = OSStatus
        m.MIDIDestinationCreate.argtypes = [
            MIDIObjectRef,
            ctypes.c_void_p,
            ReadProc,
            ctypes.c_void_p,
            ctypes.POINTER(MIDIObjectRef),
        ]
        m.MIDIPacketListInit.restype = ctypes.c_void_p
        m.MIDIPacketListInit.argtypes = [ctypes.c_void_p]
        m.MIDIPacketListAdd.restype = ctypes.c_void_p
        m.MIDIPacketListAdd.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_uint64,
            ctypes.c_ulong,
            ctypes.c_char_p,
        ]
        m.MIDIReceived.restype = OSStatus
        m.MIDIReceived.argtypes = [MIDIObjectRef, ctypes.c_void_p]
        m.MIDIEndpointDispose.restype = OSStatus
        m.MIDIEndpointDispose.argtypes = [MIDIObjectRef]
        m.MIDIClientDispose.restype = OSStatus
        m.MIDIClientDispose.argtypes = [MIDIObjectRef]
        m.MIDIGetNumberOfSources.restype = ctypes.c_ulong
        m.MIDIGetNumberOfDestinations.restype = ctypes.c_ulong
        m.MIDIGetSource.restype = MIDIObjectRef
        m.MIDIGetSource.argtypes = [ctypes.c_ulong]
        m.MIDIGetDestination.restype = MIDIObjectRef
        m.MIDIGetDestination.argtypes = [ctypes.c_ulong]
        m.MIDIObjectGetStringProperty.restype = OSStatus
        m.MIDIObjectGetStringProperty.argtypes = [MIDIObjectRef, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        self._name_property = ctypes.c_void_p.in_dll(m, "kMIDIPropertyName")

    @staticmethod
    def _check(status: int, what: str) -> None:
        if status != 0:
            raise TransportError(f"CoreMIDI {what} failed (OSStatus {status})", details={"status": status})

    def _cfstring(self, text: str) -> int:
        ref = self.cf.CFStringCreateWithCString(None, text.encode(), UTF8)
        if not ref:
            raise TransportError(f"cannot create a CFString for {text!r}")
        return int(ref)

    def _string(self, ref: int) -> str:
        buffer = ctypes.create_string_buffer(512)
        return buffer.value.decode() if self.cf.CFStringGetCString(ref, buffer, len(buffer), UTF8) else ""

    def _with_name(self, name: str, create: Callable[[int], int]) -> int:
        cf_name = self._cfstring(name)
        try:
            return create(cf_name)
        finally:
            self.cf.CFRelease(cf_name)

    def client(self, name: str) -> int:
        def create(cf_name: int) -> int:
            ref = MIDIObjectRef()
            self._check(self.midi.MIDIClientCreate(cf_name, None, None, ctypes.byref(ref)), "MIDIClientCreate")
            return int(ref.value)

        return self._with_name(name, create)

    def source(self, client: int, name: str) -> int:
        def create(cf_name: int) -> int:
            ref = MIDIObjectRef()
            self._check(self.midi.MIDISourceCreate(client, cf_name, ctypes.byref(ref)), "MIDISourceCreate")
            return int(ref.value)

        return self._with_name(name, create)

    def destination(self, client: int, name: str, read_proc: Any) -> int:
        def create(cf_name: int) -> int:
            ref = MIDIObjectRef()
            status = self.midi.MIDIDestinationCreate(client, cf_name, read_proc, None, ctypes.byref(ref))
            self._check(status, "MIDIDestinationCreate")
            return int(ref.value)

        return self._with_name(name, create)

    def received(self, source: int, data: bytes) -> None:
        """Publish ``data`` (one complete message) on a virtual source."""
        size = len(data) + 64
        buffer = ctypes.create_string_buffer(size)
        packet = self.midi.MIDIPacketListInit(buffer)
        packet = self.midi.MIDIPacketListAdd(buffer, size, packet, 0, len(data), data)
        if not packet:
            raise TransportError("the message does not fit in a MIDI packet list")
        self._check(self.midi.MIDIReceived(source, buffer), "MIDIReceived")

    def endpoint_names(self) -> tuple[set[str], set[str]]:
        """Names of every MIDI source and destination in the system."""
        names: list[set[str]] = []
        for count, get in ((self.midi.MIDIGetNumberOfSources, self.midi.MIDIGetSource),
                           (self.midi.MIDIGetNumberOfDestinations, self.midi.MIDIGetDestination)):  # fmt: skip
            found = set()
            for index in range(count()):
                ref = ctypes.c_void_p()
                status = self.midi.MIDIObjectGetStringProperty(get(index), self._name_property, ctypes.byref(ref))
                if status == 0 and ref.value:
                    found.add(self._string(ref.value))
                    self.cf.CFRelease(ref.value)
            names.append(found)
        return names[0], names[1]

    def dispose_endpoint(self, ref: int) -> None:
        self.midi.MIDIEndpointDispose(ref)

    def dispose_client(self, ref: int) -> None:
        self.midi.MIDIClientDispose(ref)


class CoreMidiTransport:
    """Real transport over CoreMIDI. ``api`` is injectable for tests."""

    name = "coremidi-ctypes"

    def __init__(self, to_cubase: str, from_cubase: str, *, api: Any | None = None) -> None:
        self.to_cubase = to_cubase
        self.from_cubase = from_cubase
        self._api = api
        self._client: int | None = None
        self._source: int | None = None
        self._destination: int | None = None
        self._read_proc: Any = None  # must outlive the destination
        self._send_lock = threading.Lock()
        self._stats = TransportStats()
        self._assembler = SysExAssembler()

    def _core(self) -> Any:
        if self._api is None:
            self._api = CoreMidiApi()
        return self._api

    def _on_packets(self, packet_list: int | None, _ref: object = None, _src: object = None) -> None:
        if not packet_list:
            return
        try:
            for chunk in packets(packet_list):
                for data in self._assembler.feed(chunk):
                    self._deliver(data)
            self._stats.non_sysex_messages = self._assembler.non_sysex
        except Exception:  # never let an exception reach the CoreMIDI thread
            logger.exception("error reading MIDI packets")

    def _deliver(self, data: list[int]) -> None:
        if not is_ours(data):
            self._stats.foreign_frames += 1
            logger.trace("ignoring foreign SysEx {}", data[:8])
            return
        self._stats.received_frames += 1
        try:
            self._receiver(data)
        except Exception:
            logger.exception("receiver failed")

    def open(self, receiver: Receiver) -> None:
        api = self._core()
        sources, destinations = api.endpoint_names()
        if self.to_cubase in sources or self.from_cubase in destinations:
            raise TransportError(
                "virtual ports with these names already exist: is another bridge running?",
                details={"to_cubase": self.to_cubase, "from_cubase": self.from_cubase},
            )
        self._receiver = receiver
        self._read_proc = ReadProc(self._on_packets)
        try:
            self._client = api.client("Trackwright")
            self._source = api.source(self._client, self.to_cubase)
            self._destination = api.destination(self._client, self.from_cubase, self._read_proc)
        except Exception as exc:
            self.close()
            raise TransportError(f"cannot create virtual ports: {exc}") from exc
        logger.info("virtual MIDI ports open (CoreMIDI): '{}' (to Cubase), '{}' (from Cubase)",
                    self.to_cubase, self.from_cubase)  # fmt: skip

    def send_sysex(self, data: Sequence[int]) -> None:
        if self._source is None:
            raise TransportError("transport is not open")
        with self._send_lock:
            self._core().received(self._source, bytes([SYSEX_START, *data, SYSEX_END]))
            self._stats.sent_frames += 1

    def close(self) -> None:
        api = self._api
        for ref in (self._destination, self._source):
            if ref is not None and api is not None:
                try:
                    api.dispose_endpoint(ref)
                except Exception:
                    logger.exception("error closing MIDI endpoint")
        if self._client is not None and api is not None:
            try:
                api.dispose_client(self._client)
            except Exception:
                logger.exception("error closing MIDI client")
        self._client = self._source = self._destination = None

    def stats(self) -> dict[str, int]:
        return {
            "sent_frames": self._stats.sent_frames,
            "received_frames": self._stats.received_frames,
            "foreign_frames": self._stats.foreign_frames,
            "non_sysex_messages": self._stats.non_sysex_messages,
        }
