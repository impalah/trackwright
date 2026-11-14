# Installation manual

**English** · [Español](01-installation.es.md)

Trackwright is an MCP server for DAWs; this first version supports Cubase. By the end of this manual you will have Trackwright installed, the script loaded in Cubase and a check that Python and Cubase are talking to each other. Allow about 15 minutes.

> **Verification status.** The script's protocol and operations were verified against Cubase Elements 15.0.30 in the proof of concept (`cubase-mcp-poc`). The `Trackwright_Bridge.js` script derives from that version. Before using it for real work, run the integration tests in step 9.

## How the pieces fit together

```text
MCP client (Claude, Copilot…) ──stdio──► trackwright serve ──local socket──► trackwright bridge ──virtual MIDI──► Cubase (MIDI Remote script)
```

- **`trackwright bridge`:** the bridge. It creates the virtual MIDI ports through which it talks to Cubase. `trackwright serve` starts it automatically if it isn't running; you can also launch it by hand in a terminal.
- **`trackwright serve`:** the MCP server. You don't start it yourself: your MCP client (Claude Code, Claude Desktop, GitHub Copilot…) launches it when needed.
- **The `Trackwright_Bridge.js` script:** runs inside Cubase and answers the requests.

## 1. Requirements

| Requirement | Version | How to check |
|---|---|---|
| macOS | Verified on 27.2 (Apple Silicon) | ` > About This Mac` |
| Cubase | 15.0.20 or later (MIDI Remote API 1.3). Verified on Elements 15.0.30 | `Help > About Cubase` |
| uv | 0.13 or later | `uv --version` |
| git | any (only to install from source) | `git --version` |

If you don't have uv, install it with Homebrew: `brew install uv`. **You don't need to install Python**: uv downloads the right version (3.14) the first time. There is nothing to compile either.

## 2. Install Trackwright

### From PyPI (recommended)

```sh
uv tool install trackwright
trackwright version
```

uv installs the `trackwright` executable in `~/.local/bin`. If the terminal can't find it, run `uv tool update-shell` and open a new terminal. With this installation, **type the commands in the manuals without `uv run`**: `trackwright setup`, `trackwright doctor`…

To update: `uv tool upgrade trackwright`, then `trackwright bridge-stop` (the MCP server starts the new bridge when it needs it), `trackwright setup` (it updates the Cubase script if it changed), and restart Cubase and your MCP client. The [changelog](../../CHANGELOG.md) lists the steps of each version.

Continue with the [guided installation](#guided-installation-recommended).

### From source (development)

```sh
git clone https://github.com/impalah/trackwright.git
cd trackwright
```

The manuals write `/path/to/trackwright` for the folder where you cloned it: replace it with yours.

## 3. Create the environment (from source only)

```sh
uv sync
```

uv creates `.venv/` inside the project with all the dependencies. Check it:

```sh
uv run trackwright version
```

It should answer something like `{"trackwright": "0.2.0"}`.

## Guided installation (recommended)

A single command performs steps 4 and 8 and the check in step 7:

```sh
trackwright setup          # installed from PyPI
uv run trackwright setup   # from source
```

The server is registered in Claude Code with the command that fits each case: the absolute path of `trackwright` if you installed it with `uv tool`, or `uv --directory <repository> run trackwright serve` from source.

It goes through three steps. At each one it **shows what it is going to do and asks** before applying it (the default answer is "no"):

1. **Cubase script:** the destination, the version and, if there was one already, the version being replaced. If it is already up to date, it does nothing.
2. **Configuration:** if `~/.config/trackwright/config.toml` doesn't exist, it asks whether writes and saving are allowed (default: no), shows the content and creates it with `600` permissions. **An existing file is never touched.**
3. **Claude Code:** if `claude` is on the `PATH` and the server isn't registered, it shows the `claude mcp add --scope user trackwright -- …` command and runs it. If it can't find `claude`, it only shows the command. **An existing registration is never replaced.**

At the end it runs `doctor` and lists what is left to do, for example restarting Cubase. Right after installing, it is normal for "bridge running" to fail: the bridge starts with the MCP server.

The questions go to standard error; a JSON summary goes to standard output. Options:

| Option | Effect |
|---|---|
| `--yes script`, `--yes config`, `--yes claude` | Applies that step without asking. Repeat it for several steps; there is no implicit "yes to all". |
| `--writes` / `--no-writes` | When creating the configuration, allows writes or not. With `--yes config` and without this option: no. |
| `--save` / `--no-save` | Same for project saving. Only counts when writes are allowed. |
| `--config PATH` (before `setup`) | Creates or uses the configuration at another path. |

`setup` never uses `sudo`, and never changes Cubase, IAC or Accessibility settings. Then continue with step 6 (activate the script in Cubase).

If you prefer to do it by hand, follow steps 4 to 8.

## 4. Install the script in Cubase

First a dry run, which copies nothing and only shows the destination:

```sh
uv run trackwright script install
```

You will see the destination, by default `~/Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/trackwright/bridge/Trackwright_Bridge.js`, and its status: `missing`, `different` or `up_to_date`. If it is correct, copy it:

```sh
uv run trackwright script install --apply
```

Cubase **does not reload** changed scripts on its own. If it was open, restart it in step 6.

## 5. Start the bridge

**Normally you don't need to:** the MCP server starts the bridge when it needs it (`[bridge] autostart`). Starting it by hand is useful for running the checks in step 7 before connecting your MCP client, or for watching its log live. In a terminal that you will leave open:

```sh
cd /path/to/trackwright
uv run trackwright bridge
```

You will see `virtual MIDI ports open` and `bridge listening on …/bridge.sock`. As long as this terminal stays open, the `Trackwright To Cubase` and `Trackwright From Cubase` ports exist.

## 6. Activate the script in Cubase

1. Open or restart Cubase, and open a project. For the first tests, an empty, throwaway project is best.
2. Cubase detects the **Trackwright – Bridge** surface automatically when the ports exist. To check, open the **MIDI Remote** tab in the lower zone of the project window.
3. If it doesn't appear, click **+ Add MIDI Controller Surface** in that tab and choose:
   - Vendor: `Trackwright`;
   - Model: `Bridge`;
   - MIDI input: `Trackwright To Cubase`;
   - MIDI output: `Trackwright From Cubase`.
4. **What you will see on the surface** when the bridge is running:
   - **Row 1:** "Trackwright" with the version of the loaded script, and a **lamp** on the right. The lamp lights up briefly every time Trackwright sends a request to Cubase.
   - **Row 2:** the name of the selected track. It shows "-" if the selected track has no mixer channel (markers, folders) or if no track is selected.

   - **On the right:** dozens of faders. These are the automation controls (volume, pan, sends, EQ, pre-filter, Quick Controls and plugin parameters of the selected track) used by `cubase_record_automation`. Don't assign them to other functions in the mapping assistant.

   With the bridge stopped, only the lamp is visible: the texts appear when the "Bridge" page becomes active.
5. **Recommended:** in *Studio > Studio Setup > MIDI Port Setup*, uncheck the **"In 'All MIDI Inputs'"** column for `Trackwright To Cubase`. This way control messages never reach a track.

Exact menu names may vary slightly between versions.

## 7. Check the connection

```sh
uv run trackwright ping
```

It should answer `"ok": true`, with the script version (for example, `1.0.1`) and the echo `hola-ñ-✓`. Then run the full diagnostics:

```sh
uv run trackwright doctor
```

`doctor` checks every link and, if something fails, tells you what to do (`fix`). Everything should come out with `"ok": true`.

## 8. Connect your MCP client

Follow the [operation manual](02-operation.md#connect-an-mcp-client).

## 9. Verification against your Cubase (from source)

With the bridge running and Cubase open:

```sh
TRACKWRIGHT_INTEGRATION=1 uv run pytest tests/integration -v
```

To also test reversible writes on a test track (use a throwaway project):

```sh
TRACKWRIGHT_INTEGRATION=1 TRACKWRIGHT_ALLOW_WRITES=1 TRACKWRIGHT_TEST_TRACK="POC-TEST" \
  uv run pytest tests/integration -v
```

Each write is undone when the test finishes.

## Uninstall

1. Delete the `~/Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/trackwright/` folder.
2. In Cubase, remove the **Trackwright – Bridge** surface from the MIDI Remote tab.
3. Remove the server from Claude Code (`claude mcp remove trackwright -s user`), stop the bridge (`trackwright bridge-stop`) and uninstall Trackwright: `uv tool uninstall trackwright`, or delete the repository if you installed it from source.
4. If you created it, delete `~/.config/trackwright/`.
