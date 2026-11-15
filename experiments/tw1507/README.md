# TW-1507 — Setting a noise gate on a speech-like signal

**English** · [Español](README.es.md)

`make_fixture.py` writes `tw1507-fixture.wav` (not committed; run it again to get it): mono, 48 kHz, 24-bit, 30 s; noise at −55 dBFS everywhere; "phrases" of 250 ms syllables with 100 ms gaps, loud at −16 dBFS RMS (2–8 and 20–26 s) and soft at −36 dBFS RMS (11–17 s); pauses with only the noise.

A well-set gate removes the noise in the pauses and keeps both phrases. Run on 2026-11-15 on the test project with Steinberg's `Gate` (threshold −45.5 dB, range −30 dB, hold 50 ms, release 200 ms): noise floor −58.2 → −88.05 dB, soft phrase −40.8 → −40.8 dB, loud phrase −20.9 → −20.9 dB. Details in the verification log.
