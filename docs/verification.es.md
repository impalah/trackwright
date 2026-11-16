# Registro de verificación contra Cubase

[English](verification.md) · **Español**

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

- **Registro:** `claude mcp add --scope user trackwright -- uv --directory /ruta/a/trackwright run trackwright serve`. `claude mcp list` → `✔ Connected`.
- **Configuración:** `~/.config/trackwright/config.toml` con `[writes] enabled = true`, sin limitar pistas.
- **Sesión nueva de Claude Code,** sin el contexto del desarrollo. Según el usuario funcionaron:
  - `cubase_status`;
  - el listado de pistas;
  - silenciar y volver a activar una pista. El modelo **ensayó primero** (`dry_run`) y **pidió confirmación** antes de aplicar, siguiendo las instrucciones del servidor.
- **Conclusión:** la cadena completa cliente MCP → `trackwright serve` → puente → Cubase funciona en uso real, y un modelo sin conocimiento previo del proyecto usa las herramientas a partir de sus descripciones.

## 2026-11-13 — experimento TW-1101 (panel de estado, script 1.0.1+tw1101)

- **Protocolo:** [`experiments/tw1101/README.md`](../experiments/tw1101/README.es.md).
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

Detalle en [experiments/tw1209/README.md](../experiments/tw1209/README.es.md).

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
  - carpeta del proyecto: `/ruta/a/proyectos/TEST`.
- **Consecuencia:** con 3/4, la automatización que suponía 4/4 habría calculado mal las posiciones. Ahora usa el compás leído; probado en el simulador con 3/4 y 6/8.

## 2026-11-13 — TW-1211: experimento de edición por rangos

Detalle en [experiments/tw1211/README.md](../experiments/tw1211/README.es.md).

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
- Detalle en [experiments/tw1212](../experiments/tw1212/README.es.md).
- **El usuario lo verificó desde otra sesión de Claude Code:** funciona.

## 2026-11-13 — TW-1204: exportar la mezcla

- **Experimento** ([experiments/tw1204](../experiments/tw1204/README.es.md)):
  - el diálogo se abre y exporta entre los localizadores: `TEST.mp3` dura 27,99 s para un rango de 2–30 s;
  - Select All + Locators to Selection dejan los localizadores en 0 → 2:19,976 s.
- **`cubase_export_mix`, contra Cubase:**
  - el ensayo de `start` propone la carpeta `…/TEST/Mixdown`, deducida con `lsof`;
  - `confirm` encontró `TEST.mp3` (27,99 s), con `verified: true`.
- **Prueba del usuario, episodio completo en MP3:** 139,721 s para 139,976 s. Se amplía la tolerancia para formatos comprimidos.

## 2026-11-13 — TW-1202: guardar

- **Experimento,** con autorización del usuario: `File / Save` reescribió `TEST.cpr` y `Save New Version` creó `TEST-01.cpr`, ambos sin diálogo. Detalle en [experiments/tw1202](../experiments/tw1202/README.es.md).
- **`cubase_save_project`:** en ensayo, contra Cubase, listó los dos `.cpr`; sin `[writes] save`, el guardado real da `SAVE_DISABLED`.
- **Prueba del usuario desde Claude Code,** con `[writes] save = true`: funciona.

## 2026-11-13 — TW-1203: importar audio

- **Experimento** ([experiments/tw1203](../experiments/tw1203/README.es.md)):
  - el tono de 3 s entra en la pista seleccionada y en el cursor: bordes en 150 y 153 s de POC-TEST;
  - Cubase copia el archivo a `Audio/`;
  - con el selector abierto, Cubase no responde al script;
  - Deshacer quita el evento, no la copia.
- **`cubase_import_audio`** contra Cubase: el ensayo planifica 0:02:30.000 y 3,0 s; `confirm` da `not_found`, lo correcto porque estaba deshecho, y lista las copias.
- **Prueba del usuario desde Claude Code** (importación del tono en POC-TEST): funciona.

## 2026-11-13 — TW-1210: ajustes del proyecto

- **Experimento** ([experiments/tw1210](../experiments/tw1210/README.es.md)): los 9 interruptores del Transporte y el Metronome y el nivel del clic se escriben, se releen y se restauran.
- **`cubase_set_project`** contra Cubase: metrónomo, nivel 100 y ciclo, con `verified: true`; restaurados con `verified: true`.
- **Prueba del usuario desde Claude Code** (metrónomo y precuenta): funciona.

## 2026-11-13 — TW-1205: presets de plugins

- **Next y Previous** cambian y devuelven los parámetros del Compressor cuando su editor tiene el foco de teclado, que se consigue con un clic del usuario la primera vez. Sin foco o sin preset cargado, no hacen nada.
- **El nombre del preset** no es accesible.
- Detalle en [experiments/tw1205](../experiments/tw1205/README.es.md).
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

## 2026-11-13 — TW-1303: 0.3.0 publicada en PyPI

- El usuario publicó con `make publish` (construcción, `twine check --strict`, `uv publish`) desde el commit etiquetado `v0.3.0`.
- El primer intento se rechazó con `403 Invalid or non-existent authentication information`: el token guardado en el Llavero tenía exactamente 128 caracteres, cortado por la petición interactiva de `security add-generic-password -w`. Con un token nuevo guardado desde el portapapeles la subida funcionó. El intento fallido no subió nada.
- **Comprobado después:** la API JSON de PyPI da `trackwright` 0.3.0, `License-Expression: AGPL-3.0-or-later`, `Requires-Python: >=3.14` y la URL `Author`; el SHA-256 del wheel y del sdist en PyPI coincide con el `dist/` local; `uvx trackwright@0.3.0 version` desde otra carpeta lo descarga de PyPI y responde `0.3.0`.

## 2026-11-14 — Fase 1 de E14 (TW-1401, TW-1402) en Cubase

Cubase Elements 15.0.30, script 1.5.5, el proyecto de pruebas. Se reinició el puente con el código nuevo (un puente anterior ignora el campo de sesión).

- **Rechazos de la política** (TW-1401), con una política `enabled = true`, `save = false`, `allowed_tracks = ["POC-TEST"]`; en cada caso se registraron las operaciones de escritura enviadas a Cubase: ninguna.
  - `cubase_run_command("file.save")` → `USE_DEDICATED_TOOL`; `marker.insert` → `NOT_ALLOWED`;
  - `edit_range` en POC-INSTR → `NOT_ALLOWED`; en todas las pistas → `NOT_ALLOWED`; `split_at_locators` → `NOT_ALLOWED`;
  - `set_parameter` sobre el enrutado de salida (4102) y de entrada (4101) del canal → `READ_ONLY_PARAM`;
  - mover `cycle_left` con las escrituras desactivadas → `WRITES_DISABLED`.
- **Sesión a través del puente** (TW-1402):
  - un `da.param.set` enviado con una sesión inventada lo rechazó el script con `STALE_SESSION`; el mute de POC-TEST no cambió;
  - `cubase_set_track_mix` en POC-TEST (mute activado y luego desactivado) envió las dos escrituras con la sesión actual; ambas verificadas, con `track_uid` en la salida; mute restaurado.
- **Selección borrada antes de *Select in Loop*** (TW-1401): `edit_range("19", "20", "delete", verify_track="POC-TEST")` en todas las pistas lanzó `edit.select_none` antes de `tool.range` y `edit.select_in_loop`; resultado verificado (bordes nuevos en 19 s y 20 s dentro del evento de 18–22 s); `Edit > Undo` devolvió exactamente los bordes de POC-TEST.
- **A través de la capa MCP** (Claude Code reconectado al servidor nuevo): los esquemas de las herramientas exigen `track` en `cubase_set_parameter` y `cubase_insert_plugin`; un ensayo de `cubase_set_parameter` sobre el volumen de POC-TEST devolvió `track_uid`; el enrutado de salida (4102) se rechazó con `READ_ONLY_PARAM` y `cubase_run_command("file.save")` con `USE_DEDICATED_TOOL`.
- **Sin comprobar en directo:** los cambios de TW-1403 que necesitan un diálogo o reproducción (importar, guardar sin carpeta conocida, una grabación interrumpida); están cubiertos por tests unitarios con el simulador.

## 2026-11-14 — Fase 2 de E14 (TW-1405, TW-1406, TW-1407) en Cubase

- **Puente** (TW-1405): reiniciado con el código nuevo. El `pkill -f "trackwright bridge"` documentado no paraba el puente arrancado automáticamente (se ejecuta como `python -m trackwright --config … bridge`); el nuevo `trackwright bridge-stop` lo paró (con el pid de `bridge.status`), el lanzador arrancó otro y Cubase se reconectó en 3 s. `bridge.status` informa de `duplicate_responses`.
- **Versión del script en ejecución** (TW-1407): `doctor` dio «script loaded in Cubase» con 1.5.5 = la del paquete antes de actualizar, y 1.6.0 = la del paquete después.
- **Script 1.6.0** (TW-1406): instalado con permiso del usuario (sustituyó a 1.5.5; permisos 0644) y cargado al reiniciar el usuario Cubase («Trackwright 1.6.0» en la superficie).
  - `doctor`: todas las comprobaciones bien; tests de integración (lecturas y escrituras reversibles en POC-TEST): 5 pasados;
  - `da.channels` con 17 tags → `BAD_REQUEST`; con 2 tags lista los tres canales;
  - `da.param.set` devuelve `guard` solo con `base` y `baseTitle`; mute de POC-TEST activado y restaurado;
  - latencia de escritura, 20 `da.param.set` sobre el mute de POC-TEST: mediana de 112 ms con 1.5.5 y de 112 ms con 1.6.0. En un proyecto de tres pistas, el recorrido del árbol que quitó S-01 no costaba nada medible; domina un ciclo de idle.

## 2026-11-14 — 0.4.0 preparada

- `make check`: 547 pasados, 6 omitidos; `uv build` y `twine check --strict` correctos; el wheel lleva el script 1.6.0 y los enlaces `Repository`, `Issues` y `Author`.
- **Ensayo de actualización** en carpetas desechables: `trackwright==0.3.0` desde PyPI, cuyo `setup` instaló el script 1.5.5; después, el wheel de la 0.4.0. `bridge-stop` sin puente responde `stopped: false`; `setup` sustituyó 1.5.5 por 1.6.0 (permisos 0644) y listó los pasos siguientes.
- Encontrado durante el ensayo: un servidor registrado con `uvx --from trackwright==0.3.0` seguiría ejecutando la 0.3.0 tras actualizar. `setup` ahora avisa cuando el registro fija otra versión; los pasos de actualización del registro de cambios explican cómo sustituirlo.
- El wheel de la 0.4.0 instalado aparte: `doctor` contra el puente y el Cubase del usuario, todas las comprobaciones bien (script 1.6.0 = el del paquete).

## 2026-11-14 — Script 1.6.1: el panel explica los faders

- Instalado por el usuario (`trackwright script install --apply`, sustituyendo a 1.6.0) y cargado al reiniciar Cubase.
- **Visto por el usuario:** las tres líneas fijas bajo el nombre de la pista («Faders on the right:», «automation (Trackwright)», «do not move or map them») se ven en la superficie.
- `doctor`: todas las comprobaciones bien, «script loaded in Cubase» 1.6.1 = el del paquete; `capabilities.panel`: activado, sin errores; tests de integración (lecturas y escrituras reversibles en POC-TEST): 5 pasados.

## 2026-11-14 — 0.4.0 publicada

- **CI:** la primera ejecución de GitHub Actions (push de `a342347`) pasó todos los pasos en macOS: entorno, lint/formato/tipos/tests con cobertura, tests con Node del script, construcción y `twine check`.
- **PyPI:** el usuario publicó la 0.4.0 con `make publish`. El wheel y el sdist de PyPI tienen el mismo SHA-256 que la construcción local del commit `fc506e1` (etiqueta `v0.4.0`); los metadatos llevan los enlaces `Repository`, `Issues` y `Author`.
- `uvx --refresh trackwright@0.4.0 version` desde otra carpeta responde `0.4.0`. Sin `--refresh`, uv dijo primero que no existía la 0.4.0: su índice en caché era anterior a la subida.

## 2026-11-14 — TW-1408: qué debe imitar el simulador

Dos preguntas que planteó el test de conformidad, hechas a Cubase Elements 15.0.30 (solo lecturas, proyecto de pruebas):
- `da.channels` con un tag que los canales no tienen (9999): cada canal responde `{"title": "Nombre", "display": "", "process": -1}`: el título de otro parámetro, una visualización vacía y `process` -1. El script lo pasa tal cual; el simulador devolvía `null`. Ahora ambos devuelven lo mismo, y `track_info` trata `process: -1` como ausente.
- `da.children` con `limit` 0: un elemento (de 6), porque el script fija el límite en 1 como mínimo. El simulador no devolvía ninguno; ahora recorta igual.

## 2026-11-14 — TW-1410: mutation testing de los módulos de seguridad

mutmut 3.8.1 con `uv run --with`, 4 trabajadores, ~2 minutos para 899 mutantes.

| Módulo | Mutantes | Muertos | Puntuación |
|---|---|---|---|
| `protocol` | 198 | 188 | 94,9 % |
| `hostport` | 63 | 62 | 98,4 % |
| `host` | 406 | 338 | 83,3 % |
| `core/policy` | 63 | 49 | 77,8 % |
| `core/refs` | 169 | 110 | 65,1 % |

- **Primera ejecución** (protocol, policy, refs): 72 % muertos. Supervivientes con sentido: invertir la comprobación de `save` en `check_save` no rompía ningún test seleccionado; opciones de la codificación JSON; límites `>`/`>=`; el descarte del ensamblado más antiguo; un selector `name:` de una letra. Tests en `tests/unit/test_mutation_edges.py`.
- **Con `host` y `hostport`:** el superviviente más grave era `BridgeHost` reintentando cuando no se sabe si la petición se envió (`sent is False` en lugar de `is not False`), justo el caso que prohíbe la regla de no reintentar; sus tests están en `test_launcher.py`, que mutmut no puede ejecutar. Además: escrituras que perdían su sesión, el plazo del llamante que no llegaba a cada paso interno, los límites de los historiales y los textos de error. Tests en `tests/unit/test_mutation_host.py` (28).
- **Supervivientes restantes, revisados uno a uno:** textos de mensajes y argumentos de logs; cambios equivalentes en Python (`"ascii"`/`"ASCII"`, `allow_nan=None`, `code=None` donde el código por defecto es el mismo, valores iniciales sin efecto, una rama a la que no se puede llegar tras esperar el cerrojo); y `ObjectRef.decode`/`check_*`, que ninguna herramienta llama (C-25, TW-1412).
- **Puntuación sin `core/refs`:** 637 de 730 mutantes muertos, 87,3 % (objetivo: 85 %). No queda ningún superviviente que cambie el comportamiento en `protocol`, `policy`, `hostport` ni `host`.

## 2026-11-14 — TW-1411: más tests de integración en directo

Cubase Elements 15.0.30, script 1.6.1, proyecto de pruebas, `TRACKWRIGHT_TEST_TRACK=POC-TEST`.

- **Tests de lectura nuevos** (10 pasan): canal seleccionado, catálogo de plugins, parámetros del canal y uno concreto, propiedades del proyecto, cambios, objetivos de automatización y la conversión exacta de 0 dB (0,7891), navegación por marcadores devolviendo el cursor a su sitio.
- **Tests de escritura reversibles nuevos** (7 pasan junto con los anteriores): volumen con `set_parameter`, renombrar, selección, tempo y metrónomo, cada uno restaurado en `finally`.
- **Incidente en la primera ejecución:** el test de renombrar cambió POC-TEST a «TW-RENAME-TEST» y luego no pudo devolverle el nombre: su política solo permitía `POC-TEST`, y la pista ya no se llamaba así. El nombre se restauró a mano en el momento (verificado), y el test permite ahora los dos nombres. Tras la ejecución corregida todas las pistas tienen su nombre, volumen 0,00 dB, sin mute, tempo 120 y el metrónomo apagado, como antes.
- **Cobertura en directo:** 20 de las 32 herramientas tienen un test repetible en directo (antes, 6). Siguen siendo manuales, porque abren diálogos, reproducen audio o borran cosas: `insert_plugin`, `remove_selected_tracks`, `split_at_locators`, `add_track_interactive`, `run_command`, `edit_range`, `plugin_preset`, `save_project`, `import_audio`, `export_mix`, `launch` y `record_automation`; sus comprobaciones están en este registro.

## 2026-11-14 — TW-1413: cortar en segundos y el formato del cursor, en Cubase

- `split_at_locators("19", "20", unit="seconds")` en el proyecto de pruebas: los localizadores fueron a `10. 3. 1. 0` y `11. 1. 1. 0` (19 s y 20 s a 120 BPM en 4/4), se ejecutó Split Loop y POC-TEST tuvo bordes de evento nuevos en 19 s y 20 s. `Edit > Undo` devolvió exactamente sus bordes; los localizadores se quedan en los puntos de corte, como está documentado.
- `set_position("cursor", "1.5", unit="seconds")` responde con la posición del cursor en compases y el formato que indica Cubase (`Compases+Tiempos` en este Cubase en castellano), ya no un texto escrito en el código.

## 2026-11-14 — TW-1501: exportar una pista para analizarla

- En Cubase Elements 15 el diálogo «Exportar mezcla de audio» solo exporta Stereo Out; una pista se aísla con solo. WAV hasta 64 bits float, de 8 a 192 kHz.
- Una señal de prueba conocida importada en 4,000 s y exportada entre localizadores en 2 y 36 s (WAV, 48 kHz, 32 bits float), con su pista en solo: el clic de alineación cae a 3,000 s del archivo, con **0 muestras** de error; 34,000 s de duración. La pista mono llega por los dos canales 3 dB más baja (ley de panorama centrada). Antes y después del evento el archivo contiene ceros exactos. Detalles en `experiments/tw1501/`.

## 2026-11-15 — TW-1504: `cubase_analyze_audio` por MCP

- Con `[analysis] enabled = true`, `cubase_status` indica `analysis_enabled: true`.
- `cubase_analyze_audio` sobre la exportación de TW-1501 (`tw1501-a.wav`, inicio del rango 2 s, `min_seconds` 3): ruido de fondo −63,19 dB, umbral −53,19 dB, pico −3,1 dB; cuatro silencios en tiempo del proyecto, 2,00–5,75, 10,25–13,75, 21,25–25,75 y 29,25–36,00 s, que es donde la señal de prueba (colocada en 4 s) tiene sus silencios de 3 s o más, con 0,25 s de margen; el silencio de 1 s no aparece.
- Visto por el camino: justo después de reconectar el MCP, el puente se arrancó solo y la primera petición (`hello`) agotó el tiempo; la segunda, unos segundos después, obtuvo respuesta. Cubase tardó un momento en enlazarse a los puertos virtuales nuevos.

## 2026-11-15 — TW-1509: esperar a Cubase tras arrancar el puente

- `trackwright bridge-stop`, y luego `status()` desde un proceso nuevo con el código nuevo: arrancó el puente, un primer `hello` falló (el puente contó un error) y el siguiente obtuvo respuesta; `status` devolvió conectado, script 1.6.1, 3,7 s después de la llamada. La misma situación daba `TIMEOUT` en la primera petición antes de este cambio (ver TW-1504).

## 2026-11-15 — TW-1506: el flujo de `podcast-silence-trim` en el proyecto de pruebas

- Los pasos de la skill, seguidos desde una sesión de Claude Code contra el Cubase real (todavía sin cargarla a través del plugin): `cubase_status` (escrituras y análisis activados); el usuario eligió analizar solo `TW1501`; solo activado (releído), `cubase_export_mix` 2–36 s, el usuario exportó `silence-check.wav` (WAV, 48 kHz, 32 bits float), confirm lo encontró (34 s, diferencia 0), solo desactivado (releído).
- `cubase_analyze_audio` (`start` 2, `min_seconds` 3): los cuatro silencios esperados, 18,5 s en total. El usuario aprobó los cuatro.
- Ensayo del último corte y después `delete_time` del final hacia el principio: 29,25–36,00, 21,25–25,75, 10,25–13,75 y 2,00–5,75 s, cada uno `verified: true` frente a los bordes de `TW1501` (bordes finales 2,000, 6,500, 14,000 y 17,500 s) y un paso de deshacer cada uno.

- **A través del plugin** (según el usuario, 2026-11-15; no observado desde esta sesión): en una sesión nueva de Claude Code con `TRACKWRIGHT_FROM=$PWD claude --plugin-dir plugins/claude-code`, la petición funcionó correctamente. Después se comprobó el proyecto desde aquí: `TW1501` de nuevo con un evento en 4,000–34,000 s, ninguna pista en solo.

## 2026-11-15 — TW-1507: el flujo de `noise-gate` en el proyecto de pruebas

- `experiments/tw1507/make_fixture.py` (ruido −55 dBFS, frases de sílabas a −16 y −36 dBFS, pausas) importado por el usuario en una pista mono nueva `TW1507` en 0 s.
- Descubrimiento: los filtros `gate`, `expander` y `noise` encontraron `Gate` y `MidiGate` (Steinberg); `MidiGate` descartado (se abre con MIDI); el catálogo también muestra un VST de terceros (Voxengo CurveEQ), así que las puertas de otros fabricantes aparecerían igual. Una vez cargado, `Gate` tiene Threshold (tag 4201, dB, −60…0 lineal), Range (4243), Attack (4202), Hold (4204), Release (4203) y un filtro paso banda en la cadena lateral activado por defecto.
- Exportación con la pista en solo (`gate-check.wav`): ruido de fondo −58,2 dB, voz más baja −39,0 dB, típica −19,1 dB (los niveles del origen menos los 3 dB de la ley de panorama). Umbral en la exportación −48,5 dB, traducido a la entrada de la puerta (+3 dB por pista mono centrada, faders a 0 dB): −45,5 dB. El usuario aprobó: Threshold −45,5 dB, Range −30 dB, Hold 50 ms, Release 200 ms; cada uno aplicado con `expect_title` y releído.
- Segunda exportación con la puerta (`gate-after.wav`), analizada con el primer umbral (−48,2 dB): ruido de fondo −88,05 dB (−30 dB, el Range); voz más baja −39,0 dB y típica −19,06 dB, sin cambios; pausas a −83/−85 dB (los primeros 200 ms son la liberación), las dos frases al mismo nivel que antes.
- Encontrado por el camino: (1) el `merge_gap_seconds` por defecto de 0,3 s tomaba las sílabas de 250 ms por ruidos breves y daba todo el archivo como un único silencio; bajado a 0,05 s. (2) Volver a analizar tras la puerta con el umbral relativo compara cosas distintas (el umbral baja con el ruido); la skill pasa ahora el primer umbral.

## 2026-11-15 — Comprobaciones de la versión 0.5.0

- `make check`: 691 tests superados, 18 omitidos (integración), cobertura del 98 %. `claude plugin validate --strict` pasa para el plugin y el marketplace.
- Mutation testing sobre los módulos de seguridad: primero 705 de 856 mutantes muertos (82,4 %), porque los tests nuevos de TW-1502 y TW-1509 no estaban en la selección de tests de mutmut; con ellos, **747 de 856 (87,3 %)**, y 748 tras una aserción más que mata el límite `>=`/`>` de la espera a Cubase. Los supervivientes que quedan en el código nuevo son textos de mensajes y un valor por defecto que en producción se sustituye.
- El wheel de la 0.5.0 arrancado con `uvx --from <wheel>` lee la configuración del usuario con `[analysis]` (la 0.4.0 la rechaza), y `TRACKWRIGHT_FROM=<wheel> claude --plugin-dir plugins/claude-code mcp list` muestra conectado el servidor del plugin.

## 2026-11-15 — TW-1601: lo que ofrece Cubase Elements para las skills de podcast

- Limitador en Stereo Out insertado y ajustado (−1,0 dB, releído); la cadena lateral del Compressor no está al alcance de los parámetros, el botón y la elección de fuente están en su ventana (usuario); la automatización de volumen grabada en tiempo real llega ~0,1 s tarde (puntos medios de la exportación en 7,185 y 8,655 s para escalones pedidos en 7,0–7,125 y 8,5–8,625 s), con una primera exportación plana sin explicar; PreGain automatizable; existen comandos de teclado de fundido, fundido cruzado, duplicar y repetir (usuario); el MP3 de Cubase se decodifica con soundfile, no hay exportación AAC; un render importado en 40 s quedó en 40,000–43,000 s; reproducción en ciclo con el Bypass del Gate alternado cinco veces, oída por el usuario, sin clics. Detalles en `experiments/tw1601/`.

## 2026-11-15 — TW-1602: el espacio de trabajo del proyecto, leído en directo

- `workspace()` (status) desde el repositorio contra el proyecto de pruebas abierto: carpeta del proyecto `X0001.test` encontrada a partir de los archivos que Cubase tiene abiertos; `Trackwright/` existe (de TW-1601) y faltan `previews/`, `analysis/`, `reports/`; `init` rechazado con `WORKSPACE_DISABLED` con la configuración del usuario; `cubase_status` indica `workspace_enabled: false`.

## 2026-11-15 — TW-1603: sonoridad de exportaciones reales de Cubase

- `measure_loudness` sobre las nueve exportaciones de `Mixdown/` del proyecto de pruebas (WAV de 32 bits float y el MP3 de Cubase): sonoridad integrada a 0,04-0,07 LU de pyloudnorm (por ejemplo el episodio de 140 s `X0001.mp3`: −21,13 frente a −21,18 LUFS); el clic de 1 ms de `tw1501-a.wav` da un true peak 1,1 dB por encima de su pico de muestra; 140 s medidos en 0,59 s.

## 2026-11-15 — TW-1604: actividad vocal en un episodio real

- Un episodio de 46 minutos con una voz y cinco pistas de música y efectos: `Pod Mic` exportada sola (solo, todo el proyecto, WAV de 32 bits float, duración exacta). Detección en 2,5 s; ruido de fondo −61,8 dB, contraste 52 dB, voz típica −13,1 dB, 87 % de voz.
- Un fragmento de 0,37 s a −52 dB en 17:15,36 era un ruido dentro de una pausa (el usuario lo comprobó: ahí hay una pausa); con `faint_db` el detector descarta 108 fragmentos así antes de unir, y la pausa de 17:15 vuelve a estar entera.
- El usuario escuchó los 10 primeros minutos con un tono en el canal derecho durante la voz detectada: entra y sale en los sitios correctos.
- Visto por el camino: `Pod Mic` del episodio y `POC-TEST` del proyecto de pruebas tienen el mismo uid de pista (proyectos de la misma plantilla).

## 2026-11-15 — TW-1605: exportar una pista con todos los solos restaurados

- En el proyecto de pruebas, con `POC-TEST` en solo de antemano: `start` con `solo=[TW1507]` quitó el solo de `POC-TEST` y puso en solo `TW1507`; el usuario exportó `tw1605-a.wav` (idéntico a la exportación anterior `gate-after`, diferencia 1e-10); `confirm` lo encontró, informó `solo_restored: true`, y `cubase_list_tracks` mostró `POC-TEST` en solo y `TW1507` no.
- Un segundo `start` con el mismo solo; el usuario cerró el diálogo sin exportar; `cancel` informó de las dos pistas restauradas (`solo_restored: true`), y `cubase_list_tracks` volvió a mostrar el estado anterior. Después se quitó el solo de `POC-TEST` para dejar el proyecto como estaba.

## 2026-11-15 — TW-1606: un render importado de vuelta, contra una señal conocida

- `cubase_workspace init` en el proyecto de pruebas creó los `previews/`, `analysis/` y `reports/` que faltaban.
- `cubase_render` sobre `tw1605-a.wav` (`TW1507` sola, 0–5 s, pico −16,07 dBFS), `gain_db` −6,0206, `track` `TW1507`: `renders/TW1507-gain.wav` (32 bits float, 48 kHz, estéreo, pico −22,09 dBFS) y su procedencia; el render es igual al origen × 0,5 con un error de 8e-10.
- El usuario creó una pista de audio estéreo, `TW1606 render`. `cubase_import_audio` rechazó el render en `TW1507` (`BAD_REQUEST`) y en 1 s (`MISALIGNED`); en 0 s el usuario lo importó con «Copiar archivo a carpeta del proyecto» desmarcado.
- La primera confirmación solo encontró el borde final (5,000 s): **un borde al inicio del proyecto no se puede sondear**, porque Localizar evento siguiente nunca se detiene en 0, y Localizar evento anterior fue a 0 desde 2 s en una pista cuyo único evento empieza en 2 s. Corregido: en la posición 0 el borde final nuevo sustituye al de inicio (una importación coloca el archivo entero). Tras recargar el servidor, la confirmación devolvió `done`, `owned: true` (`verified: null`, porque el servidor había perdido su foto de la pista antes de importar; la pista se acababa de crear vacía), y `state.json` registró el render y la pista como de `tw1606-test`.
- Cubase dejó un `Audio/TW1606 render_01.wav` de 0 bytes (con el nombre de la pista, no una copia del render); `copied_to_project` ya ignora los archivos vacíos.
- `TW1507` silenciada; el usuario exportó `TW1606 render` sola, 0–5 s (`solo`, restaurado después): es igual al origen × 0,5 hasta −182 dB (la mayor diferencia, 4,7e-10 frente al render), sin desplazamiento (retardo de correlación cruzada 0) y con la relación de RMS en 0,5000. `cubase_render list` muestra el render en esa pista, presente y sin problemas.

## 2026-11-15 — TW-1607: perfiles leídos y escritos en directo

- Con el servidor recargado y el proyecto de pruebas abierto: `resolve` no encontró perfil de episodio ni programa, y dio los criterios de silencio integrados (2 s, margen de 0,25 s); `shows` no encontró ninguno en `~/.config/trackwright/shows`; `delivery` listó Apple, iVoox, Spotify y YouTube con sus fuentes.
- `write_episode` en el proyecto de pruebas: el dry run mostró el TOML y no escribió nada; aplicado, escribió `Trackwright/profile.toml` (roles de `POC-TEST`, `TW1507` y `TW1606 render`, un paneo, margen de 0,3 s, destinos Apple y Spotify, un rango protegido en 40–43 s). Después `resolve` dio el margen desde `episode` y el silencio mínimo desde `built-in`, el rango protegido, y los dos perfiles de entrega con sus fuentes.
- `write_show` solo como dry run (nada escrito en la configuración del usuario): su TOML llevaba un `notes = ""` vacío, que ahora se omite.

## 2026-11-15 — TW-1608: análisis con su origen, en caché

- `cubase_analyze_audio` sobre `X0001.test/Mixdown/tw1606-render.wav`: `cache: stored`, `source.sha256` igual al `shasum -a 256` del archivo, rango 0–5 s, `project_saved_after: false` (el `.cpr` más reciente se guardó a las 15:03 y la exportación es de las 19:39); `Trackwright/analysis/` recibió `hashes.json` y un `silences-….json`. La misma llamada otra vez con `offset` 1: `cache: hit`, el mismo origen y la página aplicada a la lista guardada.
- Dos llamadas idénticas enviadas en paralelo respondieron ambas `stored` (las dos fallaron la caché antes de que ninguna guardase); sin consecuencias, porque las escrituras son atómicas y la segunda escribió el mismo resultado.
- `cubase_measure_loudness` sobre la exportación del episodio de 46 minutos de otro proyecto (`E0004…/Mixdown/tw1604-podmic.wav`, solo lectura): `cache: off`, `project_saved_after: null`, nada escrito en ningún sitio. En ese archivo de 1,07 GB el SHA-256 tarda 0,39 s y la medida de sonoridad 12,25 s, así que un acierto ahorra casi todo.

## 2026-11-15 — TW-1610 y TW-1609: la auditoría de sesión y los registros de propiedad, en directo

- Las lecturas de la auditoría en el proyecto de pruebas: `cubase_get_project` (carpeta, transporte parado), `cubase_list_tracks` (seis canales; `TW1507` silenciada), `cubase_list_inserts` (Brickwall Limiter en Stereo Out, Compressor en `POC-TEST` y `TW1501`, Gate en `TW1507`, ninguno en `TW1606 render`) y `cubase_track_edges` en las cuatro pistas de audio: `POC-TEST` 2,0 … 139,976 s (7 bordes), `TW1501` 4–34 s, `TW1507` 30, 40, 43 s, `TW1606 render` 5 s. Tras los sondeos, `POC-INSTR` seguía seleccionada y el cursor donde estaba.
- `TW1507` tiene un número impar de bordes: su evento desde 0 s no se ve (solo su final en 30 s), igual que `TW1606 render` (0–5 s, solo el final). La skill señala ahora un número impar de bordes como un probable evento en 0 s.
- `cubase_list_inserts` no dice que el Compressor de `TW1501` está en bypass: añadido al informe de capacidades de la skill.
- El dry run del perfil del episodio, construido desde el nuevo campo `episode` de `resolve`, solo añadió la línea del rol nuevo; el `min_silence_seconds` integrado no se copió en el episodio. No se aplicó (el rol era un ejemplo, no del usuario).
- `cubase_workspace` `record` (la Gate de `TW1507` como elemento `plugin` de `noise-gate`), `status` (tres elementos) y `forget` funcionaron; `state.json` quedó como estaba. Sus respuestas dejaban `owned` e `items` vacíos; ahora llevan el estado después del cambio.

## 2026-11-15 — TW-1611: el control final a través del servidor

- `cubase_final_qc` sobre `Mixdown/X0001.mp3` del proyecto de pruebas (140 s, MP3 de 128 kbps, 44,1 kHz) con los destinos del perfil del episodio (Apple, Spotify) y `expected_seconds` 140: veredicto `fail`, un fallo: la sonoridad de Apple, −21,13 LUFS frente a −16 ± 1 (con la página de Apple como fuente); códec, canales, frecuencia de muestreo, tasa de bits (127,7 kbps medidos a partir del tamaño y la duración), pico real (−9,47 dBTP) y duración (140,042 s, dentro de los 0,1 s permitidos en MP3) pasan. La sonoridad y el pico real de Spotify salieron como `info`, "not published by the platform".
- Avisos: dos pausas de 32,1 s y 35,2 s (en 23,26 s y 76,58 s) y un cambio de nivel de −10,8 LU en 2:10. `project_saved_after: true` (el MP3 es del 13 de noviembre y el proyecto se guardó el 15), con su nota.
- El cursor fue a la pausa más larga con `cubase_set_position`. Con `report: true` se escribieron los informes JSON y Markdown en `Trackwright/reports/`, y el Markdown se registró con `cubase_workspace` como elemento `report` de `podcast-final-qc`.
- Corregido después: un título decía "1 level changes"; el final (2:10,042) y el cambio de nivel (2:10,000) eran dos momentos a 42 ms, ahora unidos; las notas del informe tienen ya su propio encabezado.

## 2026-11-16 — TW-1612: alcanzar un objetivo de sonoridad en Elements, en un episodio entero

- La exportación de 46 minutos del episodio E0004 (`Pod Mic` sola), importada sin copiar en el proyecto de pruebas y exportada sola cinco veces por el usuario: detalles y tabla en `experiments/tw1612/`. El fader a −5,25 dB lo llevó de −10,75 a −16,00 LUFS en una pasada; el MP3 de 128 kbps subió el pico real 0,78–0,82 dB; el Brickwall Limiter de la ranura 1 actúa antes del fader y el de la ranura 7 después; con DIC activado, 0,24 dB de picos entre muestras pasan el umbral de −1 dB.
- `cubase_export_mix` confirmó las dos exportaciones MP3 como 6,3 s más cortas, por la duración estimada de afinfo (2767,55 s frente a 2773,92 s decodificados); las duraciones salen ahora de soundfile, y de afinfo solo para AAC.
- Queda en el proyecto de pruebas: la pista `TW1612 episode`, un segundo Brickwall Limiter en la ranura 7 de Stereo Out (en bypass; los plugins no se pueden quitar por la API), las cinco exportaciones `tw1612-r0` … `r4` en `Mixdown`. El fader de Stereo Out vuelve a estar en 0,00 dB.
