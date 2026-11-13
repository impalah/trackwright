"""TW-1101: the status panel stays off in the released script and works in the experiment build.

These tests use an emulated surface: they prove the script calls the API as intended and never
breaks while doing so. What Cubase really draws can only be learnt in Cubase (experiment protocol).
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.script.test_script_node import Harness
from trackwright.cubase import SCRIPT_VERSION

pytestmark = pytest.mark.node
BUILD = Path(__file__).resolve().parents[2] / "experiments" / "tw1101" / "build.py"


def load_builder():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("tw1101_build", BUILD)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def experiment(tmp_path: Path) -> Iterator[Harness]:
    script = load_builder().build(target=tmp_path / "Trackwright_Bridge.js")
    harness = Harness(script)
    hello = harness.call("hello")
    harness.sid = hello["r"]["sessionId"]
    yield harness
    harness.close()


def test_released_script_keeps_the_single_placeholder() -> None:
    harness = Harness()
    try:
        harness.sid = harness.call("hello")["r"]["sessionId"]
        surface = harness.step(state=True)["state"]["surface"]
        assert surface == [{"kind": "label", "x": 0, "y": 0, "w": 4, "h": 1, "related": None}]
        assert harness.call("capabilities")["r"]["capabilities"]["panel"] == {"enabled": False}
    finally:
        harness.close()


def test_experiment_build_is_marked() -> None:
    builder = load_builder()
    text = builder.SOURCE.read_text(encoding="utf-8")
    assert "var PANEL_ENABLED = false" in text


def test_experiment_layout(experiment: Harness) -> None:
    state = experiment.step(state=True)["state"]
    by_row = {(e["kind"], e["y"]): e for e in state["surface"]}
    assert by_row[("label", 0)]["text"] == f"Trackwright {SCRIPT_VERSION}+tw1101"
    assert by_row[("label", 1)]["hostObject"] == "selected"
    assert by_row[("label", 2)]["related"] == "lamp@8,2"
    assert by_row[("lamp", 2)]["shape"] == "circle"
    caps = experiment.call("capabilities")["r"]["capabilities"]["panel"]
    assert caps == {"enabled": True, "errors": []}


def test_experiment_shows_requests_and_heartbeat(experiment: Harness) -> None:
    experiment.step(state=True)  # drain the log
    experiment.call("ping", {"echo": "hola panel"})
    log = experiment.step(state=True)["state"]["panelLog"]
    assert any(entry.get("display", "").endswith("ping hola panel") for entry in log)
    experiment.step(idle=18)
    lamp = [entry["lamp"] for entry in experiment.step(state=True)["state"]["panelLog"] if "lamp" in entry]
    assert lamp == [1, 0]


def test_experiment_still_answers_everything(experiment: Harness) -> None:
    assert experiment.call("ping", {"echo": "x"})["ok"]
    assert experiment.call("da.channels", {"scope": "mixer"})["ok"]
    assert experiment.call("transport.get")["ok"]
