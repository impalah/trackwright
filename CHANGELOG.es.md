# Cambios

[English](CHANGELOG.md) · **Español**

## 0.4.0 — 2026-11-14

Fases 1 y 2 de la remediación de calidad (épica E14): seguridad y resultados veraces, robustez del puente y del script de Cubase. Requiere el **script de Cubase 1.6.0**.

**Actualizar desde 0.3.0:**

1. `uv tool upgrade trackwright`
2. `trackwright bridge-stop`: el puente que arrancó la 0.3.0 ignora la sesión que llevan ahora las escrituras. El servidor MCP arranca otro cuando lo necesita.
3. `trackwright setup`: instala el script 1.6.0 (muestra lo que sustituye y pregunta); después, **reinicia Cubase**.
4. Reinicia tu cliente MCP (en Claude Code, `/mcp`) para que cargue las herramientas nuevas. Si registraste el servidor con `uvx --from trackwright==0.3.0`, ese registro sigue ejecutando la 0.3.0: `setup` ahora lo avisa; sustitúyelo con `claude mcp remove trackwright -s user` y `trackwright setup`.
5. `trackwright doctor`: «script loaded in Cubase» debe indicar 1.6.0.

- **Cambio incompatible:** `track` es obligatorio en `cubase_set_parameter` y `cubase_insert_plugin`; sus salidas incluyen `track_uid` para reutilizarlo al aplicar un ensayo.
- **Política de escrituras** (TW-1401): `cubase_run_command` rechaza guardar y borrar pistas (usa las herramientas específicas) y se rechaza, como las ediciones de rango y los cortes en todas las pistas, mientras `[writes] allowed_tracks` tenga pistas; las ediciones de rango en una pista respetan `allowed_tracks`; `cubase_set_parameter` rechaza el enrutado, el nombre y la selección del canal; mover los localizadores del ciclo necesita las escrituras activadas.
- **Sesión fijada a través del puente** (TW-1402): las escrituras llevan la sesión que fijó la herramienta, así que el script las rechaza tras una recarga; una escritura con muy poco tiempo para esperar su respuesta no se envía (`BUSY`). **Reinicia el puente tras actualizar** (`trackwright bridge-stop`): un puente anterior ignora la sesión.
- **Resultados veraces** (TW-1403): una importación solo se confirma con bordes de evento nuevos; un guardado sin carpeta de proyecto conocida queda en `fired`, no en `saved`; una grabación de automatización interrumpida indica `complete: false`; `cubase_set_project` informa de lo aplicado cuando falla una escritura; nunca se adivina entre varios proyectos abiertos; los errores inesperados llegan al cliente como `INTERNAL_ERROR`.
- **Integración continua** (TW-1404): GitHub Actions en macOS ejecuta `make check`, los tests con Node del script de Cubase y la construcción del paquete en cada push y pull request; el umbral de cobertura sube al 95 %.
- **Robustez del puente** (TW-1405): un segundo puente rechazado ya no borra el socket del que está activo (ni abre puertos MIDI); cola de conexiones de 128 y un segundo sondeo antes del arranque automático; tiempo máximo de lectura por cliente; búfer de SysEx acotado; una trama perdida ya no destruye un reensamblado y una tabla llena descarta la entrada más antigua; todo error del socket es un error `BRIDGE_UNAVAILABLE`; tiempos máximos en los subprocesos; nada de directorios del socket enlazados; instalación atómica del script; `--log-level` se valida.
- **`trackwright bridge-stop`** (y `make bridge-stop`): para el puente en marcha a través del pid que él mismo indica. El `pkill -f "trackwright bridge"` documentado no encontraba un puente arrancado automáticamente, que se ejecuta como `python -m trackwright --config … bridge`.
- **Versión del script en ejecución** (TW-1407): `doctor` comprueba que Cubase ejecuta el script del paquete (tras actualizar sin reiniciar Cubase falla y explica qué hacer), y `cubase_status` indica `script_outdated`.
- **Script de Cubase 1.6.0** (TW-1406): las escrituras de parámetros ya no recorren el árbol del mezclador; cada ámbito de DirectAccess comprueba su propia activación; `da.channels` admite como mucho 16 tags; las peticiones aún en cola cuando se desactiva la página reciben `NOT_ACTIVE`; `page.mOnIdle` nunca lanza excepciones a Cubase; los nombres heredados (`toString`) no son operaciones ni comandos; las peticiones incompletas caducan a los ~6 s en vez de ~225 s; `RESPONSE_TOO_LARGE` conserva `op` y `via`. Instálalo con `trackwright setup` y reinicia Cubase.
- **Revisión de calidad del código** (`docs/quality-review.es.md`) y su plan de remediación, la épica E14: agujeros de la política de escrituras, fijación de sesión en el puente, resultados veraces, robustez, conformidad entre simulador y script, mutation testing e integración continua.
- **Enlaces del proyecto:** `Repository` e `Issues` (GitHub) en los metadatos del paquete; el README enlaza en GitHub la versión en castellano, la documentación y la licencia, enlaces que también funcionan en PyPI.
- **Documentación:** la instalación desde el código fuente clona el repositorio de GitHub; las rutas locales se sustituyen por otras genéricas.

## 0.3.0 — 2026-11-13

Primera versión publicada en PyPI: `uv tool install trackwright`.

- **`Makefile`** con las tareas habituales (comprobaciones, tests, build, publicación, doctor, script de Cubase…), siempre a través de uv; `make help` las lista.
- **Publicación en PyPI** (TW-1303): el paquete pasa a llamarse **`trackwright`** (antes `trackwright-mcp`) y se instala con `uv tool install trackwright`.
  - Licencia **AGPL-3.0-or-later** (archivo `LICENSE`, metadatos según PEP 639).
  - README reescrito para el usuario final; el índice de la documentación pasa a `docs/README.md`.
  - `setup` registra en Claude Code la ruta absoluta de `trackwright` (instalado con `uv tool`), o `uvx --from trackwright==<versión> trackwright serve` cuando se ejecuta con `uvx`, fijado a la versión del script que instala.
- **Enfoque:** Trackwright se presenta como un servidor MCP independiente para DAW cuya primera implementación es Cubase. La documentación habla de clientes MCP en general (probado con Claude Code) y explica cómo conectar GitHub Copilot en VS Code (aún sin probar). Los tutoriales y la referencia de herramientas hablan de «el asistente» e indican que se probaron con Claude Code y Cubase.
- **Documentación en inglés**, con traducción al castellano de cada documento en un archivo hermano `*.es.md`. Nombres de archivos y carpetas en inglés (`docs/tutorials`, `docs/reference`, `docs/manual/01-installation.md`…). `tests/unit/test_docs.py` comprueba que cada documento tiene su traducción y que los enlaces y anclas no cambian de idioma.
- **Instalación guiada** (TW-1301): `trackwright setup` instala el script de Cubase, crea la configuración si no existe (escrituras y guardado desactivados por defecto) y registra el servidor en Claude Code. Cada paso se muestra y se confirma; `--yes PASO` para no preguntar. Termina con `doctor`.
- `doctor` muestra también `[writes] save` y, con `autostart`, explica que el puente arranca con el servidor MCP.
- **Transporte MIDI con CoreMIDI vía `ctypes`** (TW-1302), por defecto en macOS:
  - el paquete es Python puro y no necesita compilar nada (ni Xcode);
  - `mido` y `python-rtmidi` quedan comentados en `pyproject.toml`; el transporte basado en ellos se conserva y se elige con `[bridge] backend = "rtmidi"`.

## 0.2.0 — 2026-11-13

Épica E12 cerrada (TW-1201 a TW-1212): 32 herramientas, script Cubase 1.5.5.

- **Presets de plugins** (TW-1205):
  - herramienta `cubase_plugin_preset` (siguiente o anterior), verificada por el cambio de parámetros; pide un clic en la ventana del plugin la primera vez;
  - **script 1.5.5**, con `Preset / Next` y `Previous`.
- **Ajustes del proyecto** (TW-1210):
  - herramienta `cubase_set_project`: ciclo, metrónomo, precuenta, punch, uso del pre-roll y post-roll, clic al reproducir y al grabar, y nivel del clic, con relectura;
  - `cubase_get_project` da el nivel del clic como 0–127.
- **Importar audio** (TW-1203):
  - herramienta `cubase_import_audio` en dos fases: pista, posición y selector de Cubase; después, la confirmación por sondeo de bordes y la copia en el proyecto;
  - **script 1.5.4**, con `File / Import Audio File`.
- **Guardar el proyecto** (TW-1202):
  - herramienta `cubase_save_project` (`save` o `new_version`), con permiso propio `[writes] save`, desactivado por defecto, y verificación por la fecha de los `.cpr`;
  - **script 1.5.3**, con `File / Save` y `Save New Version`.
- **Exportar la mezcla** (TW-1204):
  - herramienta `cubase_export_mix` en dos fases: el rango (o todo el audio) y el diálogo de Cubase; después, la confirmación del archivo y de su duración;
  - **script 1.5.2**, con `File / Export Audio Mixdown`.
- **Borrado en una sola pista** (TW-1212): `cubase_edit_range` con `track` y `action: "delete"`. Corta, borra los trozos uno a uno, verifica e informa de los pasos de deshacer.
- **Edición por rangos en segundos** (TW-1211):
  - herramienta `cubase_edit_range` (`delete`, `delete_time`, `cut_time`, `insert_silence`, `crop`), con verificación por sondeo de los bordes de los eventos;
  - **script 1.5.1**, con 14 comandos de edición, herramienta y sondeo.
- **`cubase_set_position` en segundos:** verifica con la pantalla de segundos de Cubase y coloca los localizadores mediante el cursor. **Corrige** los localizadores en segundos, que antes quedaban en otra posición.
- **Propiedades del proyecto** (TW-1209):
  - herramienta `cubase_get_project`: compás, ciclo, punch, pre-roll y post-roll, metrónomo, precuenta, estado del transporte, modos de grabación y carpeta del proyecto;
  - `cubase_record_automation` usa el compás del proyecto en lugar de suponer 4/4.
- **Arranque automático** (TW-1201):
  - `trackwright serve` arranca el puente si no está en marcha (`[bridge] autostart`, activado por defecto), sin duplicarlo;
  - herramienta `cubase_launch`, que abre Cubase (opcionalmente con un proyecto) y espera al script;
  - sección de configuración `[cubase]`.
- **Unidades reales en la automatización** (TW-1208):
  - los puntos de `cubase_record_automation` aceptan `plain` (dB, Hz…), que Cubase convierte con exactitud;
  - herramienta nueva `cubase_convert_value`, de solo lectura;
  - `cubase_list_automation_targets` indica si cada parámetro admite unidades reales (`converts_units`).
- **Automatización** (TW-1207):
  - herramientas `cubase_list_automation_targets` y `cubase_record_automation`: graban curvas de volumen, panorama, envíos, EQ del canal, pre-filtro y parámetros de plugins de inserción, reproduciendo el proyecto, con verificación opcional;
  - **script 1.4.0**, con 45 controles de automatización activos en la superficie y las operaciones `auto.control` y `auto.list`;
  - el simulador reproduce y graba automatización.
- **Script 1.2.2:** comandos `Transport / Start` y `Stop` (`transport.start`, `transport.stop`), para reproducir sin intervención del usuario. Nunca graba.
- **Script 1.2.1:** fader de automatización experimental (TW-1206, variante B2), **desactivado** (`AUTOMATION_FADER_ENABLED = false`), y la operación `auto.fader`, que responde `UNSUPPORTED` mientras esté desactivado. La versión de prueba se genera con `experiments/tw1206/build.py`.
- **Script 1.2.0:** comandos de automatización (modos Touch, Auto-Latch y Cross-Over, siguiente modo y escritura en las pistas seleccionadas) para el experimento TW-1206. Clase `unknown` hasta observarlos.
- **Script 1.1.0:** panel de estado en la superficie MIDI Remote (TW-1101): título con la versión, pista seleccionada y lámpara de actividad. Solo usa mecanismos verificados en Cubase 15. Las operaciones no cambian.
- **Experimento TW-1101** (`experiments/tw1101/README.md`): protocolo y resultados, en `docs/verification.es.md`.
- **`trackwright script install --file <script>`:** instala otro script, como el del experimento.
- **Simulador:** «Locate Next Marker» sin marcador siguiente va al final del último evento, como en Cubase 15.

## 0.1.0 — 2026-11-12

Primera versión, basada en el diseño verificado en la prueba de concepto `cubase-mcp-poc`.

- **Servidor MCP `trackwright`** con 21 herramientas: 9 de lectura, 7 de escritura y navegación, y 5 basadas en comandos.
- **Script MIDI Remote** `Trackwright_Bridge.js` 1.0.0, con su instalador (`trackwright script install`).
- **Puente** con puertos virtuales CoreMIDI e IPC por socket Unix privado.
- **Seguridad:** solo lectura por defecto, ensayo (`dry_run`) en todas las escrituras, verificación por relectura, sin reintentos y referencias opacas validadas.
- **Simulador** `FakeCubase` y modo `trackwright serve --simulate`.
- **Diagnóstico** `trackwright doctor`.
- **Pruebas:** unitarias, de contrato MCP, del script con Node.js, de extremo a extremo y de integración opcionales contra Cubase.
- **Documentación:** manuales, tutoriales, arquitectura, desarrollo e issues.
- **Endurecimiento** tras una revisión independiente (épica E10):
  - sesión fijada durante cada herramienta;
  - borrado solo con selección única;
  - paginación del filtro de parámetros sin pérdidas;
  - plazo único con `BUSY` en el puente;
  - `INTERNAL_ERROR` con resultado desconocido;
  - cambios ya aplicados en los errores parciales;
  - `expectTitle` comprobado en el script.
