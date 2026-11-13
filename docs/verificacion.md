# Registro de verificación contra Cubase

Cada entrada registra una ejecución **real** contra Cubase. Las pruebas con el simulador no se registran aquí.

## 2026-11-12 — primera verificación de Trackwright 0.1.0 (script 1.0.0)

- **Entorno:** macOS 27.2 (arm64), Cubase **Elements** 15.0.30, proyecto de pruebas con `POC-INSTR` (instrumento, con StudioEQ en el slot 1) y `POC-TEST` (audio).
- **Instalación:** `trackwright script install --apply` (tras corregir TW-1014). Cubase reiniciado. La superficie «Trackwright – Bridge» apareció sola al arrancar el puente.
- **`trackwright doctor`:** todas las comprobaciones correctas (script `up_to_date`, puente en marcha, Cubase responde con el script 1.0.0 y la aplicación 15.0.30).
- **`trackwright ping`:** correcto en 16 ms, con el eco Unicode `hola-ñ-✓`.
- **Tests de integración de lectura** (`TRACKWRIGHT_INTEGRATION=1`): 3 superados. Los 2 de escritura se saltaron: no se pidieron.
- **Las 9 herramientas de lectura**, ejecutadas sobre el servicio real:

| Herramienta | Resultado | Tiempo |
|---|---|---|
| `cubase_status` | sesión `dv06ye6vc1gb`, script 1.0.0, acceso al mezclador | 36 ms |
| `cubase_list_tracks` | 3 canales (Stereo Out, POC-INSTR, POC-TEST), sin el duplicado del final | 129 ms |
| `cubase_get_selected_channel` | `track: null`: no había ninguna pista con canal seleccionada | 108 ms |
| `cubase_list_inserts` (POC-INSTR) | slot 1 = StudioEQ, del 2 al 8 vacíos | 449 ms |
| `cubase_list_available_plugins` (filtro «eq») | colección «Por defecto», 53 plugins, 3 coincidencias (CurveEQ, DJ-Eq, StudioEQ) | 562 ms |
| `cubase_list_parameters` (channel, límite 5) | 39 parámetros; `next_offset` = 5, `truncated` = true | 224 ms |
| `cubase_list_parameters` (filtro «vol») | `Volumen` (1025) y `clickVolume` (4117) | 339 ms |
| `cubase_get_parameter` (strip:eq, 4232) | «EQ 1 Gain» = 0,5 («0.0dB», plain 0,0) | 554 ms |
| `cubase_get_transport` | cursor en 1. 1. 1. 0; ciclo entre los compases 2 y 4 | 17 ms |
| `cubase_poll_changes` | 2 eventos | 207 ms |

### Escrituras reversibles (tests de integración)

Comando: `TRACKWRIGHT_ALLOW_WRITES=1 TRACKWRIGHT_TEST_TRACK="POC-TEST"`. Resultado: **5 superados** en 1,52 s.

- **`test_mute_roundtrip`:** `cubase_set_track_mix` activa el mute de POC-TEST, lo verifica releyendo y lo restaura.
- **`test_cursor_roundtrip`:** `cubase_set_position` lleva el cursor al compás 3, lo verifica y lo devuelve a su posición.
- **Estado antes y después,** leído de forma independiente: mute `False` → `False`; cursor `1. 1. 1.  0` → `1. 1. 1.  0`. Nada quedó cambiado.

### Resto de escrituras y comandos (segunda tanda)

Ejecutadas directamente sobre el servicio, con la política de escritura habilitada solo para esta sesión. El usuario confirmó a la vista los pasos no observables por la API.

**Parte A, sin intervención:** 23 de 25 pasos correctos. Los 2 errores eran los esperados (`PRECONDITION_FAILED` por `expect_title` erróneo y `SLOT_OCCUPIED`).

| Herramienta | Prueba | Resultado |
|---|---|---|
| `cubase_set_track_mix` | volumen 0,7 y solo en POC-TEST, y restauración | `-1.98` dB y `Activ.`; restaurado y verificado |
| `cubase_rename_track` | POC-TEST → TW-RENAMED → POC-TEST, por `uid:` | verificado en los dos sentidos |
| `cubase_set_parameter` | EQ del strip +3 dB (`unit=plain`) y restauración | display `3.0dB`; restaurado |
| `cubase_set_parameter` | `expect_title` erróneo | `PRECONDITION_FAILED`, sin escribir |
| `cubase_select_track` | POC-INSTR, siguiente, anterior, POC-TEST | 4/4 verificados |
| `cubase_set_tempo` | 120 → 100 → 120 | relectura 99,99999 → 120 |
| `cubase_set_position` | ciclo 3–5, cursor en el segundo 4 (→ compás 3) y restauración | verificados |
| `cubase_insert_plugin` | Compressor en el slot 1 de POC-TEST y repetición | insertado y verificado; la repetición da `SLOT_OCCUPIED` |
| `cubase_list_parameters` | Threshold del Compressor insertado | tag 4201, `-20.0 dB` |

El estado final de POC-TEST (volumen, mute, solo, nombre), el tempo y el cursor coinciden con el inicial. **Queda insertado a propósito** Compressor en el slot 1 de POC-TEST: la API no tiene una forma verificada de quitar plugins.

**Parte B, con confirmación visual:**

| Herramienta | Prueba | Resultado |
|---|---|---|
| `cubase_markers` | crear pista de marcadores; marcador en el compás 2 | confirmado a la vista |
| `cubase_markers` | `locate_prev` desde el compás 4 | → compás 2 |
| `cubase_markers` | `locate_next` desde el compás 2, sin más marcadores | → `70. 4. 4. 97`, el final del audio de POC-TEST. **Hallazgo:** en la POC se observó que se quedaba quieto; ahora va al final del último evento |
| `cubase_run_command` | `project.remove_selected_tracks` con la pista de marcadores seleccionada a mano | borrada; las demás pistas, intactas. **Sin diálogo de confirmación**, porque el usuario había marcado «no volver a preguntar» en Cubase |
| `cubase_split_at_locators` | compases 10–12 | audio de POC-TEST cortado en 10 y 12 (confirmado a la vista); `previous_left` y `previous_right` = 2 y 4; restaurados después |
| `cubase_add_track_interactive` | `start` (diálogo) y `confirm` | diálogo abierto; el usuario nombró `TW-GROUP`; `confirm` → `done`, verificado, con su `uid:` |
| `cubase_remove_selected_tracks` | con una pista esperada errónea | `SELECTION_MISMATCH`, sin borrar |
| `cubase_remove_selected_tracks` | TW-GROUP, tras seleccionarlo | `done`, verificado; quedan Stereo Out, POC-INSTR y POC-TEST |

**Conclusión:** las **21 herramientas** se han ejecutado contra Cubase Elements 15.0.30. Los resultados que la API no puede observar los confirmó el usuario a la vista.

**Cambios que quedan en el proyecto de pruebas:**
- Compressor en el slot 1 de POC-TEST;
- audio de POC-TEST cortado en los compases 10 y 12;
- POC-TEST seleccionada.

El proyecto no se ha guardado.

## 2026-11-13 — uso real desde Claude Code

- **Registro:** `claude mcp add --scope user trackwright -- uv --directory /Volumes/Data/projects/sound/trackwright run trackwright serve`. `claude mcp list` → `✔ Connected`.
- **Configuración:** `~/.config/trackwright/config.toml` con `[writes] enabled = true`, sin limitar pistas.
- **Sesión nueva de Claude Code,** sin el contexto del desarrollo. Según el usuario funcionaron:
  - `cubase_status`;
  - el listado de pistas;
  - silenciar y volver a activar una pista. El modelo **ensayó primero** (`dry_run`) y **pidió confirmación** antes de aplicar, siguiendo las instrucciones del servidor.
- **Conclusión:** la cadena completa cliente MCP → `trackwright serve` → puente → Cubase funciona en uso real, y un modelo sin conocimiento previo del proyecto usa las herramientas a partir de sus descripciones.

## 2026-11-13 — experimento TW-1101 (panel de estado, script 1.0.1+tw1101)

- **Protocolo:** [`experiments/tw1101/README.md`](../experiments/tw1101/README.md).
- **Instalación:** `script install --file experiments/tw1101/Trackwright_Bridge.js --apply` y reinicio de Cubase.
- **Observación:** capturas del usuario de la pestaña MIDI Remote.

| Paso | Mecanismo | Resultado observado |
|---|---|---|
| E1 (puente parado) | superficie sin página activa | Solo se dibuja la lámpara, redonda y en su posición (8, 2). Los campos de texto no se ven y «Página de mapeado» muestra «-» |
| E2 (puente en marcha) | `page.setLabelFieldText` | ✅ Fila 0: «Trackwright 1.0.1+tw1101», recuadrado y con líneas a los lados |
| E2 | `lamp.mSurfaceValue.setProcessValue` cada 9 ciclos | ✅ La lámpara parpadea una vez por segundo, según el usuario |
| E2/E3 | `lamp.mSurfaceValue.setDisplayValue` + `statusField.relateTo(lamp)` | ❌ La fila 2 muestra siempre «-», también después de `ping --echo "hola panel"` (09:41:53). La API no da error (`capabilities.panel.errors = []`) |
| E4 | `page.setLabelFieldHostObject(…, mTrackSelection.mMixerChannel)` | ✅ La fila 1 muestra «-» sin selección y «POC-TEST» al seleccionarla. Se actualiza sola |
| E5 | rendimiento | ✅ `ping` en 15,9 ms, igual que sin panel |
| E6 | `capabilities.panel` | `{enabled: true, errors: []}` |

**Conclusiones:**
- **El dibujo antiguo** (un recuadro con una barra blanca y líneas a los lados) era el campo de texto `makeLabelField(0, 0, 4, 1)` **vacío**: Cubase dibuja así los campos sin texto («-»). Queda resuelta la pregunta abierta de TW-1101.
- **Funcionan:** el texto fijo, el nombre de la pista seleccionada y una lámpara controlada por el script.
- **No funciona:** mostrar texto variable mediante un campo asociado a un elemento (`relateTo` + `setDisplayValue`). Por lo que se ve en la barra superior («Último control tocado: Ningún mapeado»), un campo asociado parece mostrar el mapeo del elemento, no su valor. Es una hipótesis sin verificar.

## 2026-11-13 — panel de estado en el script 1.1.0

- **Instalación:** `script install --apply` (1.1.0) y reinicio de Cubase. `capabilities.panel = {enabled: true, errors: []}`.
- **Observado por el usuario:**
  - **Fila 1:** «Trackwright 1.1.0».
  - **Fila 2:** el nombre de la pista seleccionada.
  - **Lámpara de actividad:**
    - tres `ping` separados por 2 s (09:47:39–09:47:45) → **tres destellos cortos**;
    - diez `da.channels` seguidos durante 1,0 s (09:47:45–09:47:46) → **encendida todo ese segundo** y apagada al terminar.
- **Conclusión:** TW-1101 verificado en Cubase Elements 15.0.30.

## 2026-11-13 — experimento TW-1206 (grabar automatización de volumen), variante A

- **Script:** `experiments/tw1206/automation.py`. Datos completos en `experiments/tw1206/results.json`.
- **Pista:** POC-TEST, con audio. Modo de automatización: el que tenía el proyecto, presumiblemente **Touch** (el habitual; no se comprobó).

| Paso | Resultado |
|---|---|
| A0–A1 | Estado inicial: volumen 0,79 (0 dB), W y R desactivados. Escritura (4013) → «Activ.» |
| A2 (10:42:56) | Reproducción detectada por los avisos de transporte. Rampa de 21 escrituras de 0,79 a 0,40 (−12,2 dB), todas releídas exactas. **El fader se movió** (observado por el usuario). Cada paso tardó unos 0,33 s, porque cada escritura vuelve a resolver la pista |
| Observación | **No apareció ninguna curva** en el carril de automatización de volumen |
| A3–A4 (10:46:07) | Escritura desactivada y lectura (4014) activada; volumen puesto a 0,79. Durante 5 s de reproducción el volumen **se quedó en 0,79** todo el tiempo (12 lecturas) |
| A6 | Restaurado: 0 dB, W y R desactivados, cursor en el compás 1 |

**Hallazgos:**
1. **No se graba automatización** al escribir el parámetro de volumen por DirectAccess (`setParameterProcessValue`) con la escritura activada y en reproducción. Hipótesis: Cubase no considera esos cambios un control «tocado», que es lo que necesita para grabar en Touch.
2. **El script recibe la posición del cursor durante la reproducción** (`mTransportLocator.mOnChange`): avanzó del compás 1 al 4 a lo largo de la rampa. Así se puede detectar la reproducción y seguir la posición.
3. **Latencia:** una escritura completa con resolución de la pista cuesta unos 0,33 s. Para escrituras rápidas en serie habría que escribir sobre el objeto ya resuelto.
