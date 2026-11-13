# Referencia de herramientas MCP

El servidor `trackwright` publica 28 herramientas. Cada una tiene un esquema de entrada y otro de salida que el cliente MCP recibe automáticamente; aquí se explica cómo usarlas y qué limitaciones tienen.

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
- **Formato de segundos:** `"2.5"`, `"1:30"` o `"0:00:02.000"`.
- **En segundos,** la posición se relee con la pantalla de segundos de Cubase, sin suponer compás ni tempo. Los localizadores no se pueden mover con la pantalla de segundos (verificado), así que se colocan llevando el cursor allí y usando «Set Left/Right Locator»; luego el cursor vuelve a su sitio.

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
| `addtrack.audio`, `addtrack.group`, `addtrack.folder`, `audio.detect_silence`, `file.export_audio_mixdown` | dialog (exportar: verificado, TW-1204) |
| `addtrack.marker`, `marker.insert`, `project.select_track_next`, `project.select_track_prev`, `transport.locate_next_marker`, `transport.locate_prev_marker` | direct |
| `project.remove_selected_tracks` | confirm |
| `project.selected_to_new_folder`, `transport.return_to_zero`, `transport.locators_to_selection` | unknown |
| `automation.mode_touch`, `automation.mode_auto_latch`, `automation.mode_cross_over`, `automation.next_mode`, `automation.toggle_write_selected` | unknown (experimento TW-1206) |
| `transport.start`, `transport.stop` | direct (verificado: reproduce y para; nunca graba) |
| `edit.delete_time`, `edit.cut_time`, `edit.insert_silence`, `edit.crop_range`, `edit.select_all_on_tracks` | ui_selection (verificado, TW-1211: actúan sobre la selección de rango) |
| `transport.set_left_locator`, `transport.set_right_locator`, `transport.locate_next_event`, `transport.locate_selection`, `transport.locate_selection_end` | direct (verificado, TW-1211) |
| `process.silence` | dialog (verificado, TW-1211: pregunta si el archivo de audio está compartido) |
| `edit.select_events_under_cursor`, `transport.locate_prev_event`, `transport.to_left_locator`, `tool.range`, `tool.select` | unknown |

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
- **Errores:** `BAD_TIME`, `TRANSPORT_RUNNING`, `NO_RANGE_SELECTION` (Cubase no creó la selección, por ejemplo porque la ventana de proyecto no está delante), `SPLIT_FAILED` y `WRITES_DISABLED`.
- **Deshacer:** **Edición > Deshacer** en Cubase lo revierte, como se verificó con cada acción. No se guarda el proyecto.
- **No incluida:** «Process > Silence» abre un diálogo si el archivo de audio lo comparten varios eventos.

## Exportar la mezcla

### `cubase_export_mix` (con el usuario, dos fases)

Trackwright **nunca exporta por sí mismo**: coloca el rango y abre el diálogo de Cubase; el formato y el botón son del usuario.

- **Fase `start`** (`dry_run` por defecto):
  - **Entrada:** `start` y `end` en segundos (o compases con `unit: "bars"`). Sin ellos, exporta **todo el audio**: «Select All» y «Locators to Selection» ponen los localizadores del primer al último evento.
  - **Qué hace:** pone los localizadores en el rango y abre «Exportar mezcla de audio». En Elements el diálogo no tiene campo de rango: exporta entre los localizadores (verificado).
  - **Salida:** `awaiting_user`, la carpeta que propondrá Cubase (`<carpeta del proyecto>/Mixdown`, deducida de los archivos abiertos), la duración esperada y `since` (marca de tiempo).
- **El usuario,** en el diálogo, revisa el canal (Stereo Out), el nombre, la ruta y el formato (WAV para archivar, MP3 para publicar) y pulsa **Exportar audio**.
- **Fase `confirm`:**
  - **Entrada:** `since` y `expected_seconds` de la fase anterior; `folder` si se eligió otra carpeta.
  - **Qué hace:** busca en la carpeta los archivos de audio creados después de `since` y lee **solo** su nombre, tamaño, fecha y duración (con `afinfo` de macOS).
  - **Salida:** `done` y `verified`, si la duración coincide con el rango (±0,15 s), o `not_found`.
- Los localizadores **se quedan** en el rango exportado.
- **Errores:** `TRANSPORT_RUNNING`, `CANNOT_PERFORM` (hay otro diálogo abierto), `BAD_TIME` y `WRITES_DISABLED`.

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
  5. para la reproducción y deja W y R como estaban.
  - Con `verify`, vuelve a reproducir con R activado y compara el valor leído con la curva (tolerancia 0,05).
- **Salida:** la curva con el valor normalizado de cada punto (`points`), los valores escritos (`written`), `verified`, las discrepancias (`mismatches`) y notas.
- **Errores:** `PARAM_NOT_FOUND`, `OUT_OF_RANGE`, `NO_UNIT_CONVERSION`, `NOT_AUTOMATABLE` (no hay nada enlazado: slot vacío o Quick Control sin asignar), `TRANSPORT_RUNNING`, `NOT_RECORDED`, `BAD_TIME` y `WRITES_DISABLED`.
- **Limitaciones:**
  - las posiciones usan el compás en la posición del cursor (`cubase_get_project`). Si hay cambios de compás a lo largo del proyecto, no se siguen; si Cubase no informa del compás, se supone 4/4;
  - hay un punto escrito cada ~0,1–0,3 s;
  - **suena**: baja el volumen del monitor;
  - con R activado, la curva grabada manda sobre el parámetro.

## Lo que no se puede hacer

Verificado en la prueba de concepto:
- **Enrutado:** cambiar entradas, salidas o el destino de los envíos. La API lo ignora o lo deja en «Sin bus».
- **Leer el contenido de las pistas:** eventos, audio, marcadores como datos o curvas de automatización.
- **Completar diálogos** de Cubase: añadir pistas con opciones o detectar silencios.
- **Cargar módulos del channel strip** distintos del EQ (Cubase Elements).
