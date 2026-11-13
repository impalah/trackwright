# Experiment TW-1209: project properties

**English** · [Español](README.es.md)

**Date:** 2026-11-13.
**Environment:** Cubase Elements 15.0.30, script 1.4.0 and test project.
**Scope:** everything read-only, except moving the cursor in step 2, which was restored afterwards. There was no need to install an experiment script.

## 1. Project folder with `lsof` (with the user's permission)

- **Cubase does not keep the `.cpr` open** (0 matches): it reads it on opening and closes it.
- **The project's audio files do stay open**, in `<project folder>/Audio/`. The folder comes from there: `/Volumes/Data/Produccion/Cubase/X0001.test`.
- **Limits:**
  - it does not give the exact name of the `.cpr`;
  - in a project without audio nothing is seen;
  - with several projects open, several folders would appear.
- The contents of the folder were not listed.

## 2. Time signature deduced by normalizing positions (cursor moved and restored)

| Requested position | Cubase leaves it at | Conclusion |
|---|---|---|
| `1. 5. 1. 0` | `2. 1. 1. 0` | 4 beats per bar |
| `1. 4. 1. 0` | `1. 4. 1. 0` | Beat 4 exists |
| `1. 1. 5. 0` | `1. 2. 1. 0` | 4 sixteenths per beat: the beat is a quarter note, denominator 4 |
| `1. 7. 1. 0` | `2. 3. 1. 0` | Consistent with 4/4 |
| `1. 1. 1. 300` | `1. 1. 3. 60` | 120 ticks per sixteenth |
| `1. 1. 1. 500` | `1. 2. 1. 20` | Same |

It works, but step 3 makes it unnecessary.

## 3. DirectAccess objects outside the mixer

`da.object` accepts any ID. The children of «Device Root» (ID 1) include studio and project objects, **read without writing anything**.

### «Transporte» (*Transport*) (`type: Transport`, ID 18 in this session; 101 parameters)

| Tag | Title | Value read |
|---|---|---|
| 4027 | `signature` | **«4/4»** |
| 4022 | `cycle` | Desact. (*Off*) |
| 4099 | `metronomeOn` | Desact. (*Off*) |
| 4100 | `precountOn` | Desact. (*Off*) |
| 4020 / 4021 | `punchIn` / `punchOut` | Desact. (*Off*) |
| 4028 / 4029 | `punchInTime` / `punchOutTime` | 2. 1. 1. 0 / 4. 1. 1. 0 |
| 4030 / 4031 / 4051 | `cycleLeftTime` / `cycleRightTime` / `cycleDuration` | 2. 1. 1. 0 / 4. 1. 1. 0 / 2. 0. 0. 0 |
| 4032 / 4033, 4037 / 4038 | `preRoll` / `postRoll`, `usePreRoll` / `usePostRoll` | 0 / Desact. (*Off*) |
| 4023 / 4101 | `time` / `time2` | 1. 1. 1. 0 / 0:00:00.000 (**the second display does give seconds here**) |
| 4025 / 4102 | `timeFormat` / `timeFormat2` | Compases+Tiempos / Segundos (*Bars+Beats* / *Seconds*) |
| 4129, 4121, 4106, 4107, 4108 | Recording modes | Punch in/out, Mantener historial, Nuevas partes, Mix, Iniciar en cursor (*Punch in/out, Keep History, New Parts, Mix, Start at Cursor*) |
| 4145 / 4150 | `startPlayModes` / `returnOnStop` | Inicio desde posición / Desact. (*Start from position* / *Off*) |
| 4015 / 4016 / 4019 | `start` / `stop` / `record` | Transport state (stop = Activ. (*On*)) |
| 4098 | `message` | OFFLINE |

### Other objects

- **«Metronome»** (`type: Metronome`): `clickLevel` 127, `tickInRecord` Desact. (*Off*) and `tickInPlayback` Desact. (*Off*). The latter is the “click during playback”.
- **«Sistema de audio»** (*Audio System*): its only child is the audio interface, with no parameters. **It is not touched** (rule of not controlling audio interfaces).
- **No trace in any object** (IDs 0–699) of the sample rate, the resolution, the frame rate, the project length or its name.

## 4. Verification with 3/4 (changed by the user in the transport bar)

- **`signature`** (tag 4027) = **«3/4»**. The process value is 1966.12 (with 4/4 it was 2621.48): an internal encoding, so the displayed text is used.
- **Cursor normalization:** `1. 4. 1. 0` → `2. 1. 1. 0` (3 beats), `1. 3. 1. 0` stays and `1. 1. 5. 0` → `1. 2. 1. 0` (denominator 4). **It matches.**
- **Unverified:** the behavior with time signature changes in the middle of the project, because there is no signature track.

## Conclusions

1. **TW-1209 can be implemented without a new script,** with `da.params` on the Transport and Metronome objects. They are located **by type** among the children of Device Root, because the IDs change between sessions.
2. **Time signature:** the `signature` parameter gives it directly, verified with 4/4 and 3/4. It remains to be seen whether it follows the cursor when there are time signature changes.
3. **TW-1210:** the Transport parameters (`cycle`, `metronomeOn`, `precountOn`, `punchIn`…) are candidates to be written with `da.param.set` and read back. **Untested:** writing is part of TW-1210.
4. **Sample rate, length and name:** not accessible through the API. For the folder, `lsof`, with its limits.
