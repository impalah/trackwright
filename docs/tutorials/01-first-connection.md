# Tutorial 1 — First connection

**English** · [Español](01-first-connection.es.md)

**Goal:** go from zero to Claude telling you what is in your Cubase project.
**Time:** 15 minutes.
**You need:** uv and Cubase 15.0.20 or later (see the [installation manual](../manual/01-installation.md#1-requirements)).

The commands are those of an installation from PyPI. From source, prefix them with `uv run`.

## Step 1. Dry run with the simulator

Before touching Cubase, check that Claude can talk to Trackwright using the simulator, which needs nothing installed:

1. Register the simulated server in Claude Code:
   ```sh
   claude mcp add trackwright-sim -- uvx trackwright serve --simulate
   ```
2. Open Claude Code and ask:
   > What tracks are in my Cubase project?
3. Claude will call `cubase_list_tracks` and tell you there are `Stereo Out`, `POC-INSTR` and `POC-TEST`. These are the simulator's tracks.
4. Ask for `cubase_status`. It should show `simulated: true`.

If this works, the MCP side is fine. Remove the simulated server with `claude mcp remove trackwright-sim`.

## Step 2. Install

```sh
uv tool install trackwright
trackwright setup
```

`setup` asks at each step. For this tutorial:

- **the script:** yes;
- **writes:** no; this tutorial only reads, and you can enable them later;
- **create the configuration:** yes;
- **register in Claude Code:** yes.

At the end, `doctor` will show "bridge running" in red: this is expected, because the bridge starts with the MCP server.

## Step 3. Connect to Cubase

1. **Restart Cubase** and open a throwaway project that has at least one audio track.
2. Restart Claude Code (or open `/mcp`) so that the `trackwright` server starts. The server starts the bridge, and the **Trackwright – Bridge** surface appears in Cubase's **MIDI Remote** tab. If it does not appear, follow step 6 of the [installation manual](../manual/01-installation.md#6-activate-the-script-in-cubase).
3. In a terminal:
   ```sh
   trackwright doctor
   ```
   Everything should show `"ok": true`, with the script version under "Cubase answers".
4. In Claude Code:
   > Check Cubase's status with Trackwright.

   Claude should answer with `simulated: false`, the Cubase version and `writes_enabled: false`: you are in read-only mode.

## Step 4. Explore

Try these requests:

- "List the Cubase tracks with their volume and whether they are muted."
- "Which track is selected and what sections does it have?"
- "Where is the cursor and what tempo is the project at?"

## What you have learned

- The full chain: MCP client → `serve` → bridge → Cubase.
- The simulator lets you practice without risk.
- By default Trackwright only reads.

**Next:** [Tutorial 2 — Inspect a track and its plugins](02-inspect-track.md).
