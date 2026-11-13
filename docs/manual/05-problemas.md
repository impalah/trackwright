# Resolución de problemas

Empieza siempre por:

```sh
uv run trackwright doctor
```

Cada comprobación que falla incluye un `fix` con la solución.

## `BRIDGE_UNAVAILABLE`: el puente no está disponible

- **Síntoma:** cualquier herramienta falla con `bridge socket not found` o `not accepting connections`.
- **Causa:** el puente no está en marcha, o se arrancó con otra configuración y usa otro socket.
- **Solución:**
  1. Arranca `uv run trackwright bridge` en una terminal.
  2. Si usas un archivo de configuración, el puente y el cliente MCP deben leer el mismo. Compara `socket_path` en `uv run trackwright config` desde ambos entornos.

## «another bridge is already listening» o «virtual ports … already exist»

- **Causa:** ya hay un puente en marcha, quizá en otra terminal.
- **Solución:** usa ese puente o ciérralo con Ctrl+C. Si se cerró de forma abrupta, el socket huérfano se limpia solo al arrancar.

## `ping` falla con `TIMEOUT`: Cubase no responde

- **Causa más probable:** la superficie MIDI Remote no está activa, o Cubase no tiene el script.
- **Solución:**
  1. `uv run trackwright script status` debe decir `up_to_date`. Si no, ejecuta `script install --apply` y **reinicia Cubase**.
  2. En la pestaña **MIDI Remote** de Cubase debe aparecer **Trackwright – Bridge**. Si no, añádela a mano (paso 6 del [manual de instalación](01-instalacion.md#6-activar-el-script-en-cubase)).
  3. Comprueba que la superficie usa la entrada `Trackwright To Cubase` y la salida `Trackwright From Cubase`.

## El panel de la superficie muestra «-» o solo la lámpara

- **Solo la lámpara, sin textos:** la página «Bridge» no está activa, normalmente porque el puente está parado. Arráncalo.
- **«-» en la fila de la pista:** no hay ninguna pista con canal de mezclador seleccionada.
- **Otra versión en el título:** Cubase tiene cargado otro script. Ejecuta `uv run trackwright script install --apply` y reinicia Cubase.

## El script no se actualiza

- **Causa:** Cubase no recarga los scripts modificados por sí mismo.
- **Solución:** reinicia Cubase. `cubase_status` mostrará la versión cargada (`script_version`).

## `STALE_REF` o `STALE_SESSION`

- **Causa:** Cubase se reinició o recargó el script, y los identificadores internos cambiaron. Además se **reutilizan** para otros objetos, así que una `ref` antigua podría señalar a otro objeto. Trackwright lo detecta y se niega a usarla.
- **Solución:** vuelve a listar (`cubase_list_tracks`, `cubase_list_inserts`). Para designar pistas, usa los selectores `uid:`, que son estables.

## `TIMEOUT` en una escritura

- **Causa:** Cubase no respondió a tiempo. Las operaciones con la API esperan a un ciclo interno de Cubase, de unos 110 ms; con Cubase muy cargado puede tardar más.
- **Qué significa:** **el cambio puede haberse aplicado o no.** Trackwright no reintenta y adjunta la relectura del valor (`read_back`).
- **Solución:** consulta `read_back`. Si se repite, sube `[bridge] write_timeout`.

## `BUSY`

- **Causa:** otra escritura, quizá de otra sesión MCP, seguía en curso cuando llegó esta. La escritura **no se envió**.
- **Solución:** repetirla es seguro.

## `WRITES_DISABLED` o `NOT_ALLOWED`

- **Causa:** la configuración no permite esa escritura.
- **Solución:** `[writes] enabled = true` y, si usas `allowed_tracks`, añade la pista. Reinicia el cliente MCP.

## Un comando «no hace nada»

- **Causa:** muchos comandos dependen del contexto de la ventana de Cubase (`ui_selection`) o abren un diálogo (`dialog`).
- **Solución:**
  - mira la pantalla de Cubase: puede haber un diálogo esperando;
  - `cubase_run_command` con `dry_run=true` muestra `can_perform`: con `false`, Cubase no puede ejecutarlo en ese momento (por ejemplo, Deshacer sin historial).

## La salida de una pista quedó en «Sin bus»

- **Causa:** alguien escribió el enrutado por la API. Trackwright no lo hace: el enrutado no se puede escribir por la API, y lo rechaza.
- **Solución:** en el Inspector de la pista, vuelve a elegir la salida, por ejemplo «Stereo Out».

## Una pista no aparece en `cubase_list_tracks`

- **Causa:** solo se listan las pistas con canal de mezclador. Las de marcadores y las carpetas no lo tienen.

## `UNAVAILABLE` en `cubase_get_transport`

- **Causa:** Cubase aún no ha enviado la posición del transporte en esta sesión.
- **Solución:** mueve el cursor una vez en Cubase y repite.

## Ver qué está pasando

```sh
uv run trackwright --log-level DEBUG bridge   # cada petición, su duración y su resultado
uv run trackwright bridge-status              # respuestas tardías, errores de protocolo, sesión
```

Cubase envía cada 5 segundos un «MIDI Identity Request» por el puerto de salida. Es normal: el puente lo cuenta como `foreign_frames` y lo ignora.
