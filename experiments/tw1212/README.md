# Experiment TW-1212: deleting a range on a single track

**English** · [Español](README.es.md)

**Date:** 2026-11-13.
**Environment:** Cubase Elements 15.0.30, script 1.5.1, saved test project and Object tool.
**Means:** event edge probing (TW-1211) and «Locate Selection / Selection End» to measure the selection. `experiments/tw1211/probe.py` and ad hoc scripts were used.

## Scope of the selections

| Command | Test | Result |
|---|---|---|
| `Select Events under Cursor` | POC-INSTR selected, cursor at 5 s. POC-INSTR has a part from 4 to 6 s; POC-TEST, an event from 2 to 6.8 s | Selection **4–6 s**: **only the selected track** ✅ |
| `Select All on Tracks` | POC-INSTR selected | Selection measured 0–2 s; with POC-TEST it had given 0–2:19.976. Ambiguous, not used |
| `Select Events under Cursor` with no event under the cursor | — | `canPerform = false` |

## Complete flow: delete 2–30 s only on POC-TEST

1. **Splits:** at 2 s and at 30 s: `Select None`, cursor, `Select Events under Cursor` and `Split at Cursor`. POC-TEST's edges become `2.0, 6.0, 6.8, 18.0, 22.0, 30.0, 2:19.976`. POC-INSTR does not change.
2. **Deletions:** at the midpoint of each segment between edges within the range: `Select None`, cursor, `Select Events under Cursor` (if possible) and `Delete`.
3. **A hidden piece:** when the event on top was removed, an edge reappeared at 2.4 s. It was the end of the first event, hidden under the second: the probe does not see the edges of pieces that are completely covered. **Another round** was needed.
4. **Result:**
   - POC-TEST: edges `2.0, 30.0, 2:19.976`, the exact gap ✅;
   - POC-INSTR: `2, 4, 6, 8`, unchanged ✅.
5. **Undo:** **7 steps** (2 splits and 5 deletions) returned POC-TEST exactly to its initial state ✅.

## Conclusions

- **Deleting while leaving a gap** (`delete`) on one track can be done with the Object tool:
  1. split at the ends on that track only;
  2. delete in rounds, probing until nothing is left inside;
  3. verify with the probe.
- **Safety:** before each deletion the selection is measured with «Locate Selection / Selection End». If it goes outside the range, because the split failed, nothing is deleted.
- **Undo** needs several steps. The tool must report how many.
- **Closing the gap** (`delete_time`) or **inserting silence** on a single track would desynchronize that track from the rest. Not offered.

## Implementation and bug found (2026-11-13)

- **First version of the tool:** before each deletion it measured the selection with «Locate Selection End», which **moves the cursor**. With the Cubase preference «seleccionar automáticamente eventos bajo el cursor» (*Auto Select Events under Cursor*), enabled on the user's system, the selection changed to the event starting where the measured one ends, and `Delete` deleted it: **the event from 30 to 139.976 s was lost**.
  - In addition, the tool reported 8 undo steps and 15 were needed.
  - The project was restored by undoing step by step until the original edges were recovered.
- **Diagnosis:** it was repeated step by step, looking at the edges after each action. The 18–22 selection was measured and the event from 22 to 139.976 disappeared.
- **Fix:** after measuring, the tool goes back to the center of the piece and repeats the selection before deleting. The simulator reproduces the preference (`auto_select_under_cursor`) and a test covers both cases.
- **Verification after the fix:** `verified: true`. POC-TEST is left with edges `2.0, 30.0, 2:19.976` and POC-INSTR unchanged. **7** undo steps were reported and **7** were needed. It takes 26 s.
