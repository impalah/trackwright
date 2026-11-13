# E12 — Funcionalidades ampliadas

Origen: preguntas del usuario del 2026-11-13. El análisis y la procedencia de cada dato están en [`docs/investigacion.md`](../investigacion.md); los comandos, en [`docs/referencia/comandos-cubase.txt`](../referencia/comandos-cubase.txt).

Regla común: un comando sin probar **no** se expone como herramienta hasta verificar en Cubase su clase (`direct`, `dialog`, `confirm`…) y su efecto observable.

## TW-1201 Arranque automático de Cubase y del puente

- **Estado:** pendiente
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

- **Estado:** pendiente
- **Objetivo:** guardar desde Trackwright; por ejemplo, antes y después de una sesión de cambios.
- **Experimento previo**, en un proyecto desechable: clase y efecto de `File / Save`, `Save New Version` y, solo para clasificarlos, `Save As`, `Open`, `New`, `Close` y `Revert`.
- **Alcance tras el experimento:**
  - **`cubase_save_project`:** `Save` o `Save New Version`. Verificación: sin diálogo, y comprobación visual o de la fecha del archivo si se conoce la ruta.
  - **`Close`, `Revert` y `Quit`:** como mucho en la lista de `cubase_run_command`, clasificados como destructivos.
- **Nota:** cambia la política actual («Trackwright nunca guarda»). Hay que documentarlo y requerir `dry_run` y confirmación.

## TW-1203 Flujo guiado de importación de audio

- **Estado:** pendiente
- **Objetivo:** «Importa este audio en la pista X en el compás N» con el mínimo esfuerzo del usuario.
- **Flujo:**
  1. seleccionar la pista [VER];
  2. colocar el cursor [VER];
  3. `File / Import Audio File` [CMD], que abre el selector;
  4. el usuario elige el archivo, y Trackwright le indica cuál, si se le ha dado una ruta;
  5. confirmación, en dos fases, como `cubase_add_track_interactive`.
- **Experimento previo:** clase del comando, y si la importación va a la pista seleccionada y a la posición del cursor (o pide opciones de copia y conversión).
- **Verificación:** visual. La API no ve los eventos.

## TW-1204 Flujo guiado de exportación de audio

- **Estado:** pendiente
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

- **Estado:** en curso
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
