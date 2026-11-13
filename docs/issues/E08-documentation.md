# E08 — User documentation: manuals and tutorials

**English** · [Español](E08-documentation.es.md)

Goal: someone who does not know the project can install it, start it and operate it by following the documents, without help.

## TW-0801 Installation manual

- **Status:** done
- **Scope:** `docs/manual/01-installation.md`.
  - Requirements: macOS, Cubase 12 or later (verified on Elements 15.0.30) and uv.
  - Clone the repository and run `uv sync`.
  - Install the script in Cubase (`trackwright script install`).
  - Activate the MIDI Remote surface in Cubase.
  - Check with `trackwright doctor`.

## TW-0802 Operation manual

- **Status:** done
- **Scope:** `docs/manual/02-operation.md`.
  - Start and stop the bridge.
  - Check its status.
  - Connect the MCP server to Claude Code and Claude Desktop, with configuration examples.
  - Enable writes.
  - Logs.

## TW-0803 Configuration reference

- **Status:** done
- **Scope:** `docs/manual/03-configuration.md`. All TOML keys and environment variables, with their defaults and examples.

## TW-0804 MCP tools reference

- **Status:** done
- **Scope:** `docs/manual/04-tools.md`.
  - Each tool with its input, output, errors, whether it writes, its command class and its known limitations.
  - Generated or validated against the real schema by a test (TW-0905).

## TW-0805 Troubleshooting

- **Status:** done
- **Scope:** `docs/manual/05-troubleshooting.md`. Symptoms, cause and solution for:
  - bridge unavailable;
  - Cubase does not see the ports;
  - `STALE_SESSION`;
  - timeouts;
  - open dialogs;
  - output set to "No Bus";
  - the script does not reload.

## TW-0806 Step-by-step tutorials

- **Status:** done
- **Scope:** `docs/tutorials/`.
  1. First connection, from zero to `cubase_status`.
  2. Inspect a track and its plugins.
  3. First safe change: dry run, apply and restore the volume.
  4. Insert an EQ and adjust a band.
  5. Markers and cursor position.
  6. Create a track with the help of the dialog.

## TW-0807 Development and architecture documentation

- **Status:** done
- **Scope:**
  - `docs/development.md`: `uv` commands, tests, coverage, node tests, optional integration tests and how to add a tool.
  - `docs/architecture.md`: components, request flow and decisions.
  - `README.md` with a quick start and links.

Since 2026-11-13 the documentation is in English, with Spanish translations in `*.es.md` files.
