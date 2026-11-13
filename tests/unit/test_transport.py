from __future__ import annotations

import pytest

from tests.support import FakeMessage, FakeMido
from trackwright import protocol
from trackwright.errors import TransportError
from trackwright.transport import MidiTransport

TO, FROM = "Trackwright To Cubase", "Trackwright From Cubase"


def opened(mido: FakeMido) -> tuple[MidiTransport, list[list[int]]]:
    received: list[list[int]] = []
    transport = MidiTransport(TO, FROM, backend=mido)
    transport.open(received.append)
    return transport, received


def test_open_send_receive() -> None:
    mido = FakeMido()
    transport, received = opened(mido)
    assert mido.out_port is not None
    assert mido.in_port is not None
    assert mido.out_port.name == TO
    assert mido.in_port.name == FROM

    transport.send_sysex([0x7D, 0x54, 0x57])
    assert mido.out_port.sent == [FakeMessage("sysex", (0x7D, 0x54, 0x57))]

    own = protocol.build_frames(b"{}", 1)[0]
    assert mido.in_port.callback is not None
    mido.in_port.callback(FakeMessage("sysex", tuple(own)))
    mido.in_port.callback(FakeMessage("sysex", (0x7E, 0x7F, 0x06, 0x01)))  # Identity Request
    mido.in_port.callback(FakeMessage("note_on"))
    assert received == [own]
    assert transport.stats() == {
        "sent_frames": 1,
        "received_frames": 1,
        "foreign_frames": 1,
        "non_sysex_messages": 1,
    }


def test_receiver_exception_does_not_escape(log_records: list[str]) -> None:
    mido = FakeMido()
    transport = MidiTransport(TO, FROM, backend=mido)

    def broken(_data: list[int]) -> None:
        raise RuntimeError("boom")

    transport.open(broken)
    assert mido.in_port is not None
    assert mido.in_port.callback is not None
    mido.in_port.callback(FakeMessage("sysex", tuple(protocol.build_frames(b"{}", 1)[0])))
    assert any("receiver failed" in r for r in log_records)


@pytest.mark.parametrize(("inputs", "outputs"), [([TO], []), ([], [FROM])])
def test_refuses_existing_port_names(inputs: list[str], outputs: list[str]) -> None:
    with pytest.raises(TransportError, match="another bridge"):
        MidiTransport(TO, FROM, backend=FakeMido(inputs, outputs)).open(lambda _d: None)


def test_open_failure_closes_and_raises() -> None:
    mido = FakeMido(fail_open=True)
    with pytest.raises(TransportError, match="cannot create"):
        MidiTransport(TO, FROM, backend=mido).open(lambda _d: None)
    assert mido.out_port is not None
    assert mido.out_port.closed


def test_send_requires_open() -> None:
    with pytest.raises(TransportError, match="not open"):
        MidiTransport(TO, FROM, backend=FakeMido()).send_sysex([1])


def test_close_is_best_effort(log_records: list[str]) -> None:
    mido = FakeMido()
    transport, _ = opened(mido)
    assert mido.in_port is not None
    mido.in_port.fail_on_close = True
    transport.close()
    transport.close()  # idempotent
    assert mido.out_port is not None
    assert mido.out_port.closed
    assert any("error closing" in r for r in log_records)


def test_real_mido_backend_is_loaded_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    mido = pytest.importorskip("mido", reason="mido + python-rtmidi are optional since TW-1302 (see pyproject.toml)")

    calls: list[str] = []
    monkeypatch.setattr(mido, "set_backend", calls.append)
    transport = MidiTransport(TO, FROM)
    assert transport._mido() is mido
    assert calls == ["mido.backends.rtmidi"]
