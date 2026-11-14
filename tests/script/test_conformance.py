"""TW-1408: the simulator answers with the same shapes as the real script (quality review F-01, F-04, S-11).

Unit tests run against ``FakeCubase``; these tests make sure it does not drift from the script that runs
inside Cubase. Both receive the same operations; the answers are compared by structure (keys and value
types), error codes and clamping, not by values (the two in-memory projects differ).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest

from tests.script.node_harness import NODE, Harness
from tests.script.test_automation_controls import EXPECTED_KEYS
from trackwright.core.base import CHANNEL_TAGS
from trackwright.cubase import SCRIPT_PATH
from trackwright.errors import TrackwrightError
from trackwright.fake import FakeCubase
from trackwright.ops import ALL_OPS

pytestmark = [pytest.mark.node, pytest.mark.skipif(NODE is None, reason="node is not installed")]
JsonObject = dict[str, Any]
FAKE_ONLY = {"simulated"}  # how Trackwright tells the simulator apart: intentionally absent from the script


@pytest.fixture(scope="module")
def pair() -> Iterator[tuple[Harness, FakeCubase, JsonObject]]:
    harness = Harness()
    harness.sid = harness.call("hello")["r"]["sessionId"]
    fake = FakeCubase()
    fake.call("hello")
    ids = harness.step(state=True)["state"]["ids"]
    yield harness, fake, {"script": ids["audio"], "fake": fake.channel_by_title("POC-TEST").id}
    harness.close()


def shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: shape(v) for k, v in value.items() if k not in FAKE_ONLY}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    if isinstance(value, bool) or value is None:
        return type(value).__name__
    return "number" if isinstance(value, int | float) else type(value).__name__


def differences(script: Any, fake: Any, path: str = "") -> list[str]:
    if isinstance(script, dict) and isinstance(fake, dict):
        found = [f"{path}.{k}: only in the script" for k in script.keys() - fake.keys()]
        found += [f"{path}.{k}: only in the simulator" for k in fake.keys() - script.keys()]
        for key in script.keys() & fake.keys():
            found += differences(script[key], fake[key], f"{path}.{key}")
        return found
    if isinstance(script, list) and isinstance(fake, list):
        return differences(script[0], fake[0], f"{path}[]") if script and fake else []
    if script == fake or {script, fake} <= {"NoneType", "str"} or {script, fake} <= {"NoneType", "number"}:
        return []  # an error text may be null or empty; a value Cubase has not reported yet is null
    return [f"{path}: script {script} vs simulator {fake}"]


def both(pair: tuple[Harness, FakeCubase, JsonObject], op: str, params: JsonObject) -> tuple[JsonObject, JsonObject]:
    harness, fake, ids = pair
    script_params = {k: ids["script"] if v == "AUDIO" else v for k, v in params.items()}
    fake_params = {k: ids["fake"] if v == "AUDIO" else v for k, v in params.items()}
    answer = harness.call(op, script_params)
    script = answer["r"] if answer["ok"] else {"error": answer["err"]["code"]}
    try:
        simulated = fake.call(op, fake_params)
    except TrackwrightError as exc:
        simulated = {"error": exc.code}
    return script, simulated


OPERATIONS: list[tuple[str, JsonObject]] = [
    ("hello", {}),
    ("status", {}),
    ("capabilities", {}),
    ("transport.get", {}),
    ("cmd.list", {}),
    ("auto.list", {}),
    ("da.base", {"scope": "mixer"}),
    ("da.channels", {"scope": "mixer", "limit": 4}),
    ("da.channels", {"scope": "mixer", "limit": 4, "tags": [1024, 9999]}),
    ("da.children", {"id": "AUDIO", "scope": "mixer"}),
    ("da.children", {"id": "AUDIO", "scope": "mixer", "limit": 0}),
    ("da.object", {"id": "AUDIO", "scope": "mixer"}),
    ("da.params", {"id": "AUDIO", "scope": "mixer", "limit": 3}),
    ("da.param.get", {"id": "AUDIO", "tag": 1027, "scope": "mixer"}),
    ("da.param.set", {"id": "AUDIO", "tag": 1027, "value": 1, "scope": "mixer"}),
    ("da.param.set", {"id": "AUDIO", "tag": 1027, "value": 0, "scope": "mixer"}),
    ("cmd.canPerform", {"key": "edit.undo"}),
]


@pytest.mark.parametrize(("op", "params"), OPERATIONS, ids=[f"{o}{sorted(p)}" for o, p in OPERATIONS])
def test_same_shape(pair: tuple[Harness, FakeCubase, JsonObject], op: str, params: JsonObject) -> None:
    script, simulated = both(pair, op, params)
    assert differences(shape(script), shape(simulated)) == []


@pytest.mark.parametrize(
    ("op", "params"),
    [
        ("da.param.set", {"id": "AUDIO", "tag": 1027, "value": 2, "scope": "mixer"}),
        ("da.param.get", {"id": 999999, "tag": 1027, "scope": "mixer"}),
        ("da.channels", {"scope": "mixer", "tags": list(range(1000, 1017))}),
        ("nope.op", {}),
    ],
)
def test_same_errors(pair: tuple[Harness, FakeCubase, JsonObject], op: str, params: JsonObject) -> None:
    script, simulated = both(pair, op, params)
    assert "error" in script
    assert simulated.get("error") == script["error"]


def test_limits_are_clamped_alike(pair: tuple[Harness, FakeCubase, JsonObject]) -> None:
    """Verified in Cubase (2026-11-14): limit 0 returns one item."""
    script, simulated = both(pair, "da.children", {"id": "AUDIO", "scope": "mixer", "limit": 0})
    assert len(script["items"]) == len(simulated["items"]) == 1


def test_a_missing_tag_reads_alike(pair: tuple[Harness, FakeCubase, JsonObject]) -> None:
    script, simulated = both(pair, "da.channels", {"scope": "mixer", "limit": 2, "tags": [9999]})
    assert script["items"][0]["values"]["9999"]["process"] == simulated["items"][0]["values"]["9999"]["process"] == -1


# ---------------------------------------------------------------- lists copied between the three sides
def script_text() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_automation_keys_match() -> None:
    assert list(FakeCubase.AUTO_KEYS) == list(EXPECTED_KEYS)


def test_default_channel_tags_match() -> None:
    match = re.search(r"var tags = \(p\.tags && p\.tags\.length\) \? p\.tags : \[([\d, ]+)\]", script_text())
    assert match is not None
    script_tags = [int(t) for t in match.group(1).split(",")]
    assert script_tags == list(CHANNEL_TAGS)
    assert FakeCubase().call("da.channels", {"scope": "mixer", "limit": 1})["items"][0]["values"].keys() == {
        str(t) for t in CHANNEL_TAGS
    }


def test_every_operation_has_a_simulator_handler() -> None:
    fake = FakeCubase()
    missing = [op for op in sorted(ALL_OPS) if not hasattr(fake, "_op_" + op.replace(".", "_"))]
    assert missing == []
