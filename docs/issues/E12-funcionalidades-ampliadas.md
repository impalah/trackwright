# E12 — Funcionalidades ampliadas

Origen: preguntas del usuario del 2026-11-13. El análisis y la procedencia de cada dato están en [`docs/investigacion.md`](../investigacion.md); los comandos, en [`docs/referencia/comandos-cubase.txt`](../referencia/comandos-cubase.txt).

Regla común: un comando sin probar **no** se expone como herramienta hasta verificar en Cubase su clase (`direct`, `dialog`, `confirm`…) y su efecto observable.

## TW-1201 Arranque automático de Cubase y del puente

- **Estado:** cerrada. Verificada en Cubase el 2026-11-13: puente arrancado por `serve`, Cubase abierto por `cubase_launch` y `awaiting_user` hasta abrir el proyecto
- **Objetivo:** que el usuario no tenga que abrir Cubase ni el puente a mano.
- **Alcance:**
  - **`cubase_launch`** (escritura del sistema, con confirmación):
    - comprueba si Cubase está abierto, por el proceso y porque el script responde;
    - si no, lo abre con `open -a "Cubase 15"`, opcionalmente con un proyecto `.cpr`;
    - espera, con un plazo configurable, a que el script responda.
  - **Arranque del puente:** `trackwright serve` lo arranca como proceso separado si no responde. Debe ser opcional (`[bridge] autostart`) y no duplicarse si ya existe.
  - **Configuración:** ruta de la aplicación (`[cubase] app = "Cubase 15"`) y plazo de espera.
- **Riesgos:**
  - diálogos de arranque (aviso de MediaBay, Steinberg Hub) que bloquean hasta que el usuario responde: la herramienta debe informar `awaiting_user` si el script no responde a tiempo;
  - no abrir dos instancias.
- **Pruebas:**
  - unitarias, con el lanzador y el comprobador de procesos simulados;
  - verificación manual: Cubase cerrado → herramienta → Cubase abierto y el script respondiendo.

## TW-1202 Guardar el proyecto y otras operaciones de archivo

- **Estado:** cerrada. `cubase_save_project` probada por el usuario desde Claude Code el 2026-11-13. Experimento en [experiments/tw1202](../../experiments/tw1202/README.md). `Close`, `Revert` y `Quit` se descartan
- **Objetivo:** guardar desde Trackwright; por ejemplo, antes y después de una sesión de cambios.
- **Experimento previo**, en un proyecto desechable: clase y efecto de `File / Save`, `Save New Version` y, solo para clasificarlos, `Save As`, `Open`, `New`, `Close` y `Revert`.
- **Alcance tras el experimento:**
  - **`cubase_save_project`:** `Save` o `Save New Version`. Verificación: sin diálogo, y comprobación visual o de la fecha del archivo si se conoce la ruta.
  - **`Close`, `Revert` y `Quit`:** como mucho en la lista de `cubase_run_command`, clasificados como destructivos.
- **Nota:** cambia la política actual («Trackwright nunca guarda»). Hay que documentarlo y requerir `dry_run` y confirmación.

## TW-1203 Flujo guiado de importación de audio

- **Estado:** implementada (`cubase_import_audio`, script 1.5.4). Experimento en [experiments/tw1203](../../experiments/tw1203/README.md). La verificación ya no es visual: usa el sondeo de eventos. Falta que el usuario la pruebe
- **Objetivo:** «Importa este audio en la pista X en el compás N» con el mínimo esfuerzo del usuario.
- **Flujo:**
  1. seleccionar la pista [VER];
  2. colocar el cursor [VER];
  3. `File / Import Audio File` [CMD], que abre el selector;
  4. el usuario elige el archivo, y Trackwright le indica cuál, si se le ha dado una ruta;
  5. confirmación, en dos fases, como `cubase_add_track_interactive`.
- **Experimento previo:** clase del comando, y si la importación va a la pista seleccionada y a la posición del cursor (o pide opciones de copia y conversión).
- **Verificación:** ~~visual~~ por sondeo de bordes de eventos (TW-1211).

## TW-1204 Flujo guiado de exportación de audio

- **Estado:** cerrada. `cubase_export_mix` probada por el usuario el 2026-11-13 con el episodio completo en MP3. La tolerancia de duración se amplió para formatos comprimidos ([experiments/tw1204](../../experiments/tw1204/README.md))
- **Objetivo:** exportar la mezcla de un rango.
- **Flujo:**
  1. colocar los localizadores [VER];
  2. `File / Export Audio Mixdown` [CMD], que abre su diálogo;
  3. el usuario revisa las opciones y exporta;
  4. confirmación en dos fases.
- **Experimento previo:** clase del comando y si el diálogo toma el rango de los localizadores.

## TW-1205 Experimento: presets de los plugins

- **Estado:** pendiente
- **Hipótesis:** `Preset / Next` y `Previous` actúan sobre el editor del plugin que tiene el foco.
- **Experimento:**
  1. abrir el editor del plugin desde la API, con el parámetro de edición del slot;
  2. leer los parámetros;
  3. lanzar `Preset / Next`;
  4. releer y comparar.
  - Probar también con el editor cerrado y con otro plugin enfocado, para saber sobre qué actúa.
- **Si funciona:** herramienta `cubase_plugin_preset_step(track, slot, direction)`, que verifica comparando parámetros. Elegir un preset por su nombre no es posible [NE].

## TW-1206 Experimento: grabar automatización de volumen

- **Estado:** hecha. **Resultado positivo con la variante B2** (2026-11-13); la A no graba y la B1 no está disponible en Elements
- **Hipótesis:** con la escritura de automatización activada (parámetro 4013) y el transporte en marcha, los cambios de volumen hechos por la API quedan grabados como automatización y se reproducen con la lectura activada (4014).
- **Experimento**, sin cambiar el script, en una pista con audio de un proyecto desechable:

  | Paso | Acción | Medida |
  |---|---|---|
  | A0 | Anotar el volumen, 4013 y 4014, el cursor y el modo de automatización visible | estado inicial |
  | A1 | 4013 = 1 (escritura activada) en POC-TEST; cursor en el compás 1 | relectura |
  | A2 | **El usuario pulsa Play.** Trackwright escribe una rampa de volumen (0,79 → 0,40 en unos 4 s, un paso cada 0,2 s). **El usuario pulsa Stop** | escrituras con relectura |
  | A3 | 4013 = 0 y 4014 = 1; cursor en el compás 1; el volumen a 0,79 a mano | relectura |
  | A4 | **El usuario pulsa Play.** Trackwright **lee** el volumen cada 0,2 s durante unos 5 s. El usuario pulsa Stop | ¿reproduce la rampa? |
  | A5 | El usuario mira el carril de automatización de volumen de POC-TEST | ¿aparece la curva? |
  | A6 | Limpieza: el usuario borra la automatización, o Deshacer; 4014 = 0; volumen original | estado final igual que A0 |

- **Precaución:** se reproduce audio. Baja el monitor o silencia la salida; el silencio de la salida no afecta a la automatización de la pista.
- **Resultado de la variante A (2026-11-13): no graba.** Detalle en [verificacion.md](../verificacion.md). El fader se mueve durante la reproducción, pero no queda automatización; con la lectura activada, el volumen no varía.
- **Variantes pendientes:**
  - **B1 — descartada en Elements (2026-11-13):** los comandos de modo dan `canPerform=false` y el selector no aparece en la interfaz.
  - *(B1, planteamiento original)* **Sin cambiar el script:** el usuario pone a mano el modo de automatización **Auto-Latch** (o Cross-Over), en el que la escritura arranca con cualquier cambio del parámetro, y se repiten A1–A4.
  - **B2 — FUNCIONA (2026-11-13):** el fader de la superficie con toque graba la automatización, y esta se reproduce con R activado (de 0 a −12,2 dB entre los compases 1 y 4.3). Ver [verificacion.md](../verificacion.md).
  - *(B2, preparación)* script 1.2.1 con el fader detrás de `AUTOMATION_FADER_ENABLED`; versión de prueba `1.2.1+tw1206` con `experiments/tw1206/build.py`; paso `record-b2` en `experiments/tw1206/automation.py`; tests con el arnés en `tests/script/test_automation_fader.py`. Protocolo en `experiments/tw1206/README.md`.
  - *(B2, planteamiento)* **Con cambios en el script:** un fader de la superficie enlazado (`makeValueBinding`) al volumen de la pista seleccionada (`mTrackSelection.mMixerChannel.mValue.mVolume`). El script movería el fader con su estado de toque (`mTouchState`), como un controlador físico, que es como los controladores graban automatización.
- **Si alguna variante funciona:** diseñar `cubase_record_automation(track, parameter, points)`. Requeriría iniciar el transporte desde Trackwright, con `Transport / Start` o `mTransport.mValue.mStart`, que habría que verificar.

## TW-1207 Herramienta de automatización y ampliación a otros parámetros

- **Estado:** cerrada. Verificada en Cubase el 2026-11-13: fundido de volumen grabado desde Claude Code con el script 1.4.0
- **Objetivo:** la herramienta `cubase_record_automation` y la automatización de más parámetros que el volumen.
- **Base verificada:**
  - fader de la superficie con toque (TW-1206 B2);
  - `Transport / Start` y `Stop` desde Trackwright (2026-11-13).
- **Experimento B3** (script `1.3.0`, controles detrás de `AUTOMATION_CONTROLS_ENABLED`; prueba automática en `experiments/tw1206/controls.py`):
  - **controles enlazados a la pista seleccionada (45):** volumen, panorama, nivel de los envíos 1 a 4, EQ del canal (ganancia, frecuencia y Q de las bandas 1 a 4), pre-filtro (ganancia, corte de graves y de agudos), Quick Controls 1 a 8, y parámetros 1 a 8 de los slots de inserción 1 y 2 (bancos de parámetros del plugin);
  - **identificación:** cada control informa del título del parámetro que tiene enlazado (`auto.list`), para saber qué parámetro del plugin cae en cada posición del banco;
  - **criterio:** un control «graba» si en la reproducción con lectura su valor sigue la rampa sin que nadie lo toque.
- **Diseño previsto de la herramienta, tras el experimento:** `cubase_record_automation(track, parameter, points[(posición, valor)])`:
  1. selecciona la pista;
  2. activa W;
  3. coloca el cursor antes del primer punto y arranca la reproducción;
  4. toca el control, escribe los valores sincronizados con la posición del cursor y lo suelta;
  5. para la reproducción y desactiva W;
  6. verifica con una reproducción en lectura (opcional).
  - Exigirá escrituras habilitadas y confirmación, porque reproduce audio y modifica el proyecto.

## TW-1208 Unidades reales en la automatización (conversión exacta de Cubase)

- **Estado:** cerrada. Verificada en Cubase el 2026-11-13: conversión de 12 parámetros y grabación con `plain` desde Claude Code
- **Origen:** en el uso real (2026-11-13), el modelo no conocía la correspondencia entre el valor normalizado y los dB. Estimó −20 dB ≈ 0,36 (es 0,2551) y propuso calibrar moviendo el fader.
- **Evidencia:** `da.convert` (`convertParameterPlainToProcessValue`) convierte con exactitud y en los dos sentidos el volumen, los envíos, el EQ (ganancia y frecuencia), el pre-filtro y los parámetros de plugin ([verificacion.md](../verificacion.md)).
- **Alcance:**
  1. **Correspondencia** entre cada control de automatización y su parámetro DirectAccess:

     | Control | Objeto | Parámetro |
     |---|---|---|
     | `volume` | canal | tag 1025 |
     | `pan` | Panner | tag 4201 |
     | `sendN.level` | slot de envío N | tag 4097 |
     | `eqB.gain/freq/q` | EQ del strip | título «EQ B Gain/Freq/Q» |
     | `prefilter.gain/lowcut/highcut` | InputFilter | `PreGain`, `LC-Freq` y `HC-Freq` |
     | `insertS.pN` | plugin del slot S | por título, tomado del título del control, por ejemplo «Compressor / Threshold» → «Threshold» |

     Los `qcN` no tienen correspondencia conocida: solo admiten valores normalizados.
  2. **`cubase_record_automation`:** cada punto acepta `value` (normalizado) **o** `plain` (unidades reales: dB, Hz…). Los `plain` se convierten con Cubase antes de grabar, y el ensayo muestra la conversión.
  3. **Herramienta `cubase_convert_value(track, parameter, plain | value)`:** solo lectura, convierte en los dos sentidos. Sustituye a la calibración: es exacta y no mueve nada.
  4. **`cubase_list_automation_targets`:** el campo `display` ya está en unidades reales. Se documenta así en lugar de convertir los 45 parámetros, que costaría varios segundos.
- **Pruebas:** simulador con los objetos Panner, slots de envío, InputFilter, EQ con 12 parámetros y plugins con parámetros nombrados; tests de correspondencia, conversión, errores (`NO_UNIT_CONVERSION` en los Quick Controls, `OUT_OF_RANGE`) y contrato MCP.

## TW-1209 Leer las propiedades del proyecto abierto

- **Estado:** cerrada. `cubase_get_project`, verificada en Cubase el 2026-11-13 (3/4, metrónomo, carpeta del proyecto); la automatización usa el compás leído. Queda fuera: seguir los cambios de compás a lo largo del proyecto
- **Objetivo:** que el modelo conozca el contexto del proyecto antes de actuar: nombre, tempo, compás, frecuencia de muestreo, longitud, ciclo y metrónomo. Hoy supone 4/4 y no conoce el nombre ni la frecuencia.
- **Qué hay hoy:** `cubase_get_transport` ya lee el cursor, los localizadores del ciclo y el tempo.
- **Qué ofrece la API de MIDI Remote** (según `midiremote_api_v1.d.ts` de Cubase 15; **sin verificar**):

  | Propiedad | Vía candidata | Lectura |
  |---|---|---|
  | Ciclo activado | `mHostAccess.mTransport.mValue.mCycleActive` (valor de host, enlazable a un control de superficie) | Probable, como los controles de automatización |
  | Metrónomo activado y nivel del clic | `mTransport.mValue.mMetronomeActive` y `mMetronomeClickLevel` | Probable |
  | Tempo, cursor, localizadores | `mTimeDisplay` | **Verificado** |
  | Nombre y ruta del proyecto | No aparece en la API. Alternativa: el `.cpr` abierto por el proceso de Cubase (`lsof`), sin abrir el archivo | Por explorar; **requiere permiso del usuario** |
  | Compás (numerador/denominador) | No aparece en la API. Alternativas: un objeto DirectAccess fuera del mezclador (por explorar) o deducirlo de la relación entre las pantallas de tiempo primaria y secundaria | Incierto |
  | Frecuencia de muestreo, resolución, frame rate, inicio y longitud del proyecto | No aparecen en la API (son de «Configuración del proyecto», un diálogo) | Probablemente imposible desde el script |
  | Precuenta, uso de la pista de tempo | Solo como comandos que alternan el estado (`Transport / Precount On`, `Tempo Track Rehearsal Mode On/Off`), sin lectura | Imposible leer el estado |
- **Experimento previo (TW-1209a):**
  1. añadir al script, en una compilación de experimento, controles de superficie enlazados a `mCycleActive`, `mMetronomeActive` y `mMetronomeClickLevel`, y comprobar que sus valores llegan;
  2. explorar con DirectAccess los objetos del proyecto fuera del mezclador, en solo lectura, buscando compás o frecuencia;
  3. con permiso del usuario, comprobar si `lsof` identifica el `.cpr` abierto.
- **Entregable:** herramienta `cubase_get_project`, que devuelve lo verificado y marca como `null`, con su motivo, lo que no se puede leer.
- **Consecuencia:** si el compás se puede leer, `cubase_record_automation` y la conversión de segundos dejan de suponer 4/4.

## TW-1210 Modificar las propiedades del proyecto

- **Estado:** pendiente; depende de TW-1209
- **Objetivo:** cambiar desde el MCP las propiedades del proyecto que la API permita, con ensayo, confirmación y relectura, como el resto de escrituras.
- **Qué hay hoy:** `cubase_set_tempo` (verificado) y `cubase_set_position` (cursor y localizadores del ciclo, verificado).
- **Candidatas:**

  | Propiedad | Vía candidata | Relectura |
  |---|---|---|
  | Ciclo activado/desactivado | Valor de host `mCycleActive` desde un control de superficie, o el comando `Transport / Cycle` (alterna) | Depende de TW-1209 |
  | Metrónomo activado y nivel del clic | `mMetronomeActive` y `mMetronomeClickLevel` | Depende de TW-1209 |
  | Precuenta, uso de la pista de tempo | Comandos que alternan, sin lectura: solo serían seguros si se pudiera leer el estado | Sin relectura: **no se implementan** salvo que TW-1209 encuentre cómo leerlos |
  | Compás, frecuencia de muestreo, longitud | Solo en el diálogo «Configuración del proyecto» (comando `Project / Setup`, clase `dialog`) | Herramienta interactiva como `cubase_add_track_interactive`: Trackwright abre el diálogo, el usuario lo cambia y Trackwright relee lo que pueda |
- **Reglas:** toda escritura comprueba la política (`check_project_write`), ensaya por defecto y relee. Nada sin relectura se presenta como verificado.

## TW-1211 Edición por rangos en segundos (podcast)

- **Estado:** cerrada. Verificada en Cubase el 2026-11-13 desde Claude Code (`delete_time` 2–30 s, `verified: true`, estado restaurado y deshecho con Undo)
- **Origen:** el usuario edita podcasts, donde el compás no importa. Quiere dar órdenes como «borra el audio de la pista X entre el segundo 2 y el 30».
- **Qué hay:**
  - `cubase_set_position` con `unit: "seconds"` para el cursor y los localizadores. Su verificación supone 4/4 y tempo constante: hay que pasar a releer `time2` del objeto Transport (TW-1209);
  - comandos verificados: `Split Loop` corta todas las pistas con eventos en el rango, y `Select in Loop` crea una selección de rango.
- **Limitación de la API:** no se pueden leer ni modificar eventos. Toda edición pasa por comandos que actúan entre los localizadores o sobre la selección.
- **Experimento** ([experiments/tw1211](../../experiments/tw1211/README.md)):
  1. posicionar en segundos y releer con `time2`;
  2. ver si `Locate Next/Previous Event` permite leer los bordes de los eventos (sondeo de eventos, para verificar);
  3. ver el alcance de `Select in Loop`: ¿pistas seleccionadas o todas?;
  4. ver el efecto de cada acción sobre el rango 2–30 s de una pista:

     | Acción | Comando |
     |---|---|
     | Borrar dejando hueco | `Delete` sobre la selección de rango |
     | Borrar cerrando el hueco | `Delete Time` |
     | Cortar el tiempo | `Cut Time` |
     | Silenciar | `Process / Silence` |
     | Insertar silencio | `Insert Silence` |
     | Recortar | `Crop Range` |
  5. clase de cada comando (directo, diálogo, selección) y si `Undo` lo deshace.
- **Entregable:** herramienta `cubase_edit_range(tracks, start, end, unit, action)`, con ensayo, confirmación y, si el sondeo de eventos funciona, verificación.
- **Riesgos:**
  - `Delete Time` y `Split Loop` afectan a todas las pistas;
  - sin sondeo de eventos no hay relectura;
  - por eso el experimento se hace con el proyecto guardado y con el usuario mirando.

## TW-1212 Edición por rangos en una sola pista

- **Estado:** cerrada. `cubase_edit_range` con `track` (solo `delete`). Verificada en Cubase el 2026-11-13, primero por Claude (`verified: true`, 7 pasos de deshacer, informados y reales) y después por el usuario desde Claude Code. Detalle en [experiments/tw1212](../../experiments/tw1212/README.md)
- **Origen:** `cubase_edit_range` actúa sobre todas las pistas, porque `Select in Loop` con la herramienta de rango selecciona todas (TW-1211). Para un podcast hace falta también quitar, por ejemplo, una tos del micro de un invitado sin tocar los demás.
- **Vías a investigar:**
  1. **Objeto en vez de rango:** `Split Loop` corta en los localizadores (en todas las pistas, sin cambiar el sonido); después, seleccionar solo los eventos de la pista dentro del rango (con `Select All on Tracks`, `Select Events under Cursor` o `Select from Cursor to End` con la pista seleccionada) y aplicar `Delete`. Hay que verificar qué alcance tiene cada selección.
  2. **Ocultar o bloquear las demás pistas** durante la edición, si la API o los comandos lo permiten, y si `Select in Loop` respeta pistas bloqueadas u ocultas.
  3. **Comandos de la lista oficial** que limiten el rango a las pistas seleccionadas.
  4. **Silenciar en lugar de borrar** con el volumen automatizado (TW-1207). No toca los eventos, así que es otra semántica.
- **Verificación:** el sondeo de eventos (TW-1211), que ya funciona por pista seleccionada, en la pista editada y en otra que no debe cambiar.
- **Entregable:** un parámetro `tracks` en `cubase_edit_range`, o una herramienta aparte, si alguna vía funciona.
