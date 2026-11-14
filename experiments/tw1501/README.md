# TW-1501 — Exporting one track from Cubase Elements

**English** · [Español](README.es.md)

Question: can an export be used to analyze one track, aligned with the project? Checked on 2026-11-14 on the test project (Cubase Elements 15.0.30, 48 kHz, 120 BPM).

## Setup

- `make_fixture.py` writes `tw1501-fixture.wav` (not committed; run it again to get it): mono, 48 kHz, 24-bit, 30 s; noise at −60 dBFS everywhere; a 1 ms click at 1.000 s; a 440 Hz tone at −12 dBFS RMS at 2–6, 10–12, 13–17 and 22–25 s.
- The user created a mono audio track `TW1501` and imported the file with the cursor at 4.000 s (bar 3).
- `TW1501` in solo through `cubase_set_track_mix` (read back), then `cubase_export_mix` start with 2–36 s; the user exported Stereo Out as WAV, 48 kHz, 32-bit float, interleaved; `confirm` found `tw1501-a.wav`, 34 s, difference 0. Solo undone afterwards (read back).
- `measure.py` (numpy and soundfile through `uv run --with`): `results-a.json`.

## What the dialog offers (Elements 15)

- **Exportar canal: only Stereo Out.** One track is isolated with solo.
- Types: WAV, AIFF, MP3, FLAC, Ogg Vorbis. WAV: 8, 16, 24, 32-bit, 32-bit float and 64-bit float; 8 to 192 kHz; interleaved or split.
- Name, path and conflicts ("always ask"); options for Broadcast Wave, markers and iXML; real-time export off by default.

## Results

- **Alignment exact:** the click at 3.000 s into the file, as expected (4 + 1 − 2); error **0 samples**. Project time = left locator + file time.
- **Duration exact:** 34.000 s for 2–36 s.
- **Stereo, −3 dB:** the mono track reaches Stereo Out on both channels 3 dB lower (peak −3.1 dBFS, tone −15 dBFS RMS instead of −12): the pan law of a centered mono channel. Levels in the export are not the levels of the source file.
- **Silences in the right place:** the quiet spans in the file (8–12, 14–15, 19–24 s) are the fixture's 6–10, 12–13 and 17–22 s.
- **Digital silence outside the event:** 0–2 s and 32–34 s of the file (before and after the event) are exact zeros. The 10th percentile of the window levels gave −240 dBFS: a noise floor estimate must ignore digital silence.

## Consequences for TW-1503 and TW-1504

- Analyze a Stereo Out export of the track in solo, between the locators; convert with `project = locator + file time`.
- Use thresholds relative to the measured noise floor; absolute dBFS values depend on the pan law, faders, inserts and the output bus.
- Exclude digital silence (all-zero windows) from the noise floor, and report it as silence.
- 32-bit float WAV at the project's rate is the format to ask the user for.

## Not measured

Whether the channel fader and insert plugins change the levels was not measured separately. A mixdown goes through them, so they are expected to; with relative thresholds it does not change the plan.
