"""TW-1505: the Claude Code plugin and its marketplace stay consistent with the package and the server.

- plugin.json, marketplace.json and .mcp.json agree on the name and on the package version;
- every skill uses only the fields of the Agent Skills standard (so it can be tried in other clients), has a
  valid name equal to its folder, and names only tools that the server registers.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "claude-code"
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
SERVER_TOOLS = set(re.findall(r"async def (cubase_\w+)\(", (ROOT / "src/trackwright/server.py").read_text()))
STANDARD_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
SKILL_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TOOL = re.compile(r"\bcubase_[a-z_]+\b")


def load(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def frontmatter(text: str) -> dict[str, str]:
    """Top-level keys of a SKILL.md YAML frontmatter (nested lines belong to the key above)."""
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if match is None:
        raise AssertionError("SKILL.md must start with a --- frontmatter block")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if line and not line[0].isspace() and ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip().strip('"')
    return fields


def skill_problems(folder: Path) -> list[str]:
    """Everything wrong with one skill folder; empty when it is fine."""
    problems: list[str] = []
    skill = folder / "SKILL.md"
    if not skill.is_file():
        return [f"{folder.name}: no SKILL.md"]
    fields = frontmatter(skill.read_text(encoding="utf-8"))
    problems += [f"{folder.name}: non-standard field {key!r}" for key in sorted(set(fields) - STANDARD_FIELDS)]
    name = fields.get("name", "")
    if name != folder.name or not SKILL_NAME.match(name) or len(name) > 64:
        problems.append(f"{folder.name}: name {name!r} must be lowercase-hyphenated and equal the folder")
    if not 1 <= len(fields.get("description", "")) <= 1024:
        problems.append(f"{folder.name}: description must have 1 to 1024 characters")
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix in {".md", ".txt", ".json"}):
        for tool in sorted(set(TOOL.findall(path.read_text(encoding="utf-8"))) - SERVER_TOOLS):
            problems.append(f"{folder.name}: {path.name} names {tool}, which the server does not register")
    return problems


def test_manifest_matches_the_package() -> None:
    manifest = load(PLUGIN / ".claude-plugin" / "plugin.json")
    assert manifest["name"] == "trackwright"
    assert manifest["version"] == VERSION
    assert manifest["license"] == "AGPL-3.0-or-later"


def test_the_server_is_pinned_to_the_package_version() -> None:
    """The plugin starts exactly the server version its skills were written for (an older one would also
    refuse a configuration written for a newer one: unknown sections are errors)."""
    server = load(PLUGIN / ".mcp.json")["mcpServers"]["trackwright"]  # type: ignore[index]
    # TRACKWRIGHT_FROM (development only) points uvx at a checkout instead: see the plugin README
    assert server == {
        "command": "uvx",
        "args": ["--from", f"${{TRACKWRIGHT_FROM:-trackwright=={VERSION}}}", "trackwright", "serve"],
    }


def test_marketplace_points_at_the_plugin() -> None:
    market = load(ROOT / ".claude-plugin" / "marketplace.json")
    entries = market["plugins"]
    assert isinstance(entries, list)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["name"] == load(PLUGIN / ".claude-plugin" / "plugin.json")["name"]
    assert ".." not in entry["source"]
    assert (ROOT / entry["source"]).resolve() == PLUGIN


def test_every_skill_is_standard_and_names_real_tools() -> None:
    folders = sorted(p for p in (PLUGIN / "skills").iterdir() if p.is_dir())
    assert [problem for folder in folders for problem in skill_problems(folder)] == []


@pytest.mark.parametrize(
    ("front", "body", "expected"),
    [
        ("name: demo\ndescription: Does a thing.", "Use cubase_status.", []),
        ("name: demo\ndescription: x\nwhen_to_use: always", "", ["non-standard field 'when_to_use'"]),
        ("name: Demo_Skill\ndescription: x", "", ["must be lowercase-hyphenated"]),
        ("name: other\ndescription: x", "", ["must be lowercase-hyphenated and equal the folder"]),
        ("name: demo\ndescription: ", "", ["description must have"]),
        ("name: demo\ndescription: x", "Call cubase_remove_selected_tracks.", ["does not register"]),
        ("name: demo\ndescription: x\nmetadata:\n  author: impalah", "", []),
    ],
)
def test_the_skill_checker(tmp_path: Path, front: str, body: str, expected: list[str]) -> None:
    folder = tmp_path / "demo"
    folder.mkdir()
    (folder / "SKILL.md").write_text(f"---\n{front}\n---\n\n{body}\n", encoding="utf-8")
    problems = skill_problems(folder)
    assert len(problems) == len(expected)
    for problem, fragment in zip(problems, expected, strict=True):
        assert fragment in problem


def test_a_skill_without_skill_md(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    assert skill_problems(tmp_path / "empty") == ["empty: no SKILL.md"]
    with pytest.raises(AssertionError):
        frontmatter("no frontmatter")
