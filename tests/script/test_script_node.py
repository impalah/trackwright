"""Run the real MIDI Remote script under Node.js with an emulated Cubase API (TW-0302).

The frames are built and decoded by the Python protocol module, so these tests prove that the
Python side and the script speak the same wire format.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from tests.script.node_harness import NODE, Harness
from trackwright import ops
from trackwright.commands import COMMANDS
from trackwright.cubase import SCRIPT_PATH, SCRIPT_VERSION

pytestmark = pytest.mark.node
JsonObject = dict[str, Any]

if NODE is None:  # pragma: no cover - depends on the machine
    pytest.skip("node is not installed: the MIDI Remote script tests need Node.js", allow_module_level=True)


def ids(h: Harness) -> dict[str, int]:
    state: dict[str, int] = h.step(state=True)["state"]["ids"]
    return state


def test_script_ops_match_python_ops() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    idle = set(re.findall(r"^\t'([a-zA-Z.]+)': function", source, flags=re.MULTILINE))
    direct = set(re.findall(r"(\w+|'[\w.]+'): true", source.split("var DIRECT_OPS = ")[1].split("\n")[0]))
    direct = {d.strip("'") for d in direct}
    assert direct == ops.DIRECT_READ_OPS
    assert idle == ops.IDLE_READ_OPS | ops.WRITE_OPS


def test_hello_reports_identity(h: Harness) -> None:
    hello = h.call("hello")
    assert hello["r"]["scriptVersion"] == SCRIPT_VERSION
    assert hello["r"]["host"]["appName"] == "Cubase"
    assert hello["via"] == "sysex"


def test_ping_unicode(h: Harness) -> None:
    assert h.call("ping", {"echo": "hola-ñ-✓"})["r"]["echo"] == "hola-ñ-✓"


def test_capabilities(h: Harness) -> None:
    caps = h.call("capabilities")["r"]["capabilities"]
    assert caps["directAccessCreated"] is True
    assert caps["mixerDirectAccessCreated"] is True
    assert caps["commandErrors"] == 0
    assert caps["commandsBound"] == len(COMMANDS)  # T-09: every command of the table is bound


def test_channels_are_deduplicated(h: Harness) -> None:
    r = h.call("da.channels", {"scope": "mixer"})["r"]
    titles = [i["title"] for i in r["items"]]
    assert titles == ["Stereo Out", "POC-INSTR", "POC-TEST"]
    assert r["duplicates"] == [{"index": 3, "id": ids(h)["audio"]}]
    assert r["items"][2]["values"]["1024"]["display"] == "POC-TEST"


def test_param_write_and_read_back(h: Harness) -> None:
    instr = ids(h)["instr"]
    resp = h.call("da.param.set", {"id": instr, "tag": 1025, "value": 0.75, "scope": "mixer"})
    assert resp["ok"], resp
    assert resp["r"]["before"]["process"] == pytest.approx(0.7890865802764893)
    assert resp["r"]["after"]["process"] == 0.75
    assert resp["via"] == "idle"


def test_write_outside_unit_range_is_refused(h: Harness) -> None:
    resp = h.call("da.param.set", {"id": ids(h)["audio"], "tag": 4102, "value": 22, "scope": "mixer"})
    assert resp["err"]["code"] == "BAD_REQUEST"


def test_rename_by_display_value(h: Harness) -> None:
    instr = ids(h)["instr"]
    resp = h.call("da.param.setDisplay", {"id": instr, "tag": 1024, "value": "RENAMED", "scope": "mixer"})
    assert resp["r"]["after"]["display"] == "RENAMED"
    assert h.call("da.object", {"id": instr, "scope": "mixer"})["r"]["title"] == "RENAMED"


def test_invalid_object_after_removal(h: Harness) -> None:
    instr = ids(h)["instr"]
    h.step(remove=instr)
    resp = h.call("da.object", {"id": instr, "scope": "mixer"})
    assert resp["err"]["code"] == "INVALID_OBJECT"
    events = h.call("events")["r"]["events"]
    assert {"k": "mix.removed", "id": instr} in [{"k": e["k"], "id": e["id"]} for e in events]


def test_stale_session(h: Harness) -> None:
    assert h.call("status", sid="not-the-session")["err"]["code"] == "STALE_SESSION"


def test_duplicate_rid_sequential_is_cached(h: Harness) -> None:
    first = h.call("da.base", rid="dup-1")
    second = h.call("da.base", rid="dup-1")
    assert second["dup"] is True
    assert second["r"] == first["r"]


def test_duplicate_in_flight_is_dropped(h: Harness) -> None:
    frames = h.frames_for("da.base", rid="burst-1")
    assert h.step(frames=frames)["sent"] == []
    assert h.step(frames=frames)["sent"] == []  # second copy arrives while the first is queued
    replies = h.decode(h.step(idle=2)["sent"])
    assert len(replies) == 1
    assert h.call("status")["r"]["dupInFlightDropped"] == 1


def test_selection_by_parameter_and_action(h: Harness) -> None:
    instr = ids(h)["instr"]
    h.call("da.param.set", {"id": instr, "tag": 4000, "value": 1, "scope": "mixer"})
    assert h.call("da.base")["r"]["base"] == instr
    h.call("sel.step", {"direction": "next"})
    assert h.call("da.base")["r"]["base"] == ids(h)["audio"]
    assert h.call("sel.step", {"direction": "sideways"})["err"]["code"] == "BAD_REQUEST"


def test_transport_read_and_set(h: Harness) -> None:
    before = h.call("transport.get")["r"]
    assert before["primary"]["locator"]["time"] == "1. 1. 1.  0"
    assert before["tempoBPM"] == 120
    assert h.call("transport.setTime", {"which": "locator", "display": "primary", "time": "3. 1. 1.  0"})["ok"]
    assert h.call("transport.get")["r"]["primary"]["locator"]["time"] == "3. 1. 1.  0"
    assert h.call("transport.setTempo", {"bpm": 100})["ok"]
    assert h.call("transport.get")["r"]["tempoBPM"] == 100
    assert h.call("transport.setTempo", {"bpm": 999})["err"]["code"] == "BAD_REQUEST"


def test_commands(h: Harness) -> None:
    listed = {c["key"]: c for c in h.call("cmd.list")["r"]["commands"]}
    assert listed["addtrack.audio"]["category"] == "AddTrack"
    can = h.call("cmd.canPerform")["r"]["canPerform"]
    assert can["edit.undo"] is False
    assert h.call("cmd.run", {"key": "edit.undo"})["err"]["code"] == "CANNOT_PERFORM"
    assert h.call("cmd.run", {"key": "addtrack.marker"})["r"]["fired"] == 1
    assert "cmd_addtrack.marker" in h.step(state=True)["state"]["fired"]
    assert h.call("cmd.run", {"key": "nope"})["err"]["code"] == "NOT_FOUND"


def test_plugin_insert_flow(h: Harness) -> None:
    channels = h.call("da.channels", {"scope": "mixer"})["r"]["items"]
    audio = next(c for c in channels if c["title"] == "POC-TEST")
    inserts = h.call("da.children", {"id": audio["id"], "scope": "mixer"})["r"]["items"][0]
    slot = h.call("da.children", {"id": inserts["id"], "scope": "mixer"})["r"]["items"][0]
    assert slot["children"] == 0
    entries = h.call("pm.entries", {"slot": slot["id"], "collection": 0, "filter": "eq"})["r"]
    assert [e["name"] for e in entries["items"]] == ["StudioEQ"]
    resp = h.call("pm.set", {"slot": slot["id"], "uid": "946051208E29496E804F64A825C8A047"})
    assert resp["r"]["result"] is True
    assert resp["r"]["after"]["children"] == 1
    again = h.call("pm.set", {"slot": slot["id"], "uid": "946051208E29496E804F64A825C8A047"})
    assert again["err"]["code"] == "SLOT_NOT_EMPTY"


def test_write_guard_reports_only_the_base(h: Harness) -> None:
    """1.6.0 (S-01): no subtree walk; expectChannelTitle is gone (Trackwright never sent it)."""
    resp = h.call("da.param.set", {"id": ids(h)["instr"], "tag": 1027, "value": 1, "expectChannelTitle": "Other"})
    assert resp["ok"] is True
    assert set(resp["r"]["guard"]) == {"base", "baseTitle"}


def test_inherited_names_are_not_operations_or_commands(h: Harness) -> None:
    """1.6.0 (S-07): plain-object lookups no longer accept 'toString' or 'constructor'."""
    assert h.call("toString")["err"]["code"] == "UNKNOWN_OP"
    resp = h.call("cmd.run", {"key": "constructor"})
    assert resp["ok"] is False
    assert resp["err"]["code"] != "SCRIPT_ERROR"


def test_channel_listing_caps_the_tags(h: Harness) -> None:
    """1.6.0 (S-03)."""
    resp = h.call("da.channels", {"tags": list(range(1000, 1017)), "scope": "mixer"})
    assert resp["err"]["code"] == "BAD_REQUEST"
    assert h.call("da.channels", {"tags": list(range(1000, 1016)), "scope": "mixer"})["ok"] is True


def test_deactivation_answers_queued_requests(h: Harness) -> None:
    """1.6.0 (S-05): queued requests get NOT_ACTIVE instead of waiting for the caller's timeout."""
    h.call("hello")
    sent = h.step(frames=h.frames_for("da.base", {"scope": "mixer"}))["sent"]
    assert h.decode(sent) == []  # queued for the idle tick
    replies = h.decode(h.step(deactivate=True)["sent"])
    assert [(r["op"], r["err"]["code"]) for r in replies] == [("da.base", "NOT_ACTIVE")]
