# Investigación de funcionalidades ampliadas

[English](research.md) · **Español**

Preguntas del usuario del 2026-11-13 sobre qué más puede hacer Trackwright. Cada respuesta indica su **procedencia**:

| Etiqueta | Significado |
|---|---|
| **[VER]** | Verificado en Cubase Elements 15.0.30 (ver [verification.es.md](verification.es.md)) |
| **[CMD]** | El comando existe en la lista oficial de comandos ([reference/cubase-commands.txt](reference/cubase-commands.txt), Cubase/Nuendo 13), pero **no se ha probado** |
| **[API]** | Aparece en los typings locales de la API MIDI Remote; sin probar |
| **[NE]** | No encontrado |

Issues derivadas: épica [E12](issues/E12-extended-features.es.md).

## 1. ¿Puede Trackwright arrancar Cubase?

- **MIDI Remote no puede hacerlo:** solo existe con Cubase abierto.
- **Trackwright sí puede hacerlo desde macOS:**
  - comprobar si Cubase está abierto, por el proceso o porque el script responde;
  - abrirlo con `open -a "Cubase 15"`, o con un proyecto: `open -a "Cubase 15" <proyecto>.cpr`.
- **Limitaciones:**
  - el arranque tarda;
  - puede mostrar diálogos que hay que atender a mano. Observado: el aviso de acceso a MediaBay **[VER]**; posiblemente también el Steinberg Hub.
- Del mismo modo, `trackwright serve` podría arrancar el puente si no está en marcha.
- **Issue:** TW-1201.

## 2. ¿Operaciones generales: abrir, guardar…?

- **Comandos existentes [CMD]**, categoría `File`: `New`, `New Empty`, `Open`, `Save`, `Save As`, `Save New Version`, `Save as Template`, `Close`, `Revert`, `Quit` y `Back up Project`.
- **Comportamiento previsto, sin verificar:**
  - `Save`, en un proyecto ya guardado, y `Save New Version` actúan sin diálogo;
  - `Open`, `Save As` y `New` abren un diálogo, y no se les puede pasar una ruta.
- **Riesgo:** `Close`, `Revert` y `Quit` pueden perder trabajo sin guardar. Hay que tratarlos como destructivos.
- **Abrir un proyecto concreto:** desde macOS (punto 1).
- **Issue:** TW-1202.

## 3. ¿Importar audio en una pista?

- **Ya se puede [VER]:** seleccionar la pista y colocar el cursor.
- **El comando existe [CMD]:** `File / Import Audio File`. Previsiblemente abre el selector de archivos, y **la API no permite pasarle la ruta [NE]**.
- **Flujo posible:** Trackwright prepara la pista y la posición, y abre el diálogo; el usuario elige el archivo; Trackwright verifica lo que pueda.
- Sin intervención del usuario solo sería posible automatizando la interfaz gráfica, que el diseño descarta.
- Otros comandos de importación [CMD]: `Import MIDI File`, `Import Tracks from Project`, `Import Track Archive`…
- **Issue:** TW-1203.

## 4. ¿Presets de los inserts?

- **No hay parámetro de preset [VER]:** ni StudioEQ (40 parámetros) ni Compressor (46) exponen ninguno con «prog» o «preset» en el título (consulta del 2026-11-13).
- **Comandos [CMD]:** `Preset / Next`, `Preset / Previous` y `Preset / Open Browser`, más sus equivalentes de presets de pista (`Track Preset: …`) y `AddTrack / From Track Presets`.
  - **No existen [NE]:** cargar un preset por nombre, guardar presets o cambio de programa.
  - Se desconoce sobre qué actúan. Probablemente sobre el editor del plugin que tiene el foco.
- **Experimento propuesto:** abrir el editor del plugin desde la API, mediante el parámetro de edición del slot; lanzar `Preset / Next`; comprobar si cambian los parámetros. Permitiría recorrer presets, no elegirlos por nombre.
- **Issue:** TW-1205.

## 5. ¿Grupos y control conjunto?

- **Enrutar una salida o un envío a un grupo por la API no es posible [VER]:** se queda en «Sin bus» (findings 39 y 41 de la POC).
- **Comandos [CMD]:**
  - `Mixer / Add Track To Selected: Group Channel`: crea un grupo y envía a él los canales seleccionados;
  - `Mixer / Add Track To Selected: VCA Fader`: crea un fader VCA para los seleccionados;
  - `Mixer / Link Channels`, `Unlink Channels` y `Q-Link`.
- **Limitación:** la API selecciona **una** pista cada vez **[VER]**. La selección múltiple la haría el usuario. Estos comandos pueden abrir diálogos.
- **Issue:** no solicitada por ahora; candidata para una épica futura.

## 6. ¿Exportar audio?

- **Comando [CMD]:** `File / Export Audio Mixdown`. Previsiblemente abre su diálogo.
- **Flujo posible:** Trackwright coloca los localizadores **[VER]**, que delimitan el rango, y abre el diálogo; el usuario revisa las opciones y pulsa Exportar.
- Otros [CMD]: `Export Selected Tracks` y `Export Selected Events`.
- **Issue:** TW-1204.

## 7. ¿Automatización (por ejemplo, del volumen)?

- **Acceso a curvas o puntos de automatización: [NE].**
- **Parámetros del canal [VER]:** 4013 «Escribir automatización», 4014 «Leer automatización» y 4105 «Medidores de automatización».
- **Comandos [CMD]:**
  - **modos:** `Automation Mode - Touch`, `- Auto-Latch`, `- Cross-Over`, `- Trim` y `Next Automation Mode`;
  - **activación:** `Toggle Read/Write Enable All/Selected Tracks`;
  - **relleno:** `Fill Gaps`, `Fill Loop`, `Fill To End`, `Fill To Start`…;
  - **borrado:** `Delete Automation in Range` y `Delete Automation of Selected Tracks`;
  - **visibilidad:** `Show/Hide Automation`;
  - **suspensión:** `Suspend Reading/Writing …`.
- **Transporte:** comandos `Transport / Start`, `Stop` y `Cycle` [CMD], y valores `mTransport.mValue.mStart`, `mStop`, `mRecord` y `mCycleActive` [API].
- **Vía posible:** **grabar** la automatización: escritura activada + reproducción + cambios del valor desde Trackwright durante la reproducción.
- **Issue:** TW-1206 (experimento).

## 8. ¿Inserts de Stereo Out y otras salidas?

- **Sí [VER]:** Stereo Out (`OutputChannel`) aparece en el mezclador, con 8 slots de inserción y el catálogo completo de 53 plugins (consulta del 2026-11-13).
- **Previsiblemente funcionan igual,** porque usan las mismas operaciones: insertar plugins y escribir parámetros en la salida. No se ha probado todavía.
- Los canales de grupo y FX también aparecen en el mezclador **[VER]** (se vio con «Group 01» y «POC-GROUP»).
