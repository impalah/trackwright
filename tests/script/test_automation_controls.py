"""TW-1207: the automation controls of the released script (emulated surface).

Recording automation through them was verified in Cubase (docs/verification.md, 2026-11-13); these
tests check every binding, the touch wiring and the auto.control / auto.list operations.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.script.test_script_node import Harness
from trackwright.cubase import SCRIPT_VERSION

pytestmark = pytest.mark.node
EXPECTED_KEYS = (
    ["volume", "pan"]
    + [f"send{i}.level" for i in range(1, 5)]
    + [f"eq{b}.{p}" for b in range(1, 5) for p in ("gain", "freq", "q")]
    + ["prefilter.gain", "prefilter.lowcut", "prefilter.highcut"]
    + [f"qc{i}" for i in range(1, 9)]
    + [f"insert{s}.p{p}" for s in (1, 2) for p in range(1, 9)]
)


def started() -> Harness:
    harness = Harness()
    harness.sid = harness.call("hello")["r"]["sessionId"]
    return harness


@pytest.fixture
def experiment() -> Iterator[Harness]:
    harness = started()
    harness.step(state=True)  # drain logs
    yield harness
    harness.close()


def test_experiment_binds_every_parameter(experiment: Harness) -> None:
    listed = experiment.call("auto.list")["r"]
    assert [c["key"] for c in listed["controls"]] == EXPECTED_KEYS
    assert listed["errors"] == []
    state = experiment.step(state=True)["state"]
    assert state["valueBindings"] == [f"selected.{key}" for key in EXPECTED_KEYS]
    faders = [e for e in state["surface"] if e["kind"] == "fader"]
    assert len(faders) == len(EXPECTED_KEYS)
    assert {f["touchBoundTo"] for f in faders} == {f"autoTouch.{key}" for key in EXPECTED_KEYS}
    assert len({(f["x"], f["y"]) for f in faders}) == len(faders), "faders must not overlap"
    caps = experiment.call("capabilities")["r"]["capabilities"]["automationControls"]
    assert caps == {"enabled": True, "count": len(EXPECTED_KEYS), "errors": []}
    assert experiment.call("hello")["r"]["scriptVersion"] == SCRIPT_VERSION


def test_touch_move_release_sequence(experiment: Harness) -> None:
    out = experiment.call("auto.control", {"key": "pan", "touch": True, "value": 0.3})["r"]
    assert (out["key"], out["touchedBefore"], out["touched"], out["value"]) == ("pan", False, True, 0.3)
    experiment.call("auto.control", {"key": "pan", "value": 0.2})
    released = experiment.call("auto.control", {"key": "pan", "value": 0.1, "touch": False})["r"]
    assert released["touched"] is False
    log = experiment.step(state=True)["state"]["panelLog"]
    assert [e for e in log if "fader" in e] == [{"fader": 0.3}, {"fader": 0.2}, {"fader": 0.1}]


def test_errors(experiment: Harness) -> None:
    assert experiment.call("auto.control", {"key": "volume", "value": 2})["err"]["code"] == "BAD_REQUEST"
    assert experiment.call("auto.control", {"key": "nope"})["err"]["code"] == "NOT_FOUND"
