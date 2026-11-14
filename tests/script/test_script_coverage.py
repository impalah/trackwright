"""S-13: script behaviours that had no Node test: reads that only the simulator exercised, protocol errors,
the request queue and the reassembly of incoming fragments."""

from __future__ import annotations

from typing import Any

import pytest

from tests.script.node_harness import Harness
from trackwright import protocol

pytestmark = pytest.mark.node
JsonObject = dict[str, Any]


def audio(h: Harness) -> int:
    return int(h.step(state=True)["state"]["ids"]["audio"])


def status(h: Harness) -> JsonObject:
    result: JsonObject = h.call("status")["r"]
    return result


# ---------------------------------------------------------------- reads
def test_params_are_paged(h: Harness) -> None:
    first = h.call("da.params", {"id": audio(h), "limit": 2, "scope": "mixer"})["r"]
    assert len(first["items"]) == 2
    assert first["total"] > 2
    rest = h.call("da.params", {"id": audio(h), "offset": 2, "limit": 25, "scope": "mixer"})["r"]
    assert {p["tag"] for p in first["items"]}.isdisjoint({p["tag"] for p in rest["items"]})


def test_param_get_and_invalid_objects(h: Harness) -> None:
    mute = h.call("da.param.get", {"id": audio(h), "tag": 1027, "scope": "mixer"})["r"]
    assert (mute["title"], mute["process"]) == ("Enmudecer", 0)
    assert h.call("da.param.get", {"id": 999999, "tag": 1027, "scope": "mixer"})["err"]["code"] == "INVALID_OBJECT"


def test_convert_both_ways(h: Harness) -> None:
    out = h.call("da.convert", {"id": audio(h), "tag": 1025, "process": 0.5, "plain": 0, "scope": "mixer"})["r"]
    assert out["plainFromProcess"] == pytest.approx(0.0)
    assert out["processFromPlain"] == pytest.approx(0.5)


def test_plugin_collections(h: Harness) -> None:
    channel = h.call("da.children", {"id": audio(h), "scope": "mixer"})["r"]["items"][0]
    slot = h.call("da.children", {"id": channel["id"], "scope": "mixer"})["r"]["items"][0]
    collections = h.call("pm.collections", {"slot": slot["id"]})["r"]
    assert collections["total"] == 1


def test_write_preconditions_on_the_title(h: Harness) -> None:
    resp = h.call("da.param.set", {"id": audio(h), "tag": 1027, "value": 1, "expectTitle": "Solo", "scope": "mixer"})
    assert resp["err"]["code"] == "PRECONDITION_FAILED"
    assert h.call("da.param.get", {"id": audio(h), "tag": 1027, "scope": "mixer"})["r"]["process"] == 0


# ---------------------------------------------------------------- protocol errors
def test_invalid_json_is_answered(h: Harness) -> None:
    replies = h.decode(h.step(frames=protocol.build_frames(b"{not json", 900))["sent"])
    assert [(r["rid"], r["err"]["code"]) for r in replies] == [("", "BAD_REQUEST")]


def test_another_protocol_version_is_refused(h: Harness) -> None:
    request = {"v": 99, "rid": "r-v99", "op": "ping", "sid": h.sid}
    replies = h.decode(h.step(frames=protocol.build_frames(protocol.encode_payload(request), 901))["sent"])
    assert [(r["rid"], r["err"]["code"]) for r in replies] == [("r-v99", "PROTOCOL_MISMATCH")]


def test_a_request_in_several_fragments(h: Harness) -> None:
    echo = "x" * 1000  # more than four fragments of 240 bytes
    frames = h.frames_for("ping", {"echo": echo})
    assert len(frames) > 4
    replies = h.decode(h.step(frames=frames)["sent"])
    assert replies[0]["r"]["echo"] == echo


def test_malformed_frames_are_counted(h: Harness) -> None:
    before = status(h)["framesRejected"]
    h.step(frames=[[0x7D, 0x54, 0x57, 9, 0, 1, 0, 1]])  # unknown protocol version in the frame header
    assert status(h)["framesRejected"] == before + 1


def test_an_incomplete_request_expires(h: Harness) -> None:
    """1.6.0 (S-08): after ~50 idle ticks a missing fragment no longer holds a slot."""
    frames = h.frames_for("ping", {"echo": "y" * 600})
    h.step(frames=frames[:1])
    assert status(h)["pendingAssemblies"] == 1
    h.step(idle=60)
    after = status(h)
    assert after["pendingAssemblies"] == 0
    assert after["framesRejected"] >= 1


# ---------------------------------------------------------------- the idle queue
def test_queue_full_is_busy_and_ops_per_tick_are_bounded(h: Harness) -> None:
    frames = []
    for _ in range(33):  # MAX_QUEUE is 32
        frames += h.frames_for("da.base", {"scope": "mixer"})
    busy = h.decode(h.step(frames=frames)["sent"])
    assert [r["err"]["code"] for r in busy] == ["BUSY"]
    first_tick = h.decode(h.step(idle=1)["sent"])
    assert len(first_tick) == 4  # MAX_OPS_PER_IDLE
    answered = len(first_tick)
    while answered < 32:
        answered += len(h.decode(h.step(idle=1)["sent"]))
    assert answered == 32
