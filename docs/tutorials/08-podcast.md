# Tutorial 8 — Edit a podcast by seconds

**English** · [Español](08-podcast.es.md)

> **Tested setup.** These tutorials use **Claude Code** and **Cubase**: the tool behavior they describe was verified with Claude Code and Cubase Elements 15.0.30 (see the [verification log](../verification.md)). Any other MCP client calls the same tools; where the text says "the assistant", read your client's AI assistant. For now, Cubase is the only DAW Trackwright supports.

**Goal:** remove a section of a podcast by specifying it in seconds and check that it was done correctly.
**You need:**
- writes enabled;
- script 1.5.1 or later;
- the project **saved**;
- the transport stopped.

## Step 1. Dry run

> Remove the section between second 2 and second 30 from the podcast, closing the gap. Check it with the Voice track.

The assistant uses `cubase_edit_range` with `action: "delete_time"`, `start: "2"`, `end: "30"` and `verify_track: "Voice"`, first as a dry run. It shows you:
- the range (`0:00:02.000`–`0:00:30.000`, 28 s);
- the effect: the section is removed and everything after it moves earlier;
- the scope: **every track** with audio in that section.

## Step 2. Apply

After your confirmation:
1. Trackwright sets the locators to 2 and 30 s;
2. activates the Range tool, selects the section and deletes it;
3. switches back to the Object tool and restores the locators and the cursor.

With `verify_track`, it compares the audio edges of that track before and after: `verified: true` means the section is gone and everything after it moved 28 s earlier.

## Other actions

| You want to… | Ask |
|---|---|
| Delete and leave a gap (to put something else in) | "Delete the audio between 1:10 and 1:25, without moving anything" → `delete` |
| Make room for an ad spot | "Insert 15 seconds of silence at minute 5" → `insert_silence` from 5:00 to 5:15 |
| Keep only one fragment | "Keep only 10 to 70" → `crop` |
| Remove a cough on a single mic | "Delete from 1:12.4 to 1:13.1 only on the Guest track" → `delete` with `track: "Guest"` |

## Importing the theme music

> Import the theme music /Users/me/Music/theme.wav on the Music track, at second 0.

1. The assistant uses `cubase_import_audio` with `phase: "start"`: it selects the track, puts the cursor at 0 and opens "Import Audio File".
2. In the file picker, press **Cmd+Shift+G**, paste the path and open the file. Accept the options (Cubase copies it into the project).
3. Tell the assistant "done". With `phase: "confirm"` it will check that the track has audio from 0 to the length of the theme music.

## Exporting the episode

> Export the full episode.

1. The assistant uses `cubase_export_mix` with `phase: "start"`: it sets the locators around all the audio and opens "Export Audio Mixdown".
2. You choose the format (for example, MP3 at 128 kB/s for publishing) and click **Export Audio**.
3. Tell the assistant "done". With `phase: "confirm"` it will find the file in the project's *Mixdown* folder and check that it is as long as the episode.

For a fragment, for example a teaser: "export from 5:00 to 5:45".

## If something does not go as expected

- **Edit > Undo** in Cubase reverts it.
- `NO_RANGE_SELECTION`: bring the Cubase Project window to the front and try again.
- **When undoing a single-track edit,** press Undo as many times as `undo_steps` indicates.

## What you have learned

- Commands in seconds do not depend on the time signature or the tempo.
- The result is checked by walking the audio edges of one track.
