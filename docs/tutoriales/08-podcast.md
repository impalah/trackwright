# Tutorial 8 — Editar un podcast por segundos

**Objetivo:** quitar un tramo de un podcast indicándolo en segundos y comprobar que se ha hecho bien.
**Necesitas:**
- las escrituras habilitadas;
- el script 1.5.1 o posterior;
- el proyecto **guardado**;
- el transporte parado.

## Paso 1. Ensayar

> Quita del podcast el tramo entre el segundo 2 y el 30, cerrando el hueco. Comprueba con la pista Voz.

Claude usa `cubase_edit_range` con `action: "delete_time"`, `start: "2"`, `end: "30"` y `verify_track: "Voz"`, primero en ensayo. Te enseña:
- el rango (`0:00:02.000`–`0:00:30.000`, 28 s);
- el efecto: se quita el tramo y se adelanta todo lo posterior;
- el alcance: **todas las pistas** con audio en ese tramo.

## Paso 2. Aplicar

Tras tu confirmación:
1. Trackwright coloca los localizadores en 2 y 30 s;
2. activa la herramienta de rango, selecciona el tramo y lo borra;
3. vuelve a la herramienta de objetos y deja los localizadores y el cursor como estaban.

Con `verify_track`, compara los bordes del audio de esa pista antes y después: `verified: true` quiere decir que el tramo desapareció y lo posterior se adelantó 28 s.

## Otras acciones

| Quieres… | Pide |
|---|---|
| Borrar y dejar un hueco (para meter otra cosa) | «Borra el audio entre 1:10 y 1:25, sin mover nada» → `delete` |
| Hacer sitio para una cuña | «Inserta 15 segundos de silencio en el minuto 5» → `insert_silence` del 5:00 al 5:15 |
| Quedarte solo con un fragmento | «Deja solo del 10 al 70» → `crop` |

## Si algo no sale como esperabas

- **Edición > Deshacer** en Cubase lo revierte.
- `NO_RANGE_SELECTION`: pon la ventana de proyecto de Cubase delante y repite.
- **Una sola pista** (por ejemplo, una tos en un micro) todavía no se puede: está en estudio (TW-1212).

## Qué has aprendido

- Las órdenes en segundos no dependen del compás ni del tempo.
- El resultado se comprueba recorriendo los bordes del audio de una pista.
