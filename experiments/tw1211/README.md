# Experiment TW-1211: range editing in seconds

**English** · [Español](README.es.md)

**Requirements:**
- script **1.5.0**, which adds 12 commands for range editing and event probing;
- the test project **saved**;
- the user watching Cubase.

**Tool:** `uv run python experiments/tw1211/probe.py <step>` (see the script's help). The destructive steps only act with `--apply`.

## Plan

1. **Seconds:** `seconds cursor 0:00:02.000` and `seconds cycle_left/right`. `time2` is read back from the Transport.
2. **Event probing:** `events`. Does `Locate Next Event` walk through the event edges? Those of all tracks or only those of the selected ones?
3. **Scope of `Select in Loop`:** with POC-TEST selected and the cycle at 2–30 s, which tracks end up with a range selection? The user observes it.
4. **Actions**, one at a time, undoing between each one:
   - `Delete` on the selection;
   - `Delete Time`, `Cut Time`, `Process / Silence`, `Insert Silence` and `Crop Range`.

   For each one: whether it acts without a dialog, what changes (observed by the user, and with `events` if probing works) and whether `Undo` undoes it.

## Results (2026-11-13, Cubase Elements 15.0.30, script 1.5.0, with the user watching)

**Starting state:**
- POC-TEST with 5 audio events, some overlapping and sharing a file;
- POC-INSTR with 4 MIDI parts in bars 1–5;
- 120 BPM, 4/4 and project saved.

### 1. Positions in seconds

- **Cursor:** `set_position(cursor, 0:00:02.000, seconds)` works. `time2` of the Transport reads it back exactly (`0:00:02.000`, `0:00:30.000`).
- **Locators, directly: ❌ fails.** When requesting `0:00:02.000` and `0:00:30.000` through the secondary display they ended up at `1. 1. 1. 0` and `1. 3. 2. 0`.
- **Locators, with a workaround: ✅ works.** The cursor is set in seconds and `Transport / Set Left Locator` or `Set Right Locator` (class *direct*) is run. The cycle ended up at `2. 1. 1. 0` – `16. 1. 1. 0` (2–30 s).

### 2. Event probing

- **`Locate Next Event`** walks through the edges (starts and ends mixed) of the events on the **selected tracks**. With no track selected it does not move.
  - POC-TEST: `2.0, 2.4, 6.0, 6.8, 18.0, 22.0, 2:19.976` s.
  - It matches the user's screenshot: overlapping events starting at 0, 2, 6, 18 and 22 s.
- **`Locate Selection` / `Locate Selection End`** give the start and end of the whole selection. With `Select All on Tracks`: 0 → 2:19.976.

### 3. Selection

- **Object tool:** `Select in Loop` selected only the first event (0–2.4 s). Not useful.
- **Range Selection tool** (key 2, switched by the user): `Select in Loop` creates a **2.000–30.000 s range on all tracks**, not only on the selected one (observed by the user). With a range, `Crop Range` becomes executable.
- **The cycle follows the range selection:** a click with the range tool left the locators at `1. 3. 1. 0` – `1. 3. 1. 0`, and then `Select in Loop` could not be executed.

### 4. Actions on the 2–30 s range

Measured with the POC-TEST probe, each one undone before the next:

| Action | Class | Edges afterwards | Interpretation | `Undo` |
|---|---|---|---|---|
| `Edit / Delete` | direct | `2.0, 30.0, 2:19.976` | Gap between 2 and 30 s; nothing moves | ✅ exact |
| `Edit / Delete Time` | direct | `2.0, 1:51.976` | Removes 28 s and moves everything after it earlier | ✅ exact |
| `Edit / Cut Time` | direct | `2.0, 1:51.976` | Same as Delete Time, and copies it to the clipboard | ✅ exact |
| `Edit / Insert Silence` | direct | everything +28 s, end `2:47.976` | Inserts 28 s of silence at 2 s | ✅ exact |
| `Edit / Crop Range` | direct | `2.0 … 30.0` | Keeps only the range. The 2.4 s edge did not appear: unexplained | ✅ exact |
| `Process / Silence` | **dialog** | no changes | Warns that there are events sharing a file («Continuar / Nueva versión / Cancelar» (*Continue / New Version / Cancel*), with «No volver a preguntar» (*Don't ask again*)). The user canceled without ticking the box | — |

- All of them act on the **tracks included in the range**, which with `Select in Loop` are all of them.
- While a dialog is open, `Undo` reports `canPerform = false`. This serves to detect a pending dialog.
- The range selection survives `Undo`.

## Conclusions for `cubase_edit_range`

1. **Range:** cursor in seconds or in bars, `Set Left/Right Locator`, range tool (`Tool / Range Tool`, which must be added to the script), `Select in Loop`, action, and back to the previous tool (`Tool / Select Tool`).
2. **Verification:** probing with `Locate Next Event` on the selected tracks, before and after, compared with what is expected for each action.
3. **Scope:** all tracks. This is the natural choice for cutting a podcast (`Delete Time`). Deleting on only one track needs another route (to be investigated).
4. **`Process / Silence`:** interactive, because the dialog depends on whether the file is shared.
5. **Undo:** `Undo` works as a safety net. A failed `Undo` (`canPerform = false`) indicates an open dialog.
