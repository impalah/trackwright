# E10 — Endurecimiento tras la revisión independiente

Origen: revisión de código independiente del 2026-11-12, hecha por un agente sin contexto previo. Cada hallazgo se comprobó en el código antes de abrir su issue. Todas exigen un test que reproduzca el fallo.

## TW-1001 Recarga del script durante una herramienta → escritura sobre otro objeto

- **Estado:** hecha
- **Gravedad:** alta.
- **Problema:** `HostClient.call` renegocia la sesión y reintenta las lecturas tras `STALE_SESSION`. Una herramienta reúne IDs en varias llamadas. Si el script se recarga entre medias, una escritura posterior viaja con la sesión nueva y un ID de la anterior, y los IDs se reutilizan.
- **Solución:** cada herramienta fija la sesión en su primera llamada. Si una respuesta posterior trae otra sesión, la herramienta se detiene con `STALE_SESSION` **antes** de cualquier escritura.

## TW-1002 `remove_selected_tracks` con varias pistas seleccionadas

- **Estado:** hecha
- **Gravedad:** alta.
- **Problema:** solo comprueba `da.base`. «Remove Selected Tracks» borra **todas** las seleccionadas.
- **Solución:**
  - exigir que haya exactamente una pista con el parámetro 4000 activo y que sea la esperada;
  - documentar que las pistas sin canal de mezclador seleccionadas no se ven.

## TW-1003 Filtro de `list_parameters`: coincidencias perdidas y `truncated` erróneo

- **Estado:** hecha
- **Problema:** se pierden las coincidencias de una página que superan `limit`, y `truncated` no lo refleja.
- **Solución:** recorrer parámetro a parámetro, devolver `next_offset` (el índice siguiente al último consumido) y `truncated` siempre que queden parámetros.

## TW-1004 Relectura sin protección en `insert_plugin`

- **Estado:** hecha
- **Problema:** si la relectura tras un timeout de escritura también vence, el error resultante parece el de una lectura (`not_executed_or_lost`) y oculta que el resultado de la escritura es desconocido.
- **Solución:** proteger la relectura (`read_back_error`) y conservar el error de escritura.

## TW-1005 Presupuesto de tiempo en el puente

- **Estado:** hecha
- **Problema:** la espera del cerrojo de escritura, el `hello` y el reintento no cuentan dentro del timeout. El cliente puede rendirse mientras el puente ejecuta la escritura más tarde.
- **Solución:**
  - un plazo único por petición, del que cada subpetición usa solo lo que queda;
  - si el cerrojo de escritura no se libera a tiempo, responder `BUSY`, sin ejecutar.

## TW-1006 `set_track_mix` pierde los cambios ya aplicados si falla uno posterior

- **Estado:** hecha
- **Solución:** adjuntar `applied` al error con los cambios ya hechos.

## TW-1007 `add_track_interactive` confirma una pista que ya existía

- **Estado:** hecha
- **Solución:** la fase `start` rechaza nombres existentes con `NAME_CONFLICT`.

## TW-1008 `poll_changes` marca como inválidos objetos no comprobados

- **Estado:** hecha
- **Solución:** `still_valid` pasa a ser `null` cuando no se comprueba, y se informa de cuántos eventos no se comprobaron (`unchecked`).

## TW-1009 `expect_title` debe comprobarse en el script, de forma atómica

- **Estado:** hecha
- **Solución:** enviar `expectTitle` en `da.param.set`. La comprobación en Python se mantiene para los ensayos.

## TW-1010 Excepciones no previstas en el puente

- **Estado:** hecha
- **Problema:** `Bridge.handle` solo captura `TrackwrightError`. Cualquier otra excepción cierra la conexión sin respuesta y el cliente informa `BRIDGE_UNAVAILABLE`, que sugiere que no se ejecutó nada.
- **Solución:** responder `INTERNAL_ERROR`, con `outcome: unknown` en las escrituras.

## TW-1011 Respuesta que llega justo al vencer el timeout

- **Estado:** hecha
- **Problema:** si la respuesta llega entre el fin de la espera y la retirada de la petición pendiente, se pierde: ni se devuelve ni pasa a `late_responses`.
- **Solución:** tras una espera fallida, comprobar la respuesta bajo el cerrojo y, si ha llegado, usarla.

## TW-1012 Comprobaciones demasiado tempranas tras disparar un comando

- **Estado:** hecha
- **Problema:** `remove_selected_tracks` y `select_track` leen el estado en cuanto disparan el comando, y el efecto puede llegar un instante después.
- **Solución:** usar `wait_until`.

## TW-1013 Coherencia entre el código y el manual

- **Estado:** hecha
- **Problemas:**
  - **Referencias:** ninguna herramienta acepta `ref`; el manual dice que se validan antes de usarse, y `resolve_ref` es código muerto.
  - **`dry_run`:** el manual dice que toda escritura tiene `dry_run`, pero `add_track_interactive` no lo tiene.
  - **Localizadores:** `split_at_locators` sobrescribe los localizadores sin informar.
- **Solución:**
  - las `ref` son informativas: se elimina `resolve_ref` y se corrige el manual;
  - se documenta la excepción de `add_track_interactive`;
  - `split_at_locators` informa de los localizadores anteriores (`previous_left` y `previous_right`), pero **no** los restaura: hacerlo justo después de disparar el comando podría adelantarse a él, porque Cubase lo ejecuta en su propio ciclo. Es una decisión que se aparta de la sugerencia de la revisión.
  - Menores: `offset ≥ 0` en `cubase_list_tracks`.

## TW-1014 La ruta de instalación por defecto no se expandía

- **Estado:** hecha
- **Gravedad:** alta. Detectado al instalar por primera vez en la máquina del usuario (2026-11-12).
- **Problema:** pydantic no ejecuta los validadores sobre los valores por defecto. `[script] install_dir` conservaba el `~` literal, y `trackwright script install --apply` copió el script en `./~/Documents/…` **dentro del repositorio**, mientras informaba `up_to_date`. Los tests no lo detectaron porque siempre pasaban `--dir` con una ruta absoluta.
- **Solución:**
  - `validate_default=True` en `install_dir` y `socket_dir`;
  - `install_script` rechaza rutas relativas;
  - tests de regresión: las rutas por defecto son absolutas y el destino por defecto queda bajo `$HOME`.
- **Limpieza:** se borró la carpeta `./~` creada por error, que solo contenía ese archivo, y se reinstaló en la ruta correcta.
