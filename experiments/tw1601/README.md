# TW-1601 — What Cubase Elements offers for the podcast skills

**English** · [Español](README.es.md)

Checked on 2026-11-15 on the test project (Cubase Elements 15.0.30, 48 kHz, 120 BPM), part by Trackwright and part by the user in Cubase's windows. `measure_steps.py` measures the exports (numpy and soundfile).

| # | Question | Answer |
|---|---|---|
| 1 | Plugins on Stereo Out | **Yes.** Brickwall Limiter inserted in slot 1 of Stereo Out; its parameters: Threshold (tag 4201, the output ceiling), Release, Auto Release, Link and **DIC** (detect intersample clipping, on by default). Threshold set to −1.0 dB and read back. |
| 2 | Side-chain | The Compressor's 46 parameters include **nothing about side-chain** (the Gate does have `SCOn` and a detector filter). In its window, Elements **does** have the side-chain button, and the source can be chosen among the project's tracks (seen by the user). Routing stays out of the API's reach: a Cubase-side ducking needs the user to set the source. |
| 3 | Automation precision | Values are written every ~107 ticks (~110 ms, the script's idle tick). Steps land **~0.1 s late**: read at the cursor, −11.3 dB at 7.2 s for a drop requested at 7.0–7.125 s and −4.5 dB at 8.7 s for a recovery requested at 8.5–8.625 s; in an export, the midpoints at 7.185 s and 8.655 s. The tool's read-back reported `verified: false` (its own readings arrive one tick late). **Open:** the first export after recording was flat, with the fader left at −1.43 dB instead of the last point's 0 dB; a second export, after the user checked that the curve existed and R was on, had the drop. The cause was not observed. |
| 4 | Automatable channel parameters | Volume, pan, sends 1–4, the four EQ bands, and the input filter: **PreGain** (`prefilter.gain`, dB, exact conversion), low cut, high cut. PreGain is a candidate for a parameter a Cubase-side ducking mode can own. |
| 5 | Fade and repeat commands | In Key Commands (Spanish UI, seen by the user): no "fade in/out to cursor". Audio: Abrir editor de fundidos, **Ajustar fundidos al rango** (key A), Aumentar/Disminuir longitud del fundido de entrada/salida, Cerrar huecos (fundido cruzado), Eliminar fundidos, **Fundido cruzado** (X). Proceso: Fundido de entrada, Fundido de salida. Edición: **Repetir** (Cmd+K), **Duplicar** (Cmd+D). None is bound by the script today; binding them is a script change (TW-1626). |
| 6 | MP3 and AAC | MP3 export defaults: 44.1 kHz, 128 kbps (192 kbps available). soundfile decodes Cubase's MP3 (44.1 kHz; 4.075 s decoded for a 4 s range, afinfo says 4.066 s: encoder padding). On a −13 dBFS tone the true peak rose 0.1 dB (not representative of speech). **No AAC** in Elements' export: AAC would be encoded with macOS `afconvert`. |
| 7 | Importing a Trackwright render | A WAV written to `Trackwright/renders/` and imported at 40 s on `TW1507` landed at **40.000–43.000 s** (event edges). Import options: "Copiar archivo a carpeta del proyecto" (on by default: the file is copied to `Audio/`), sample rate conversion (not needed), bit depth 32 float → 24 (off by default). |
| 8 | A/B listening | `transport.start` with a cycle (7–12 s of `TW1507`), the Gate's Bypass toggled five times while playing, each write read back in 0.71–0.79 s, `transport.stop`. The user heard the noise come back when bypassed, **without clicks**. |

## Consequences for E16

- Delivery (TW-1612, TW-1613): a limiter can go on Stereo Out and be set; its DIC option suits a true-peak ceiling. MP3 at the profile's bitrate is chosen by the user in the dialog; AAC goes through `afconvert`.
- Ducking (TW-1616): real-time automation is ~0.1 s late and quantized to ~110 ms: acceptable for slow moves (a pre-roll can compensate), not for edits; the side-chain mode needs the user to pick the source. The offline path stays first.
- Render and re-import (TW-1606): placement exact to the millisecond of the edge probe; renders already live in the project folder, so the skill asks to untick "copy to project folder" to avoid a second copy, and to keep 32-bit float.
- Fades (TW-1626): "Ajustar fundidos al rango" with the range selection that range edits already use is the candidate for fades at cut points; "Duplicar" and "Repetir" for beds made in Cubase.
- Voice tone and cleanup (TW-1625): A/B by cycle playback and Bypass works and is click-free.
- `cubase_record_automation` (TW-1635): the flat first export and the dry run's title of another track need a fix.
