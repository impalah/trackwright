# Tutorial 5 — Marcadores y posición del cursor

[English](05-markers-cursor.md) · **Español**

**Objetivo:** mover el cursor y los localizadores, crear una pista de marcadores, insertar un marcador y navegar entre marcadores.
**Necesitas:** las escrituras habilitadas. Basta con `enabled = true`: los marcadores no pertenecen a ninguna pista concreta. Ten el transporte parado.

## Paso 1. Leer la posición

> ¿Dónde está el cursor?

`cubase_get_transport` devuelve, por ejemplo, `1. 1. 1.  0`, en compases, tiempos, semicorcheas y ticks.

## Paso 2. Mover el cursor

> Lleva el cursor al compás 3.

`cubase_set_position` con `which: "cursor"` y `time: "3.1.1.0"`. Es **navegación**, así que funciona aunque las escrituras estén deshabilitadas. La respuesta trae `verified: true` y el cursor se mueve en Cubase.

También puedes usar segundos:

> Pon el cursor en el segundo 2.

Usa `unit: "seconds"` y `time: "0:00:02.000"`. La verificación supone compás de 4/4 y tempo constante.

## Paso 3. Localizadores de ciclo

> Marca el ciclo entre los compases 2 y 4.

Son dos llamadas a `cubase_set_position`, con `cycle_left` y con `cycle_right`.

## Paso 4. Crear la pista de marcadores e insertar un marcador

> Crea una pista de marcadores y pon un marcador en el compás 2.

1. `cubase_markers` con `add_marker_track`. Es de clase `direct`: Cubase la crea sin diálogo.
2. `cubase_set_position` lleva el cursor al compás 2.
3. `cubase_markers` con `insert_at_cursor`.

Las pistas de marcadores no se ven a través de la API, así que la respuesta dice `verified: "not_observable"`. **Compruébalo en pantalla.**

## Paso 5. Navegar

> Lleva el cursor al compás 3 y luego al marcador anterior.

`locate_prev` lleva el cursor al compás 2, y la respuesta muestra `cursor_before` y `cursor_after`. Ojo: los saltos van solo de marcador en marcador, no se detienen en los localizadores, y si no hay marcadores llevan al inicio del proyecto.

## Paso 6. Limpieza

Para borrar la pista de marcadores, selecciónala **a mano**: no tiene canal de mezclador, así que Trackwright no puede seleccionarla. Después bórrala tú, o pídelo con `cubase_run_command` y la clave `project.remove_selected_tracks`. Como contiene un marcador, Cubase pedirá confirmación.

## Qué has aprendido

- Mover posiciones es navegación y se verifica leyendo el transporte.
- Las pistas de marcadores se crean sin diálogo, pero no son visibles para la API.

**Siguiente:** [Tutorial 6 — Crear una pista con ayuda del diálogo](06-track-with-dialog.es.md).
