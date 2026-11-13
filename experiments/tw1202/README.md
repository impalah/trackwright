# Experiment TW-1202: saving the project

**English** · [Español](README.es.md)

**Date:** 2026-11-13.
**Environment:** Cubase Elements 15.0.30, script 1.5.3 and test project `TEST`, with the user's explicit authorization to save it.
**Verification:** names, sizes and dates of the `.cpr` files in the project folder (deduced with `lsof`). No file was opened.

| Step | Before | After |
|---|---|---|
| `File / Save` (13:58:16) | `TEST.cpr`, 227 194 bytes, 2026-11-12 20:54:01 | `TEST.cpr`, 228 091 bytes, **13:58:17**. No `.bak` (the user's Cubase does not make a backup copy on save) |
| `File / Save New Version` (13:58:26) | — | New **`TEST-01.cpr`**, 228 094 bytes, 13:58:27. `TEST.cpr` unchanged |

- **`canPerform`** for both commands: `true`. They act without the script stopping responding (class *direct* on an already saved project).
- **After `Save New Version`,** Cubase works on the new file: subsequent `Save` operations will go to `TEST-01.cpr`.
- **Not tested:** `Save` on a project that has **never been saved**. Presumably it opens «Guardar como» (*Save As*) (a dialog).

## Design of `cubase_save_project`

- **Modes:** `save` and `new_version`.
- **Its own permission** (`[writes] save = true`, disabled by default) in addition to writes, and `dry_run` by default.
- **Verification:** some `.cpr` in the project folder with a date later than the command. With `new_version`, a new one.
- **If none appears within a few seconds:** `awaiting_user`, because there may be a dialog, as in an unsaved project.
- **Out of scope:** `Close`, `Revert` and `Quit`. They are not offered.
