# TW-1612 — Reaching a loudness target in Cubase Elements

**English** · [Español](README.es.md)

Run on 2026-11-16 in the test project (Cubase Elements 15.0.30, 48 kHz) with a whole episode: the 46-minute export of the user's episode E0004 (`Pod Mic` alone, read-only), imported without copying on a stereo track `TW1612 episode` at 0 s. Every export was that track alone (`cubase_export_mix` with `solo`, every solo restored), 0–2773.85 s, by the user; every measurement by `cubase_measure_loudness`. Stereo Out had the Brickwall Limiter in slot 1 (Threshold −1.0 dB, Release 5 ms, Auto Release off, DIC on).

| Run | Stereo Out | Format | Integrated | True peak | Sample peak |
|---|---|---|---|---|---|
| source | — | WAV (the E0004 export) | −10.56 LUFS | +0.30 dBTP | −0.30 dBFS |
| R0 | fader 0 dB | WAV 32-bit float | −10.75 LUFS | −0.77 dBTP | −1.01 dBFS |
| R1 | fader −5.25 dB | WAV 32-bit float | **−16.00 LUFS** | −6.02 dBTP | −6.26 dBFS |
| R2 | fader −5.25 dB | MP3 128 kbps, 44.1 kHz | −16.04 LUFS | −5.24 dBTP | −5.98 dBFS |
| R3 | fader +3 dB, second limiter in slot 7 (−1 dB) | WAV 32-bit float | −8.95 LUFS | −0.77 dBTP | −1.01 dBFS |
| R4 | as R3 | MP3 128 kbps, 44.1 kHz | −8.98 LUFS | **+0.05 dBTP** | −0.55 dBFS |

## What it shows

1. **One round is enough to reach a target by lowering:** the fader moves the integrated loudness by exactly its gain (R0 −10.75 + −5.25 = R1 −16.00). Measure, set the fader to target − measured, export: done.
2. **Slot 1 is before the fader, slot 7 after it.** In R1 the peaks are R0's minus 5.25 dB (−1.01 → −6.26): the slot 1 limiter acted first and the fader lowered everything after it, so a limiter in slots 1–6 is no ceiling once the fader raises the level. In R3 (fader +3 dB) the sample peak stayed at −1.01 dBFS: the limiter in slot 7 is after the fader and holds the ceiling.
3. **The Brickwall Limiter lets about 0.24 dB of intersample peaks through** even with DIC on: −0.77 dBTP with a −1.0 dB threshold (R0, R3).
4. **MP3 raises the true peak:** +0.78 dB on the unlimited mix (R1 → R2), +0.82 dB on the limited one (R3 → R4), where the result went over 0 dBTP. Loudness moved by 0.03–0.04 LU only.
5. **Limiting costs loudness:** R3 would be −7.75 LUFS without the limiter (R0 + 3 dB) and measured −8.95: 1.2 LU taken by the slot 7 limiter. In R0 the slot 1 limiter changed 43.6 % of the samples (Release 5 ms after each of the 167,753 source samples above −1 dBFS), by up to −17.5 dBFS of difference.
6. **afinfo's MP3 duration is an estimate:** 2767.55 s for a file that decodes to 2773.92 s (the range plus 66 ms of encoder padding). `cubase_export_mix` reported the MP3 exports as 6.3 s short; fixed: durations now come from the header through soundfile.

## Consequences for `podcast-delivery` (TW-1613)

- Gain on Stereo Out's fader, computed from a WAV export: target − measured.
- A ceiling goes in a **post-fader slot (7 or 8)**, never in slots 1–6.
- For a ceiling of −1 dBTP in the delivered MP3, the limiter's threshold needs about 1.1 dB of margin (0.24 dB of intersample peaks plus about 0.8 dB from the encoding): about −2.1 dB, then **measure the MP3 itself** and lower it if needed. The margin is from this episode and this encoder setting; another one may differ.
- When the fader lowers the level, as here, the peaks stay under the ceiling and the limiter is not needed.
