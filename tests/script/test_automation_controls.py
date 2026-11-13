"""TW-1206/1207: automation controls are off in released scripts and drivable in the experiment build.

These tests use an emulated surface. Whether Cubase records automation from each control is what the
experiment in Cubase must find out (verified for volume, variant B2).
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.script.test_script_node import Harness
from trackwright.cubase import SCRIPT_VERSION

pytestmark = pytest.mark.node
BUILD = Path(__file__).resolve().parents[2] / "experiments" / "tw1206" / "build.py"
EXPECTED_KEYS = (
    ["volume", "pan"]
    + [f"send{i}.level" for i in range(1, 5)]
    + [f"eq{b}.{p}" for b in range(1, 5) for p in ("gain", "freq", "q")]
    + ["prefilter.gain", "prefilter.lowcut", "prefilter.highcut"]
    + [f"qc{i}" for i in range(1, 9)]
    + [f"insert{s}.p{p}" for s in (1, 2) for p in range(1, 9)]
)


def builder() -> Any:
    spec = importlib.util.spec_from_file_location("tw1206_build", BUILD)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def started(script: Path | None = None) -> Harness:
    harness = Harness(script) if script else Harness()
    harness.sid = harness.call("hello")["r"]["sessionId"]
    return harness


@pytest.fixture
def experiment(tmp_path: Path) -> Iterator[Harness]:
    harness = started(builder().build(target=tmp_path / "Trackwright_Bridge.js"))
    harness.step(state=True)  # drain logs
    yield harness
    harness.close()


def test_released_script_has_no_controls() -> None:
    harness = started()
    try:
        assert harness.call("auto.control", {"key": "volume", "touch": True})["err"]["code"] == "UNSUPPORTED"
        assert harness.call("auto.list")["r"] == {"enabled": False, "controls": []}
        assert harness.call("capabilities")["r"]["capabilities"]["automationControls"] == {"enabled": False}
        assert all(e["kind"] != "fader" for e in harness.step(state=True)["state"]["surface"])
    finally:
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
    assert experiment.call("hello")["r"]["scriptVersion"] == f"{SCRIPT_VERSION}+tw1206"


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


def test_source_keeps_the_controls_off() -> None:
    assert "var AUTOMATION_CONTROLS_ENABLED = false" in builder().SOURCE.read_text(encoding="utf-8")
