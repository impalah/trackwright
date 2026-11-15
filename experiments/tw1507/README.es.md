# TW-1507 — Ajustar una puerta de ruido sobre una señal parecida a la voz

[English](README.md) · **Español**

`make_fixture.py` escribe `tw1507-fixture.wav` (no se guarda en el repositorio; se vuelve a generar ejecutándolo): mono, 48 kHz, 24 bits, 30 s; ruido a −55 dBFS en todo el archivo; «frases» de sílabas de 250 ms con huecos de 100 ms, fuertes a −16 dBFS RMS (2–8 y 20–26 s) y suave a −36 dBFS RMS (11–17 s); pausas solo con el ruido.

Una puerta bien ajustada quita el ruido de las pausas y conserva las dos frases. Probado el 2026-11-15 en el proyecto de pruebas con `Gate` de Steinberg (umbral −45,5 dB, rango −30 dB, hold 50 ms, release 200 ms): ruido de fondo −58,2 → −88,05 dB, frase suave −40,8 → −40,8 dB, frase fuerte −20,9 → −20,9 dB. Detalles en el registro de verificación.
