# Tutorial 2 — Inspect a track and its plugins

**English** · [Español](02-inspect-track.es.md)

**Goal:** read a track's inserts, the plugin catalog and a plugin's parameters, without modifying anything.
**You need:** [tutorial 1](01-first-connection.md). So that there is something to read, manually insert a plugin (for example, StudioEQ) in slot 1 of a track.

## Step 1. Identify the track by its uid

Ask:

> List the tracks and give me the selector for the "POC-TEST" track.

Claude uses `cubase_list_tracks` and gives you something like `uid:79CDBA14…`. **That selector does not change even if you restart Cubase**, so it is the safest way to refer to the track.

## Step 2. View the inserts

> What plugins does POC-TEST have in its inserts?

`cubase_list_inserts` returns the 8 slots. In slot 1 you will see `StudioEQ` and its `plugin_uid`; the rest will appear empty.

## Step 3. Browse the catalog

> Which equalizers can I load in slot 2?

`cubase_list_available_plugins` with `filter: "eq"` lists the available plugins, with their `uid`. You will need it in [tutorial 4](04-insert-eq.md).

## Step 4. Read parameters

> Show me the gain parameters of the plugin in slot 1.

Claude uses `cubase_list_parameters` with `target: "insert:1"` and a filter. Each parameter has:
- `tag`: its stable identifier;
- `title`: in Cubase's language;
- `display`: the value as Cubase shows it, for example `0.0 dB`;
- `process`: the normalized value, between 0 and 1;
- `plain`: the value in real units, if the plugin provides it.

> What is the value of parameter 4207 in slot 1?

`cubase_get_parameter` returns that specific parameter.

## Step 5. The channel strip EQ

> Show me the parameters of POC-TEST's channel strip EQ.

It uses `target: "strip:eq"`.

## What you have learned

- `uid:` selectors are the stable way to refer to a track.
- `target` chooses which part of the track: `channel`, `insert:N` or `strip:eq`.
- Titles are localized; the `tag` is what identifies a parameter.

**Next:** [Tutorial 3 — First safe change](03-first-safe-change.md).
