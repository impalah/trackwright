# Referencia de herramientas MCP

[English](04-tools.md) · **Español**

El servidor `trackwright` publica 43 herramientas. Cada una tiene un esquema de entrada y otro de salida que el cliente MCP recibe automáticamente; aquí se explica cómo usarlas y qué limitaciones tienen.

Trackwright aspira a admitir varios DAW, pero hoy solo implementa **Cubase**. Por eso todas las herramientas se llaman `cubase_*` y esta página describe el comportamiento de Cubase: se verificó contra Cubase Elements 15.0.30, con scripts de experimento y desde Claude Code (ver el [registro de verificación](../verification.es.md)). Cualquier cliente MCP recibe las mismas herramientas. Otro DAW tendría su propio conjunto de herramientas; ver [Extensión a otros DAW](../architecture.es.md#extensión-a-otros-daw-posible-no-implementada).

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
| `insert:N` | El plugin cargado en el slot de inserción N, de 1 al número de slots de tu Cubase (8 en Elements; `cubase_status` da `insert_slots`). |
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
| `ANALYSIS_DISABLED`, `TOO_LONG` | La configuración no permite leer audio, o el archivo es más largo de lo permitido. |
| `WORKSPACE_DISABLED` | La configuración no permite escribir la carpeta `Trackwright/` del proyecto. |
| `TRACK_NOT_FOUND`, `TRACK_AMBIGUOUS`, `NO_SELECTION` | No se puede resolver la pista. |
| `INVALID_OBJECT` | El objeto ya no existe (por ejemplo, se borró en Cubase). |
| `CANNOT_PERFORM` | Cubase dice que ahora no se puede ejecutar ese comando. |
| `PRECONDITION_FAILED` y otros (`SLOT_OCCUPIED`, `NAME_CONFLICT`, `SELECTION_MISMATCH`…) | El estado actual no permite la operación. |

## Herramientas de lectura

No modifican nada.

### `cubase_status`

Estado de la conexión: versión del script, aplicación y versión de Cubase, acceso al mezclador y al transporte, número de comandos y política de escritura. `simulated: true` indica que responde el simulador, no Cubase. `script_outdated: true` indica que Cubase ejecuta otro script que el que instala este Trackwright (`packaged_script_version`): instálalo con `trackwright setup` y reinicia Cubase.

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

### `cubase_get_project` (lectura)

- **Entrada:** `include_folders` (por defecto `true`).
- **Salida:**
  - tempo;
  - **compás en la posición del cursor** (`signature`: texto, numerador y denominador);
  - ciclo (activado y localizadores);
  - punch in/out y su rango;
  - pre-roll y post-roll;
  - metrónomo (activado, nivel del clic, si suena al grabar y al reproducir) y precuenta;
  - estado del transporte (`stopped`, `playing`, `recording`);
  - formatos de las pantallas de tiempo y modos de grabación y reproducción, tal como los muestra Cubase.
- **`project_folders`:** las carpetas de los proyectos abiertos. Se deducen de los archivos de audio que Cubase tiene abiertos (`lsof`), sin leer la carpeta ni el `.cpr`. Está vacía si el proyecto no tiene audio.
- **`unavailable`:** lo que la API de Cubase no expone (frecuencia de muestreo, resolución, longitud y nombre del proyecto) y el motivo.
- **Cómo funciona:** lee los objetos internos «Transporte» y «Metronome» de Cubase, que se localizan por tipo. Verificado con 4/4 y 3/4.
- **Coste:** alrededor de 1 s.

### `cubase_set_project` (escritura, con ensayo)

- **Entrada:** cualquiera de estos ajustes, más `dry_run`:
  - interruptores (`true`/`false`): `cycle`, `metronome`, `precount`, `punch_in`, `punch_out`, `pre_roll` y `post_roll` (usar el pre-roll y el post-roll), `click_in_playback` y `click_in_record`;
  - `click_level`, de 0 a 127.
- **Qué hace:** escribe cada ajuste en el objeto «Transporte» o «Metronome» de Cubase y lo relee. La salida da el valor antes, el pedido, el leído y `verified` de cada uno. Si una escritura falla o agota el tiempo, el error lista los ajustes ya aplicados (`applied`) y el que falló (`failed_setting`), con su valor releído tras un tiempo agotado; no se reintenta nada.
- **Verificado en Cubase Elements:** los 9 interruptores y el nivel del clic (experimento TW-1210).
- **No disponible:**
  - **compás:** Cubase no acepta escribirlo por esta vía; se cambia en la barra de transporte o en «Configuración del proyecto»;
  - **duración** del pre-roll y el post-roll: su escala no está verificada;
  - **pista de tempo.**
  - El tempo se cambia con `cubase_set_tempo`.

## Herramientas de escritura y navegación

### `cubase_set_parameter` (escritura)

- **Entrada:** `track` (obligatorio), `target`, `tag`, `value`, `unit` (`process` de 0 a 1, o `plain` en unidades reales vía Cubase), `expect_title`, `dry_run`.
- **Salida:** incluye `track_uid` (`uid:<UID>`); pásalo como `track` al aplicar un ensayo, porque `"selected"` puede apuntar ya a otra pista.
- **Verificación:** relectura, con una tolerancia de 1e-3.
- **Parámetros protegidos del canal:** con el objetivo `channel`, el enrutado de entrada y de salida (tags 4101 y 4102), el nombre (1024) y la selección (4000) se rechazan con `READ_ONLY_PARAM`, también en el ensayo. Escribir el enrutado desconecta la pista; el nombre y la selección tienen sus propias herramientas verificadas (`cubase_rename_track`, `cubase_select_track`).
- **Errores:** `OUT_OF_RANGE`, `PARAM_LOCKED`, `PARAM_NOT_FOUND` y `READ_ONLY_PARAM`.

### `cubase_insert_plugin` (escritura)

- **Entrada:** `track` (obligatorio), `slot`, `plugin_uid`, `dry_run`.
- **Salida:** incluye `track_uid`, para reutilizarlo al aplicar el ensayo.
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

- **Entrada:** `track`, o bien `step` (`next` o `previous`).
- La selección es única: deselecciona las demás pistas.
- Con `step`, `verified` solo es `true` si la selección se movió (en la primera o la última pista no se mueve).

### `cubase_track_edges` (navegación)

Dónde empiezan y acaban los eventos de una pista (TW-1610). La API no puede leer eventos, así que la herramienta selecciona la pista y recorre sus bordes con Localizar evento siguiente desde `start` (segundos) hasta `end`, y después devuelve el cursor y la selección a su sitio.

- **Entrada:** `track`, `start` (por defecto 0), `end` (por defecto, hasta el último borde), `limit` (máximo de bordes a recorrer, por defecto 100, hasta 400; cada uno tarda un momento).
- **Salida:** `edges` (inicios y finales juntos, en orden), `first` y `last` (la extensión de la pista), `complete` (false cuando `limit` paró el recorrido: sondear otra vez desde el último borde).
- **Límites:** un evento que empieza exactamente en 0 s no se ve (el sondeo encuentra bordes después del cursor; TW-1606), así que `first` puede ser su final; los bordes de eventos contiguos coinciden; el silencio dentro de un evento no se ve (analiza una exportación para eso). El transporte debe estar parado (`TRANSPORT_RUNNING`).

### `cubase_set_position` (navegación)

- **Entrada:** `which` (`cursor`, `cycle_left` o `cycle_right`), `time`, `unit` (`bars` o `seconds`) y `dry_run`.
- **Formato de compases:** `"3. 1. 1. 0"` (compás, tiempo, semicorchea, tick).
- **Formato de segundos:** `"2.5"`, `"1:30"` o `"0:00:02.000"`.
- **Permiso:** mover el cursor es navegación y funciona con las escrituras desactivadas. Los localizadores del ciclo se guardan con el proyecto, así que moverlos requiere `[writes] enabled = true` (`WRITES_DISABLED`). La herramienta mantiene `dry_run` en falso por defecto, como las demás de navegación.
- **En segundos,** la posición se relee con la pantalla de segundos de Cubase, sin suponer compás ni tempo. Los localizadores no se pueden mover con la pantalla de segundos (verificado), así que se colocan llevando el cursor allí y usando «Set Left/Right Locator»; luego el cursor vuelve a su sitio.

### `cubase_set_tempo` (escritura)

- **Entrada:** `bpm` (de 20 a 300) y `dry_run`.
- **Verificación:** relectura, con una tolerancia de 0,01.

### `cubase_plugin_preset` (escritura, con ensayo; a veces con el usuario)

- **Entrada:** `track`, `slot`, `direction` (`next` o `previous`) y `dry_run`.
- **Qué hace:**
  1. abre el editor del plugin (parámetro «Edición» del slot) si está cerrado;
  2. lanza `Preset / Next` o `Previous`;
  3. compara los parámetros del plugin antes y después, sin contar los medidores;
  4. cierra el editor si lo abrió.
- **Salida:** `changed` (parámetro: antes → después), `verified` y `status`.
- **Requisitos verificados en Cubase Elements** (experimento TW-1205):
  - **un preset cargado** en el plugin; sin él, los comandos no hacen nada;
  - **el foco de teclado en su ventana:** hace falta **un clic del usuario la primera vez**. Después funciona aunque Trackwright cierre y reabra el editor.
- **`awaiting_user`:** si no cambia nada, deja el editor abierto y pide ese clic (y un preset cargado). La siguiente llamada ya funciona.
- **No se puede** elegir un preset por nombre **ni leer su nombre**: la API no lo expone. Solo se sabe que cambió, por sus parámetros.
- **Deshacer:** el paso contrario (`previous` tras `next`) devuelve exactamente los valores anteriores.

## Herramientas basadas en comandos

### `cubase_markers`

- **`action`:** `add_marker_track` (`direct`, escritura), `insert_at_cursor` (`direct`, escritura; necesita una pista de marcadores), `locate_prev` o `locate_next` (navegación: el cursor salta al marcador anterior o siguiente).
- Sin un marcador siguiente, `locate_next` lleva al final del último evento del proyecto; sin uno anterior, `locate_prev` lleva al inicio. No se detienen en los localizadores.
- La creación de pistas y marcadores no se puede leer desde la API, así que devuelve `verified: "not_observable"`.

### `cubase_remove_selected_track` (destructiva)

- **Entrada:** `expect_selected` y `dry_run`.
- Solo actúa si la indicada es la **única** pista seleccionada (`SELECTION_MISMATCH`, con la lista de las seleccionadas), porque el comando de Cubase borra todas las seleccionadas. Selecciónala antes con `cubase_select_track`.
- Limitación: no ve las pistas sin canal de mezclador (marcadores, carpetas), así que no sabe si hay alguna de ellas seleccionada. Revísalo en pantalla antes de aplicar.
- Si la pista tiene eventos, Cubase puede pedir confirmación (salvo que se haya desactivado ese aviso) y la herramienta devuelve `pending_confirmation`.
- Para pistas sin canal de mezclador (marcadores, carpetas), selecciónalas a mano y usa `cubase_run_command` con `project.remove_selected_tracks`.

### `cubase_split_at_locators` (destructiva)

- **Entrada:** `left`, `right`, `unit` (`bars`, por defecto, o `seconds`) y `dry_run`.
- Coloca los localizadores, los relee y lanza «Split Loop». En segundos, los localizadores se colocan moviendo el cursor y usando «Set Left/Right Locator» (el visor de segundos no puede moverlos); el cursor vuelve a su sitio, y la salida añade `left_bars` y `right_bars`.
- **Corta todas las pistas** que tienen eventos en ese rango, así que se rechaza con `NOT_ALLOWED` mientras `[writes] allowed_tracks` tenga pistas.
- Los localizadores **se quedan** en los puntos de corte; restaurarlos enseguida podría adelantarse al comando. La salida incluye `previous_left` y `previous_right`, para restaurarlos después con `cubase_set_position`.

### `cubase_add_track_interactive` (escritura, con el usuario)

- **Entrada:** `phase` (`start` o `confirm`), `kind` (`audio`, `group` o `folder`) y `suggested_name`.
- **`start`:** abre el diálogo «Añadir pista» de Cubase y devuelve `awaiting_user` con instrucciones para el usuario. Rechaza nombres que ya existen (`NAME_CONFLICT`), para que `confirm` no confunda una pista antigua con la nueva.
- **`confirm`:** comprueba que la pista existe. Las carpetas no tienen canal de mezclador, así que en ese caso la verificación es visual.

### `cubase_run_command` (destructiva, avanzada)

- **Entrada:** `key`, `dry_run` y `force`.
- Ejecuta un comando de la lista permitida. Es mejor usar las herramientas específicas.
- **Se rechazan aquí** (`USE_DEDICATED_TOOL`, también en el ensayo): `file.save` y `file.save_new_version` (usa `cubase_save_project`, que comprueba `[writes] save` y verifica el archivo) y `project.remove_selected_tracks` (usa `cubase_remove_selected_track`, que comprueba la selección).
- **Permiso:** los comandos actúan sobre la selección de la ventana de Cubase, que puede incluir cualquier pista; por eso todos, salvo los de navegación, necesitan las escrituras activadas y se rechazan con `NOT_ALLOWED` mientras `[writes] allowed_tracks` tenga pistas.

| `key` | Clase |
|---|---|
| `zoom.in`, `zoom.out` | unknown |
| `edit.undo`, `edit.redo`, `edit.cut`, `edit.copy`, `edit.paste`, `edit.delete`, `edit.split_at_cursor`, `edit.split_range`, `edit.select_all`, `edit.select_none`, `edit.select_in_loop` | ui_selection |
| `edit.split_loop` | direct |
| `addtrack.audio`, `addtrack.group`, `addtrack.folder`, `audio.detect_silence`, `file.export_audio_mixdown`, `file.import_audio` | dialog (exportar e importar: verificados, TW-1204 y TW-1203; el selector de importación bloquea Cubase mientras está abierto) |
| `addtrack.marker`, `marker.insert`, `project.select_track_next`, `project.select_track_prev`, `transport.locate_next_marker`, `transport.locate_prev_marker` | direct |
| `project.remove_selected_tracks` | confirm (se rechaza aquí: usa `cubase_remove_selected_track`) |
| `project.selected_to_new_folder`, `transport.return_to_zero`, `transport.locators_to_selection` | unknown |
| `automation.mode_touch`, `automation.mode_auto_latch`, `automation.mode_cross_over`, `automation.next_mode`, `automation.toggle_write_selected` | unknown (experimento TW-1206) |
| `transport.start`, `transport.stop` | direct (verificado: reproduce y para; nunca graba) |
| `edit.delete_time`, `edit.cut_time`, `edit.insert_silence`, `edit.crop_range`, `edit.select_all_on_tracks` | ui_selection (verificado, TW-1211: actúan sobre la selección de rango) |
| `transport.set_left_locator`, `transport.set_right_locator`, `transport.locate_next_event`, `transport.locate_selection`, `transport.locate_selection_end` | direct (verificado, TW-1211) |
| `process.silence` | dialog (verificado, TW-1211: pregunta si el archivo de audio está compartido) |
| `edit.select_events_under_cursor`, `transport.locate_prev_event`, `transport.to_left_locator`, `tool.range`, `tool.select` | unknown |
| `file.save`, `file.save_new_version` | direct (verificado, TW-1202, en un proyecto ya guardado; se rechaza aquí: usa `cubase_save_project`) |
| `preset.next`, `preset.previous` | ui_selection (verificado, TW-1205: actúan sobre el editor de plugin con el foco) |

## Edición por rangos en segundos

### `cubase_edit_range` (destructiva, con ensayo)

Pensada para editar podcasts: trabaja en **segundos** y el compás no importa.

- **Entrada:**
  - `start` y `end`: segundos (`"2"`, `"2.5"`, `"1:30"`, `"0:01:30.250"`) o compases con `unit: "bars"`;
  - `action`:

    | Acción | Efecto |
    |---|---|
    | `delete` | Borra el audio del rango y deja el hueco; nada se mueve |
    | `delete_time` | Borra el rango y adelanta todo lo posterior, cerrando el hueco |
    | `cut_time` | Como `delete_time`, y además copia el rango |
    | `insert_silence` | Inserta un silencio tan largo como el rango, en su inicio |
    | `crop` | Deja solo el rango |
  - `verify_track`: una pista con audio cuyos bordes de eventos se sondean antes y después para comprobar el resultado. **Recomendado.**
  - `dry_run`.
- **Alcance: todas las pistas con eventos en el rango.** Es lo que hace Cubase con «Seleccionar en ciclo». Para un podcast, `delete_time` corta el tramo en todas las pistas a la vez.
- **Una sola pista** (`track`, solo con `action: "delete"`): borra el audio del rango únicamente en esa pista, por ejemplo una tos en un micro. Usa la herramienta de objetos:
  1. corta los eventos de la pista en los dos extremos;
  2. borra los trozos de dentro uno a uno, poniendo el cursor encima y usando «Select Events under Cursor», que solo mira la pista seleccionada;
  3. repite el sondeo hasta que no queda nada, porque puede haber trozos ocultos bajo otros.
  - **Seguridad:** antes de cada borrado mide la selección; si se sale del rango (un corte no se hizo), para con `SPLIT_FAILED` sin borrar más.
  - **Deshacer:** necesita varios pasos. `undo_steps` dice cuántos.
  - **Duración:** tarda más, unos 25 s para un rango con 6 eventos.
  - **No se permite** cerrar o abrir tiempo en una sola pista: la desincronizaría del resto.
- **Qué hace:**
  1. pone los localizadores en el rango: lleva el cursor a cada extremo, en segundos, y usa «Set Left/Right Locator»;
  2. activa la herramienta de **Selección de rango**, lanza «Select in Loop» y ejecuta la acción;
  3. vuelve a la herramienta de **Selección de objetos** (no puede saber cuál tenías antes);
  4. deja como estaban los localizadores, el cursor y la pista seleccionada.
- **Verificación:** con `verify_track`, recorre los bordes de los eventos de esa pista con «Locate Next Event» (inicios y finales, sin distinguirlos) y comprueba que coinciden con lo esperado. Revisa hasta 48 bordes a partir de 1 s antes del rango.
- **Errores:** `BAD_TIME`, `TRANSPORT_RUNNING`, `NO_RANGE_SELECTION` (Cubase no creó la selección, por ejemplo porque la ventana de proyecto no está delante), `SPLIT_FAILED`, `WRITES_DISABLED` y `NOT_ALLOWED` (con `track`, una pista fuera de `[writes] allowed_tracks`; sin `track`, cualquier edición mientras `allowed_tracks` tenga pistas, porque actúa sobre todas).
- **Deshacer:** **Edición > Deshacer** en Cubase lo revierte, como se verificó con cada acción. No se guarda el proyecto.
- **No incluida:** «Process > Silence» abre un diálogo si el archivo de audio lo comparten varios eventos.

## Guardar el proyecto

### `cubase_save_project` (destructiva, con ensayo)

**Solo cuando el usuario pide guardar.** Trackwright nunca guarda por iniciativa propia ni encadena un guardado tras otras escrituras.

- **Permiso:** necesita `[writes] enabled = true` **y** `[writes] save = true`.
- **Entrada:**
  - `mode`:
    - `save`: sobrescribe el `.cpr` abierto;
    - `new_version`: crea `<nombre>-NN.cpr`, y Cubase pasa a trabajar sobre él;
  - `dry_run`, por defecto `true`.
- **Ensayo:** muestra la carpeta del proyecto (deducida de los archivos de audio abiertos) y sus `.cpr` con fecha y tamaño, para saber qué se va a sobrescribir.
- **Verificación:** algún `.cpr` de la carpeta con fecha posterior a la orden; con `new_version`, uno nuevo. Solo se leen nombres, tamaños y fechas.
- **Carpeta desconocida:** si no se conoce la carpeta del proyecto, o parece haber varios proyectos abiertos, el estado es `fired` y `verified` es `null`: se pidió guardar, pero nada lo demuestra (un proyecto que nunca se guardó muestra *Guardar como*).
- **Estados:** `done` o `awaiting_user`. El segundo, si en 10 s no se escribió nada: probablemente hay un diálogo, como «Guardar como» en un proyecto que nunca se guardó.
- **Verificado en Cubase Elements:** `Save` reescribió `TEST.cpr` en 1 s, y `Save New Version` creó `TEST-01.cpr`. Ninguno abrió diálogo.
- **No se ofrecen** cerrar, revertir ni salir.

## Importar audio

### `cubase_import_audio` (con el usuario, dos fases)

- **Fase `start`** (`dry_run` por defecto):
  - **Entrada:**
    - `track` y `position` (segundos o compases);
    - `file`, opcional: la ruta del archivo que el usuario elegirá. Sirve para indicársela y para conocer su duración (de la cabecera con soundfile; `afinfo` de macOS solo para AAC).
  - **Qué hace:**
    1. selecciona la pista;
    2. pone el cursor en la posición;
    3. abre «Importar archivo de audio».
  - **Con el selector abierto, Cubase no responde al script** (verificado). Por eso la fase no hace nada más y devuelve `awaiting_user`, con instrucciones: Cmd+Shift+G y la ruta.
- **El usuario** elige el archivo y acepta las opciones. Cubase lo copia a la carpeta *Audio* del proyecto.
- **Fase `confirm`** (misma pista, posición y archivo, más `since`):
  - si Cubase aún no responde: `awaiting_user`, porque el selector sigue abierto;
  - si no, sondea la pista y busca bordes en la posición y en la posición más la duración. Devuelve `done` y `verified`, o `not_found` si se canceló o fue a otra parte. Solo cuentan los bordes **nuevos**: la fase de inicio sondea la pista antes de abrir el diálogo, así que un evento que ya estaba en esa posición no confirma una importación cancelada, y cada posición esperada necesita su propio borde. Si la fase de inicio se hizo en otra sesión del servidor, no se conocen los bordes previos y `verified` es `null`;
  - al inicio del proyecto (posición 0) no se puede sondear el borde de inicio (Localizar evento siguiente nunca se detiene en 0, y Localizar evento anterior va a 0 aunque no haya un evento allí): lo sustituye el borde final nuevo en la posición más la duración del archivo, con una nota (TW-1606);
  - `copied_to_project` lista las copias nuevas en `<proyecto>/Audio`, solo con el nombre.
- **Verificado en Cubase Elements:** un tono de 3 s quedó en POC-TEST de 150 a 153 s.
- **Deshacer** quita el evento, **no** la copia en disco.
- **Renders** (`file` en `Trackwright/renders/` con su procedencia, TW-1606): `start` rechaza una posición distinta de la del render (`MISALIGNED`), la pista a la que sustituye el render (`BAD_REQUEST`) y un render que cambió después de hacerse (`BAD_RENDER`); las instrucciones piden desmarcar «Copiar archivo a carpeta del proyecto». `confirm` devuelve `render` y, con `[workspace] enabled`, registra el render y la pista nueva en `state.json` como de la skill que lo renderizó (`owned: true`), y recuerda silenciar la pista original; si una pista de render anterior de la misma skill sustituía a la misma pista, lo dice, para quitarla cuando el usuario lo confirme.

## Exportar la mezcla

### `cubase_export_mix` (con el usuario, dos fases)

> **Pistas silenciadas y `solo`** (TW-1616): en Cubase una pista en solo suena aunque esté silenciada. Por eso `solo` deja fuera las pistas silenciadas, con una nota, salvo si `include_muted` es true; cuando todas las pistas pedidas están silenciadas, se niega (`BAD_REQUEST`).

Trackwright **nunca exporta por sí mismo**: coloca el rango y abre el diálogo de Cubase; el formato y el botón son del usuario.

- **Fase `start`** (`dry_run` por defecto):
  - **Entrada:** `start` y `end` en segundos (o compases con `unit: "bars"`). Sin ellos, exporta **todo el audio**: «Select All» y «Locators to Selection» ponen los localizadores del primer al último evento.
  - **Qué hace:** pone los localizadores en el rango y abre «Exportar mezcla de audio». En Elements el diálogo no tiene campo de rango: exporta entre los localizadores (verificado).
  - **Salida:** `awaiting_user`, la carpeta que propondrá Cubase (`<carpeta del proyecto>/Mixdown`, deducida de los archivos abiertos), la duración esperada y `since` (marca de tiempo).
- **El usuario,** en el diálogo, revisa el canal (Stereo Out), el nombre, la ruta y el formato (WAV para archivar, MP3 para publicar) y pulsa **Exportar audio**.
- **Fase `confirm`:**
  - **Entrada:** `since` y `expected_seconds` de la fase anterior; `folder` si se eligió otra carpeta.
  - **Qué hace:** busca en la carpeta los archivos de audio creados después de `since` y lee **solo** su nombre, tamaño, fecha y duración (de la cabecera con soundfile, exacta también en MP3; `afinfo` de macOS, cuya duración de un MP3 es una estimación que se quedó 6,3 s corta en 46 minutos, solo para AAC; TW-1612).
  - **Salida:** `done` y `verified`, con la diferencia de duración de cada archivo (`difference_seconds`), o `not_found`.
  - **Tolerancia:**
    - ±0,15 s en WAV y AIFF;
    - ±(0,5 s + 0,2 %) en MP3, AAC y OGG, cuya duración es una estimación y que pierden o ganan tramas al final. Verificado: un MP3 del episodio de 139,976 s midió 139,721 s.
- Los localizadores **se quedan** en el rango exportado.
- **Exportar algunas pistas solas** (TW-1605): Cubase Elements solo exporta Stereo Out, así que `start` acepta `solo`, una lista de pistas. Durante la exportación solo esas están en solo (otro solo que tuviera el usuario se quita ese rato); `confirm` deja cada solo como estaba, relee cada uno e indica `solo_restored`, aunque no encuentre el archivo. Si el usuario cierra el diálogo sin exportar, `phase: "cancel"` con `since` restaura los solos sin buscar ningún archivo. Si algo falla antes de abrirse el diálogo, los solos se restauran en el momento. Con `[writes] allowed_tracks`, solo puede cambiar el solo de esas pistas (`NOT_ALLOWED`).
- **Errores:** `TRANSPORT_RUNNING`, `CANNOT_PERFORM` (hay otro diálogo abierto), `BAD_TIME`, `WRITES_DISABLED` y `NOT_ALLOWED`.

### `cubase_detect_speech` (lectura, necesita `[analysis] enabled`)

Dónde hay voz en una pista de voz (TW-1604), para las skills que actúan alrededor de la voz: atenuar la música, nivelar, colocar transiciones. Exporta antes la pista de voz sola (en solo): con cada voz en su pista, la pregunta es solo «voz o no», nunca «quién».

- **Entrada:** `file` (ruta absoluta), `start` (tiempo del proyecto de la primera muestra del archivo, como en `cubase_analyze_audio`), `on_db` (12), `off_db` (6), `hangover` (0,15 s), `merge_gap` (0,2 s), `min_region` (0,08 s), `faint_db` (30), `offset`, `limit` (100, como mucho 500).
- **Cómo decide:** se mide la banda vocal (de 100 Hz a 4 kHz, así que el zumbido de la red y el siseo no cuentan) cada 10 ms; el ruido de fondo es el percentil 10 de esos niveles, sin el silencio digital. La voz empieza cuando el nivel sube `on_db` por encima del ruido y dura mientras se mantiene `off_db` por encima, así que las caídas entre sílabas no parten una palabra; se añade `hangover` tras cada región para los finales de palabra, se unen los huecos más cortos que `merge_gap` y se descartan las regiones más cortas que `min_region` (clics). Los fragmentos más de `faint_db` por debajo del nivel típico de la voz se descartan antes de unir: en un episodio real, ruidos pequeños 30 dB o más por debajo de la voz unían pausas y las ocultaban.
- **Salida:** `regions` en tiempo del proyecto (inicio, fin, duración, nivel medio de la banda vocal, `confidence` según lo lejos que está del ruido de fondo), `total`, `speech_seconds`, el ruido de fondo y los dos umbrales, el nivel típico de la voz (`speech_level_db`) y cuántos fragmentos débiles se descartaron (`faint_dropped`), y `contrast_db` (con menos contraste que `on_db` no hay voz clara, y una nota lo indica).
- **Límites:** es un detector de energía. Una risa, una tos o una puerta fuerte en la banda vocal cuentan como actividad, que es lo que necesitan el ducking y la nivelación; encontrar palabras es tarea de la transcripción (TW-1630).
- **Errores:** `ANALYSIS_DISABLED`, `TOO_LONG`, `NOT_FOUND`, `BAD_AUDIO`, `BAD_TIME`, `BAD_REQUEST`.

### `cubase_measure_loudness` (lectura, necesita `[analysis] enabled`)

La sonoridad tal como la piden las especificaciones de entrega, medida como la definen ITU-R BS.1770 y EBU R128 (TW-1603).

- **Entrada:** `file`, una ruta absoluta: WAV, AIFF, FLAC, Ogg, MP3, o AAC (`.m4a`, decodificado con `afconvert` de macOS en un archivo temporal que se borra después).
- **Salida:**

  | Campo | Significado |
  |---|---|
  | `integrated_lufs` | Sonoridad integrada: bloques de 400 ms, con puerta en −70 LUFS y 10 LU por debajo de su media. `null` para el silencio o un archivo de menos de 400 ms. |
  | `momentary_max_lufs`, `short_term_max_lufs` | El bloque de 400 ms más alto y la ventana de 3 s más alta. |
  | `loudness_range_lu` | Rango de sonoridad (EBU Tech 3342): dispersión de los valores a corto plazo entre sus percentiles 10 y 95. `null` por debajo de unos 3 s. |
  | `sample_peak_dbfs`, `true_peak_dbtp` | La muestra más alta, y el pico de la señal sobremuestreada 4× (a lo que se refiere un techo como −1 dBTP). |
- **Los archivos mono** se miden como un solo canal: dan 3 dB menos que la misma señal en dos canales (una nota lo indica).
- **Comprobado con** las señales de prueba de EBU Tech 3341 (sonoridad integrada, puertas; ±0,1 LU) y Tech 3342 (rango de sonoridad; ±1 LU), las tablas de coeficientes de BS.1770 a 48 kHz y una implementación independiente (pyloudnorm, ±0,1 LU).
- **Errores:** `ANALYSIS_DISABLED`, `TOO_LONG`, `NOT_FOUND`, `BAD_AUDIO`, `BAD_REQUEST`.

## Espacio de trabajo del proyecto

### `cubase_workspace` (`status` lee; `init`, `record` y `forget` escriben archivos, con dry run)

La carpeta `Trackwright/` dentro de la carpeta del proyecto abierto, donde las skills guardan sus archivos (TW-1602). La carpeta del proyecto sale de los archivos que Cubase tiene abiertos; sin proyecto, o con varios, no se adivina.

- **Entrada:** `action` (`status` por defecto, o `init`) y `dry_run` (para `init`).
- **`status`:** dice si la carpeta existe, qué subcarpetas crearía `init`, si existen `state.json` y `profile.toml`, cuántos elementos tiene anotados cada skill (`owned`, por `skill:tipo`) y un resumen del perfil del episodio. Siempre permitido.
- **`init`:** crea `Trackwright/` y sus subcarpetas `renders/`, `previews/`, `analysis/` y `reports/`, y nada más. Necesita `[workspace] enabled`; se puede repetir sin efecto.
- **`record`, `forget`** (TW-1609): mantienen `state.json`, lo que ha creado cada skill. `record` recibe `kind` (`track`, `plugin`, `render`, `preview`, `marker`, `automation`, `report`), `key` (un uid de pista, `<uid de pista>/slot:N`, una ruta…), `skill`, `run_id` y `details`; un registro con el mismo tipo y clave sustituye al anterior (el creador más reciente es el dueño, y una nota dice de quién era). `forget` lo quita. Dry run por defecto (`before` y `after`); necesitan `[workspace] enabled` y el espacio de trabajo creado. `status` lista los elementos (`items`, los 200 primeros). Ver [el contrato de las skills](07-skill-contract.es.md).
- **Estructura:**

  | Ruta | Contenido |
  |---|---|
  | `renders/` | audio procesado que las skills vuelven a importar en Cubase |
  | `previews/` | archivos cortos para escuchar antes de aprobar un cambio |
  | `analysis/` | resultados de análisis ligados a la exportación de la que salen |
  | `reports/` | informes de control de calidad y de entrega |
  | `state.json` | lo que ha creado cada skill, para que al repetirla actualice lo suyo y nunca lo del usuario |
  | `profile.toml` | el perfil del episodio: roles de las pistas, rangos protegidos, notas |
- **Seguridad:** cada ruta se comprueba para que quede dentro de `Trackwright/` (sin `..`, rutas absolutas ni enlaces simbólicos que salgan); se rechaza un `Trackwright` que sea un enlace simbólico o un archivo; los archivos se escriben de forma atómica.
- **Errores:** `WORKSPACE_DISABLED`, `NO_PROJECT_FOLDER` (desconocida o ambigua), `BAD_WORKSPACE`, `NO_WORKSPACE`.

### `cubase_profile` (lee; `write_show` y `write_episode` escriben archivos, con dry run)

Perfiles de programa, de episodio y de entrega (TW-1607). Tres capas, cada una por encima de la anterior: **integrado** (los valores por defecto de Trackwright: los criterios de silencio de `cubase_analyze_audio`) < **programa** (`~/.config/trackwright/shows/<programa>.toml`, compartido por todos los episodios) < **episodio** (`Trackwright/profile.toml`, que además nombra su programa). Las tablas se combinan clave a clave; las listas se sustituyen enteras.

- **Entrada:** `action`, `show` (por defecto, el que nombra el episodio), `data` (para escribir: el perfil completo, como las tablas del archivo TOML), `dry_run`.
- **`resolve`** (por defecto): los `settings` combinados, `origins` (de qué capa viene cada valor, como `editing.padding_seconds: show`), los rangos `protected` del episodio, los perfiles de entrega de `delivery.targets`, y `episode`: el perfil del episodio tal como está guardado (parte de él para `write_episode`, nunca de `settings`, o los valores del programa se copiarían en el episodio).
- **`shows`:** los perfiles de programa encontrados. **`delivery`:** todos los perfiles de entrega disponibles, integrados y propios del programa o del episodio.
- **`write_show`, `write_episode`:** validan `data` y sustituyen el archivo entero; el dry run devuelve `before` y `after` (TOML) para enseñárselos al usuario. Necesitan `[workspace] enabled`; el del episodio necesita el espacio de trabajo creado.
- **Ajustes:** `track_roles` y `voices` (`pan`) por **nombre** de pista (los uid se repiten entre proyectos hechos con la misma plantilla); `music.approved`; `ducking` (`depth_db`, `pre_roll_seconds`, `hold_seconds`, `release_seconds`); `editing` (`min_silence_seconds`, `padding_seconds`); `delivery` (`targets`, y `profiles` de los servicios propios del programa). El episodio añade `show`, `protected` (`start`, `end`, `note` en segundos) y `notes`.
- **Perfiles de entrega:** objetivo de sonoridad y tolerancia, techo de pico real, si la plataforma normaliza al reproducir, códecs, canales, frecuencias de muestreo, tasas de bits, tamaño de archivo, qué es obligatorio y qué solo recomendado, y `sources`. **Cada valor debe estar respaldado por una fuente** (una URL, la fecha en que se leyó, los campos que respalda, una cita breve), o el perfil se rechaza. Integrados, leídos el 2026-11-15:

  | Nombre | Sonoridad | Pico real | Formato | Fuente |
  |---|---|---|---|---|
  | `apple` | −16 LUFS ±1 | −1 dBTP | AAC o MP3; 44,1/48 kHz; 64–256 kbps | Apple Podcasts for Creators, requisitos de audio |
  | `spotify` | no publicada para podcasts | no publicado | MP3, M4A o WAV; mono o estéreo; 128 kbps o más | Spotify for Creators; Podcast Delivery Specification v1.10 |
  | `youtube` | no publicada | no publicado | AAC u Opus; estéreo; 48 kHz; 384 kbps; hasta 256 GB o 12 h | Ayuda de YouTube |
  | `ivoox` | no publicada | no publicado | MP3, M4A o WAV; 300 MB (consejo, blog de 2022) | blog de iVoox (no se pudo leer el centro de ayuda) |

  Los −14 LUFS de Spotify están en su página de música, no de podcasts, así que no se usan. Un programa puede añadir un servicio con `delivery.profiles.<nombre>` y la fuente del usuario.
- **Errores:** `WORKSPACE_DISABLED`, `NO_PROJECT_FOLDER`, `NO_WORKSPACE`, `NOT_FOUND` (un programa), `BAD_PROFILE`, `BAD_REQUEST`.

### `cubase_preview` (escribe un archivo, con dry run)

Un archivo corto para escuchar antes de cambiar el proyecto (TW-1615): hasta 8 exportaciones, cada una colocada por su inicio en el proyecto y con su propia ganancia, mezcladas en un rango del proyecto de hasta 120 s, y escritas como WAV de 32 bits float en `Trackwright/previews/` (sin sobrescribir: el siguiente recibe `-2`). Por ejemplo, la exportación de la voz más la música atenuada alrededor de una primera palabra. El usuario lo escucha fuera de Cubase (Vista rápida en el Finder, o cualquier reproductor).

- **Entrada:** `sources` (`[{file, start, gain_db}]`), `start` y `end` (segundos de proyecto), `name`, `skill`, `dry_run`.
- **`levels_db`:** el nivel de cada fuente en el rango; una nota avisa cuando una está en silencio allí (una preescucha en un hueco de la música solo suena la voz).
- **Mezcla:** silencio donde una fuente no tiene audio; una fuente mono en los dos canales; todas las fuentes deben tener la misma frecuencia de muestreo (`BAD_AUDIO` si no).
- **Necesita** `[analysis] enabled` y `[workspace] enabled`, y el espacio de trabajo creado.
- **Errores:** `WORKSPACE_DISABLED`, `ANALYSIS_DISABLED`, `NO_WORKSPACE`, `NO_PROJECT_FOLDER`, `NOT_FOUND`, `BAD_AUDIO`, `BAD_TIME`, `BAD_REQUEST`.

### `cubase_ducking_plan` (lectura, necesita `[analysis] enabled`)

Planifica cómo baja la música bajo la voz (TW-1614), sin escribir nada. El mismo objeto `ducking` renderiza la música con `cubase_render` (`process: "duck"`).

- **Entrada:** `ducking`: `voice_file` (la exportación de las pistas de voz en solo juntas) y `voice_start` (el inicio de su rango), `attenuation_db` (−10), `pre_roll` (0,25 s), `hold` (0,8 s), `recovery` (1,2 s), `merge_gap` (0,9 s), `overrides` y `use_protected` (true); `music_start` y `music_seconds` (dónde está la exportación de la música, para recortar a ella los tramos); `offset`, `limit`. Los valores por defecto son los de partida de la lluvia de ideas, no normas.
- **Cómo:** regiones de voz de la exportación de la voz (como `cubase_detect_speech`), unidas sobre pausas más cortas que `merge_gap`, mantenidas `hold` después de la última palabra; dos tramos demasiado cercanos para que la música suba y vuelva a bajar se convierten en uno (sin bombeo). La música empieza a bajar `pre_roll` antes de la primera palabra y vuelve a subir durante `recovery`, en líneas rectas en dB: sin saltos, exactamente `attenuation_db` en la parte plana.
- **Excepciones** (segundos de proyecto): `hold` mantiene la música abajo en un tramo ("no subas la música entre esas dos frases"), `free` la mantiene arriba ("sin ducking bajo la intro"), `depth` usa otro `depth_db`. Con `use_protected`, los rangos protegidos del perfil del episodio también se quedan arriba. Junto a un tramo `free` o un rango protegido, la bajada termina `recovery` antes y empieza `pre_roll` después, así que la música está a nivel completo durante todo él.
- **Salida:** el número de regiones de voz, los rangos protegidos usados, los tramos atenuados (inicio y fin, profundidad, dónde empiezan y acaban las rampas), el tiempo atenuado, y `moments` para preescuchar (la primera palabra y la recuperación de cada tramo; con `music_file`, la exportación de la música, solo aquellos con música sonando alrededor, con su nivel). Con `previous` (el plan antes de un cambio, TW-1615), `changed` lista los tramos donde cambia la música, para preescuchar y comprobar solo esos.
- **Errores:** `ANALYSIS_DISABLED`, `TOO_LONG`, `NOT_FOUND`, `BAD_REQUEST` (una especificación incorrecta), `BAD_TIME`.

### `cubase_render` (`render` escribe archivos, con dry run; `list` lee)

Audio procesado para el proyecto, escrito en `Trackwright/renders/` (TW-1606). La API de Cubase no puede procesar el audio de una pista, así que una skill exporta la pista sola, procesa la exportación en Python e importa el resultado en una pista nueva, silenciando la original.

- **Entrada:** `action` (`render` por defecto, o `list`); para `render`: `file` (ruta absoluta de la exportación), `start` (tiempo de proyecto de la primera muestra de la exportación: el inicio de su rango), `process` (`gain` o `duck`), `gain_db` (±40), `ducking` (para `duck`: el objeto de `cubase_ducking_plan`), `name` (por defecto `<pista u origen>-<proceso>`), `track` (la pista a la que sustituye el render), `skill` y `run_id` (quién renderiza, se guarda en la procedencia), `dry_run`.
- **`render`:** escribe `<nombre>.wav` (WAV de 32 bits float, con la frecuencia y los canales del origen) y `<nombre>.json`, la **procedencia**: ruta, tamaño y SHA-256 del origen, el proceso y sus parámetros, la posición en el proyecto, la pista a la que sustituye (nombre y uid), el SHA-256 y el pico del propio render, y la versión de Trackwright. Un render existente nunca se sobrescribe (Cubase puede seguir usándolo): el siguiente es `<nombre>-2.wav`. Necesita `[analysis] enabled` (lee audio, con su `max_seconds`) y `[workspace] enabled`, y el espacio de trabajo creado con `cubase_workspace`.
- **`duck`** (TW-1614): la exportación de la música (`file`, `start`) atenuada bajo la voz con la envolvente que `cubase_ducking_plan` muestra para el mismo objeto `ducking`; la procedencia guarda el objeto completo, el SHA-256 de la exportación de la voz, los rangos protegidos usados y el tiempo atenuado.
- **Después:** crear una pista de audio (`cubase_add_track_interactive`), importar el render en ella con `cubase_import_audio` en la posición devuelta y silenciar la pista original (`cubase_set_track_mix`). En las opciones de importación de Cubase, desmarcar «Copiar archivo a carpeta del proyecto» (el render ya está en la carpeta del proyecto) y dejar desactivada la conversión a 24 bits.
- **`list`:** cada render con su procedencia, la pista en la que se importó (de `state.json`), si esa pista sigue en el proyecto, y `problems`: el render cambió después de hacerse, su origen cambió o ya no está.
- **Errores:** `WORKSPACE_DISABLED`, `ANALYSIS_DISABLED`, `TOO_LONG`, `NO_PROJECT_FOLDER`, `NO_WORKSPACE`, `NOT_FOUND`, `BAD_AUDIO`, `BAD_TIME`, `BAD_REQUEST`, `BAD_RENDER`.

## Analizar audio

### Qué audio, y la caché (TW-1608)

`cubase_analyze_audio`, `cubase_measure_loudness` y `cubase_detect_speech` dicen qué audio midieron y guardan sus resultados:

- **`source`:** el archivo, su tamaño, fecha de modificación y SHA-256, y el rango del proyecto que cubre (`start`, `end`). `project_saved_after` es true cuando un archivo de proyecto (`.cpr`) de la carpeta del proyecto se guardó después de escribirse el archivo: puede que el proyecto haya cambiado (cortes, procesado, automatización), así que una skill pregunta si exportar de nuevo (null para un archivo fuera de la carpeta del proyecto abierto). Los cambios sin guardar no se pueden ver; solo se leen las fechas de modificación de los `.cpr` de la carpeta.
- **`cache`:** para un archivo dentro de la carpeta del proyecto abierto, con el espacio de trabajo creado y `[workspace] enabled`, cada resultado se guarda en `Trackwright/analysis/` con una clave hecha del análisis, el SHA-256 del archivo y los parámetros (`start` incluido). La misma pregunta sobre el mismo audio se responde desde allí (`hit`) sin volver a leer el archivo; una exportación nueva tiene otros bytes, así que nunca se confunde con la anterior (`stored`: calculado y guardado; `off`: sin caché). `hashes.json` recuerda el hash de cada archivo por ruta, tamaño y fecha de modificación, para no calcular el hash de un episodio largo en cada llamada. La paginación (`offset`, `limit`) funciona sobre el resultado guardado.

### `cubase_final_qc` (lectura, necesita `[analysis] enabled`)

Control de calidad final de un archivo de episodio, el entregado o una exportación nueva (TW-1611). Una sola lectura del archivo, comparada con los perfiles de entrega (`targets`, por defecto los `delivery.targets` del perfil; ver `cubase_profile`).

- **Entrada:** `file`, `start` (tiempo de proyecto de su primera muestra), `expected_seconds` (el rango aprobado), `targets`, `long_pause_seconds` (3), `jump_lu` (6), `report`.
- **Comprobaciones** (`pass` o `fail`, cada una con la `source` de la plataforma): códec (por la extensión: `.m4a` es AAC), canales, frecuencia de muestreo, tasa de bits media de los archivos comprimidos (tamaño entre duración, ±2 %), tamaño del archivo, sonoridad integrada frente a objetivo ± tolerancia, pico real frente al techo, y duración frente a `expected_seconds` (±0,01 s en PCM, ±0,1 s en MP3/AAC, que añaden relleno del codificador). Un valor que la plataforma no publica da un elemento `info` ("not published by the platform"), nunca un aprobado ni un fallo.
- **Avisos** (`warn`, nunca un fallo): silencio al principio o al final, pausas de `long_pause_seconds` o más, cambios de nivel de `jump_lu` o más entre secciones consecutivas de 10 s (sonoridad a corto plazo, sin contar las pausas), muestras a fondo de escala, una tasa de bits por debajo de la recomendada.
- **Elementos manuales:** pistas que no deben estar en el archivo (una mezcla no las muestra), etiquetas y portada, contenido.
- **`moments`:** dónde escuchar, en tiempo de proyecto: el principio, el final, las pausas más largas, los cambios de nivel, los 3 s más fuertes.
- **`verdict`:** `fail` cuando falló alguna comprobación. `source` dice qué archivo se midió (TW-1608).
- **`report`:** escribe además `Trackwright/reports/qc-<archivo>-<hora>.json` y `.md`; necesita `[workspace] enabled` y el espacio de trabajo creado.
- **Errores:** `ANALYSIS_DISABLED`, `TOO_LONG`, `NOT_FOUND`, `BAD_AUDIO`, `BAD_TIME`, `BAD_REQUEST` (un destino desconocido), `WORKSPACE_DISABLED`, `NO_WORKSPACE`, `NO_PROJECT_FOLDER`.

### `cubase_delivery_plan` (lectura, necesita `[analysis] enabled`)

Qué poner en Stereo Out para entregar la mezcla a un perfil de entrega (TW-1613), a partir de una exportación maestra y del fader actual. No cambia nada: la skill `podcast-delivery` aplica el plan con `cubase_set_parameter` y `cubase_insert_plugin` después de que el usuario lo apruebe.

- **Entrada:** `file` (la maestra: una exportación WAV del episodio entero), `target` (un perfil de entrega), `codec` (el formato a entregar: `mp3`, `aac`, `wav`; por defecto el primero del perfil).
- **Salida:** la sonoridad, la tolerancia y el techo del destino con su `source`; la sonoridad integrada y el pico real de la maestra; `fader_now_db`, `gain_db` (objetivo − medido) y `fader_db` (el valor a aplicar); `reachable` (false cuando pasaría de los +6,02 dB del fader); `predicted_lufs` y `predicted_true_peak` del archivo entregado antes de cualquier limitador; `limiter`, `threshold_db` y `peak_reduction_db` cuando se pasaría del techo; `limiter_slot` (la ranura 7 u 8 de Stereo Out, reutilizando un limitador que ya esté allí).
- **Las cifras en que se basa** (TW-1612, `experiments/tw1612/`): el fader mueve la sonoridad exactamente lo que vale su ganancia; las ranuras 1–6 están antes del fader y las 7–8 después, así que un limitador en 1–6 no es un techo en cuanto el fader sube el nivel (se avisa cuando hay uno); el Brickwall Limiter deja pasar 0,24 dB de picos entre muestras; el MP3 de 128 kbps subió el pico real 0,82 dB (se usa también para AAC, con un aviso: no medido). El umbral es el techo menos ambos márgenes, redondeado hacia abajo a 0,1 dB.
- **Avisos:** un objetivo que el fader no alcanza; más de 6 dB de reducción de picos (trabajo para compresión o nivelado antes); la sonoridad que se lleva el limitador (contar con una segunda pasada); un perfil sin objetivo de sonoridad o sin techo; las ranuras 7 y 8 ocupadas por otros plugins.
- **Errores:** `ANALYSIS_DISABLED`, `TOO_LONG`, `NOT_FOUND`, `BAD_AUDIO` (una maestra en silencio), `BAD_REQUEST` (un destino desconocido, un fader en −∞).

### `cubase_analyze_audio` (lectura, necesita `[analysis] enabled`)

La API de Cubase no puede leer lo que contiene una pista, así que los silencios y el ruido se miden sobre un **archivo exportado**. Una exportación entre localizadores está alineada con el proyecto a la muestra (verificado, TW-1501): tiempo del proyecto = inicio del rango + tiempo en el archivo.

- **Flujo habitual:**
  1. Poner en solo la pista que se quiere analizar (`cubase_set_track_mix`): Cubase Elements solo exporta Stereo Out.
  2. `cubase_export_mix` con el rango; el usuario exporta WAV, 32 bits float, a la frecuencia del proyecto.
  3. `cubase_analyze_audio` con el archivo de la fase `confirm` y `start` = el inicio del rango. Quitar el solo.
- **Entrada:**
  - `file`: ruta absoluta (WAV, AIFF, FLAC u Ogg).
  - `start`: tiempo del proyecto de la primera muestra del archivo, en segundos (`"2"`, `"0:00:02.000"`); `"0"` por defecto.
  - `min_seconds` (2), `above_floor_db` (10), `threshold_db` (ninguno), `padding_seconds` (0,25), `merge_gap_seconds` (0,05: más corto que una sílaba, para que la voz nunca se tome por un ruido breve), `offset` y `limit` (100, como mucho 500).
- **Cómo mide:** el nivel RMS de cada ventana de 20 ms, con todos los canales a la vez. El ruido de fondo es el percentil 10 de esos niveles, sin contar el silencio digital (los ceros exactos que tiene una exportación antes y después de los eventos). Un silencio es un tramo por debajo del umbral que dura al menos `min_seconds`; los ruidos más cortos que `merge_gap_seconds` dentro de él no lo rompen, y se conserva `padding_seconds` a cada lado para no cortar palabras (no en los extremos del archivo).
- **Umbral:** ruido de fondo + `above_floor_db`, que no depende de los faders ni de la ley de panorama (una pista mono centrada se exporta 3 dB más baja). Solo si queda por debajo del nivel del sonido (percentil 90); si no, solo cuenta el silencio digital, y una nota lo indica. `threshold_db` da en su lugar un valor absoluto en dBFS.
- **Salida:** formato, frecuencia de muestreo, canales y duración; `noise_floor_db`, `threshold_db`, `peak_db`, `rms_db`; `silences` en tiempo del proyecto (`start`, `end`, sus valores en segundos, `seconds`, `level_db`, `digital`), `total` y `total_seconds`. Los niveles son los de la exportación, no los del archivo de origen.
- **Solo lee el archivo:** no se envía nada a Cubase, y solo se devuelven las medidas.
- **Errores:** `ANALYSIS_DISABLED`, `TOO_LONG` (más largo que `[analysis] max_seconds`), `NOT_FOUND`, `BAD_AUDIO`, `BAD_TIME`, `BAD_REQUEST` (ruta relativa, criterios no válidos).

## Abrir Cubase

### `cubase_launch` (escritura, con ensayo)

- **Entrada:** `project` (ruta de un `.cpr`, opcional) y `dry_run`.
- **Qué hace:**
  - comprueba si el script responde y si el proceso de Cubase existe (`pgrep -x`);
  - si Cubase está cerrado, lo abre con `open -a "Cubase 15"` (y el proyecto, si lo hay);
  - espera hasta `[cubase] launch_timeout` a que el script responda.
- **Estados:**

  | Estado | Significado |
  |---|---|
  | `planned` | Ensayo: Cubase está cerrado y se abriría. |
  | `already_running` | El script ya responde. No hace nada. |
  | `running_without_script` | Cubase está abierto pero el script no responde (sin proyecto, con un diálogo o sin el script instalado). **No abre una segunda instancia.** |
  | `ready` | Cubase abierto y el script respondiendo. |
  | `awaiting_user` | Cubase arranca, pero el script no ha respondido a tiempo: probablemente hay un diálogo esperando al usuario. |
- **Nunca** cierra Cubase, fuerza su salida ni guarda proyectos.
- Requiere las escrituras habilitadas.

## Herramientas de automatización

Mecanismo verificado en Cubase Elements 15.0.30: el script tiene en la superficie MIDI Remote un control por parámetro, enlazado a la **pista seleccionada**. Moverlo «tocado» mientras la pista tiene activada la escritura de automatización (W) y el proyecto se reproduce graba automatización, como un controlador físico en modo Touch. Escribir el parámetro directamente **no** graba.

### `cubase_list_automation_targets` (navegación)

- **Entrada:** `track`.
- **Salida:** cada parámetro automatizable con su clave (`parameter`), el parámetro de Cubase al que está enlazado (`title`, por ejemplo «Compressor / Threshold»), su valor actual y si está disponible (`available`).
- **Selección:** los controles de automatización siguen a la pista seleccionada, y Cubase los vincula a una nueva selección un momento después. Esta herramienta, `cubase_convert_value` y `cubase_record_automation` seleccionan la pista y esperan (hasta 3 s) a que el control de volumen lleve su nombre; si los controles nunca la siguen, se detienen con `CONTROLS_NOT_BOUND` y no tocan nada (TW-1616: leído al instante, el volumen de POC-TEST salió como el de otra pista).
- **Claves:**
  - `volume`, `pan`;
  - `send1.level` a `send4.level`;
  - `eq1.gain`, `eq1.freq` y `eq1.q`, hasta la banda 4;
  - `prefilter.gain`, `prefilter.lowcut` y `prefilter.highcut`;
  - `qc1` a `qc8` (Quick Controls);
  - `insert1.p1` a `insert2.p8`: los parámetros del plugin de los slots 1 y 2, en el orden de banco que decide Cubase.
- **Selecciona la pista,** porque los controles siguen la selección.
- **`display`** es el valor actual tal como lo muestra Cubase, en unidades reales («-18.2», «-20.0 dB», «100.0Hz»).
- **`converts_units`** indica si el parámetro admite valores en unidades reales. Todos lo admiten salvo los Quick Controls.

### `cubase_convert_value` (navegación, no cambia nada)

- **Entrada:** `track`, `parameter` y **uno** de estos dos: `plain` (unidades reales: −20 para −20 dB, 1000 para 1 kHz) o `value` (0..1).
- **Salida:** los dos valores. La conversión la hace Cubase (`convertParameterPlainToProcessValue`) y es exacta.
- **Para qué sirve:** sustituye a cualquier calibración. Verificado en Cubase Elements: el volumen va de 0 dB → 0,7891 a −20 dB → 0,2551, una escala **no lineal**, así que no hay que estimar valores.
- **Unidades verificadas:**
  - volumen, envíos y ganancias en dB;
  - frecuencias en Hz;
  - Q sin unidad;
  - Ratio del compresor como número (4 = 4:1);
  - **panorama de −100 (izquierda) a +100 (derecha)**, con 0 en el centro.
- **Errores:** `OUT_OF_RANGE` (fuera del rango del parámetro), `NO_UNIT_CONVERSION` (Quick Controls) y `NOT_AUTOMATABLE`.

### `cubase_record_automation` (escritura, reproduce audio)

- **Entrada:**
  - `track` y `parameter`;
  - `points`: de 1 a 64 puntos en orden creciente. Cada punto lleva `position` («9. 1. 1. 0») y **uno** de estos dos valores:
    - `plain`: en unidades reales, convertido por Cubase. **Es lo recomendado;**
    - `value`: normalizado, de 0 a 1;
  - `verify` (por defecto `true`) y `dry_run`.
- **Qué hace:**
  1. selecciona la pista;
  2. activa W y desactiva R;
  3. reproduce desde un compás antes del primer punto;
  4. «toca» el control, recorre la curva (lineal entre puntos) siguiendo la posición del cursor y lo «suelta»;
  5. para la reproducción, deja W como estaba y **R activada**, para que suene la curva nueva (TW-1616: con R desactivada de nuevo, una exportación sonó con el valor del último punto en lugar de la curva); `read_automation` lo indica.
  - Con `verify`, vuelve a reproducir con R activado y compara el valor leído con la curva (tolerancia 0,05).
- **Salida:** la curva con el valor normalizado de cada punto (`points`), los valores escritos (`written`), `complete` (`false` si la reproducción se paró antes del último punto, por ejemplo porque el usuario pulsó Stop: la curva queda cortada), `read_automation`, `verified`, las discrepancias (`mismatches`) y notas.
- **Errores:** `PARAM_NOT_FOUND`, `OUT_OF_RANGE`, `NO_UNIT_CONVERSION`, `NOT_AUTOMATABLE` (no hay nada enlazado: slot vacío o Quick Control sin asignar), `TRANSPORT_RUNNING`, `NOT_RECORDED`, `BAD_TIME`, `CONTROLS_NOT_BOUND` (los controles no siguieron la selección de la pista) y `WRITES_DISABLED`.
- **Limitaciones:**
  - las posiciones usan el compás en la posición del cursor (`cubase_get_project`). Si hay cambios de compás a lo largo del proyecto, no se siguen; si Cubase no informa del compás, se supone 4/4;
  - hay un punto escrito cada ~0,1–0,3 s;
  - **una pista creada después de cargarse el script de MIDI Remote no graba automatización desde él** (TW-1616: el parámetro se mueve, pero Cubase no escribe nada; tras recargar los scripts la misma curva se grabó y verificó). Usa `verify`: una relectura fallida lo indica; recarga los scripts de MIDI Remote o reinicia Cubase, y graba de nuevo;
  - la curva actúa donde actúa el parámetro: PreGain está antes de las inserciones, así que un compresor en la pista cambia cuánto se oye de una bajada de PreGain (TW-1616: −10 dB salieron entre −7 y −9 dB);
  - **suena**: baja el volumen del monitor;
  - con R activado, la curva grabada manda sobre el parámetro.

## Lo que no se puede hacer

Verificado en la prueba de concepto:
- **Enrutado:** cambiar entradas, salidas o el destino de los envíos. La API lo ignora o lo deja en «Sin bus».
- **Leer el contenido de las pistas:** eventos, audio, marcadores como datos o curvas de automatización.
- **Completar diálogos** de Cubase: añadir pistas con opciones o detectar silencios.
- **Cargar módulos del channel strip** distintos del EQ (Cubase Elements).
