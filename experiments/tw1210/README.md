# Experiment TW-1210: modifying project properties

**English** · [Español](README.es.md)

**Date:** 2026-11-13.
**Environment:** Cubase Elements 15.0.30 and script 1.5.4.
**Method:** `da.param.set` on the «Transporte» (*Transport*) and «Metronome» objects (TW-1209). Each value was read, the opposite was written, read back and restored.

## Switches (all ✅: write, readback and restore)

| Object | Parameter (tag) | Desact. → Activ. → Desact. (*Off → On → Off*) |
|---|---|---|
| Transport | `cycle` (4022) | ✅ |
| Transport | `metronomeOn` (4099) | ✅ |
| Transport | `precountOn` (4100) | ✅ |
| Transport | `punchIn` (4020) / `punchOut` (4021) | ✅ / ✅ |
| Transport | `usePreRoll` (4037) / `usePostRoll` (4038) | ✅ / ✅ |
| Metronome | `tickInPlayback` / `tickInRecord` | ✅ / ✅ |

## Continuous values

| Parameter | Written | Displayed | Conclusion |
|---|---|---|---|
| `clickLevel` (Metronome) | 0.5 / 0 | «64» / «0» | Scale 0–127 = value × 127 ✅ (restored to 127) |
| `preRoll` (Transport) | 0.1 / 0.5 | «1. 2. 0. 0» / «7. 2. 0. 0» | 6 and 30 beats: beats = value × 60? **Few points measured: left out** |
| `postRoll` (Transport) | 0.1 | «1. 2. 0. 0» | Same as the pre-roll |

- **Time signature** (`signature`): its internal value is not in [0, 1] (2621.48 with 4/4) and the script rejects writes outside that range. **It is not written.** It is changed in «Configuración del proyecto» (*Project Setup*) or in the transport bar, as the user did.

## Conclusion

`cubase_set_project` can change, with dry run and readback:
- cycle, metronome, precount, punch in/out and use of pre-roll and post-roll;
- click during playback and during recording;
- click level.
