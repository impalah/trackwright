# Operation manual

**English** · [Español](02-operation.es.md)

## Daily routine

1. **Use your MCP client.**
   - It launches `trackwright serve`, which **starts the bridge** if it isn't running (`[bridge] autostart`).
   - If Cubase is closed, ask Claude to open it ("open Cubase", or with a `.cpr` project). It uses `cubase_launch`.
2. **If Cubase shows a dialog** at startup (Steinberg Hub, project selection, audio device), answer it yourself and open a project. The script starts responding once a project is open.
3. **When you're done,** close Cubase yourself; Trackwright never closes it. An automatically started bridge keeps running in the background. To stop it:
   ```sh
   pkill -f "trackwright bridge"
   ```

You can also start the bridge by hand in a terminal, as before (`uv run trackwright bridge`), and stop it with **Ctrl+C**. If it is already running, `serve` uses it and doesn't start another one.

## Bridge status

```sh
uv run trackwright bridge-status   # pid, requests, script session, late responses, errors
uv run trackwright ping            # round trip Python → Cubase → Python
uv run trackwright doctor          # full diagnostics with fixes
```

## Connect an MCP client

The server is called **`trackwright`** and uses the **stdio** transport. The command the client must launch is:

```sh
uv --directory /Volumes/Data/projects/sound/trackwright run trackwright serve
```

### Claude Code

`uv run trackwright setup` registers it for you (see the [installation manual](01-installation.md#guided-installation-recommended)). By hand:

```sh
claude mcp add trackwright -- uv --directory /Volumes/Data/projects/sound/trackwright run trackwright serve
```

- Add `--scope user` to have it in all your projects.
- To check: `claude mcp list`, or `/mcp` inside a session.

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` and add:

```json
{
  "mcpServers": {
    "trackwright": {
      "command": "/opt/homebrew/bin/uv",
      "args": ["--directory", "/Volumes/Data/projects/sound/trackwright", "run", "trackwright", "serve"]
    }
  }
}
```

- Claude Desktop doesn't inherit your terminal's `PATH`, so use the **absolute path** of uv (the one shown by `which uv`).
- Restart Claude Desktop after saving the file.

### Try it without Cubase: the simulator

```sh
uv --directory /Volumes/Data/projects/sound/trackwright run trackwright serve --simulate
```

It responds from an in-memory simulated Cubase with two tracks: `POC-INSTR` and `POC-TEST`. It is useful for learning the tools or debugging the client. `cubase_status` returns `simulated: true`, and nothing it returns says anything about the real Cubase.

## Enable writes

By default, Trackwright **only reads**. To allow changes, create `~/.config/trackwright/config.toml`:

```toml
[writes]
enabled = true
allowed_tracks = ["POC-TEST"]   # optional: limits which tracks can be modified
```

You don't need to restart the bridge, because the policy is applied by the MCP server. You do need to restart the MCP client, which is what launches `serve`. Details in the [configuration reference](03-configuration.md).

How the model works with writes:
1. It calls the tool with `dry_run=true`, which is the default, and shows you the plan.
2. After you agree, it calls it with `dry_run=false`.
3. Trackwright applies the change, reads it back and returns `verified`.

## Logs

- They go to stderr. With `serve`, the MCP client usually stores them (for example, Claude Desktop in `~/Library/Logs/Claude/`).
- To have your own file: `[logging] file = "~/Library/Logs/trackwright/trackwright.log"`.
- More detail: `--log-level DEBUG` or `[logging] level = "DEBUG"`.

## What happens when something restarts

| Situation | Effect | What to do |
|---|---|---|
| You restart the bridge | Cubase reconnects on its own. The `ref` values remain valid. | Nothing. |
| The bridge crashes | The next tool starts it again (if `autostart`). A write that was never sent is sent after the restart; one that was sent is never retried. | Nothing. If it doesn't start, check `bridge.log` in the socket directory. |
| You restart Cubase or reload the script | New session: previous `ref` values give `STALE_REF`. | List again. `uid:` selectors still work. |
| You update Trackwright | It may bring a new script. | `uv run trackwright script install --apply` and restart Cubase. |
| A write times out | Unknown result; it is not retried. | Check the error's `read_back`. |

## Good practices

- Work with the **transport stopped** while the model changes parameters.
- **Save the project before** sessions with writes. Trackwright never saves.
- For long tasks, limit writes with `allowed_tracks`.
- When you get a `dialog` or a `ui_selection`, look at the Cubase screen: Trackwright can't see it.
