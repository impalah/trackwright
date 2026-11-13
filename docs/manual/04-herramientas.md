# Referencia de herramientas MCP

El servidor `trackwright` publica 23 herramientas. Cada una tiene un esquema de entrada y otro de salida que el cliente MCP recibe automáticamente; aquí se explica cómo usarlas y qué limitaciones tienen.

## Conceptos comunes

### Cómo se indica una pista: `track`

| Forma | Ejemplo | Notas |
|---|---|---|
| `"selected"` | `"selected"` | La pista seleccionada en Cubase. Es el valor por defecto. |
| `"uid:<UID>"` | `"uid:79CDBA14…"` | **Recomendada.** Identificador estable, incluso tras reiniciar Cubase. Se obtiene de `cubase_list_tracks`. |
| Nombre exacto | `"Voz"` o `"name:Voz"` | Falla con `TRACK_AMBIGUOUS` si dos pistas se llaman igual. Usa `name:` si el nombre es literalmente `selected`. |

Solo se ven las pistas que tienen **canal de mezclador** (audio, instrumento, grupo, FX, salidas). Las de marcadores y las carpetas no aparecen.

### Qué parte de una pista: `target`

| Valor | Qué es |
|---|---|
| `channel` | Los parámetros del canal: nombre (1024), volumen (1025), mute (1027), solo (1028), selección (4000), armado (4002)… |
| `insert:N` | El plugin cargado en el slot de inserción N (1–8). |
| `strip:eq` | El EQ del channel strip. |

### Referencias `ref` y sesiones

Las salidas incluyen `ref` opacas para los objetos. Son **informativas**: ninguna herramienta las acepta como entrada. Identifican el objeto dentro de la sesión actual del script.

Tras reiniciar Cubase, los identificadores internos cambian y se reutilizan para otros objetos. Para designar una pista de forma duradera, usa su `uid:`.

Cada herramienta fija la sesión del script mientras se ejecuta. Si Cubase recarga el script en mitad de una operación, la herramienta se detiene con `STALE_SESSION` **antes de escribir nada más**. Basta con volver a lanzarla.

### Ensayo y aplicación (`dry_run`)

Toda herramienta que modifica el proyecto tiene `dry_run`, que por defecto es `true`: devuelve el plan (valor actual y valor pedido) sin tocar nada. Con `dry_run=false` aplica el cambio, relee el valor y devuelve `verified`.

Hay una excepción: `cubase_add_track_interactive`. Su fase `start` solo abre un diálogo de Cubase, y quien decide si se crea la pista eres tú, en ese diálogo.

Las escrituras **no se reintentan nunca**. Si una vence por tiempo (`TIMEOUT`), su resultado es desconocido: el error incluye la relectura del valor (`read_back`).

### Clases de comando

Las herramientas basadas en comandos de Cubase informan de `command_class`:

| Clase | Significado |
|---|---|
| `direct` | Actúa sin intervención. |
| `dialog` | Abre un diálogo de Cubase que el usuario debe completar. **Nunca se da por terminado.** |
| `confirm` | Cubase puede pedir confirmación (por ejemplo, al borrar una pista con eventos), salvo que el usuario haya marcado «no volver a preguntar». |
| `ui_selection` | Actúa sobre la selección de la ventana de Cubase, que Trackwright no puede ver. |
| `unknown` | Cubase la acepta, pero su efecto no se ha observado. |

### Errores

Los errores llegan como error de herramienta, con el formato `CÓDIGO: mensaje | details: {...}`. Los más habituales:

| Código | Causa |
|---|---|
| `BRIDGE_UNAVAILABLE` | El puente no está en marcha (`trackwright bridge`). |
| `BUSY` | Otra escritura seguía en curso y esta **no se envió**. Se puede repetir. |
| `INTERNAL_ERROR` | Error inesperado en el puente. En escrituras, el resultado es desconocido (`outcome: unknown`). |
| `STALE_SESSION` | Cubase recargó el script durante la operación; se detuvo antes de seguir escribiendo. |
| `TIMEOUT` | Cubase no respondió a tiempo. En escrituras: resultado desconocido. |
| `WRITES_DISABLED`, `NOT_ALLOWED` | La configuración no permite esa escritura. |
| `TRACK_NOT_FOUND`, `TRACK_AMBIGUOUS`, `NO_SELECTION` | No se puede resolver la pista. |
| `STALE_REF`, `INVALID_OBJECT` | La referencia es de otra sesión o el objeto ya no existe. |
| `CANNOT_PERFORM` | Cubase dice que ahora no se puede ejecutar ese comando. |
| `PRECONDITION_FAILED` y otros (`SLOT_OCCUPIED`, `NAME_CONFLICT`, `SELECTION_MISMATCH`…) | El estado actual no permite la operación. |

## Herramientas de lectura

No modifican nada.

### `cubase_status`

Estado de la conexión: versión del script, aplicación y versión de Cubase, acceso al mezclador y al transporte, número de comandos y política de escritura. `simulated: true` indica que responde el simulador, no Cubase.

### `cubase_list_tracks`

- **Entrada:** `offset`, `limit` (≤ 128).
- **Salida:** por pista, `track` (selector `uid:`), `name`, `type`, `selected`, `volume`, `mute`, `solo`, `input`, `output` y `ref`.

### `cubase_get_selected_channel`

La pista seleccionada y sus secciones (Inserts, Strips, Sends…). Si la seleccionada no tiene canal de mezclador, `track` es `null`.

### `cubase_list_inserts`

- **Entrada:** `track`.
- **Salida:** los 8 slots, con `empty` y, si están ocupados, el `name` y el `plugin_uid` del plugin cargado.

### `cubase_list_available_plugins`

- **Entrada:** `track`, `slot`, `filter` (nombre, fabricante o categoría), `offset`, `limit`.
- **Salida:** los plugins que se pueden cargar, con su `uid`. Los slots del channel strip no ofrecen catálogo (`NO_COLLECTION`).

### `cubase_list_parameters`

- **Entrada:** `target`, `track`, `offset`, `limit` (≤ 25), `filter`.
- **Salida:** los parámetros, con `tag`, `title` (localizado), `process`, `display`, `plain` y `automatable`.
- **Paginación:** la salida incluye `next_offset`, que es el `offset` para pedir la página siguiente, y `truncated: true` mientras queden parámetros. Con `filter`, cada llamada recorre como mucho 500 parámetros; ninguna coincidencia se pierde entre páginas.

### `cubase_get_parameter`

- **Entrada:** `target`, `tag`, `track`.
- **Salida:** un solo parámetro.

### `cubase_get_transport`

Posición del cursor, localizadores de ciclo y tempo, en compases. Si Cubase aún no ha enviado ningún valor, responde `UNAVAILABLE`: mueve el cursor una vez en Cubase y vuelve a intentarlo.

### `cubase_poll_changes`

Cambios que Cubase ha notificado desde la última llamada; la llamada vacía el registro. Un evento `removed` es una **pista para volver a comprobar**, no una prueba de borrado: Cubase también lo emite al cambiar de pista seleccionada.

Solo se comprueban los primeros 20 objetos distintos. Los demás eventos llevan `still_valid: null`, y `unchecked` dice cuántos son.

## Herramientas de escritura y navegación

### `cubase_set_parameter` (escritura)

- **Entrada:** `target`, `tag`, `value`, `track`, `unit` (`process` de 0 a 1, o `plain` en unidades reales vía Cubase), `expect_title`, `dry_run`.
- **Verificación:** relectura, con una tolerancia de 1e-3.
- **Errores:** `OUT_OF_RANGE`, `PARAM_LOCKED` y `PARAM_NOT_FOUND`.

### `cubase_insert_plugin` (escritura)

- **Entrada:** `slot`, `plugin_uid`, `track`, `dry_run`.
- Solo en slots vacíos (`SLOT_OCCUPIED`).
- **Verificación:** el slot contiene un plugin con ese `uid`.

### `cubase_set_track_mix` (escritura)

- **Entrada:** `track` y, al menos, uno de `volume` (normalizado de 0 a 1), `mute`, `solo` o `record_arm`; además, `dry_run`.
- Funciona en pistas **no seleccionadas**.
- El volumen en dB todavía no está disponible.
- Si un cambio falla después de aplicar otros, el error incluye `applied`, con los cambios que sí se hicieron.

### `cubase_rename_track` (escritura)

- **Entrada:** `track`, `new_name`, `dry_run`.
- Rechaza los nombres que ya usa otra pista (`NAME_CONFLICT`).
- Después del cambio, usa el selector `uid:`: el selector por nombre deja de valer.

### `cubase_select_track` (navegación)

- **Entrada:** `track`, o bien `step` (`next` o `prev`).
- La selección es única: deselecciona las demás pistas.

### `cubase_set_position` (navegación)

- **Entrada:** `which` (`cursor`, `cycle_left` o `cycle_right`), `time`, `unit` (`bars` o `seconds`) y `dry_run`.
- **Formato de compases:** `"3. 1. 1. 0"` (compás, tiempo, semicorchea, tick).
- **Formato de segundos:** `"0:00:02.000"`.
- La verificación en segundos asume compás de 4/4 y tempo constante.

### `cubase_set_tempo` (escritura)

- **Entrada:** `bpm` (de 20 a 300) y `dry_run`.
- **Verificación:** relectura, con una tolerancia de 0,01.

## Herramientas basadas en comandos

### `cubase_markers`

- **`action`:** `add_marker_track` (`direct`, escritura), `insert_at_cursor` (`direct`, escritura; necesita una pista de marcadores), `locate_prev` o `locate_next` (navegación: el cursor salta al marcador anterior o siguiente).
- Sin un marcador siguiente, `locate_next` lleva al final del último evento del proyecto; sin uno anterior, `locate_prev` lleva al inicio. No se detienen en los localizadores.
- La creación de pistas y marcadores no se puede leer desde la API, así que devuelve `verified: "not_observable"`.

### `cubase_remove_selected_tracks` (destructiva)

- **Entrada:** `expect_selected` y `dry_run`.
- Solo actúa si la indicada es la **única** pista seleccionada (`SELECTION_MISMATCH`, con la lista de las seleccionadas), porque el comando de Cubase borra todas las seleccionadas. Selecciónala antes con `cubase_select_track`.
- Limitación: no ve las pistas sin canal de mezclador (marcadores, carpetas), así que no sabe si hay alguna de ellas seleccionada. Revísalo en pantalla antes de aplicar.
- Si la pista tiene eventos, Cubase puede pedir confirmación (salvo que se haya desactivado ese aviso) y la herramienta devuelve `pending_confirmation`.
- Para pistas sin canal de mezclador (marcadores, carpetas), selecciónalas a mano y usa `cubase_run_command` con `project.remove_selected_tracks`.

### `cubase_split_at_locators` (destructiva)

- **Entrada:** `left`, `right` y `dry_run`.
- Coloca los localizadores, los relee y lanza «Split Loop».
- **Corta todas las pistas** que tienen eventos en ese rango.
- Los localizadores **se quedan** en los puntos de corte; restaurarlos enseguida podría adelantarse al comando. La salida incluye `previous_left` y `previous_right`, para restaurarlos después con `cubase_set_position`.

### `cubase_add_track_interactive` (escritura, con el usuario)

- **Entrada:** `phase` (`start` o `confirm`), `kind` (`audio`, `group` o `folder`) y `suggested_name`.
- **`start`:** abre el diálogo «Añadir pista» de Cubase y devuelve `awaiting_user` con instrucciones para el usuario. Rechaza nombres que ya existen (`NAME_CONFLICT`), para que `confirm` no confunda una pista antigua con la nueva.
- **`confirm`:** comprueba que la pista existe. Las carpetas no tienen canal de mezclador, así que en ese caso la verificación es visual.

### `cubase_run_command` (destructiva, avanzada)

- **Entrada:** `key`, `dry_run` y `force`.
- Ejecuta un comando de la lista permitida. Es mejor usar las herramientas específicas.

| `key` | Clase |
|---|---|
| `zoom.in`, `zoom.out` | unknown |
| `edit.undo`, `edit.redo`, `edit.cut`, `edit.copy`, `edit.paste`, `edit.delete`, `edit.split_at_cursor`, `edit.split_range`, `edit.select_all`, `edit.select_none`, `edit.select_in_loop` | ui_selection |
| `edit.split_loop` | direct |
| `addtrack.audio`, `addtrack.group`, `addtrack.folder`, `audio.detect_silence` | dialog |
| `addtrack.marker`, `marker.insert`, `project.select_track_next`, `project.select_track_prev`, `transport.locate_next_marker`, `transport.locate_prev_marker` | direct |
| `project.remove_selected_tracks` | confirm |
| `project.selected_to_new_folder`, `transport.return_to_zero`, `transport.set_left_locator`, `transport.set_right_locator`, `transport.locators_to_selection` | unknown |
| `automation.mode_touch`, `automation.mode_auto_latch`, `automation.mode_cross_over`, `automation.next_mode`, `automation.toggle_write_selected` | unknown (experimento TW-1206) |
| `transport.start`, `transport.stop` | direct (verificado: reproduce y para; nunca graba) |

## Herramientas de automatización

Mecanismo verificado en Cubase Elements 15.0.30: el script tiene en la superficie MIDI Remote un control por parámetro, enlazado a la **pista seleccionada**. Moverlo «tocado» mientras la pista tiene activada la escritura de automatización (W) y el proyecto se reproduce graba automatización, como un controlador físico en modo Touch. Escribir el parámetro directamente **no** graba.

### `cubase_list_automation_targets` (navegación)

- **Entrada:** `track`.
- **Salida:** cada parámetro automatizable con su clave (`parameter`), el parámetro de Cubase al que está enlazado (`title`, por ejemplo «Compressor / Threshold»), su valor actual y si está disponible (`available`).
- **Claves:**
  - `volume`, `pan`;
  - `send1.level` a `send4.level`;
  - `eq1.gain`, `eq1.freq` y `eq1.q`, hasta la banda 4;
  - `prefilter.gain`, `prefilter.lowcut` y `prefilter.highcut`;
  - `qc1` a `qc8` (Quick Controls);
  - `insert1.p1` a `insert2.p8`: los parámetros del plugin de los slots 1 y 2, en el orden de banco que decide Cubase.
- **Selecciona la pista,** porque los controles siguen la selección.

### `cubase_record_automation` (escritura, reproduce audio)

- **Entrada:**
  - `track` y `parameter`;
  - `points`: de 1 a 64 puntos `{position: "9. 1. 1. 0", value: 0..1}`, en orden creciente;
  - `verify` (por defecto `true`) y `dry_run`.
- **Qué hace:**
  1. selecciona la pista;
  2. activa W y desactiva R;
  3. reproduce desde un compás antes del primer punto;
  4. «toca» el control, recorre la curva (lineal entre puntos) siguiendo la posición del cursor y lo «suelta»;
  5. para la reproducción y deja W y R como estaban.
  - Con `verify`, vuelve a reproducir con R activado y compara el valor leído con la curva (tolerancia 0,05).
- **Salida:** los valores escritos (`written`), `verified`, las discrepancias (`mismatches`) y notas.
- **Errores:** `PARAM_NOT_FOUND`, `NOT_AUTOMATABLE` (no hay nada enlazado: slot vacío o Quick Control sin asignar), `TRANSPORT_RUNNING`, `NOT_RECORDED`, `BAD_TIME` y `WRITES_DISABLED`.
- **Limitaciones:**
  - las posiciones suponen compás de 4/4;
  - hay un punto escrito cada ~0,1–0,3 s;
  - **suena**: baja el volumen del monitor;
  - con R activado, la curva grabada manda sobre el parámetro.

## Lo que no se puede hacer

Verificado en la prueba de concepto:
- **Enrutado:** cambiar entradas, salidas o el destino de los envíos. La API lo ignora o lo deja en «Sin bus».
- **Leer el contenido de las pistas:** eventos, audio, marcadores como datos o curvas de automatización.
- **Completar diálogos** de Cubase: añadir pistas con opciones o detectar silencios.
- **Cargar módulos del channel strip** distintos del EQ (Cubase Elements).
