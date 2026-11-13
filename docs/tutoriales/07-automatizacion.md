# Tutorial 7 — Grabar automatización

**Objetivo:** que Claude grabe un fundido de volumen y una curva de un parámetro de plugin en una pista, y comprobar que se reproducen.
**Necesitas:**
- las escrituras habilitadas;
- el script 1.4.0 o posterior;
- una pista con audio en un proyecto **guardado**;
- **el volumen del monitor bajo**, porque la grabación reproduce el proyecto.

## Paso 1. Ver qué se puede automatizar

> ¿Qué parámetros de POC-TEST puedo automatizar?

Claude usa `cubase_list_automation_targets`. Verás claves como `volume`, `pan` o `eq1.gain` y, si hay un plugin en el slot 1, `insert1.p1`, `insert1.p2`…, cada una con el parámetro real al que corresponde («Compressor / Threshold», «Compressor / Ratio»…). La pista queda seleccionada.

## Paso 2. Un fundido de volumen

> Haz un fundido de salida en POC-TEST: volumen de 0 dB en el compás 5 a silencio casi total en el compás 9.

1. Claude prepara la curva **en dB**: los puntos llevan `plain: 0` y `plain: -60`, y Cubase los convierte con exactitud a valores normalizados (0 dB es 0,7891; la escala no es lineal). Te enseña el plan (`dry_run`): parámetro, valor actual, puntos y compás de inicio de la reproducción, que es uno antes del primer punto.
2. Tras tu confirmación, la aplica. Verás moverse un fader de la superficie y el de la pista.
3. Con la verificación activada (por defecto), Trackwright vuelve a reproducir con la lectura de automatización y comprueba que el volumen sigue la curva: `verified: true`.

En Cubase aparecerá la curva en el carril de automatización de volumen.

## Paso 3. Un parámetro de plugin

> Sube el Threshold del compresor de POC-TEST de −20 a −35 dB entre los compases 2 y 4.

Claude buscará la clave (`insert1.p1`) y pasará los puntos como `plain: -20` y `plain: -35`, que Cubase convierte. Si quieres comprobar una conversión sin grabar nada, pregunta por ejemplo «¿qué valor normalizado son −20 dB de volumen?»: Claude usará `cubase_convert_value`.

## Paso 4. Dejarlo como estaba

- **La automatización grabada se queda en el proyecto.** Para que deje de mandar, desactiva la lectura (R) de la pista, o bórrala en Cubase.
- **Si algo sale mal, Deshacer** en Cubase. Para eso guardaste antes.

## Qué has aprendido

- Trackwright graba automatización reproduciendo el proyecto, igual que tú con un controlador.
- La curva se define con puntos (posición en compases y valor) y se verifica con una segunda pasada.
