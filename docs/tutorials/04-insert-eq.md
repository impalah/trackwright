# Tutorial 4 — Insert an EQ and adjust a band

**English** · [Español](04-insert-eq.es.md)

**Goal:** load StudioEQ in an empty slot, raise a band's gain by 3 dB in real units and restore it.
**You need:** [tutorial 3](03-first-safe-change.md), with writes enabled for POC-TEST.

## Step 1. Choose an empty slot

> Which insert slots are free on POC-TEST?

Let's assume slot 2 is empty. Trackwright **never replaces a loaded plugin**: on an occupied slot it responds `SLOT_OCCUPIED`.

## Step 2. Insert with a prior dry run

> Insert StudioEQ in slot 2 of POC-TEST. Show me the plan first.

1. Claude looks up StudioEQ's `uid` with `cubase_list_available_plugins`: it is `946051208E29496E804F64A825C8A047`.
2. It calls `cubase_insert_plugin` with `dry_run: true` and shows you the track, the slot and the plugin.
3. After your confirmation, it applies it.

The response includes `inserted: true` and `verified: true`: the slot contains a plugin with that `uid`.

## Step 3. Find the parameter

> In the EQ in slot 2, which parameter controls band 1's gain?

With `cubase_list_parameters`, `target: "insert:2"` and a filter, Claude finds the parameter `GainP1L` (tag 4207). Its value is `0.0 dB`.

## Step 4. Write in real units

> Raise that gain to +3 dB.

Claude uses `cubase_set_parameter` with `unit: "plain"` and `value: 3`. Cubase converts the 3 dB to its normalized value (0.5625), and Trackwright verifies with a tolerance of 1e-3. In the dry run you will see the normalized value that will be written.

## Step 5. Restore

> Set the gain back to 0 dB.

## Step 6. Remove the plugin

The API has no verified way to remove plugins. **Remove it yourself by hand** in Cubase.

Then ask "List the inserts of POC-TEST". If you kept a `ref` to the plugin and use it, Trackwright will respond `INVALID_OBJECT` or `STALE_REF` instead of acting on another object.

## What you have learned

- Plugins are loaded by their `uid`, never onto an occupied slot.
- With `unit: "plain"` you work in real units and Cubase does the conversion.
- References to deleted objects are detected.

**Next:** [Tutorial 5 — Markers and cursor position](05-markers-cursor.md).
