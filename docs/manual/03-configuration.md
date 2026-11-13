# Configuration reference

**English** · [Español](03-configuration.es.md)

Trackwright works **without a configuration file**. By default it is read-only: no tool modifies the project until you enable writes.

## Where the file is looked up

| Order | Location |
|---|---|
| 1 | The path given with `--config <file>` on the command line |
| 2 | The path in the `TRACKWRIGHT_CONFIG` environment variable (if you set it, the file must exist) |
| 3 | `~/.config/trackwright/config.toml` (optional) |

To see the effective, merged configuration:

```sh
uv run trackwright config
```

## Full example

```toml
# ~/.config/trackwright/config.toml

[bridge]
to_cubase_port = "Trackwright To Cubase"
from_cubase_port = "Trackwright From Cubase"
# socket_dir = "/private/tmp/my-directory"   # default: $TMPDIR/trackwright-<uid>
request_timeout = 3.0
write_timeout = 5.0
backend = "auto"           # coremidi on macOS (no compiling); rtmidi as an alternative
autostart = true            # serve starts the bridge if it isn't running
autostart_timeout = 10.0

[cubase]
app = "Cubase 15"
launch_timeout = 120.0

[writes]
enabled = true
allowed_tracks = ["POC-TEST", "Voice"] # empty = all tracks
save = false                           # true = cubase_save_project can save the .cpr

[logging]
level = "INFO"
file = "~/Library/Logs/trackwright/trackwright.log"

[script]
# install_dir = "~/Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/trackwright/bridge"
```

Unknown keys are rejected with `CONFIG_ERROR`, so that a typo doesn't go unnoticed.

## `[bridge]`

| Key | Default | Description |
|---|---|---|
| `to_cubase_port` | `"Trackwright To Cubase"` | Virtual port Python writes to. Cubase sees it as the script's **input**. |
| `from_cubase_port` | `"Trackwright From Cubase"` | Virtual port Python reads from. Cubase sees it as the script's **output**. |
| `socket_dir` | `$TMPDIR/trackwright-<uid>` | Private directory (0700 permissions) for the local `bridge.sock` socket. Don't use a volume mounted with `noowners`. |
| `request_timeout` | `3.0` | Seconds to wait for a read (between 0.05 and 30). |
| `write_timeout` | `5.0` | Seconds to wait for a write (between 0.05 and 30). After a timeout, the result is unknown: Trackwright doesn't retry. |
| `backend` | `"auto"` | MIDI transport. `coremidi`: CoreMIDI from Python with `ctypes`; it is pure Python, with nothing to compile (macOS). `rtmidi`: mido + python-rtmidi, for other platforms or as an alternative; you need to uncomment those dependencies in `pyproject.toml`. `auto`: `coremidi` on macOS and `rtmidi` elsewhere. |
| `autostart` | `true` | If `trackwright serve` doesn't find the bridge, it starts it as an independent process. It doesn't duplicate it if one already exists, and its log goes to `bridge.log` inside `socket_dir`. |
| `autostart_timeout` | `10.0` | Seconds to wait for the started bridge to accept connections (between 0.5 and 60). |

If you change the port names, the Cubase script won't find them, because it has them hard-coded too. Leave them as they are unless you know what you're doing.

## `[cubase]`

| Key | Default | Description |
|---|---|---|
| `app` | `"Cubase 15"` | Application name for `open -a` and process name for `pgrep -x`. Change it if you use another version, for example `"Cubase 14"`. |
| `launch_timeout` | `120.0` | Seconds `cubase_launch` waits for the script to respond after opening Cubase (between 5 and 600). |

## `[writes]`

| Key | Default | Description |
|---|---|---|
| `enabled` | `false` | Master switch. With `false`, writes fail with `WRITES_DISABLED`; dry runs (`dry_run`) and navigation keep working. |
| `allowed_tracks` | `[]` | Names of the tracks that can be modified. Empty means all. Outside the list: `NOT_ALLOWED`. |
| `save` | `false` | Allows `cubase_save_project` to **save the project file to disk**. It is independent of `enabled`, and both are required. Without it: `SAVE_DISABLED`. Dry runs always work. |

What counts as a write:
- **Write** (subject to `[writes]`): parameters, mixing, name, plugins, tempo, markers, event deletion and splitting, commands.
- **Navigation** (always allowed): selecting a track, moving the cursor or the locators, jumping between markers.

## `[logging]`

| Key | Default | Description |
|---|---|---|
| `level` | `"INFO"` | `TRACE`, `DEBUG`, `INFO`, `SUCCESS`, `WARNING`, `ERROR` or `CRITICAL`. Also via `--log-level`. |
| `file` | no file | Additional log file. It rotates at 10 MB and keeps 5 files. |

Logs always go to **stderr**, never to stdout, because with `trackwright serve` stdout carries the MCP protocol.

## `[script]`

| Key | Default | Description |
|---|---|---|
| `install_dir` | `~/Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/trackwright/bridge` | Folder where `trackwright script install` copies `Trackwright_Bridge.js`. |

## Environment variables

| Variable | Use |
|---|---|
| `TRACKWRIGHT_CONFIG` | Path of the configuration file. |
| `TMPDIR` | Base of the default socket directory. |
| `TRACKWRIGHT_INTEGRATION`, `TRACKWRIGHT_ALLOW_WRITES`, `TRACKWRIGHT_TEST_TRACK` | Only for the integration tests (see [development](../development.md)). |
