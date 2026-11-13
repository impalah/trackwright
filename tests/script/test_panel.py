"""TW-1101: the status panel of the released script (emulated surface).

What Cubase draws was verified by hand (docs/verification.md, 2026-11-13). These tests prove the
script builds the panel with the verified mechanisms only and drives the activity lamp correctly.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.script.test_script_node import Harness
from trackwright.cubase import SCRIPT_VERSION

pytestmark = pytest.mark.node


@pytest.fixture
def h() -> Iterator[Harness]:
    harness = Harness()
    harness.sid = harness.call("hello")["r"]["sessionId"]
    harness.step(idle=5)  # let the lamp go off after hello
    harness.step(state=True)  # drain the panel log
    yield harness
    harness.close()


def lamp_values(h: Harness) -> list[int]:
    return [entry["lamp"] for entry in h.step(state=True)["state"]["panelLog"] if "lamp" in entry]


def test_layout_uses_only_verified_mechanisms(h: Harness) -> None:
    surface = [e for e in h.step(state=True)["state"]["surface"] if e["kind"] != "fader"]  # faders: automation
    assert [(e["kind"], e["x"], e["y"], e["w"]) for e in surface] == [
        ("label", 0, 0, 8),
        ("lamp", 8, 0, 1),
        ("label", 0, 1, 9),
    ]
    title, lamp, track = surface
    assert title["text"] == f"Trackwright {SCRIPT_VERSION}"
    assert track["hostObject"] == "selected"
    assert lamp["shape"] == "circle"
    assert all(e.get("related") is None for e in surface), "relateTo did not display in Cubase: not used"
    assert h.call("capabilities")["r"]["capabilities"]["panel"] == {"enabled": True, "errors": []}


def test_lamp_shows_activity(h: Harness) -> None:
    assert lamp_values(h) == []  # idle: off, nothing sent
    h.step(frames=h.frames_for("ping", {"echo": "x"}))
    assert lamp_values(h) == [1]
    h.step(idle=1)
    assert lamp_values(h) == []  # stays on for a minimum time
    h.step(idle=3)
    assert lamp_values(h) == [0]


def test_lamp_stays_on_while_requests_are_queued(h: Harness) -> None:
    h.step(frames=h.frames_for("da.channels", {"scope": "mixer"}))
    h.step(frames=h.frames_for("da.base"))
    assert lamp_values(h) == [1]  # one switch on, not one per request
    h.step(idle=4)
    assert lamp_values(h) == [0]


def test_panel_never_blocks_operations(h: Harness) -> None:
    assert h.call("ping", {"echo": "x"})["ok"]
    assert h.call("da.channels", {"scope": "mixer"})["ok"]
    assert h.call("transport.get")["ok"]
