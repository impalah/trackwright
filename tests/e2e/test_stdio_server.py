"""End-to-end: start the real ``trackwright serve --simulate`` process and talk MCP over stdio.

Proves that the executable starts, that logs never pollute stdout (which carries the protocol)
and that tool calls round-trip through a real process boundary.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

pytestmark = pytest.mark.anyio


async def test_serve_simulate_over_stdio(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[writes]\nenabled = true\n\n[logging]\nlevel = "DEBUG"\n', encoding="utf-8")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "trackwright", "--config", str(config), "serve", "--simulate"],
    )
    async with Client(params) as client:
        tools = await client.list_tools()
        assert len(tools.tools) == 29
        status = await client.call_tool("cubase_status", {})
        assert not status.is_error
        assert isinstance(status.structured_content, dict)
        assert status.structured_content["simulated"] is True
        assert status.structured_content["writes_enabled"] is True
        renamed = await client.call_tool(
            "cubase_rename_track", {"track": "POC-INSTR", "new_name": "Keys", "dry_run": False}
        )
        assert isinstance(renamed.structured_content, dict)
        assert renamed.structured_content["verified"] is True
        failed = await client.call_tool("cubase_list_inserts", {"track": "Missing"})
        assert failed.is_error
