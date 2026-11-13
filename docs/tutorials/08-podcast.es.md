# Tutorial 8 — Editar un podcast por segundos

[English](08-podcast.md) · **Español**

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
| Quitar una tos en un solo micro | «Borra del 1:12.4 al 1:13.1 solo en la pista Invitado» → `delete` con `track: "Invitado"` |

## Importar la sintonía

> Importa la sintonía /Users/yo/Música/sintonia.wav en la pista Música, en el segundo 0.

1. Claude usa `cubase_import_audio` con `phase: "start"`: selecciona la pista, pone el cursor en 0 y abre «Importar archivo de audio».
2. En el selector, pulsa **Cmd+Shift+G**, pega la ruta y abre el archivo. Acepta las opciones (Cubase lo copia al proyecto).
3. Dile «ya está». Con `phase: "confirm"` comprobará que la pista tiene audio de 0 a la duración de la sintonía.

## Exportar el episodio

> Exporta el episodio completo.

1. Claude usa `cubase_export_mix` con `phase: "start"`: pone los localizadores alrededor de todo el audio y abre «Exportar mezcla de audio».
2. Tú eliges el formato (por ejemplo, MP3 a 128 kB/s para publicar) y pulsas **Exportar audio**.
3. Dile a Claude «ya está». Con `phase: "confirm"` encontrará el archivo en la carpeta *Mixdown* del proyecto y comprobará que dura lo que el episodio.

Para un fragmento, por ejemplo un avance: «exporta del 5:00 al 5:45».

## Si algo no sale como esperabas

- **Edición > Deshacer** en Cubase lo revierte.
- `NO_RANGE_SELECTION`: pon la ventana de proyecto de Cubase delante y repite.
- **Al deshacer una edición en una sola pista,** pulsa Deshacer las veces que indica `undo_steps`.

## Qué has aprendido

- Las órdenes en segundos no dependen del compás ni del tempo.
- El resultado se comprueba recorriendo los bordes del audio de una pista.
