# Tutorial 5 — Markers and cursor position

**English** · [Español](05-markers-cursor.es.md)

> **Tested setup.** These tutorials use **Claude Code** and **Cubase**: the tool behavior they describe was verified with Claude Code and Cubase Elements 15.0.30 (see the [verification log](../verification.md)). Any other MCP client calls the same tools; where the text says "the assistant", read your client's AI assistant. For now, Cubase is the only DAW Trackwright supports.

**Goal:** move the cursor and the locators, create a marker track, insert a marker and navigate between markers.
**You need:** writes enabled. `enabled = true` is enough: markers do not belong to any particular track. Keep the transport stopped.

## Step 1. Read the position

> Where is the cursor?

`cubase_get_transport` returns, for example, `1. 1. 1.  0`, in bars, beats, sixteenths and ticks.

## Step 2. Move the cursor

> Move the cursor to bar 3.

`cubase_set_position` with `which: "cursor"` and `time: "3.1.1.0"`. This is **navigation**, so it works even if writes are disabled. The response includes `verified: true` and the cursor moves in Cubase.

You can also use seconds:

> Put the cursor at second 2.

It uses `unit: "seconds"` and `time: "0:00:02.000"`. Verification assumes a 4/4 time signature and a constant tempo.

## Step 3. Cycle locators

> Set the cycle between bars 2 and 4.

These are two calls to `cubase_set_position`, with `cycle_left` and with `cycle_right`.

## Step 4. Create the marker track and insert a marker

> Create a marker track and put a marker at bar 2.

1. `cubase_markers` with `add_marker_track`. It is of class `direct`: Cubase creates it without a dialog.
2. `cubase_set_position` moves the cursor to bar 2.
3. `cubase_markers` with `insert_at_cursor`.

Marker tracks are not visible through the API, so the response says `verified: "not_observable"`. **Check it on screen.**

## Step 5. Navigate

> Move the cursor to bar 3 and then to the previous marker.

`locate_prev` moves the cursor to bar 2, and the response shows `cursor_before` and `cursor_after`. Note: the jumps only go from marker to marker, they do not stop at the locators, and if there are no markers they go to the start of the project.

## Step 6. Clean up

To delete the marker track, select it **by hand**: it has no mixer channel, so Trackwright cannot select it. Then delete it yourself, or ask for it with `cubase_run_command` and the key `project.remove_selected_tracks`. Since it contains a marker, Cubase will ask for confirmation.

## What you have learned

- Moving positions is navigation and is verified by reading the transport.
- Marker tracks are created without a dialog, but they are not visible to the API.

**Next:** [Tutorial 6 — Create a track with the help of the dialog](06-track-with-dialog.md).
