# Experiment TW-1204: exporting the mix

**English** · [Español](README.es.md)

**Date:** 2026-11-13.
**Environment:** Cubase Elements 15.0.30, script 1.5.2 and test project.

## Results

1. **`File / Export Audio Mixdown`:**
   - `canPerform = true`;
   - opens the «Exportar mezcla de audio» (*Export Audio Mixdown*) dialog (class **dialog**);
   - with the dialog open, the script keeps responding and `Undo` reports `canPerform = false`.
2. **Dialog, in Elements and according to the user's screenshot:**
   - **channel:** Stereo Out;
   - **name:** the project's (`TEST`);
   - **path:** `<project folder>/Mixdown`;
   - **proposed format:** MP3, 44.1 kHz, 128 kB/s;
   - **conflicts:** «Preguntar siempre» (*Always ask*);
   - **there is no range field:** it exports between the locators.
3. **Export with the locators at 2–30 s** (set by Trackwright in seconds): `Mixdown/TEST.mp3`, 447 986 bytes and **27.99 s** (`afinfo`), which are the 28 s of the range ✅.
4. **Full project:** `Edit / Select All`, `Transport / Locators to Selection` and `Select None` leave the locators at `1. 1. 1. 0` – `70. 4. 4. 97`, that is, 0 → 2:19.976 s, the end of the last event ✅. No changes to the project.

## Conclusions for `cubase_export_mix`

- **`start` phase:**
  1. place the locators on the requested range, or on all the audio;
  2. open the dialog;
  3. return `awaiting_user`, with the expected folder (`<project>/Mixdown`, deduced with `lsof`), the expected duration and the timestamp.
- **`confirm` phase:** look in the folder for audio files created after that timestamp and check their duration (`afinfo`). Only name, size, date and duration are read.
- **Trackwright never exports:** the user chooses the format and presses «Exportar audio» (*Export Audio*).

## User test with `cubase_export_mix` (full episode)

- **Result:** `Mixdown/TEST.mp3` (overwritten), 2 235 665 bytes and **139.721 s**, for a range of 139.976 s (−0.255 s). The size corroborates it: 2 235 665 × 8 / 128 000 = 139.73 s.
- **Cause:** the duration of an MP3 is an estimate and the encoder loses or gains frames at the end. With the ±0.15 s tolerance, the confirmation would have given `verified: false`.
- **Fix:** tolerance of ±(0.5 s + 0.2 %) for MP3, AAC and OGG, and `difference_seconds` in the output.
