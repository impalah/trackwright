"""MCP contract tests (TW-0902): an in-memory MCP client against the real server and the simulator."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from mcp.client import Client

from trackwright import SERVER_NAME
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.fake import FakeCubase
from trackwright.server import build_server

pytestmark = pytest.mark.anyio

READ_TOOLS = {
    "cubase_status",
    "cubase_list_tracks",
    "cubase_get_selected_channel",
    "cubase_list_inserts",
    "cubase_list_available_plugins",
    "cubase_list_parameters",
    "cubase_get_parameter",
    "cubase_get_transport",
    "cubase_poll_changes",
}
WRITE_TOOLS = {
    "cubase_set_parameter",
    "cubase_insert_plugin",
    "cubase_set_track_mix",
    "cubase_rename_track",
    "cubase_set_tempo",
    "cubase_markers",
    "cubase_add_track_interactive",
    "cubase_record_automation",
}
NAVIGATION_TOOLS = {
    "cubase_select_track",
    "cubase_set_position",
    "cubase_list_automation_targets",
    "cubase_convert_value",
}
DESTRUCTIVE_TOOLS = {"cubase_remove_selected_tracks", "cubase_split_at_locators", "cubase_run_command"}
ALL_TOOLS = READ_TOOLS | WRITE_TOOLS | NAVIGATION_TOOLS | DESTRUCTIVE_TOOLS
STUDIO_EQ = "946051208E29496E804F64A825C8A047"


@pytest.fixture
def fake() -> FakeCubase:
    return FakeCubase()


@pytest.fixture
async def client(fake: FakeCubase) -> AsyncIterator[Client]:
    service = CubaseService(fake, WritePolicy(enabled=True), sleep=lambda _s: None, settle_timeout=0.0)
    async with Client(build_server(service)) as connected:
        yield connected


async def call(client: Client, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    result = await client.call_tool(name, args or {})
    assert not result.is_error, [getattr(b, "text", b) for b in result.content]
    assert isinstance(result.structured_content, dict)
    return result.structured_content


async def call_error(client: Client, name: str, args: dict[str, Any]) -> str:
    result = await client.call_tool(name, args)
    assert result.is_error
    return " ".join(getattr(b, "text", "") for b in result.content)


async def test_tool_list_and_annotations(client: Client) -> None:
    tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == ALL_TOOLS
    for name, tool in tools.items():
        assert tool.description, name
        assert tool.output_schema is not None, name
        assert tool.annotations is not None, name
        assert tool.annotations.read_only_hint is (name in READ_TOOLS), name
        assert tool.annotations.destructive_hint is (name in DESTRUCTIVE_TOOLS), name
    for name in (WRITE_TOOLS | DESTRUCTIVE_TOOLS) - {"cubase_add_track_interactive"}:
        schema = tools[name].input_schema
        assert schema["properties"]["dry_run"]["default"] is True, name


async def test_server_identity(client: Client) -> None:
    status = await call(client, "cubase_status")
    assert status["simulated"] is True
    assert SERVER_NAME == "trackwright"


async def test_read_tools(client: Client) -> None:
    tracks = await call(client, "cubase_list_tracks")
    assert [t["name"] for t in tracks["tracks"]] == ["Stereo Out", "POC-INSTR", "POC-TEST"]
    uid_selector = tracks["tracks"][1]["track"]
    assert (await call(client, "cubase_list_inserts", {"track": uid_selector}))["track"]["name"] == "POC-INSTR"
    assert (await call(client, "cubase_get_selected_channel"))["track"]["name"] == "POC-TEST"
    catalog = await call(client, "cubase_list_available_plugins", {"filter": "eq"})
    assert catalog["items"][0]["uid"] == STUDIO_EQ
    params = await call(client, "cubase_list_parameters", {"target": "channel", "filter": "vol"})
    assert params["items"][0]["tag"] == 1025
    assert (await call(client, "cubase_get_parameter", {"target": "strip:eq", "tag": 4232}))["parameter"][
        "process"
    ] == 0.5
    assert (await call(client, "cubase_get_transport"))["tempo_bpm"] == 120
    assert (await call(client, "cubase_poll_changes"))["dropped"] == 0


async def test_write_flow_dry_run_then_apply(client: Client, fake: FakeCubase) -> None:
    plan = await call(client, "cubase_set_track_mix", {"track": "POC-INSTR", "mute": True})
    assert plan["dry_run"] is True
    assert fake.channel_by_title("POC-INSTR").params[1027].value == 0
    applied = await call(client, "cubase_set_track_mix", {"track": "POC-INSTR", "mute": True, "dry_run": False})
    assert applied["verified"] is True
    inserted = await call(client, "cubase_insert_plugin", {"slot": 1, "plugin_uid": STUDIO_EQ, "dry_run": False})
    assert inserted["verified"] is True
    eq = await call(
        client,
        "cubase_set_parameter",
        {"target": "insert:1", "tag": 4207, "value": 3, "unit": "plain", "dry_run": False},
    )
    assert eq["verified"] is True
    renamed = await call(client, "cubase_rename_track", {"track": "POC-INSTR", "new_name": "Keys", "dry_run": False})
    assert renamed["verified"] is True
    assert (await call(client, "cubase_select_track", {"track": "Keys"}))["selected_after"] == "Keys"
    assert (await call(client, "cubase_set_position", {"which": "cursor", "time": "2.1.1.0"}))["verified"] is True
    assert (await call(client, "cubase_set_tempo", {"bpm": 100, "dry_run": False}))["after"] == 100


async def test_command_tools(client: Client, fake: FakeCubase) -> None:
    assert (await call(client, "cubase_markers", {"action": "add_marker_track", "dry_run": False}))["status"] == "done"
    dialog = await call(
        client, "cubase_add_track_interactive", {"phase": "start", "kind": "audio", "suggested_name": "Vox"}
    )
    assert dialog["status"] == "awaiting_user"
    fake.complete_dialog("Vox")
    confirmed = await call(
        client, "cubase_add_track_interactive", {"phase": "confirm", "kind": "audio", "suggested_name": "Vox"}
    )
    assert confirmed["verified"] is True
    split = await call(client, "cubase_split_at_locators", {"left": "2.1.1.0", "right": "4.1.1.0", "dry_run": False})
    assert split["verified"] == "not_observable"
    removed = await call(client, "cubase_remove_selected_tracks", {"expect_selected": "Vox", "dry_run": False})
    assert removed["status"] == "done"
    run = await call(client, "cubase_run_command", {"key": "zoom.in"})
    assert run["status"] == "planned"


async def test_errors_are_readable_tool_errors(client: Client) -> None:
    assert "TRACK_NOT_FOUND" in await call_error(client, "cubase_list_inserts", {"track": "Nope"})
    assert "SELECTION_MISMATCH" in await call_error(
        client, "cubase_remove_selected_tracks", {"expect_selected": "POC-INSTR", "dry_run": False}
    )
    text = await call_error(client, "cubase_set_tempo", {"bpm": 500})
    assert "500" in text or "less than or equal" in text


async def test_writes_disabled_by_default() -> None:
    service = CubaseService(FakeCubase(), WritePolicy())
    async with Client(build_server(service)) as client:
        plan = await call(client, "cubase_set_track_mix", {"track": "POC-TEST", "solo": True})
        assert plan["dry_run"] is True
        text = await call_error(client, "cubase_set_track_mix", {"track": "POC-TEST", "solo": True, "dry_run": False})
        assert "WRITES_DISABLED" in text


async def test_automation_tools(client: Client, fake: FakeCubase) -> None:
    targets = await call(client, "cubase_list_automation_targets", {"track": "POC-TEST"})
    assert {t["parameter"] for t in targets["targets"]} >= {"volume", "pan", "insert1.p1"}
    plan = await call(
        client,
        "cubase_record_automation",
        {"track": "POC-TEST", "parameter": "volume", "points": [{"position": "2.1.1.0", "value": 0.7}]},
    )
    assert plan["dry_run"] is True
    done = await call(
        client,
        "cubase_record_automation",
        {
            "track": "POC-TEST",
            "parameter": "volume",
            "points": [{"position": "2.1.1.0", "value": 0.79}, {"position": "3.1.1.0", "value": 0.5}],
            "dry_run": False,
        },
    )
    assert done["verified"] is True
    assert "NOT_AUTOMATABLE" in await call_error(
        client,
        "cubase_record_automation",
        {"track": "POC-TEST", "parameter": "qc1", "points": [{"position": "2.1.1.0", "value": 0.5}], "dry_run": False},
    )


async def test_unit_conversion_tools(client: Client) -> None:
    out = await call(client, "cubase_convert_value", {"track": "POC-TEST", "parameter": "volume", "plain": -12})
    assert out["value"] == 0.25
    plan = await call(client, "cubase_record_automation", {"track": "POC-TEST", "parameter": "volume",
                      "points": [{"position": "2.1.1.0", "plain": 0}]})  # fmt: skip
    assert plan["points"][0] == {"position": "2.1.1.0", "value": 0.5, "plain": 0}
    assert "exactly one" in await call_error(client, "cubase_record_automation", {"track": "POC-TEST",
                                             "parameter": "volume", "points": [{"position": "2.1.1.0"}]})  # fmt: skip
