# Experiment TW-1205: plugin presets

**English** · [Español](README.es.md)

**Date:** 2026-11-13.
**Environment:** Cubase Elements 15.0.30, script 1.5.5 and Compressor in slot 1 of POC-TEST.
**Method:**
- the 15 parameters of the Compressor (without meters) were saved;
- they were compared after each command;
- at the end they were restored by writing them one by one (final difference: **none**) and the editor was closed.

## Opening the editor

The slot has the parameter **«Edición»** (*Edit*) (tag 4101): writing 1 opens the plugin editor and 0 closes it. The readback gives «Activ.» / «Desact.» (*On* / *Off*) ✅.

## `Preset / Next` and `Previous`

| Case | Result |
|---|---|
| Editor opened by the API and **no preset loaded** (original state) | `canPerform = true`, **no changes** |
| The user focuses the window and picks a preset by mistake | Threshold −13.9 dB, Ratio 5.2:1… |
| **Next** with the window focused | ✅ 5 parameters change (Threshold −33.0 dB, Ratio 2.44:1, Attack 3.8 ms, Release 437 ms, Analysis 100 %) |
| **Previous** | ✅ Returns exactly to the previous values |
| Next with the editor **closed** | No changes |
| Next with the editor **opened by the API, no click**, with a preset loaded | ✅ Changes; Previous undoes it exactly |

## Tool validation and actual cause (2026-11-13)

- **First attempt with the tool:** no changes, also with a freshly chosen preset and with a 1 s wait after opening the editor.
- **Cause:** the commands act on the plugin window that has the **keyboard focus**. The case that worked (editor reopened by the API) came from an earlier click by the user on that window.
- **Confirmation:**
  1. editor opened by the API and a click by the user: Next changes 8 parameters and Previous returns them exactly;
  2. closed and reopened by the API, without a new click: Next keeps working.
- **Final design:** if nothing changes, `awaiting_user`, with the editor open and a request for a click. The next call works.
- **Preset name:** it is not in the API (the only mention of “preset” is the control room downmix) nor in the plugin or the slot. It can only be checked that it changed.
- **Restoration:** the Compressor was left with the 15 original values (difference: none) and with the editor closed.

## Conclusions

- The commands act on the **plugin editor with the keyboard focus**: a click by the user is needed the first time. With the editor closed they do nothing.
- **Without a loaded preset they do nothing:** the user must have previously chosen a preset in the plugin window. This is the most likely explanation of the first attempt.
- The change is verified by comparing the plugin parameters before and after.
- The preset **cannot be chosen by name** nor can its name be read: only stepping forward or backward.
- With several editors open, it is not known which one it applies to. The tool must work with only one.
