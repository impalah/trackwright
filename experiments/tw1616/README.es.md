# TW-1616 — Ducking dentro de Cubase

[English](README.md) · **Español**

Hecho el 2026-11-16 en el proyecto de pruebas (Cubase Elements 15.0.30, 48 kHz, 120 BPM). Primero la parte (b): la envolvente de ducking planificada escrita grabando automatización en tiempo real sobre el **PreGain** de la pista de música (`prefilter.gain`, un parámetro del que la skill podría ser dueña sin tocar el fader de volumen del usuario). La parte (a), un side-chain que monta el usuario, queda pendiente.

## Qué pasó

1. **Controles vinculados a la pista anterior.** Leído justo después de seleccionar `POC-TEST`, `cubase_list_automation_targets` daba el volumen de `POC-TEST ducked` y las inserciones de Stereo Out; una segunda lectura era correcta. Los controles de automatización siguen a una nueva selección un momento después, y las herramientas leían (y podían escribir) los de la pista anterior. Corregido: las herramientas esperan a que el control de volumen lleve el nombre de la pista, o se detienen con `CONTROLS_NOT_BOUND` (es también TW-1635 (2)).
2. **Una curva grabada que no suena.** La envolvente grabada en `POC-TEST` (14 puntos, 1.255 valores escritos, `complete: true`) se exportó plana a −10 dB: tras grabar, la herramienta devolvía la lectura (R) a su estado anterior, desactivada, así que Cubase tocaba el último valor del parámetro. Con R activada, la curva sonó (la recuperación en 67,6–68,8 s llegó a 0 dB). Corregido: R queda activada tras una grabación, y el resultado lo indica (`read_automation`). Era TW-1635 (1).
3. **PreGain está antes de las inserciones.** En `POC-TEST` las partes planas a −10 dB se exportaron entre −7 y −9 dB: su Compressor (umbral −20 dB, ratio 2:1, make-up automático) comprime menos cuando PreGain baja el nivel, y devuelve parte. El ducking sobre PreGain solo es exacto en una pista sin dinámica después.
4. **Ninguna grabación en una pista creada durante la sesión.** En `TW1616 signal`, una pista estéreo creada hoy con un archivo de ruido rosa de 140 s (−20 dBFS RMS) y sin plugins, una envolvente de 54 puntos (1.252 valores escritos) no dejó ninguna automatización: la exportación es igual al origen hasta 0,00 dB, y el usuario no encontró carril de PreGain en ninguna pista. Una sonda (`probe_binding.py`) mostró que el control de PreGain sí mueve el PreGain de esa pista (0,5 → 0,4479, ninguna otra), así que el vínculo es correcto; una curva corta con `verify` leyó 0 dB donde se escribieron −10 dB (`verified: false`). La misma curva corta en `TW1501` (una pista más antigua, sin carril de PreGain antes) se grabó y verificó a −10,0 dB. Así que no hace falta que exista un carril; lo que cambia es que `TW1616 signal` se creó después de cargarse el script. Para confirmarlo: recargar los scripts de MIDI Remote y repetir la curva corta en `TW1616 signal`.

## Archivos

- `measure.py`: la ganancia que aplicó una exportación, ventana a ventana, frente al plan (retardo, error en las partes planas, transiciones).
- `probe_binding.py`: qué PreGain de pista mueve el control de automatización una vez seleccionada una pista (sin reproducir, con el valor devuelto).
