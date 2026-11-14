# Trackwright

**English** · [Español](https://github.com/impalah/trackwright/blob/main/README.es.md)

[![PyPI version](https://badge.fury.io/py/trackwright.svg)](https://pypi.org/project/trackwright/)
[![CI](https://github.com/impalah/trackwright/actions/workflows/ci.yml/badge.svg)](https://github.com/impalah/trackwright/actions/workflows/ci.yml)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL v3+](https://img.shields.io/badge/License-AGPL%20v3%2B-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Coverage 98%](https://img.shields.io/badge/coverage-98%25-brightgreen.svg)](https://github.com/impalah/trackwright)
![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)
![DAW: Cubase 15.0.20+](https://img.shields.io/badge/DAW-Cubase%2015.0.20+-red.svg)
[![MCP](https://img.shields.io/badge/MCP-server-8A2BE2.svg)](https://modelcontextprotocol.io)

**Trackwright** is an independent [MCP](https://modelcontextprotocol.io) server for controlling digital audio workstations (DAWs).

It lets an AI assistant (Claude, GitHub Copilot or any other MCP client) **inspect and control your DAW**: tracks, mixing, plugins and their parameters, transport, markers, automation and time-range editing designed for podcasts.

The first implementation supports **Cubase**. It works through a MIDI Remote script that runs inside Cubase and needs no hardware controllers or IAC ports. Other DAWs may follow: much of the core (MIDI transport, bridge, write policy, verification by reading back) does not depend on Cubase.

| | |
|---|---|
| Package | `trackwright` |
| Executable | `trackwright` |
| MCP server | `trackwright` (stdio) |
| MCP clients | Any client that supports stdio servers. Tested with Claude Code |
| Platform | macOS. Verified on macOS 27.2 (Apple Silicon) |
| DAW | Cubase 15.0.20 or later (MIDI Remote API 1.3). Verified on Cubase Elements 15.0.30 |
| License | AGPL-3.0-or-later |

> Trackwright is an independent project. It is not affiliated with or endorsed by Steinberg; Cubase is a trademark of Steinberg Media Technologies GmbH.

## Requirements

- **[uv](https://docs.astral.sh/uv/)** 0.13 or later (`brew install uv`). You don't need to install Python: uv downloads the right one. There is nothing to compile.
- **Cubase** 15.0.20 or later.
- An MCP client: **Claude Code** (tested), Claude Desktop, **GitHub Copilot** in VS Code or any other client that supports stdio servers.

## Installation

```sh
uv tool install trackwright
trackwright setup
```

If the terminal can't find `trackwright`, run `uv tool update-shell` and open a new terminal.

`trackwright setup` is a guided installation. At each step it **shows what it is going to do and asks** before applying it (the default answer is "no"):

1. copies the `Trackwright_Bridge.js` script into the Cubase MIDI Remote folder (`~/Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/trackwright/bridge/`);
2. creates `~/.config/trackwright/config.toml` if it doesn't exist, asking whether writes and project saving are allowed (default: no);
3. registers the server in Claude Code (`claude mcp add --scope user trackwright …`) or, if it can't find `claude`, shows you the command;
4. checks everything with `trackwright doctor`.

It never uses `sudo` and never changes Cubase or system settings. To skip the question for a step: `--yes script`, `--yes config` or `--yes claude`.

### Activate the script in Cubase

1. **Restart Cubase** (it doesn't reload scripts on its own) and open a project. For the first tests, a throwaway one is best.
2. The **Trackwright – Bridge** surface should appear in the **MIDI Remote** tab of the lower zone. Trackwright creates the virtual ports when it starts, and your MCP client starts the MCP server. If the surface doesn't appear, click **+ Add MIDI Controller Surface** and choose `Trackwright` / `Bridge`, with input `Trackwright To Cubase` and output `Trackwright From Cubase`.
3. **Recommended:** in *Studio > Studio Setup > MIDI Port Setup*, uncheck **"In 'All MIDI Inputs'"** for `Trackwright To Cubase`.

### Check

```sh
trackwright doctor   # checks every link and tells you what to do if something fails
```

Then, in your MCP client (for example, Claude Code): "Check the Cubase status with Trackwright".

### Try it without Cubase

Trackwright includes a simulated Cubase. To try it from Claude Code without installing anything else:

```sh
claude mcp add trackwright-sim -- uvx trackwright serve --simulate
```

### Other MCP clients

`trackwright setup` registers the server in Claude Code. Any other MCP client needs the same command: `trackwright serve` over stdio. Desktop apps don't inherit your terminal's `PATH`, so use the absolute path shown by `which trackwright`.

**GitHub Copilot in VS Code** (not tested yet): run **MCP: Open User Configuration** and add:

```json
{
  "servers": {
    "trackwright": {
      "type": "stdio",
      "command": "/Users/<you>/.local/bin/trackwright",
      "args": ["serve"]
    }
  }
}
```

Then use Copilot Chat in agent mode. The Trackwright tools appear in its tool list.

## Update and uninstall

- **Update:** `uv tool upgrade trackwright`, `trackwright bridge-stop` (the MCP server starts the new bridge when it needs it) and `trackwright setup`, which updates the Cubase script if it changed. Restart Cubase and your MCP client. The changelog lists the steps of each version.
- **Uninstall:**
  1. `claude mcp remove trackwright -s user`;
  2. `trackwright bridge-stop`;
  3. `uv tool uninstall trackwright`;
  4. delete `~/Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/trackwright/` and `~/.config/trackwright/`, and remove the surface in the Cubase MIDI Remote tab.

## What it can do (Cubase)

32 tools, all with structured output:

- **Reading:** status, mixer tracks, selected channel, inserts, plugin catalog, parameters, transport and recent changes.
- **Writing**, always with a dry run (`dry_run`) and verification by reading back: parameters (as normalized values or in real units), plugin insertion, volume, mute, solo, record arm, track name and tempo.
- **Navigation:** select tracks and move the cursor and the locators.
- **Automation:** records volume, pan, send, channel EQ, pre-filter and plugin parameter curves by playing the project, with values in real units (dB, Hz) converted by Cubase. Verified on Cubase Elements.
- **Podcast editing:** delete, cut or insert silence over a range in seconds, on all tracks or on one, with verification of the result.
- **Project settings:** read time signature, cycle, metronome, count-in, punch…; change cycle, metronome, count-in, punch, pre-roll and post-roll, and click level.
- **Plugin presets:** next or previous, verified by the change in parameters. The preset name is not available through the API.
- **Save the project:** only on request, with its own permission (`[writes] save`), dry run and verification by the file's timestamp.
- **Import audio:** on the given track and position, with the Cubase file picker, and verification by the edges of the new event.
- **Export the mix:** of a range or of the whole project, with the Cubase dialog, and confirmation of the created file.
- **Cubase commands:** markers, track deletion, splitting at the locators, track creation with the user's help, and a list of allowed commands. Each command states how it behaves: whether it acts directly, opens a dialog or asks for confirmation.

By default it **only reads**. Writes are enabled in the configuration and can be limited to specific tracks.

## Security

- **Read-only by default.** Writes are enabled in `~/.config/trackwright/config.toml` (`[writes] enabled = true`) and can be limited to specific tracks (`allowed_tracks`). Saving the project has its own permission (`[writes] save`).
- Every write supports a **dry run** (`dry_run`) and is **verified by reading back** the state. A write whose result is uncertain is not retried.
- **It opens no network ports:** the server talks to the MCP client over stdio and to the bridge over a private Unix socket.
- It doesn't close Cubase, doesn't record audio and doesn't save anything unless asked.

## Configuration

```toml
# ~/.config/trackwright/config.toml
[writes]
enabled = true                   # allow changes to the open project
save = false                     # allow saving the project on request
# allowed_tracks = ["Voice"]     # limit writes to these tracks

[cubase]
app = "Cubase 15"                # application name for cubase_launch
```

`trackwright config` shows the effective configuration.

## Known limitations

- **Not possible through the API:** changing routing (inputs, outputs or sends), reading track contents (events, audio or automation) or completing Cubase dialogs.
- **Only tracks with a mixer channel are visible.**
- Importing audio, exporting the mix and changing presets use Cubase dialogs or windows: Trackwright opens and prepares them, and you complete the dialog.
- For now, **macOS only** and **Cubase only**.

## Status

Alpha version. Every tool has been run against Cubase Elements 15.0.30 on macOS 27.2, with visual confirmation where the API cannot observe the result. It also has unit tests, MCP contract tests, script tests with Node.js and end-to-end tests, with 98 % coverage.

## Documentation

Manuals and tutorials are in the [`docs/` folder of the repository](https://github.com/impalah/trackwright/blob/main/docs/README.md), in English with Spanish translations ([Spanish index](https://github.com/impalah/trackwright/blob/main/docs/README.es.md)). Source code and issues: [github.com/impalah/trackwright](https://github.com/impalah/trackwright).

## License

Copyright (C) 2026 impalah.

This program is free software: you can redistribute it and/or modify it under the terms of the **GNU Affero General Public License** as published by the Free Software Foundation, either version 3 or, at your option, any later version (`AGPL-3.0-or-later`). It is distributed without any warranty. See the [`LICENSE`](https://github.com/impalah/trackwright/blob/main/LICENSE) file.
