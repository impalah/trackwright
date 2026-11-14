"""TW-0401 (simulator, host port), TW-0402 (selectors, references) and TW-0403 (policy)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from trackwright.bridge import BridgeClient
from trackwright.commands import COMMANDS
from trackwright.config import WritesConfig
from trackwright.core.policy import WritePolicy
from trackwright.core.refs import ObjectRef, TrackSelector
from trackwright.errors import (
    HostError,
    PolicyError,
    ProtocolError,
    RequestTimeoutError,
    StaleReferenceError,
    StaleSessionError,
    TrackwrightError,
)
from trackwright.fake import FakeCubase
from trackwright.hostport import BridgeHost

JsonObject = dict[str, Any]


# ---------------------------------------------------------------- selectors
@pytest.mark.parametrize(
    ("text", "kind", "value"),
    [
        (None, "selected", ""),
        ("", "selected", ""),
        ("selected", "selected", ""),
        ("uid:ABC", "uid", "ABC"),
        ("name:selected", "name", "selected"),
        ("POC-TEST", "name", "POC-TEST"),
        ("uid:", "name", "uid:"),
    ],
)
def test_track_selector_parse(text: str | None, kind: str, value: str) -> None:
    selector = TrackSelector.parse(text)
    assert (selector.kind, selector.value) == (kind, value)


def test_track_selector_str() -> None:
    assert str(TrackSelector.parse("uid:X")) == "uid:X"
    assert str(TrackSelector.parse(None)) == "selected"


# ---------------------------------------------------------------- references
def test_object_ref_roundtrip() -> None:
    ref = ObjectRef("sess", 588, "Plugin", "946051208E29496E804F64A825C8A047-0")
    text = ref.encode()
    assert text.startswith("tw1.")
    assert ObjectRef.decode(text) == ref


@pytest.mark.parametrize("text", ["588", "tw1.!!!", "tw1." + "e30"])
def test_object_ref_rejects_garbage(text: str) -> None:
    with pytest.raises(ProtocolError):
        ObjectRef.decode(text)


def test_object_ref_checks() -> None:
    ref = ObjectRef("s1", 10, "Plugin", "UID-0")
    ref.check_session("s1")
    ref.check_fingerprint({"type": "Plugin", "uniqueName": "UID-0"})
    with pytest.raises(StaleReferenceError, match="previous"):
        ref.check_session("s2")
    with pytest.raises(StaleReferenceError, match="previous"):
        ref.check_session(None)
    with pytest.raises(StaleReferenceError, match="different object"):
        ref.check_fingerprint({"type": "InputFilter", "uniqueName": "InputFilter"})


# ---------------------------------------------------------------- policy
def test_policy_defaults_disable_writes() -> None:
    policy = WritePolicy.from_config(WritesConfig())
    with pytest.raises(PolicyError) as exc:
        policy.check_project_write()
    assert exc.value.code == "WRITES_DISABLED"
    with pytest.raises(PolicyError):
        policy.check_track("POC-TEST")


def test_policy_allowed_tracks() -> None:
    policy = WritePolicy(enabled=True, allowed_tracks=("POC-TEST",))
    policy.check_track("POC-TEST")
    with pytest.raises(PolicyError) as exc:
        policy.check_track("Vocals")
    assert exc.value.code == "NOT_ALLOWED"
    assert policy.describe() == {"writes_enabled": True, "allowed_tracks": ["POC-TEST"], "save": False}


def test_policy_enabled_without_list_allows_all() -> None:
    WritePolicy(enabled=True).check_track("anything")


# ---------------------------------------------------------------- simulator (TW-0401)
def test_fake_reproduces_the_duplicated_last_mixer_child() -> None:
    fake = FakeCubase()
    result = fake.call("da.channels", {"scope": "mixer"})
    assert [i["title"] for i in result["items"]] == ["Stereo Out", "POC-INSTR", "POC-TEST"]
    assert result["duplicates"] == [{"index": 3, "id": fake.channel_by_title("POC-TEST").id}]
    assert fake.simulated is True
    assert fake.call("capabilities")["capabilities"]["simulated"] is True


def test_fake_reload_reuses_ids_for_other_objects() -> None:
    fake = FakeCubase()
    old_session = fake.session_id
    audio = fake.channel_by_title("POC-TEST")
    old_id = audio.id
    fake.reload_script()
    assert fake.session_id != old_session
    assert fake.call("da.object", {"id": old_id})["title"] != "POC-TEST"


def test_fake_removed_objects_are_invalid() -> None:
    fake = FakeCubase()
    instr = fake.channel_by_title("POC-INSTR").id
    fake.remove(instr)
    with pytest.raises(HostError) as exc:
        fake.call("da.object", {"id": instr})
    assert exc.value.code == "INVALID_OBJECT"
    assert fake.call("events")["events"][0]["k"] == "mix.removed"


def test_fake_refuses_out_of_range_and_routing_by_name() -> None:
    fake = FakeCubase()
    audio = fake.channel_by_title("POC-TEST").id
    with pytest.raises(HostError, match=r"\[0,1\]"):
        fake.call("da.param.set", {"id": audio, "tag": 4102, "value": 22})
    result = fake.call("da.param.setDisplay", {"id": audio, "tag": 4102, "value": "Group 01"})
    assert result["after"]["display"] == "Stereo Out"


def test_fake_stale_session_and_unknown_op() -> None:
    fake = FakeCubase()
    with pytest.raises(StaleSessionError):
        fake.request_with_session("status", "old")
    assert fake.request_with_session("ping", "old")["pong"] is True
    with pytest.raises(HostError) as exc:
        fake.call("nope")
    assert exc.value.code == "UNKNOWN_OP"


def test_fake_bad_arguments() -> None:
    fake = FakeCubase()
    for op, params in [
        ("da.object", {}),
        ("da.object", {"id": "x"}),
        ("da.param.setDisplay", {"id": fake.mixer.id, "tag": 1024, "value": 3}),
        ("pm.set", {"slot": fake.mixer.id}),
        ("sel.step", {"direction": "up"}),
        ("transport.setTime", {"which": "x", "time": "1. 1. 1. 0"}),
        ("transport.setTime", {"which": "locator", "display": "x", "time": "1. 1. 1. 0"}),
        ("transport.setTime", {"which": "locator", "display": "primary", "time": ""}),
        ("transport.setTempo", {"bpm": 5}),
        ("cmd.run", {"key": "nope"}),
        ("pm.entries", {"slot": fake.mixer.id, "collection": 0}),
    ]:
        with pytest.raises(HostError):
            fake.call(op, params)


def test_fake_misc_reads() -> None:
    fake = FakeCubase()
    assert fake.call("ping", {"echo": "x"})["echo"] == "x"
    assert fake.call("status")["simulated"] is True
    assert fake.call("hello")["sessionId"] == fake.session_id
    assert fake.call("da.base", {"scope": "mixer"})["object"]["type"] == "VST Mixer"
    assert len(fake.call("cmd.list")["commands"]) == len(COMMANDS)
    fake.selected = -1
    assert fake.call("da.base") == {"base": -1}
    assert fake.call("da.channels") == {"base": -1, "total": 0, "items": [], "duplicates": []}
    missing = fake.call("da.param.get", {"id": fake.mixer.id, "tag": 9999})
    assert missing["process"] == -1


def test_fake_failure_injection() -> None:
    fake = FakeCubase()
    fake.fail_next["ping"] = RequestTimeoutError("late", outcome_unknown=False)
    with pytest.raises(RequestTimeoutError):
        fake.call("ping")
    assert fake.call("ping")["pong"] is True


# ---------------------------------------------------------------- BridgeHost
class _Client(BridgeClient):
    def __init__(self, responses: list[JsonObject]) -> None:
        super().__init__(Path("/nowhere"))
        self.responses = responses
        self.timeouts: list[float] = []

    def request(
        self, op: str, params: JsonObject | None = None, *, timeout: float = 3.0, session: str | None = None
    ) -> JsonObject:
        self.timeouts.append(timeout)
        return self.responses.pop(0)


def test_bridge_host_tracks_session_and_timeouts() -> None:
    client = _Client(
        [
            {"ok": True, "result": {"a": 1}, "meta": {"session_id": "s9"}},
            {"ok": True, "result": [1], "meta": {}},
            {"ok": False, "error": {"code": "INVALID_OBJECT", "message": "gone"}},
            {"ok": False, "error": "weird"},
        ]
    )
    host = BridgeHost(client, read_timeout=1.0, write_timeout=4.0)
    assert host.simulated is False
    assert host.call("da.object", {"id": 1}) == {"a": 1}
    assert host.session_id == "s9"
    assert host.call("da.param.set", {}) == {}
    with pytest.raises(TrackwrightError, match="gone") as gone:
        host.call("da.object")
    assert gone.value.code == "INVALID_OBJECT"
    with pytest.raises(TrackwrightError) as weird:
        host.call("ping")
    assert weird.value.code == "BRIDGE_ERROR"
    assert client.timeouts == [1.0, 4.0, 1.0, 1.0]
