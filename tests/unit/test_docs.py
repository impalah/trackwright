"""TW-0905: the user documentation covers every tool, command and configuration key."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from trackwright.commands import COMMANDS
from trackwright.config import Settings
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.fake import FakeCubase
from trackwright.server import build_server

DOCS = Path(__file__).resolve().parents[2] / "docs"
TOOLS_DOC = (DOCS / "manual" / "04-tools.md").read_text(encoding="utf-8")
CONFIG_DOC = (DOCS / "manual" / "03-configuration.md").read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_every_tool_is_documented() -> None:
    server = build_server(CubaseService(FakeCubase(), WritePolicy()))
    names = {tool.name for tool in await server.list_tools()}
    assert len(names) == 32
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


ROOT = DOCS.parent
LINK = re.compile(r"\]\(([^)\s]+)\)")
EXTERNAL = ("http://", "https://", "mailto:")


def doc_pages() -> list[Path]:
    """Every Markdown document of the project (English ``X.md`` and Spanish ``X.es.md``)."""
    pages = [ROOT / "README.md", ROOT / "README.es.md", ROOT / "CHANGELOG.md", ROOT / "CHANGELOG.es.md"]
    pages += sorted(DOCS.rglob("*.md")) + sorted((ROOT / "experiments").rglob("*.md"))
    return pages


def is_spanish(page: Path) -> bool:
    return page.name.endswith(".es.md")


def counterpart(page: Path) -> Path:
    if is_spanish(page):
        return page.with_name(page.name.removesuffix(".es.md") + ".md")
    return page.with_name(page.name.removesuffix(".md") + ".es.md")


def anchors(page: Path) -> set[str]:
    """GitHub heading anchors of ``page`` (headings inside code blocks do not count)."""
    found: set[str] = set()
    fenced = False
    for line in page.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        match = re.match(r"#{1,6} +(.*?) *#*$", line)
        if fenced or not match:
            continue
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", match.group(1)).lower()
        slug = re.sub(r"[^\w\- ]", "", text).replace(" ", "-")
        candidate, n = slug, 0
        while candidate in found:
            n += 1
            candidate = f"{slug}-{n}"
        found.add(candidate)
    return found


def test_every_document_has_its_translation() -> None:
    missing = [str(p.relative_to(ROOT)) for p in doc_pages() if p.exists() and not counterpart(p).exists()]
    assert missing == []


def test_every_document_links_to_its_translation() -> None:
    missing = []
    for page in doc_pages():
        head = "\n".join(page.read_text(encoding="utf-8").splitlines()[:4])
        name = counterpart(page).name
        linked = f"]({name})" in head
        if not linked and not (page == ROOT / "README.md" and f"`{name}`" in head):  # PyPI page: no relative links
            missing.append(str(page.relative_to(ROOT)))
    assert missing == []


def test_links_resolve_and_stay_in_their_language() -> None:
    broken = []
    for page in doc_pages():
        for link in LINK.findall(page.read_text(encoding="utf-8")):
            if link.startswith(EXTERNAL):
                continue
            target, _, anchor = link.partition("#")
            path = (page.parent / target).resolve() if target else page
            where = f"{page.relative_to(ROOT)} -> {link}"
            if not path.exists():
                broken.append(f"missing: {where}")
                continue
            switches_language = path.suffix == ".md" and is_spanish(page) != is_spanish(path)
            if switches_language and path != counterpart(page).resolve() and counterpart(path).exists():
                broken.append(f"other language: {where}")
            if anchor and path.suffix == ".md" and anchor not in anchors(path):
                broken.append(f"anchor: {where}")
    assert broken == []
