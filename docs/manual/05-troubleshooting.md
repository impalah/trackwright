# Troubleshooting

**English** · [Español](05-troubleshooting.es.md)

Always start with:

```sh
uv run trackwright doctor
```

Every failing check includes a `fix` with the solution.

## `BRIDGE_UNAVAILABLE`: the bridge is not available

- **Symptom:** any tool fails with `bridge socket not found` or `not accepting connections`.
- **Cause:** the bridge isn't running, or it was started with another configuration and uses another socket.
- **Solution:**
  1. Start `uv run trackwright bridge` in a terminal.
  2. If you use a configuration file, the bridge and the MCP client must read the same one. Compare `socket_path` in `uv run trackwright config` from both environments.

## "another bridge is already listening" or "virtual ports … already exist"

- **Cause:** a bridge is already running, perhaps in another terminal.
- **Solution:** use that bridge or close it with Ctrl+C. If it was closed abruptly, the orphaned socket is cleaned up automatically at startup.

## `ping` fails with `TIMEOUT`: Cubase doesn't respond

- **Most likely cause:** the MIDI Remote surface isn't active, or Cubase doesn't have the script.
- **Solution:**
  1. `uv run trackwright script status` should say `up_to_date`. If not, run `script install --apply` and **restart Cubase**.
  2. **Trackwright – Bridge** should appear in the Cubase **MIDI Remote** tab. If not, add it by hand (step 6 of the [installation manual](01-installation.md#6-activate-the-script-in-cubase)).
  3. Check that the surface uses the input `Trackwright To Cubase` and the output `Trackwright From Cubase`.

## The surface panel shows "-" or only the lamp

- **Only the lamp, no texts:** the "Bridge" page isn't active, usually because the bridge is stopped. Start it.
- **"-" in the track row:** no track with a mixer channel is selected.
- **A different version in the title:** Cubase has another script loaded. Run `uv run trackwright script install --apply` and restart Cubase.

## Why are there so many faders on the surface?

They are the 45 automation controls of `cubase_record_automation`, bound to the selected track. Cubase only records automation from a touched surface control, and a script can only create its controls when it loads, so they are always there. Don't move them: moving one changes the selected track. Details in the [installation manual](01-installation.md#6-activate-the-script-in-cubase).

## The script doesn't update

- **Cause:** Cubase doesn't reload modified scripts on its own.
- **Solution:** restart Cubase. `cubase_status` will show the loaded version (`script_version`).

## `STALE_REF` or `STALE_SESSION`

- **Cause:** Cubase restarted or reloaded the script, and the internal identifiers changed. They are also **reused** for other objects, so an old `ref` could point to a different object. Trackwright detects this and refuses to use it.
- **Solution:** list again (`cubase_list_tracks`, `cubase_list_inserts`). To refer to tracks, use the `uid:` selectors, which are stable.

## `TIMEOUT` on a write

- **Cause:** Cubase didn't respond in time. API operations wait for an internal Cubase cycle of about 110 ms; with Cubase under heavy load it can take longer.
- **What it means:** **the change may or may not have been applied.** Trackwright doesn't retry and attaches the read-back of the value (`read_back`).
- **Solution:** check `read_back`. If it keeps happening, increase `[bridge] write_timeout`.

## `BUSY`

- **Cause:** another write, perhaps from another MCP session, was still in progress when this one arrived. The write **was not sent**.
- **Solution:** repeating it is safe.

## `WRITES_DISABLED` or `NOT_ALLOWED`

- **Cause:** the configuration doesn't allow that write.
- **Solution:** `[writes] enabled = true` and, if you use `allowed_tracks`, add the track. Restart the MCP client.

## A command "does nothing"

- **Cause:** many commands depend on the context of the Cubase window (`ui_selection`) or open a dialog (`dialog`).
- **Solution:**
  - look at the Cubase screen: a dialog may be waiting;
  - `cubase_run_command` with `dry_run=true` shows `can_perform`: with `false`, Cubase can't run it at that moment (for example, Undo with no history).

## A track's output ended up as "No Bus"

- **Cause:** someone wrote the routing through the API. Trackwright doesn't do that: routing can't be written through the API, and it rejects it.
- **Solution:** in the track's Inspector, choose the output again, for example "Stereo Out".

## A track doesn't appear in `cubase_list_tracks`

- **Cause:** only tracks with a mixer channel are listed. Marker tracks and folders don't have one.

## `UNAVAILABLE` in `cubase_get_transport`

- **Cause:** Cubase hasn't sent the transport position yet in this session.
- **Solution:** move the cursor once in Cubase and try again.

## See what is going on

```sh
uv run trackwright --log-level DEBUG bridge   # each request, its duration and its result
uv run trackwright bridge-status              # late responses, protocol errors, session
```

Every 5 seconds Cubase sends a "MIDI Identity Request" through the output port. This is normal: the bridge counts it as `foreign_frames` and ignores it.
