# TW-1612 — Alcanzar un objetivo de sonoridad en Cubase Elements

[English](README.md) · **Español**

Hecho el 2026-11-16 en el proyecto de pruebas (Cubase Elements 15.0.30, 48 kHz) con un episodio entero: la exportación de 46 minutos del episodio E0004 del usuario (`Pod Mic` sola, solo lectura), importada sin copiar en una pista estéreo `TW1612 episode` en 0 s. Cada exportación fue esa pista sola (`cubase_export_mix` con `solo`, todos los solos restaurados), 0–2773,85 s, por el usuario; cada medida, con `cubase_measure_loudness`. Stereo Out tenía el Brickwall Limiter en la ranura 1 (Threshold −1,0 dB, Release 5 ms, Auto Release desactivado, DIC activado).

| Pasada | Stereo Out | Formato | Integrada | Pico real | Pico de muestra |
|---|---|---|---|---|---|
| origen | — | WAV (la exportación de E0004) | −10,56 LUFS | +0,30 dBTP | −0,30 dBFS |
| R0 | fader 0 dB | WAV 32 bits float | −10,75 LUFS | −0,77 dBTP | −1,01 dBFS |
| R1 | fader −5,25 dB | WAV 32 bits float | **−16,00 LUFS** | −6,02 dBTP | −6,26 dBFS |
| R2 | fader −5,25 dB | MP3 128 kbps, 44,1 kHz | −16,04 LUFS | −5,24 dBTP | −5,98 dBFS |
| R3 | fader +3 dB, segundo limitador en la ranura 7 (−1 dB) | WAV 32 bits float | −8,95 LUFS | −0,77 dBTP | −1,01 dBFS |
| R4 | como R3 | MP3 128 kbps, 44,1 kHz | −8,98 LUFS | **+0,05 dBTP** | −0,55 dBFS |

## Qué muestra

1. **Una pasada basta para alcanzar un objetivo bajando:** el fader mueve la sonoridad integrada exactamente lo que vale su ganancia (R0 −10,75 + −5,25 = R1 −16,00). Medir, poner el fader en objetivo − medido, exportar: hecho.
2. **La ranura 1 está antes del fader y la 7 después.** En R1 los picos son los de R0 menos 5,25 dB (−1,01 → −6,26): el limitador de la ranura 1 actuó primero y el fader bajó todo después, así que un limitador en las ranuras 1–6 no es un techo en cuanto el fader sube el nivel. En R3 (fader +3 dB) el pico de muestra se quedó en −1,01 dBFS: el limitador de la ranura 7 está después del fader y mantiene el techo.
3. **El Brickwall Limiter deja pasar unos 0,24 dB de picos entre muestras** incluso con DIC activado: −0,77 dBTP con un umbral de −1,0 dB (R0, R3).
4. **El MP3 sube el pico real:** +0,78 dB en la mezcla sin limitar (R1 → R2), +0,82 dB en la limitada (R3 → R4), donde el resultado pasó de 0 dBTP. La sonoridad solo se movió 0,03–0,04 LU.
5. **Limitar cuesta sonoridad:** R3 sería −7,75 LUFS sin limitador (R0 + 3 dB) y midió −8,95: 1,2 LU que se llevó el limitador de la ranura 7. En R0 el limitador de la ranura 1 cambió el 43,6 % de las muestras (Release de 5 ms tras cada una de las 167.753 muestras del origen por encima de −1 dBFS), con una diferencia de hasta −17,5 dBFS.
6. **La duración de un MP3 según afinfo es una estimación:** 2767,55 s para un archivo que decodificado dura 2773,92 s (el rango más 66 ms de relleno del codificador). `cubase_export_mix` daba las exportaciones MP3 por 6,3 s más cortas; corregido: las duraciones salen ahora de la cabecera con soundfile.

## Consecuencias para `podcast-delivery` (TW-1613)

- Ganancia en el fader de Stereo Out, calculada a partir de una exportación WAV: objetivo − medido.
- Un techo va en una **ranura posterior al fader (7 u 8)**, nunca en las ranuras 1–6.
- Para un techo de −1 dBTP en el MP3 entregado, el umbral del limitador necesita alrededor de 1,1 dB de margen (0,24 dB de picos entre muestras más unos 0,8 dB de la codificación): unos −2,1 dB, y después **medir el propio MP3** y bajarlo si hace falta. El margen es de este episodio y este ajuste del codificador; otro puede ser distinto.
- Cuando el fader baja el nivel, como aquí, los picos quedan por debajo del techo y el limitador no hace falta.
