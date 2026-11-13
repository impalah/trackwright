"""TW-0905: the user documentation covers every tool, command and configuration key."""

from __future__ import annotations

from pathlib import Path

import pytest

from trackwright.commands import COMMANDS
from trackwright.config import Settings
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.fake import FakeCubase
from trackwright.server import build_server

DOCS = Path(__file__).resolve().parents[2] / "docs"
TOOLS_DOC = (DOCS / "manual" / "04-herramientas.md").read_text(encoding="utf-8")
CONFIG_DOC = (DOCS / "manual" / "03-configuracion.md").read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_every_tool_is_documented() -> None:
    server = build_server(CubaseService(FakeCubase(), WritePolicy()))
    names = {tool.name for tool in await server.list_tools()}
    assert len(names) == 27
    missing = sorted(n for n in names if f"### `{n}`" not in TOOLS_DOC)
    assert missing == []


def test_every_command_key_is_documented() -> None:
    assert sorted(k for k in COMMANDS if f"`{k}`" not in TOOLS_DOC) == []


def test_every_configuration_key_is_documented() -> None:
    missing = []
    for section_name, field in Settings.model_fields.items():
        if section_name == "source":
            continue
        assert f"## `[{section_name}]`" in CONFIG_DOC, section_name
        model = field.annotation
        assert model is not None
        for key in model.model_fields:  # type: ignore[union-attr]
            if f"`{key}`" not in CONFIG_DOC:
                missing.append(f"{section_name}.{key}")
    assert missing == []


def test_relative_links_resolve() -> None:
    import re

    root = DOCS.parent
    broken = []
    for page in [root / "README.md", *DOCS.rglob("*.md")]:
        for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", page.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (page.parent / target).resolve().exists():
                broken.append(f"{page.relative_to(root)} -> {target}")
    assert broken == []
