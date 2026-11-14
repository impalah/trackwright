# TW-1501 — Exportar una sola pista desde Cubase Elements

[English](README.md) · **Español**

Pregunta: ¿se puede usar una exportación para analizar una pista, alineada con el proyecto? Comprobado el 2026-11-14 en el proyecto de pruebas (Cubase Elements 15.0.30, 48 kHz, 120 BPM).

## Montaje

- `make_fixture.py` escribe `tw1501-fixture.wav` (no se guarda en el repositorio; se vuelve a generar ejecutándolo): mono, 48 kHz, 24 bits, 30 s; ruido a −60 dBFS en todo el archivo; un clic de 1 ms en 1,000 s; un tono de 440 Hz a −12 dBFS RMS en 2–6, 10–12, 13–17 y 22–25 s.
- El usuario creó una pista de audio mono `TW1501` e importó el archivo con el cursor en 4,000 s (compás 3).
- `TW1501` en solo con `cubase_set_track_mix` (releído), luego `cubase_export_mix` start con 2–36 s; el usuario exportó Stereo Out en WAV, 48 kHz, 32 bits float, intercalado; `confirm` encontró `tw1501-a.wav`, 34 s, diferencia 0. Solo deshecho después (releído).
- `measure.py` (numpy y soundfile con `uv run --with`): `results-a.json`.

## Qué ofrece el diálogo (Elements 15)

- **Exportar canal: solo Stereo Out.** Una pista se aísla con solo.
- Tipos: WAV, AIFF, MP3, FLAC, Ogg Vorbis. WAV: 8, 16, 24, 32 bits, 32 bits float y 64 bits float; de 8 a 192 kHz; intercalado o separado.
- Nombre, ruta y conflictos («preguntar siempre»); opciones de Broadcast Wave, marcadores e iXML; exportación en tiempo real desactivada por defecto.

## Resultados

- **Alineación exacta:** el clic a 3,000 s del inicio del archivo, como se esperaba (4 + 1 − 2); error de **0 muestras**. Tiempo del proyecto = localizador izquierdo + tiempo del archivo.
- **Duración exacta:** 34,000 s para 2–36 s.
- **Estéreo, −3 dB:** la pista mono llega a Stereo Out por los dos canales 3 dB más baja (pico −3,1 dBFS, tono a −15 dBFS RMS en vez de −12): la ley de panorama de un canal mono centrado. Los niveles de la exportación no son los del archivo de origen.
- **Silencios en su sitio:** los tramos silenciosos del archivo (8–12, 14–15, 19–24 s) son los 6–10, 12–13 y 17–22 s del archivo de prueba.
- **Silencio digital fuera del evento:** 0–2 s y 32–34 s del archivo (antes y después del evento) son ceros exactos. El percentil 10 de los niveles de las ventanas dio −240 dBFS: una estimación del ruido de fondo debe ignorar el silencio digital.

## Consecuencias para TW-1503 y TW-1504

- Analizar una exportación de Stereo Out con la pista en solo, entre los localizadores; convertir con `proyecto = localizador + tiempo del archivo`.
- Usar umbrales relativos al ruido de fondo medido; los valores absolutos en dBFS dependen de la ley de panorama, los faders, las inserciones y el bus de salida.
- Excluir el silencio digital (ventanas todo ceros) del ruido de fondo, y contarlo como silencio.
- WAV de 32 bits float a la frecuencia del proyecto es el formato que hay que pedir al usuario.

## Sin medir

No se midió por separado si el fader del canal y los plugins de inserción cambian los niveles. Una mezcla pasa por ellos, así que se espera que sí; con umbrales relativos no cambia el plan.
