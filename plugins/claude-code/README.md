# Trackwright plugin for Claude Code

**English** · [Español](README.es.md)

Producer skills for Cubase, on top of the [Trackwright](../../README.md) MCP server. The plugin starts the server itself (`uvx trackwright==<version> serve`), so the server and the skills always come in matching versions.

> **Status:** in development (epic E15). The skills arrive with TW-1506 and TW-1507; the first release that includes the plugin will be the next Trackwright version after 0.4.0.

## Installing

1. **Cubase side, once:** install the MIDI Remote script and create the configuration with `uvx trackwright setup`. When it offers to register the MCP server in Claude Code, answer **no**: the plugin does it.
2. **In Claude Code:**
   ```text
   /plugin marketplace add impalah/trackwright
   /plugin install trackwright@trackwright
   ```
   The same works in Claude Code's VS Code extension (`/plugins`).

Audio analysis needs `[analysis] enabled = true` in `~/.config/trackwright/config.toml`; writes need `[writes] enabled = true` (see the [configuration chapter](../../docs/manual/03-configuration.md)).

## If you registered the server by hand before

With `claude mcp add trackwright …` (or `trackwright setup`) **and** the plugin, Claude Code runs two Trackwright servers with the same tools. Both share the bridge, but the duplicated tools confuse the model. Keep only the plugin:

```sh
claude mcp remove trackwright --scope user
```

Trackwright cannot detect this by itself: Claude Code does not document where installed plugins are recorded.

## Versions

The plugin version is the package version, and `.mcp.json` pins `trackwright==<that version>` (unless `TRACKWRIGHT_FROM` is set, see below); `tests/unit/test_plugin.py` checks it. An older server than the one that wrote your configuration refuses it (unknown sections are errors, to catch typos), so do not pin a different version by hand.

## Skills

Each skill in `skills/` uses only the fields of the open [Agent Skills](https://agentskills.io) standard and names tools by their short name (`cubase_edit_range`). The tests check that every tool a skill names exists in the server.

## Development

`TRACKWRIGHT_FROM` makes the plugin start the server from another source (a checkout, a wheel) instead of the pinned version; it is meant only for development.

```sh
TRACKWRIGHT_FROM=$PWD claude --plugin-dir plugins/claude-code   # try it with the server of this checkout
claude plugin validate plugins/claude-code --strict
claude plugin validate . --strict              # the marketplace
```
