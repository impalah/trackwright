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

## 2026-11-13 — TW-1206, variante B1 (modos de automatización), script 1.2.0

- Script 1.2.0 cargado; 35 comandos asociados, 0 errores.
- **`canPerform`**, sin pista seleccionada y con POC-TEST seleccionada (mismo resultado):
  - `false`: `automation.mode_touch`, `automation.mode_auto_latch`, `automation.mode_cross_over` y `automation.next_mode`;
  - `true`: `automation.toggle_write_selected`.
- El usuario **no encuentra** el selector de modo de automatización en la barra de herramientas de su Cubase en español.
- **Conclusión:** en Cubase **Elements** 15.0.30 los modos de automatización no se pueden cambiar por comando. Hipótesis, sin confirmar en la documentación de Steinberg: Elements no ofrece modos seleccionables y trabaja siempre en Touch. **La variante B1 no es aplicable en esta edición.**

## 2026-11-13 — TW-1206, variante B2 (fader de superficie con toque): **graba automatización**

- **Script:** `1.2.1+tw1206` (`AUTOMATION_FADER_ENABLED = true`), con puente y Cubase reiniciados. `capabilities.automationFader = {enabled: true, errors: []}`.
- **Mecanismo:**
  - un fader de la superficie, `makeFader(10, 0, 1, 2)`, enlazado con `page.makeValueBinding` a `mTrackSelection.mMixerChannel.mValue.mVolume`;
  - su `mTouchState.bindTo(customVariable)`;
  - el script pone esa variable a 1 (tocar), mueve el fader con `mSurfaceValue.setProcessValue` y la pone a 0 (soltar).
- **Datos:** `experiments/tw1206/results-variante-b2.json`. Los de la variante A, en `results-variante-a.json`.

| Paso | Resultado |
|---|---|
| A0–A1 (11:05:30) | Estado inicial: 0 dB, W y R desactivados, cursor en el compás 1. W activado |
| A2 (11:06:08) | POC-TEST seleccionada; reproducción detectada; tocar → 21 valores de 0,79 a 0,40 → soltar, sin errores. **El volumen de la pista siguió al fader** (de −0,38 a −12,2 dB). El usuario vio moverse los dos faders y, **tras parar, apareció una curva en el carril de automatización de volumen** |
| A3–A4, 1.er intento (11:07:17) | **No válido:** detección de la reproducción falseada por los avisos del propio movimiento del cursor. Corregido en el guion: se espera 0,6 s y solo cuenta que el cursor avance |
| A3–A4, reintento (11:08:06) | W desactivado y R activado. Sin intervención de Trackwright, el volumen **reprodujo la rampa**: −0,07 dB (compás 1) → −2,27 (compás 2) → −6,12 (compás 3) → **−12,2 dB (compás 4.3)**, y se mantuvo |
| A6 | Volumen 0 dB, W y R desactivados, cursor en el compás 1. **La curva grabada sigue en el proyecto**, sin efecto con R desactivado |

**Conclusiones:**
1. **Sí se puede grabar automatización de volumen desde Trackwright en Cubase Elements 15.0.30:** con un fader de la superficie enlazado al parámetro, tocado y soltado por el script. Así es como graban los controladores físicos en modo Touch.
2. La escritura directa por DirectAccess (variante A) mueve el valor, pero **no** cuenta como toque.
3. **Limitaciones actuales del mecanismo:**
   - solo el **volumen** de la **pista seleccionada**: el enlace es a `mTrackSelection.mMixerChannel`;
   - resolución temporal de unos 0,33 s por punto, con la reproducción en marcha;
   - la reproducción la inicia y la detiene el usuario.

## 2026-11-13 — reproducción desde Trackwright (script 1.2.2+tw1206)

- **`canPerform`:** `true` para `transport.start` y `transport.stop`.
- **`cubase_run_command("transport.start")`:** el cursor avanzó de `1. 1. 1. 0` a `1. 4. 3. 94` en 2,1 s, según los avisos de transporte durante la reproducción. El usuario confirma que reprodujo.
- **`cubase_run_command("transport.stop")`:** el cursor se detuvo en `2. 1. 4. 17` y no cambió en los 0,8 s siguientes. El usuario confirma que paró.
- **Conclusión:** Trackwright puede iniciar y detener la reproducción (clase `direct`).

## 2026-11-13 — TW-1207, experimento B3: automatización de más parámetros (script 1.3.0+tw1206)

- **Controles:** 45, enlazados a la pista seleccionada (POC-TEST), sin errores. `auto.list` informa del parámetro enlazado a cada uno:
  - volumen y panorama;
  - envíos 1 a 4 («Nivel»);
  - EQ del canal («EQ n Gain/Freq/Q»);
  - pre-filtro («PreGain», «LC-Freq», «HC-Freq»);
  - **slot 1 (Compressor), en este orden del banco:** Threshold, Ratio, Attack, Release, AutoRelease, Hold, MakeUp y AutoMakeUp;
  - vacíos: los Quick Controls (sin asignar en una pista de audio) y el slot 2 (vacío).
- **Prueba automática** (`experiments/tw1206/controls.py run`, datos en `results-b3.json`). Reproducción iniciada y detenida por Trackwright (`transport.start` y `transport.stop`). Para cada parámetro: grabación de una rampa con toque, comprobación en lectura y restauración.

| Parámetro | Rampa | ¿Se reproduce en lectura? |
|---|---|---|
| volume | 0,00 → −8,69 dB | ✅ |
| pan | C → L60 | ✅ |
| send1.level | 0,00 → −8,69 dB | ✅ |
| eq1.gain | 0,0 → −14,4 dB | ✅ |
| prefilter.gain | 0,0 → −28,8 dB | ✅ |
| insert1.p1 (Compressor Threshold) | −20 → −38 dB | ✅ |
| insert1.p2 (Compressor Ratio) | 2:1 → 4,10:1 | ✅ |
| qc1 | sin parámetro asignado | ❌ (esperado) |

- **Incidencia de método:** la restauración de cada parámetro la deshacía la lectura del siguiente, porque **R (leer automatización) afecta a todos los parámetros de la pista** y reproduce las curvas ya grabadas. Restaurado al final, con R desactivado, y verificado por DirectAccess: volumen 0,00, EQ 0,0 dB, Threshold −20 dB, Ratio 2:1, panorama C, envío 0,00 y pre-filtro 0,0 dB.
- **Conclusiones:**
  - Trackwright puede grabar automatización de **volumen, panorama, envíos, EQ del canal, pre-filtro y parámetros de plugins de inserción** (por banco), además de reproducir y parar solo.
  - Los Quick Controls dependen de que la pista los tenga asignados.
  - **Para la herramienta:** con R activado, la automatización manda sobre el valor. Hay que informar de ello y no «restaurar» valores bajo lectura.
- **Quedan en el proyecto** las curvas grabadas, sin efecto mientras R esté desactivado.

## 2026-11-13 — uso real de `cubase_record_automation` y conversión de unidades

- **Desde Claude Code** (sesión independiente), con el script 1.4.0: fundido de volumen en POC-TEST grabado; **la curva aparece en el carril**, según el usuario.
- **Problema detectado en esa sesión:** el modelo no conocía la correspondencia entre el valor normalizado y los dB. Estimó −20 dB ≈ 0,36 y propuso calibrar moviendo el fader.
- **Conversión de Cubase** (`da.convert`, `convertParameterPlainToProcessValue`), solo lectura, ida y vuelta exacta:

| Parámetro (objeto, tag) | Conversiones |
|---|---|
| Volumen (canal, 1025) | 0 dB → 0,7891 · −6 → 0,5708 · **−20 → 0,2551** · −60 → 0,0255 · +6 → 0,9990 |
| Nivel del envío 1 (slot de envío, 4097) | 0 dB → 0,7891 · −20 → 0,2551 |
| EQ 1 Gain (EQ del strip, 4232) | 0 dB → 0,5 · −6 → 0,375 · +6 → 0,625 |
| EQ 1 Freq (EQ del strip) | 100 Hz → 0,2811 · 1000 Hz → 0,5 |
| PreGain (InputFilter, 4201) | 0 dB → 0,5 · −12 → 0,375 |
| Threshold (Compressor) | −20 dB → 0,6667 · −35 → 0,4167 |

- **Panner:** «Izquierda-derecha» es el tag 4201, con plain 0 en el centro; escala sin medir. InputFilter: `PreGain` 4201, `LC-Freq` 4204, `HC-Freq` 4206.
- **Conclusión:** la estimación de 0,36 para −20 dB era errónea (es 0,2551; la escala no es lineal). **No hace falta calibrar moviendo el fader:** Cubase convierte con exactitud y sin modificar nada. Propuesta: aceptar unidades reales en las herramientas (TW-1208).

## 2026-11-13 — TW-1208: correspondencia entre controles y parámetros de Cubase (`cubase_convert_value`)

Medido sobre POC-TEST con el código de TW-1208, a través del puente. Solo lectura, salvo la selección de la pista. Las 12 conversiones son exactas en ida y vuelta:

| Clave | Parámetro de Cubase | Conversión |
|---|---|---|
| `volume` | POC-TEST / Volumen | −20 dB → 0,2551 · 0 dB → 0,7891 |
| `pan` | Panner / Izquierda-derecha | **escala −100 (izquierda) … 0 (centro) … +100 (derecha)**: 0 → 0,5 · −50 → 0,25 |
| `send1.level` | 1 / Nivel | −20 dB → 0,2551 |
| `eq1.gain` | EQ / EQ 1 Gain | +6 dB → 0,625 |
| `eq2.freq` | EQ / EQ 2 Freq | 1000 Hz → 0,5 |
| `eq1.q` | EQ / EQ 1 Q | 1 → 0,0833 |
| `prefilter.gain` | Input Filter / PreGain | −12 dB → 0,375 |
| `prefilter.lowcut` | Input Filter / LC-Freq | 100 Hz → 0,2811 |
| `prefilter.highcut` | Input Filter / HC-Freq | 10 kHz → 0,8535 |
| `insert1.p1` | Compressor / Threshold | −35 dB → 0,4167 |
| `insert1.p2` | Compressor / Ratio | 4:1 → 0,4286 |

- `qc1` e `insert2.p1` aparecen como no disponibles: no hay nada asignado ni plugin en el slot 2.
- **Grabación con `plain` desde la otra sesión de Claude Code:** según el usuario, funcionó correctamente.

## 2026-11-13 — TW-1201: arranque automático del puente y `cubase_launch`

- **Arranque automático,** con una configuración de prueba (puertos «TW1201 Test To/From» y socket `/tmp/tw1201-test`, para no interferir con el puente real ni con Cubase):
  - `status` sin puente → `serve` lo arrancó como proceso independiente en **0,2 s**; luego `TIMEOUT`, lo esperado porque Cubase no usa esos puertos;
  - una segunda sesión **reutilizó** el puente: seguía habiendo uno;
  - el log del puente quedó en `bridge.log` del directorio del socket;
  - el puente de prueba se paró al terminar.
- **`cubase_launch`** en ensayo, con Cubase abierto → `already_running`, script 1.4.0. No abre nada.
- **Prueba completa del usuario,** desde Claude Code, con Cubase y el puente cerrados: `serve` arrancó el puente y `cubase_launch` abrió Cubase. Devolvió **`awaiting_user`** hasta que el usuario abrió el proyecto en Steinberg Hub; después el script respondió. El script empieza a responder solo cuando hay un proyecto abierto.

## 2026-11-13 — TW-1209: experimento de propiedades del proyecto

Detalle en [experiments/tw1209/README.md](../experiments/tw1209/README.md).

- **DirectAccess:** el objeto «Transporte» (`type: Transport`) da `signature` = «4/4», `cycle`, `metronomeOn`, `precountOn`, punch, pre-roll y post-roll, y los modos de grabación. «Metronome» da `clickLevel`.
- **Compás deducido por normalización del cursor:** 4/4, coherente con lo anterior.
- **`lsof`:** el `.cpr` no queda abierto; la carpeta del proyecto se deduce de los archivos de audio abiertos.
- **No accesibles:** frecuencia de muestreo, longitud y nombre del proyecto.

## 2026-11-13 — TW-1209: `cubase_get_project`

- **Contra Cubase, en 0,96 s:**
  - tempo 120 y compás **3/4** (cambiado por el usuario);
  - ciclo desactivado, con los localizadores en `2. 2. 1. 0` y `5. 1. 1. 0`. Son los mismos instantes que antes en 4/4, renumerados por el cambio de compás;
  - metrónomo activado (clic 127), precuenta desactivada y transporte parado;
  - modos de grabación;
  - carpeta del proyecto: `/Volumes/Data/Produccion/Cubase/X0001.test`.
- **Consecuencia:** con 3/4, la automatización que suponía 4/4 habría calculado mal las posiciones. Ahora usa el compás leído; probado en el simulador con 3/4 y 6/8.

## 2026-11-13 — TW-1211: experimento de edición por rangos

Detalle en [experiments/tw1211/README.md](../experiments/tw1211/README.md).

- **Funcionan y se verifican:** `Delete`, `Delete Time`, `Cut Time`, `Insert Silence` y `Crop Range` sobre un rango 2–30 s, medidos con el sondeo de eventos (`Locate Next Event`) y deshechos con `Undo`.
- **Con diálogo:** `Process / Silence`.
- **Localizadores en segundos:** fallan directamente; funcionan poniendo el cursor en segundos y usando `Set Left/Right Locator`.
- **Alcance:** `Select in Loop` solo crea un rango con la herramienta de rango, y lo hace en todas las pistas.

## 2026-11-13 — TW-1211: `cubase_edit_range` desde Claude Code

- **Prueba:** script 1.5.1, desde otra sesión de Claude Code, con el proyecto de pruebas guardado. Se pidió «quita el tramo entre el segundo 2 y el 30 cerrando el hueco; comprueba con POC-TEST».
- **Resultado, según el usuario, todo correcto:**
  - ensayo previo;
  - aplicación con `verified: true`;
  - localizadores, cursor y pista seleccionada restaurados;
  - herramienta de objetos activa al terminar;
  - **Deshacer** en Cubase devolvió el audio.

## 2026-11-13 — TW-1212: borrado en una sola pista

- **Herramienta:** `cubase_edit_range(2, 30, delete, track=POC-TEST)`.
- **Primer intento:** borró de más, por la preferencia de selección automática bajo el cursor; restaurado con Deshacer.
- **Tras la corrección:** `verified: true`; POC-INSTR intacta; 7 pasos de deshacer, informados y reales.
- Detalle en [experiments/tw1212](../experiments/tw1212/README.md).
- **El usuario lo verificó desde otra sesión de Claude Code:** funciona.

## 2026-11-13 — TW-1204: exportar la mezcla

- **Experimento** ([experiments/tw1204](../experiments/tw1204/README.md)):
  - el diálogo se abre y exporta entre los localizadores: `X0001.mp3` dura 27,99 s para un rango de 2–30 s;
  - Select All + Locators to Selection dejan los localizadores en 0 → 2:19,976 s.
- **`cubase_export_mix`, contra Cubase:**
  - el ensayo de `start` propone la carpeta `…/X0001.test/Mixdown`, deducida con `lsof`;
  - `confirm` encontró `X0001.mp3` (27,99 s), con `verified: true`.
- **Prueba del usuario, episodio completo en MP3:** 139,721 s para 139,976 s. Se amplía la tolerancia para formatos comprimidos.

## 2026-11-13 — TW-1202: guardar

- **Experimento,** con autorización del usuario: `File / Save` reescribió `X0001.cpr` y `Save New Version` creó `X0001-01.cpr`, ambos sin diálogo. Detalle en [experiments/tw1202](../experiments/tw1202/README.md).
- **`cubase_save_project`:** en ensayo, contra Cubase, listó los dos `.cpr`; sin `[writes] save`, el guardado real da `SAVE_DISABLED`.
- **Prueba del usuario desde Claude Code,** con `[writes] save = true`: funciona.

## 2026-11-13 — TW-1203: importar audio

- **Experimento** ([experiments/tw1203](../experiments/tw1203/README.md)):
  - el tono de 3 s entra en la pista seleccionada y en el cursor: bordes en 150 y 153 s de POC-TEST;
  - Cubase copia el archivo a `Audio/`;
  - con el selector abierto, Cubase no responde al script;
  - Deshacer quita el evento, no la copia.
- **`cubase_import_audio`** contra Cubase: el ensayo planifica 0:02:30.000 y 3,0 s; `confirm` da `not_found`, lo correcto porque estaba deshecho, y lista las copias.
- **Prueba del usuario desde Claude Code** (importación del tono en POC-TEST): funciona.

## 2026-11-13 — TW-1210: ajustes del proyecto

- **Experimento** ([experiments/tw1210](../experiments/tw1210/README.md)): los 9 interruptores del Transporte y el Metronome y el nivel del clic se escriben, se releen y se restauran.
- **`cubase_set_project`** contra Cubase: metrónomo, nivel 100 y ciclo, con `verified: true`; restaurados con `verified: true`.
- **Prueba del usuario desde Claude Code** (metrónomo y precuenta): funciona.

## 2026-11-13 — TW-1205: presets de plugins

- **Next y Previous** cambian y devuelven los parámetros del Compressor cuando su editor tiene el foco de teclado, que se consigue con un clic del usuario la primera vez. Sin foco o sin preset cargado, no hacen nada.
- **El nombre del preset** no es accesible.
- Detalle en [experiments/tw1205](../experiments/tw1205/README.md).
- **Prueba del usuario desde Claude Code:** funciona.

## 2026-11-13 — TW-1302: transporte CoreMIDI con `ctypes`

- **Sin Cubase,** con una prueba en bucle con puertos de prueba propios (ahora también test automático en macOS):
  - 13 tramas de un mensaje de 3 KB en cada sentido, idénticas;
  - los puertos desaparecen al cerrar.
- **CoreMIDI entrega dos veces los SysEx universales** (`F0 7E …`, Identity Request) en dos callbacks distintos; las tramas de Trackwright (`7D`) llegan una sola vez. Probablemente es la capa MIDI-CI de macOS. Sin efecto: se cuentan como ajenas y se descartan.
- **Con Cubase:**
  - se paró el puente anterior (rtmidi) y `serve` arrancó uno nuevo con CoreMIDI;
  - **Cubase se reconectó en 4,2 s** (script 1.5.5);
  - `ping` correcto y `doctor` con 5/5;
  - lecturas: pistas, 46 parámetros del Compressor (9 KB, mensajes fragmentados) y 45 controles de automatización;
  - escritura: mute de POC-TEST escrito y restaurado, ambos verificados;
  - 260 tramas recibidas, sin errores de transporte.
- **Entorno sin `mido` ni `python-rtmidi`** (`uv sync` los quitó): todo lo anterior funciona sin ellos.

## 2026-11-13 — TW-1301: `trackwright setup`

- **Sobre la instalación real,** sin entrada (toda pregunta habría respondido «no»): script 1.5.5 al día, configuración existente y servidor ya registrado en Claude Code (`claude mcp get`, solo lectura). Los tres pasos se saltaron, nada se escribió, y `doctor` dio 5/5.
- **Instalación desde cero, aislada** (HOME y TMPDIR temporales, sin `claude` en el `PATH`, respuestas sí/sí/no/sí):
  - script instalado en la carpeta MIDI Remote del HOME temporal;
  - configuración creada con `enabled = true`, `save = false` y permisos `600`;
  - el paso de Claude Code mostró el comando para registrarlo a mano;
  - `doctor`: solo «bridge running» en rojo, como se espera sin servidor MCP. Directorios temporales borrados.

## 2026-11-13 — TW-1303: paquete 0.3.0 para PyPI

- `uv build`: `trackwright-0.3.0-py3-none-any.whl` y `trackwright-0.3.0.tar.gz`, con `License-Expression: AGPL-3.0-or-later` (cambiada desde `-only` el mismo día, antes de publicar) y el `LICENSE` incluido. `twine check --strict`: correcto en los dos.
- El sdist solo contiene `src/trackwright`, `pyproject.toml`, `README.md` y `LICENSE`.
- **`uv tool install` del wheel en directorios temporales:** `version` da 0.3.0 y `doctor` 5/5 contra el Cubase real. `setup` sin entrada se salta los tres pasos y no escribe nada.
- **`uvx --from <wheel>`:** el ejecutable está en la caché de uv (`archive-v0`), y `setup` propone `uvx --from trackwright==0.3.0 trackwright serve` en vez de esa ruta temporal.
