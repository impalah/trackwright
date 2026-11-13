"""TW-1206 variant B2: the automation fader is off in released scripts and drivable in the experiment build.

These tests use an emulated surface. Whether Cubase records automation from it is what the experiment
in Cubase must find out.
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


def test_released_script_has_no_fader() -> None:
    harness = started()
    try:
        assert harness.call("auto.fader", {"touch": True})["err"]["code"] == "UNSUPPORTED"
        assert harness.call("capabilities")["r"]["capabilities"]["automationFader"] == {"enabled": False}
        assert all(e["kind"] != "fader" for e in harness.step(state=True)["state"]["surface"])
    finally:
        harness.close()


def test_experiment_builds_a_bound_fader(experiment: Harness) -> None:
    state = experiment.step(state=True)["state"]
    fader = next(e for e in state["surface"] if e["kind"] == "fader")
    assert (fader["x"], fader["y"], fader["w"], fader["h"]) == (10, 0, 1, 2)
    assert fader["touchBoundTo"] == "autoFaderTouch"
    assert state["valueBindings"] == ["selected.volume"]
    caps = experiment.call("capabilities")["r"]["capabilities"]
    assert caps["automationFader"] == {"enabled": True, "errors": []}
    assert experiment.call("hello")["r"]["scriptVersion"] == f"{SCRIPT_VERSION}+tw1206"


def test_touch_move_release_sequence(experiment: Harness) -> None:
    out = experiment.call("auto.fader", {"touch": True, "value": 0.7})["r"]
    assert (out["touchedBefore"], out["touched"], out["value"]) == (False, True, 0.7)
    experiment.call("auto.fader", {"value": 0.6})
    released = experiment.call("auto.fader", {"value": 0.5, "touch": False})["r"]
    assert released["touched"] is False
    log = experiment.step(state=True)["state"]["panelLog"]
    events = [e for e in log if "touch" in e or "fader" in e]
    assert events == [{"touch": 1}, {"fader": 0.7}, {"fader": 0.6}, {"fader": 0.5}, {"touch": 0}]


def test_out_of_range_is_refused(experiment: Harness) -> None:
    assert experiment.call("auto.fader", {"value": 2})["err"]["code"] == "BAD_REQUEST"


def test_source_keeps_the_fader_off() -> None:
    assert "var AUTOMATION_FADER_ENABLED = false" in builder().SOURCE.read_text(encoding="utf-8")
