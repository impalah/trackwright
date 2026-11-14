# E14 — Corrección de la calidad

[English](E14-quality-remediation.md) · **Español**

**Estado de la épica: pendiente.** Origen: la revisión de calidad del código del 2026-11-14, con cada hallazgo, su evidencia y su ubicación en [`docs/quality-review.es.md`](../quality-review.es.md). Los IDs de hallazgo (C-xx, I-xx, S-xx, F-xx, T-xx, R-xx) remiten a ese documento.

**Orden:** cuatro fases, por riesgo. La fase 1 corrige las formas en que una escritura puede saltarse la configuración del usuario o una herramienta puede informar de algo que no ocurrió; debería publicarse antes que las funciones nuevas. Las fases 1 y 2 juntas forman la versión **0.4.0**: algunos cambios alteran los esquemas de las herramientas (C-04) y Trackwright sigue en alfa.

**Reglas para toda la épica:**
- Cada corrección empieza con un test que falla antes de la corrección (la mayoría de los hallazgos traen un caso de prueba listo).
- Los cambios en el script de Cubase suben `SCRIPT_VERSION` y necesitan el permiso del usuario para instalarlo (destino, contenido y archivo reemplazado), un reinicio de Cubase y verificación en Cubase, anotada en el registro de verificación.
- Documentación en inglés y en español, actualizada a la vez.

## Fase 1 — Seguridad y resultados veraces

### TW-1401 Cerrar los agujeros de la política de escritura

- **Estado:** hecha (2026-11-14); tests en `tests/unit/test_write_policy_tw1401.py`; verificada en Cubase (ver verification.es.md)
- **Decisiones:**
  - `cubase_run_command` rechaza `file.save`, `file.save_new_version` y `project.remove_selected_tracks` con `USE_DEDICATED_TOOL`, incluso con permiso: las herramientas específicas comprueban y verifican más.
  - Nuevo `WritePolicy.check_all_tracks()`: todo lo que puede cambiar cualquier pista (los comandos de Cubase, que actúan sobre la selección de la ventana, y las ediciones de rango y cortes en todas las pistas) se rechaza con `NOT_ALLOWED` mientras `allowed_tracks` tenga pistas.
  - Los localizadores del ciclo necesitan las escrituras activadas; `cubase_set_position` mantiene `dry_run=false` por defecto, como las demás herramientas de navegación (excepción documentada).
  - La protección del enrutado dentro del script de Cubase pasa a TW-1406 (script 1.6.0), para agrupar los cambios del script; la de Python ya cubre todos los caminos MCP.
  - `edit.select_none` antes de *Select in Loop*: comprobado en Cubase con una edición de rango en el proyecto de pruebas, deshecha después (2026-11-14).
- **Hallazgos:** C-01, C-02, C-03, C-08, C-10, C-09.
- **Alcance:**
  1. `run_command`: política por clave. `file.save` y `file.save_new_version` → `check_save()`. Las claves que tienen una herramienta propia con guarda (eliminación de pistas, ediciones de rango) se rechazan, o solo se permiten cuando `allowed_tracks` está vacío; documentar cuál de las dos.
  2. `edit_range` con `track=` → `check_track`; `edit_range` sobre todas las pistas y `split_at_locators` se rechazan con `NOT_ALLOWED` cuando `allowed_tracks` está definido.
  3. `set_parameter` sobre el destino `channel`: rechazar los tags de enrutado de entrada/salida, nombre y selección (`READ_ONLY_PARAM`). La misma guarda en el script.
  4. `set_position` con localizadores del ciclo: `check_project_write()` y un ensayo, o una excepción documentada (decisión anotada en esta issue).
  5. `remove_selected_tracks`: `CANNOT_PERFORM` cuando Cubase dice que no puede.
  6. Ediciones de rango sobre todas las pistas: `edit.select_none` antes de *Select in Loop* (verificar en Cubase que no cambia el resultado).
- **Tests:** los casos de política enumerados en la revisión («Tests de política que faltan»), incluido un test de contrato de que toda herramienta que modifica el proyecto tiene `dry_run=true` por defecto.
- **Verificación en Cubase:** `file.save` rechazado con `save = false`; una edición de rango de una pista rechazada fuera de `allowed_tracks`; tags de enrutado rechazados.

### TW-1402 Las escrituras llegan siempre al objeto y a la sesión que vio quien llama

- **Estado:** hecha (2026-11-14); tests en `tests/unit/test_session_pinning_tw1402.py`; verificada en Cubase (ver verification.es.md). La petición IPC tiene un campo opcional `session`, que solo se conserva en las escrituras; un puente anterior lo ignora, así que hay que reiniciar el puente tras actualizar. Margen mínimo: 0,25 s (`MIN_WRITE_BUDGET`)
- **Hallazgos:** I-02, C-04, I-03.
- **Alcance:**
  1. La petición IPC de una escritura lleva el id de sesión fijado; el puente lo reenvía tal cual (sin `hello` implícito ni sustitución), así que la comprobación `STALE_SESSION` del script rechaza una escritura tras una recarga.
  2. `track` pasa a ser obligatorio en `cubase_set_parameter` y `cubase_insert_plugin`; los ensayos devuelven el selector `uid:` y las instrucciones del servidor le dicen al cliente que lo reutilice. **Cambio de esquema.**
  3. Las escrituras necesitan un presupuesto mínimo de tiempo restante; por debajo, `BUSY` sin enviar.
- **Tests:** las sondas H1–H3 de la revisión convertidas en tests unitarios; un test de que una escritura nunca lleva un id de sesión distinto del fijado.

### TW-1403 Resultados que dicen solo lo que ocurrió

- **Estado:** hecha en el código (2026-11-14), con tests junto a los de cada herramienta (`test_service_import`, `_saving`, `_automation`, `_settings`, `_ranges`, `_writing`, `_reading`, contrato). Sin comprobar en directo: importar, guardar sin carpeta conocida y una grabación interrumpida necesitan un diálogo o reproducción; los tests unitarios los cubren con el simulador. Aquí también se hizo C-27 (el rango de exportación se convierte una sola vez), y las tres funciones de carpeta de proyecto pasaron a ser `ServiceBase.project_folder()`.
- **Hallazgos:** C-05, C-06, C-07, C-11, C-12, C-13, C-14, C-15, C-16, C-17.
- **Alcance:**
  1. `import_audio`: sondear los bordes antes de abrir el diálogo; exigir bordes nuevos, cada uno emparejado una sola vez.
  2. `save_project` sin carpeta conocida: `status: "fired"` y `verified: null`.
  3. `record_automation`: `complete: false` (o `NOT_RECORDED`) cuando el transporte se paró antes de tiempo.
  4. `_write` (relectura tras un timeout, lista `applied`) movido a `ServiceBase` y usado por `set_project`.
  5. Ensayos: restaurar el cursor en `finally`; documentar los efectos secundarios sobre el cursor y la selección.
  6. Varios proyectos abiertos: `verified: null` y una nota en lugar de usar la primera carpeta.
  7. `select_track(step)`: verificado solo si la selección se movió.
  8. Excepciones inesperadas convertidas en `INTERNAL_ERROR`; proteger los accesos por índice encontrados en C-15.
  9. Los eventos sin id no se informan como no válidos.
  10. Descripciones de herramientas y modelos: quitar «suponen 4/4».

### TW-1404 Integración continua

- **Estado:** hecha en el repositorio (2026-11-14): `.github/workflows/ci.yml` y `fail_under = 95`; falta la primera ejecución en GitHub (necesita un push).
- **Hallazgos:** R-01, R-03.
- **Alcance:** GitHub Actions en `macos-latest` con `astral-sh/setup-uv`: `make check`, `make test-node`, `make build` y `make dist-check`; `fail_under = 95`. Opcional, a decisión del usuario: publicación de confianza (trusted publishing) en PyPI desde las etiquetas.

## Fase 2 — Robustez

### TW-1405 Robustez del puente y del IPC

- **Estado:** hecha en el código (2026-11-14), con tests en `tests/unit/test_robustness_tw1405.py` y `test_protocol.py`. I-13 (carpeta de exportación resuelta) se hizo en TW-1403, y `afinfo` recibe ahora una ruta resuelta. La longitud de la ruta del socket la comprueba el puente, no la configuración (los comandos que no usan el socket deben seguir funcionando)
- **Hallazgos:** I-01, I-04, I-05, I-06, I-07, I-08, I-09, I-10, I-11, I-12, I-13, I-15, I-18, I-19.
- **Alcance:** desvincular solo un socket que haya creado esta instancia, y abrir MIDI después de la comprobación de vida; cola de escucha de 128 y tratamiento de «ocupado» en el arranque automático; timeout de lectura en el servidor; límites en `SysExAssembler`; un reensamblador que descarta solo la trama suelta y expulsa el ensamblado más antiguo; todo `OSError` convertido en `BridgeUnavailableError` (con `sent` desconocido) y validación de la longitud de la ruta del socket; timeouts en los subprocesos; contador de respuestas duplicadas; sin enlaces simbólicos en el directorio del socket; instalación atómica del script; carpeta de exportación resuelta; registros de error más cortos; `except OSError:`; `choices` para `--log-level`.
- **Tests:** las sondas P2–P5 y F2–F3 de la revisión como tests unitarios.

### TW-1406 Robustez del script de Cubase (script 1.6.0)

- **Estado:** hecha en el código (2026-11-14): script 1.6.0, tests con Node en `tests/script/test_script_node.py`; instalado en el Cubase del usuario (con permiso) y a la espera de reiniciar Cubase para verificarlo. Decisión: sin protección del enrutado dentro del script: el parámetro 4101 del slot («Edición») lo escribe legítimamente `cubase_plugin_preset`, así que el script no puede rechazar un número de tag sin conocer el tipo de objeto; la protección de Python (TW-1401) cubre todos los caminos MCP y el puente solo acepta peticiones del propio Trackwright. Referencia antes de instalar: mediana de `da.param.set` de 112 ms (script 1.5.5, n=20)
- **Hallazgos:** S-01, S-02, S-03, S-05, S-06, S-07, S-08, S-09, F-03.
- **Alcance:** eliminar el recorrido de la guarda y `expectChannelTitle`; indicador de activo por ámbito; límite de tags en `da.channels`; responder `NOT_ACTIVE` a las peticiones en cola al desactivarse; `try/catch` en `mOnIdle`; búsquedas con `hasOwnProperty`; caducidad de los ensamblados en ~50 ticks; una sola función auxiliar para el sobre de error.
- **Verificación en Cubase:** instalar con permiso, reiniciar Cubase, `doctor`, los tests de integración en vivo y una comparación de la latencia de escritura antes y después de S-01.

### TW-1407 Comprobar la versión del script en ejecución

- **Estado:** hecha (2026-11-14): comprobación «script loaded in Cubase» en `doctor` y `script_outdated` / `packaged_script_version` en `cubase_status` (null en el simulador); tests en `test_cli_serve_doctor.py` y `test_service_reading.py`; `doctor` comprobado contra Cubase (script 1.5.5 = el del paquete)
- **Hallazgos:** S-04.
- **Alcance:** `doctor` compara la versión del script que ejecuta Cubase con la empaquetada; `cubase_status` informa `script_outdated`; la pista dice que hay que reiniciar Cubase.

## Fase 3 — Tests

### TW-1408 Conformidad entre el simulador y el script

- **Estado:** pendiente
- **Hallazgos:** F-01, F-02, F-04, F-06, S-11.
- **Alcance:** un test parametrizado que envía las mismas operaciones al arnés de node (script real) y a `FakeCubase` y compara claves, recortes de valores y códigos de error; una decisión sobre los tags que faltan, verificada en Cubase; tests de que coinciden las listas de claves de automatización y de plugins; toda operación de `ALL_OPS` tiene un manejador en el simulador; un gancho público `override(op, fn)`; constantes del script con nombre comprobadas por un test.

### TW-1409 Endurecimiento de la suite de tests

- **Estado:** pendiente
- **Hallazgos:** T-01, T-02, T-03, T-04, T-05, T-06, T-08, T-09, T-10, S-12, S-13.
- **Alcance:** comprobar los códigos de error; tests de huella y de `from_config`; idas y vueltas del protocolo con distintos números de secuencia y en el límite de fragmento, más fuzzing basado en propiedades del entramado; tests parametrizados reentrantes; eventos en lugar de `sleep`; timeouts en el arnés de node; fixtures compartidas; la fixture de escritura en vivo limitada a la pista de pruebas; número exacto de comandos; `tests` bajo mypy; una comprobación ES5 del script; tests de node para las operaciones del script sin probar y cobertura JS en `make test-node`.

### TW-1410 Pruebas de mutación

- **Estado:** pendiente
- **Plan:** sección «Plan de pruebas de mutación» de la revisión.
- **Alcance:** configuración `[tool.mutmut]` y un objetivo `make mutation` (`uv run --with mutmut==3.8.1`); objetivos en el orden del plan; eliminar o registrar como equivalente cada mutante superviviente de los módulos de seguridad; meta ≥ 85 % eliminados en ellos, excluidos los mutantes que solo cambian textos; ejecutarlo antes de cada versión y anotar la puntuación en el registro de verificación.
- **Depende de:** TW-1409 (T-03 rompe la línea base).

### TW-1411 Más tests de integración en vivo

- **Estado:** pendiente
- **Alcance:** tests en vivo opcionales, reversibles y limitados a la pista de pruebas, para las herramientas de lectura que no tienen ninguno (`get_selected_channel`, `list_available_plugins`, `list_parameters`, `get_parameter`, `get_project`, `poll_changes`, `list_automation_targets`, `convert_value`) y, tras `TRACKWRIGHT_ALLOW_WRITES`, para las escrituras reversibles (`set_parameter`, `rename_track`, `select_track`, `set_tempo`, `set_project`, `markers`). Las herramientas con diálogos o audio siguen siendo manuales y se enumeran como tales.

## Fase 4 — Mantenibilidad y API

### TW-1412 Refactorización del núcleo

- **Estado:** pendiente
- **Hallazgos:** C-21, C-22, C-23, C-25, C-26, C-27, I-14, I-16, I-17.
- **Alcance:** función auxiliar `_paged()`; `core/timefmt.py`; funciones auxiliares de selección, carpeta y cursor en `ServiceBase`; `core/tags.py` con los tags de Cubase en espacios de nombres; eliminar o documentar el código sin usar; compás explícito; contadores del puente bajo un cerrojo; un pequeño módulo `ipc`; una sola función auxiliar para desempaquetar respuestas. Sin cambios de comportamiento: ni la suite ni la puntuación de mutación pueden bajar.

### TW-1413 Coherencia de la API MCP

- **Estado:** pendiente
- **Hallazgos:** C-18, C-19, C-20, C-24.
- **Alcance:** una sola forma de escribir anterior/siguiente, segundos o compases en todos los sitios donde se acepta una posición, un nombre en singular para la herramienta de eliminación de pistas, un solo vocabulario de estados, una única fuente de verdad para la numeración de slots, clases de excepción que correspondan a sus códigos, el formato de tiempo leído de Cubase. **Incompatible para los clientes:** publicar en una versión menor con una nota en el changelog.

### TW-1414 Dividir el simulador

- **Estado:** pendiente
- **Hallazgos:** F-05.
- **Alcance:** paquete `fake/` con la emulación del protocolo, el modelo de edición y los dobles de test; sin cambios de comportamiento.

### TW-1415 Higiene del repositorio

- **Estado:** pendiente
- **Hallazgos:** R-02, R-04, R-05, R-06.
- **Alcance:** pre-commit (ruff, ruff-format, mypy); Dependabot para uv y GitHub Actions; CONTRIBUTING y SECURITY (en inglés y en español) y plantillas de issue/PR; más reglas de ruff y opciones de pytest, poco a poco; límites superiores en las versiones mayores de las dependencias de ejecución; una decisión sobre pasar el linter a `experiments/`.
