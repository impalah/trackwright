"""TW-1302: the CoreMIDI transport (ctypes). The C calls are replaced by a fake API; the packet parser runs
on real ctypes buffers laid out like MIDIPacketList."""

from __future__ import annotations

import ctypes
import struct
from typing import Any

import pytest

from trackwright import protocol
from trackwright.bridge import make_transport
from trackwright.config import BridgeConfig
from trackwright.coremidi import CoreMidiTransport, SysExAssembler, packets
from trackwright.errors import TransportError
from trackwright.transport import MidiTransport

TO, FROM = "Trackwright To Cubase", "Trackwright From Cubase"


def packet_list(chunks: list[bytes], *, aligned: bool) -> ctypes.Array[ctypes.c_char]:
    raw = bytearray(struct.pack("<I", len(chunks)))
    for chunk in chunks:
        raw += struct.pack("<QH", 0, len(chunk)) + chunk
        if aligned:
            raw += b"\0" * (-len(raw) % 4)
    return ctypes.create_string_buffer(bytes(raw), len(raw) + 8)


# ---------------------------------------------------------------- pure parts
def test_assembler_rebuilds_split_and_mixed_streams() -> None:
    assembler = SysExAssembler()
    assert list(assembler.feed([0xF0, 0x7D, 0x54])) == []
    assert list(assembler.feed([0xF8, 0x57, 0xF7, 0x90, 0x3C, 0x64])) == [[0x7D, 0x54, 0x57]]  # clock ignored
    assert list(assembler.feed([0xF0, 0x01, 0x80, 0xF0, 0x02, 0xF7])) == [[0x02]]  # cut by a status byte
    assert assembler.non_sysex == 2


@pytest.mark.parametrize("aligned", [True, False])
def test_packet_parser(aligned: bool) -> None:
    chunks = [b"\xf0\x7d\x54\x57\xf7", b"\x90\x3c\x64", b"\xf0" + b"\x01" * 300 + b"\xf7"]
    buffer = packet_list(chunks, aligned=aligned)
    assert list(packets(ctypes.addressof(buffer), aligned=aligned)) == chunks


# ---------------------------------------------------------------- transport with a fake API
class FakeApi:
    def __init__(self, sources: set[str] | None = None) -> None:
        self.sources, self.destinations = sources or set(), set()
        self.sent: list[bytes] = []
        self.read_proc: Any = None
        self.disposed: list[int] = []
        self.fail_destination = False

    def endpoint_names(self) -> tuple[set[str], set[str]]:
        return set(self.sources), set(self.destinations)

    def client(self, name: str) -> int:
        return 1

    def source(self, client: int, name: str) -> int:
        self.sources.add(name)
        return 2

    def destination(self, client: int, name: str, read_proc: Any) -> int:
        if self.fail_destination:
            raise TransportError("boom")
        self.destinations.add(name)
        self.read_proc = read_proc
        return 3

    def received(self, source: int, data: bytes) -> None:
        self.sent.append(data)

    def dispose_endpoint(self, ref: int) -> None:
        self.disposed.append(ref)

    def dispose_client(self, ref: int) -> None:
        self.disposed.append(ref)


def test_open_send_receive_close() -> None:
    api = FakeApi()
    received: list[list[int]] = []
    transport = CoreMidiTransport(TO, FROM, api=api)
    transport.open(received.append)
    assert (TO in api.sources, FROM in api.destinations) == (True, True)
    transport.send_sysex([0x7D, 0x54, 0x57])
    assert api.sent == [b"\xf0\x7d\x54\x57\xf7"]
    own = protocol.build_frames(b"{}", 1)[0]
    stream = [b"\xf0" + bytes(own[:5]), bytes(own[5:]) + b"\xf7", b"\xf0\x7e\x7f\x06\x01\xf7", b"\x90\x3c\x64"]
    buffer = packet_list(stream, aligned=True)
    api.read_proc(ctypes.addressof(buffer), None, None)  # through the real ctypes callback
    assert received == [own]
    assert transport.stats() == {"sent_frames": 1, "received_frames": 1, "foreign_frames": 1,
                                 "non_sysex_messages": 1}  # fmt: skip
    transport.close()
    assert api.disposed == [3, 2, 1]
    with pytest.raises(TransportError):
        transport.send_sysex([1])


def test_duplicate_ports_and_failures() -> None:
    with pytest.raises(TransportError, match="already exist"):
        CoreMidiTransport(TO, FROM, api=FakeApi(sources={TO})).open(lambda _d: None)
    api = FakeApi()
    api.fail_destination = True
    with pytest.raises(TransportError, match="cannot create"):
        CoreMidiTransport(TO, FROM, api=api).open(lambda _d: None)
    assert api.disposed == [2, 1]  # what was created is released


def test_callback_never_raises() -> None:
    api = FakeApi()

    def explode(_data: list[int]) -> None:
        raise RuntimeError("receiver bug")

    transport = CoreMidiTransport(TO, FROM, api=api)
    transport.open(explode)
    own = protocol.build_frames(b"{}", 1)[0]
    buffer = packet_list([bytes([0xF0, *own, 0xF7])], aligned=True)
    transport._on_packets(ctypes.addressof(buffer))
    transport._on_packets(None)
    assert transport.stats()["received_frames"] == 1


def test_backend_selection() -> None:
    assert isinstance(make_transport(BridgeConfig(), system="Darwin"), CoreMidiTransport)
    assert isinstance(make_transport(BridgeConfig(), system="Windows"), MidiTransport)
    assert isinstance(make_transport(BridgeConfig(backend="rtmidi")), MidiTransport)
    assert isinstance(make_transport(BridgeConfig(backend="coremidi"), system="Linux"), CoreMidiTransport)


# ---------------------------------------------------------------- real CoreMIDI (macOS only)
@pytest.mark.skipif(__import__("platform").system() != "Darwin", reason="needs macOS CoreMIDI")
def test_real_coremidi_loopback() -> None:
    """Virtual ports with test names; a second client receives from our source and sends to our destination."""
    import time

    from trackwright.coremidi import CoreMidiApi, MIDIObjectRef, ReadProc

    to_name, from_name = f"TW test To {time.time_ns()}", f"TW test From {time.time_ns()}"
    api = CoreMidiApi()
    midi = api.midi
    got: list[list[int]] = []
    transport = CoreMidiTransport(to_name, from_name, api=api)
    transport.open(got.append)
    heard: list[list[int]] = []
    assembler = SysExAssembler()

    def on_peer(packet_list: int, _a: object, _b: object) -> None:
        for chunk in packets(packet_list):
            heard.extend(assembler.feed(chunk))

    peer_proc = ReadProc(on_peer)
    peer = api.client("TW test peer")
    midi.MIDIInputPortCreate.argtypes = [MIDIObjectRef, ctypes.c_void_p, ReadProc, ctypes.c_void_p,
                                         ctypes.POINTER(MIDIObjectRef)]  # fmt: skip
    midi.MIDIOutputPortCreate.argtypes = [MIDIObjectRef, ctypes.c_void_p, ctypes.POINTER(MIDIObjectRef)]
    midi.MIDIPortConnectSource.argtypes = [MIDIObjectRef, MIDIObjectRef, ctypes.c_void_p]
    midi.MIDISend.argtypes = [MIDIObjectRef, MIDIObjectRef, ctypes.c_void_p]
    in_port, out_port = MIDIObjectRef(), MIDIObjectRef()
    try:
        midi.MIDIInputPortCreate(peer, api._cfstring("in"), peer_proc, None, ctypes.byref(in_port))
        midi.MIDIOutputPortCreate(peer, api._cfstring("out"), ctypes.byref(out_port))

        def endpoint(count: Any, get: Any, wanted: str) -> int:
            for index in range(count()):
                ref = ctypes.c_void_p()
                obj = get(index)
                status = midi.MIDIObjectGetStringProperty(obj, api._name_property, ctypes.byref(ref))
                if status == 0 and api._string(ref.value or 0) == wanted:
                    return int(obj)
            raise AssertionError(wanted)

        midi.MIDIPortConnectSource(in_port, endpoint(midi.MIDIGetNumberOfSources, midi.MIDIGetSource, to_name), None)
        time.sleep(0.2)
        frames = protocol.build_frames(b'{"pad":"' + b"x" * 2000 + b'"}', 3)
        for frame in frames:
            transport.send_sysex(frame)
        destination = endpoint(midi.MIDIGetNumberOfDestinations, midi.MIDIGetDestination, from_name)
        for frame in frames:
            data = bytes([0xF0, *frame, 0xF7])
            buffer = ctypes.create_string_buffer(len(data) + 64)
            packet = midi.MIDIPacketListInit(buffer)
            midi.MIDIPacketListAdd(buffer, len(data) + 64, packet, 0, len(data), data)
            midi.MIDISend(out_port, destination, buffer)
        deadline = time.monotonic() + 3
        while (len(heard) < len(frames) or len(got) < len(frames)) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert heard == [list(f) for f in frames]
        assert got == [list(f) for f in frames]
    finally:
        transport.close()
        api.dispose_client(peer)
    sources, destinations = api.endpoint_names()
    assert to_name not in sources and from_name not in destinations
