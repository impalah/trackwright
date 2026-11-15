# TW-1601 — Lo que ofrece Cubase Elements para las skills de podcast

[English](README.md) · **Español**

Comprobado el 2026-11-15 en el proyecto de pruebas (Cubase Elements 15.0.30, 48 kHz, 120 BPM), en parte por Trackwright y en parte por el usuario en las ventanas de Cubase. `measure_steps.py` mide las exportaciones (numpy y soundfile).

| # | Pregunta | Respuesta |
|---|---|---|
| 1 | Plugins en Stereo Out | **Sí.** Brickwall Limiter insertado en el slot 1 de Stereo Out; sus parámetros: Threshold (tag 4201, el techo de salida), Release, Auto Release, Link y **DIC** (detección de clipping entre muestras, activado por defecto). Threshold fijado a −1,0 dB y releído. |
| 2 | Cadena lateral | Los 46 parámetros del Compressor **no incluyen nada de cadena lateral** (el Gate sí tiene `SCOn` y un filtro del detector). En su ventana, Elements **sí** tiene el botón de cadena lateral, y la fuente se elige entre las pistas del proyecto (visto por el usuario). El enrutamiento sigue fuera del alcance de la API: un ducking dentro de Cubase necesita que el usuario elija la fuente. |
| 3 | Precisión de la automatización | Los valores se escriben cada ~107 ticks (~110 ms, el tick de reposo del script). Los escalones llegan **~0,1 s tarde**: leídos en el cursor, −11,3 dB a 7,2 s para una bajada pedida en 7,0–7,125 s y −4,5 dB a 8,7 s para una subida pedida en 8,5–8,625 s; en una exportación, los puntos medios en 7,185 s y 8,655 s. La relectura de la herramienta dio `verified: false` (sus propias lecturas llegan un tick tarde). **Abierto:** la primera exportación tras grabar salió plana, con el fader en −1,43 dB en lugar de los 0 dB del último punto; una segunda exportación, después de que el usuario comprobara que la curva existía y R estaba activado, sí tenía la bajada. No se observó la causa. |
| 4 | Parámetros del canal automatizables | Volumen, panorama, envíos 1–4, las cuatro bandas de EQ y el filtro de entrada: **PreGain** (`prefilter.gain`, dB, conversión exacta), corte de graves, corte de agudos. PreGain es candidato a parámetro propio de un modo de ducking dentro de Cubase. |
| 5 | Comandos de fundido y repetición | En Comandos de teclado (Cubase en castellano, visto por el usuario): no hay «fundido de entrada/salida hasta el cursor». Audio: Abrir editor de fundidos, **Ajustar fundidos al rango** (tecla A), Aumentar/Disminuir longitud del fundido de entrada/salida, Cerrar huecos (fundido cruzado), Eliminar fundidos, **Fundido cruzado** (X). Proceso: Fundido de entrada, Fundido de salida. Edición: **Repetir** (Cmd+K), **Duplicar** (Cmd+D). El script no enlaza hoy ninguno; enlazarlos es un cambio del script (TW-1626). |
| 6 | MP3 y AAC | Valores por defecto de la exportación MP3: 44,1 kHz, 128 kbps (hay 192 kbps). soundfile decodifica el MP3 de Cubase (44,1 kHz; 4,075 s decodificados para un rango de 4 s, afinfo dice 4,066 s: relleno del codificador). En un tono a −13 dBFS el true peak subió 0,1 dB (no representativo de la voz). **No hay AAC** en la exportación de Elements: el AAC se codificaría con `afconvert` de macOS. |
| 7 | Importar un render de Trackwright | Un WAV escrito en `Trackwright/renders/` e importado en 40 s en `TW1507` quedó en **40,000–43,000 s** (bordes del evento). Opciones de importación: «Copiar archivo a carpeta del proyecto» (activada por defecto: el archivo se copia a `Audio/`), conversión de frecuencia (no hacía falta), profundidad 32 float → 24 (desactivada por defecto). |
| 8 | Escucha A/B | `transport.start` con un ciclo (7–12 s de `TW1507`), el Bypass del Gate alternado cinco veces durante la reproducción, cada escritura releída en 0,71–0,79 s, `transport.stop`. El usuario oyó volver el ruido con el bypass, **sin clics**. |

## Consecuencias para E16

- Entrega (TW-1612, TW-1613): se puede poner y ajustar un limitador en Stereo Out; su opción DIC encaja con un techo de true peak. El MP3 al bitrate del perfil lo elige el usuario en el diálogo; el AAC pasa por `afconvert`.
- Ducking (TW-1616): la automatización en tiempo real llega ~0,1 s tarde y cuantizada a ~110 ms: aceptable para movimientos lentos (un pre-roll puede compensarlo), no para ediciones; el modo de cadena lateral necesita que el usuario elija la fuente. El camino fuera de línea sigue primero.
- Renderizar e importar (TW-1606): colocación exacta al milisegundo del sondeo de bordes; los renders ya están en la carpeta del proyecto, así que la skill pide desmarcar «copiar a la carpeta del proyecto» para no tener una segunda copia, y mantener 32 bits float.
- Fundidos (TW-1626): «Ajustar fundidos al rango» con la selección de rango que ya usa la edición de rangos es el candidato para los fundidos en los cortes; «Duplicar» y «Repetir» para camas hechas en Cubase.
- Tono y limpieza de la voz (TW-1625): el A/B con reproducción en ciclo y Bypass funciona y no produce clics.
- `cubase_record_automation` (TW-1635): la primera exportación plana y el título de otra pista en el dry run necesitan una corrección.
