# Revisión de calidad del código (2026-11-14)

[English](quality-review.md) · **Español**

Revisión de Trackwright 0.3.0 (commit `3d715e4`): organización del código, API MCP, malos olores del código, tests, documentación, un análisis adversarial de la infraestructura y un plan de pruebas de mutación. El plan de corrección es la épica [E14](issues/E14-quality-remediation.es.md).

## Método

- **Tres revisiones independientes de solo lectura** del código, cada una con un alcance definido:
  - servicio de dominio y API MCP (`core/`, `server.py`, `commands.py`, `errors.py`);
  - revisión adversarial de la infraestructura (`protocol`, `coremidi`, `transport`, `host`, `bridge`, `launcher`, `config`, `cli`, `installer`, `doctor`), con sondas;
  - script de Cubase, simulador, suite de tests, herramientas del repositorio y un piloto de pruebas de mutación.
- **Herramientas,** todas ejecutadas con `uv`/`uvx`, sin instalar nada en el proyecto:
  - radon (complejidad y mantenibilidad), vulture (código muerto), pylint `duplicate-code`, interrogate (docstrings);
  - pip-audit (vulnerabilidades conocidas en `uv.lock`), `uv tree --outdated`;
  - pytest con cobertura de ramas, cobertura V8 para el script, mutmut 3.8.1 (piloto).
- **Seguridad:** no se tocó el Cubase del usuario ni el puente en marcha. Las sondas usaron `TMPDIR`/`HOME` aislados, nombres de puerto distintos de los de producción y un clon del repositorio para las pruebas de mutación.
- **Evidencia:** cada hallazgo cita `archivo:línea` y está marcado como **confirmado** (leído en el código, reproducido o medido) o **sospechado** (plausible, no reproducido). El coordinador volvió a reproducir contra el simulador los tres hallazgos de política más graves.

## Resumen

Trackwright está en buena forma para una alfa: 98 % de cobertura de ramas, mypy estricto, un conjunto amplio de reglas de ruff, una suite rápida (~9 s), una fijación de sesión bien diseñada, ningún reintento automático de escrituras, un endurecimiento cuidadoso del IPC y documentación exigida por tests. Sin vulnerabilidades conocidas en sus dependencias.

La revisión encontró **tres agujeros de política que permiten que una escritura se salte la configuración del usuario**, un **hueco en la fijación de sesión** del puente y varios puntos en los que una herramienta puede **informar de un éxito sin pruebas**. Esto va primero en el plan. El resto es robustez del puente y del script, riesgo de divergencia entre el simulador y el script real, aserciones débiles encontradas con las pruebas de mutación, falta de CI y trabajo de mantenibilidad.

| Gravedad | Número | Ejemplos |
|---|---|---|
| Alta | 6 | `run_command` se salta `[writes] save`; las ediciones de rango ignoran `allowed_tracks`; el enrutado se puede escribir con `set_parameter`; las escrituras pueden llevar una sesión renegociada; nada comprueba el simulador y el script entre sí; sin CI |
| Media | 30 | `track="selected"` por defecto en herramientas de escritura; importación, guardado y automatización dados por hechos sin pruebas; un puente rechazado borra el socket del que está en marcha; la versión del script no se comprueba en ejecución; tests débiles |
| Baja | 40+ | duplicación, números mágicos, nombres, clases de error, pequeños huecos de robustez |

## Métricas

| Métrica | Valor | Comentario |
|---|---|---|
| Tamaño | `src/` ≈ 7 800 líneas de Python + 1 130 líneas de script ES5; tests ≈ 5 750 líneas | `fake.py` (1 112) y el script son los archivos más grandes |
| Tests | 458 superados, 6 saltados, ~9 s | los tests de integración son opcionales |
| Cobertura de ramas | 98,1 % (`fail_under = 85`) | solo `coremidi.py` por debajo del 95 % (94 %) |
| Cobertura del script (tests de node) | ≈ 85 % de las líneas | la suite normal no la mide |
| Complejidad ciclomática | media A (3,45); nada peor que C fuera del simulador | peores: `split_at_locators` C(18), `edit_range`, `set_track_mix`, `set_project` C(16); `FakeCubase._apply_transport_move` D(22) |
| Índice de mantenibilidad | A en todo salvo `fake.py` (C) | |
| Duplicación (pylint, ≥ 5 líneas) | 1 bloque | ruta de recepción de SysEx en `coremidi.py` y `transport.py` |
| Código muerto (vulture) | `ServiceBase.is_host_code`; ver también C-25 | el resto de avisos son campos de pydantic (falsos positivos) |
| Docstrings (interrogate) | 26,8 % | el comportamiento de las herramientas está documentado en sus descripciones y en el manual; prioridad baja |
| Vulnerabilidades (pip-audit) | ninguna en 33 paquetes fijados de ejecución y 17 de desarrollo | |
| Dependencias directas desactualizadas | ruff 0.17.4 → 0.17.5 | |
| Tests de integración en vivo | 6 de 32 herramientas | el resto se verifica a mano (registro de verificación) y contra el simulador |

**Compatibilidad de herramientas:** `bridge.py:95` usa la forma sin paréntesis `except A, B, C:` de Python 3.14 (PEP 758). Es válida, pero radon, vulture, pylint e interrogate no consiguen analizar el archivo, así que se excluyó de sus métricas. De todos modos, todas las excepciones de la lista son subclases de `OSError` (I-18).

## Hallazgos

IDs: **C** dominio y API, **I** infraestructura, **S** script de Cubase, **F** simulador, **T** tests, **R** repositorio y herramientas. Esfuerzo: S (horas), M (uno o dos días), L (más).

### 1. Política y seguridad de las escrituras

| ID | Grav. | Hallazgo | Ubicación | Estado | Corrección | Esfuerzo |
|---|---|---|---|---|---|---|
| C-01 | alta | `cubase_run_command` solo comprueba `check_project_write()`: `file.save`/`file.save_new_version` guardan con `[writes] save = false`; `project.remove_selected_tracks` se salta la guarda de selección y `allowed_tracks`; los comandos de rango se saltan `allowed_tracks` | `core/commanding.py:101-103` | confirmado, reproducido | política por clave: `file.*` → `check_save()`; rechazar las claves que tienen una herramienta propia con guarda, o exigir que `allowed_tracks` esté vacío | S |
| C-02 | alta | `edit_range` (también con `track=`) y `split_at_locators` ignoran `allowed_tracks` | `core/ranges.py:150`, `core/commanding.py:209` | confirmado, reproducido | `check_track` en las ediciones de una pista; rechazar las ediciones de todas las pistas cuando `allowed_tracks` está definido | S |
| C-03 | alta | `set_parameter` sobre el destino `channel` acepta los tags de enrutado de entrada/salida (4101/4102); el simulador registra que escribir el enrutado deja «Sin bus» | `core/writing.py:103-136`, script `:801-807` | confirmado, reproducido en el simulador | rechazar los tags de enrutado, nombre y selección con `READ_ONLY_PARAM`, en Python y en el script | S |
| I-02 | alta | una escritura fijada a la sesión S1 se puede enviar con la sesión S2: el `HostClient` del puente pone su propio id de sesión actual (y puede hacer antes un `hello`), así que la comprobación `STALE_SESSION` del script pasa y la escritura puede caer en otro objeto tras una recarga del script; el cliente solo se da cuenta después | `host.py:140, 205-226`; `core/base.py:124-133`; `bridge.py:60-73` | confirmado con sondas | enviar el id de sesión fijado en la petición IPC de las escrituras; el puente lo reenvía tal cual, sin `hello` implícito | M |
| C-08 | media | `set_position` cambia los localizadores del ciclo (guardados en el proyecto) sin comprobación de política y con `dry_run` false por defecto | `core/writing.py:312-374`, `server.py:230-235` | confirmado | tratar los localizadores como una escritura en el proyecto, o documentar la excepción | S |
| C-04 | media | `cubase_set_parameter` y `cubase_insert_plugin` usan `track="selected"` por defecto: la llamada que aplica puede caer en otra pista que la que mostró el ensayo | `server.py:182, 197` | confirmado | hacer `track` obligatorio en las herramientas de escritura; los ensayos devuelven el selector `uid:` | S |
| C-10 | media | `remove_selected_tracks` se lanza aunque Cubase informe de que no puede | `core/commanding.py:166-170` | confirmado | lanzar `CANNOT_PERFORM` | S |
| C-09 | media | la ruta de rango sobre todas las pistas no borra una selección previa antes de *Select in Loop*; una selección que quede podría hacer que `edit.delete` actúe sobre ella | `core/ranges.py:265-280` | sospechado | primero `edit.select_none` | S |
| I-03 | media | una escritura que obtiene el cerrojo (o termina el `hello`) justo en su plazo se envía igualmente con pocos ms restantes, así que acaba como `TIMEOUT outcome: unknown` aunque probablemente se ejecute | `host.py:127-134, 218-221` | confirmado con una sonda | presupuesto mínimo restante para las escrituras; por debajo, `BUSY` sin enviar | S |
| C-12 | baja | algunos ensayos envían operaciones de escritura (movimientos del cursor para convertir compases, selección de pista); `edit_range` no restaura el cursor si falla el análisis de `end` | `core/ranges.py:118-121`, `core/exporting.py:85-87`, `core/automation.py:200` | confirmado | `try/finally`; documentar los efectos secundarios | S |

### 2. Resultados veraces

| ID | Grav. | Hallazgo | Ubicación | Estado | Corrección | Esfuerzo |
|---|---|---|---|---|---|---|
| C-05 | media | la confirmación de `import_audio` puede informar `verified: true` de una importación cancelada cuando un evento existente ya tiene un borde en la posición de destino | `core/importing.py:106-113` | confirmado (lógica) | sondear los bordes antes de abrir el diálogo; exigir bordes nuevos, cada uno emparejado una sola vez | M |
| C-06 | media | `save_project` informa `status: "saved"` sin pruebas cuando la carpeta del proyecto es desconocida (un proyecto nunca guardado muestra *Guardar como*) | `core/saving.py:53-55` | confirmado | estado `fired`/`unverified` | S |
| C-07 | media | una grabación de automatización interrumpida (transporte parado) se devuelve como si estuviera completa | `core/automation.py:352-380` | confirmado | comparar con el final de la curva; `complete: false` o `NOT_RECORDED` | S |
| C-11 | media | a `set_project` le faltan la relectura tras un timeout y la lista `applied` de `set_track_mix` (`_write` está en `WritingMixin`) | `core/settings.py:64-68` | confirmado | mover `_write` a `ServiceBase` | S |
| C-13 | baja | guardar, exportar e importar usan `folders[0]` cuando hay varios proyectos abiertos | `core/saving.py:33-35`, `core/exporting.py:58-60`, `core/importing.py:125-127` | sospechado | `verified: null` y una nota cuando hay varias carpetas | S |
| C-14 | baja | `select_track(step=…)` informa de verificado cuando nada se movió | `core/writing.py:303-305` | confirmado | exigir también `after != before` | S |
| C-15 | baja | algunos `IndexError`/`KeyError` escapan como errores genéricos sin código | `core/automation.py:166, 185`, `core/writing.py:113` | confirmado | protegerlos; convertir las excepciones inesperadas en `INTERNAL_ERROR` en `server.run` | S |
| C-16 | baja | los eventos sin id de objeto se informan como `still_valid: false` | `core/reading.py:204-220` | sospechado | omitir la búsqueda | S |

### 3. Robustez del puente y del IPC (adversarial)

| ID | Grav. | Hallazgo | Ubicación | Estado | Corrección | Esfuerzo |
|---|---|---|---|---|---|---|
| I-01 | media | un segundo puente, rechazado porque ya escucha uno en marcha, borra el socket del puente en marcha en `finally: server.stop()`; los clientes ya no pueden llegar al puente en marcha. No ocurre con el backend CoreMIDI por defecto, donde la comprobación del nombre de puerto falla antes; sí con otros nombres de puerto, con rtmidi o por una carrera | `bridge.py:205-211, 314-322` | confirmado con una sonda | desvincular solo un socket que haya creado esta instancia; abrir MIDI después de la comprobación de vida | S |
| I-04 | media | cola de escucha de 5: una ráfaga de clientes concurrentes recibe `ECONNREFUSED` (16 de 40 en una sonda); con carga, `ensure()` puede concluir que el puente está muerto | `bridge.py:185` | confirmado (la parte del arranque automático, sospechada) | `request_queue_size = 128`; tratar «rechazado pero el archivo existe» como ocupado | S |
| I-07 | baja | una trama suelta con el mismo número de secuencia destruye un ensamblado legítimo; 16 secuencias basura llenan la tabla de pendientes durante 5 s | `protocol.py:152-160` | confirmado con fuzzing | descartar solo la trama nueva; expulsar el ensamblado más antiguo | S |
| I-06 | baja | `SysExAssembler` crece sin límite hasta `F7` | `coremidi.py:62-63` | confirmado (10 MB en búfer) | limitar al tamaño máximo de trama | S |
| I-08 | baja | escapan `OSError` en bruto (ruta del socket demasiado larga, conexión reiniciada, tubería rota): la CLI imprime una traza en lugar de JSON; no se valida la longitud de la ruta del socket | `bridge.py:241-263`, `cli.py:194-199`, `config.py` | confirmado | convertir en `BridgeUnavailableError` con `sent` desconocido; validar la longitud de la ruta (< 104) | S |
| I-05 | baja | sin timeout de lectura en el servidor: un cliente que nunca envía un salto de línea ocupa un hilo para siempre (solo el mismo usuario) | `bridge.py:152` | confirmado | timeout del socket en `setup()` | S |
| I-09 | baja | `open -a`/`pgrep` no tienen timeout; los timeouts de `lsof`/`afinfo` lanzan un `TimeoutExpired` en bruto | `launcher.py:45-51`, `exports.py:20-22` | sospechado | timeouts convertidos en errores de herramienta | S |
| I-10 | baja | una respuesta duplicada se cuenta como `unsolicited` | `host.py:93-104` | confirmado | contador `duplicates` aparte | S |

### 4. Seguridad

Ningún problema de impacto alto: el socket vive en un directorio 0700 con comprobación del propietario, se crea 0600 con umask 077, las peticiones están limitadas a 64 KiB, la lista de operaciones permitidas es exacta, los timeouts rechazan NaN/inf, los subprocesos usan binarios con ruta absoluta y sin shell, y `setup` nunca sobrescribe archivos existentes.

| ID | Grav. | Hallazgo | Ubicación | Estado | Corrección | Esfuerzo |
|---|---|---|---|---|---|---|
| I-11 | baja | `stat`/`chmod` sobre el directorio del socket siguen enlaces simbólicos; si `TMPDIR` no está definido, el directorio recae en el `/tmp` compartido, donde otro usuario podría crear antes un enlace simbólico (denegación de servicio, sin ganancia de privilegios) | `bridge.py:79-86`, `config.py:29` | confirmado con una sonda | `lstat` y rechazar enlaces simbólicos (u `O_NOFOLLOW`); considerar `~/Library/Caches` | S |
| I-12 | baja | instalación del script: carrera entre la comprobación del enlace simbólico y `copyfile` (time-of-check/time-of-use), y la copia no es atómica | `cubase/__init__.py:79-82` | sospechado | archivo temporal + `os.replace` | S |
| I-13 | baja | una carpeta de exportación relativa que empieza por `-` llega a `afinfo` como opción | `exports.py:38`, `core/exporting.py:121` | sospechado | resolver la ruta | S |
| I-15 | baja | los errores inesperados registran la petición completa (hasta 64 KiB, nombres de pista incluidos) | `bridge.py:133` | confirmado | registrar solo la operación y el tamaño | S |

### 5. Script de Cubase

| ID | Grav. | Hallazgo | Ubicación | Estado | Corrección | Esfuerzo |
|---|---|---|---|---|---|---|
| S-01 | media | cada escritura de parámetro recorre hasta 3 000 nodos del mezclador (dos llamadas de DirectAccess cada uno) solo para construir un `guard.path` que Python nunca lee | script `:712-736` | confirmado en el código; latencia sospechada | eliminar el recorrido | S |
| S-02 | media | la cola de inactividad comprueba `daActive` para los dos ámbitos: las peticiones del mezclador pueden ejecutarse en una instancia del mezclador inactiva, o rechazarse cuando solo falló la instancia de la selección | script `:1018-1025` | confirmado | comprobar el indicador de activo del ámbito de la petición | S |
| S-04 | media | nada compara la versión del script **en ejecución** con la empaquetada: tras actualizar sin reiniciar Cubase, `doctor` pasa y las operaciones nuevas fallan con `UNKNOWN_OP` | `doctor.py:51`, `core/reading.py:42` | confirmado | comprobación en `doctor` y `script_outdated` en `cubase_status` | S |
| S-03 | baja | `da.channels` acepta una lista de tags sin límite (el trabajo se hace antes de `RESPONSE_TOO_LARGE`) | script `:834, 850-855` | confirmado con el arnés | limitar a 16 tags | S |
| S-05 | baja | `mOnDeactivate` descarta las peticiones en cola sin responder: quien llama espera al timeout y las escrituras parecen «unknown» | script `:1080-1092` | confirmado | responder `NOT_ACTIVE` antes de vaciar | S |
| S-06 | baja | `mOnIdle` no tiene un `try/catch` de nivel superior | script `:1094-1108` | confirmado | envolverlo | S |
| S-07 | baja | las búsquedas de operaciones en objetos planos aceptan nombres heredados (`toString`); en producción las bloquea la lista de operaciones permitidas del puente | script `:501, 540, 548` | confirmado | `hasOwnProperty` | S |
| S-08 | baja | los ensamblados caducan tras 2 000 ticks de inactividad (~225 s) frente a 5 s en Python | script `:488-498` | confirmado | ~50 ticks | S |
| S-09 | baja | a algunos sobres de error les faltan `op`/`via`; las respuestas a JSON incorrecto llevan un `rid` vacío | script `:373-379, 509, 513` | confirmado | una sola función auxiliar para el sobre | S |
| S-10 | baja | bloques duplicados y un `da` global mutable que se cambia en cada petición | script, varios | confirmado | extraer funciones auxiliares; pasar `da` explícitamente | M |
| S-11 | baja | los límites de paginación y la lista de tags por defecto son literales, copiados en `fake.py` y `core/base.py` | script, varios | confirmado | constantes con nombre comprobadas por un test | S |
| S-12 | baja | nada comprueba ES5: Node acepta ES6 que Cubase rechazaría | `tests/script` | confirmado | test de análisis ES5 (`vm.Script` + tokens prohibidos, o acorn) | S |
| S-13 | media | los tests de node cubren ≈ 85 % del script; sin probar: `da.params`, `da.param.get`, `da.convert`, `pm.collections`, errores de protocolo, rechazo y caducidad de tramas, `mOnDeactivate`, precondiciones del bloqueo de edición, peticiones de varios fragmentos | `tests/script` | confirmado (cobertura V8) | tests de node por elemento; cobertura JS en `make test-node` | M |

### 6. Simulador

| ID | Grav. | Hallazgo | Ubicación | Estado | Corrección | Esfuerzo |
|---|---|---|---|---|---|---|
| F-01 | alta | nada comprueba que `FakeCubase` y el script devuelvan las mismas formas; una sonda encontró diferencias en `status`, `capabilities`, `da.param.set`, `da.children` con `limit=0` y tags que faltan en `da.channels` | `fake.py`, `tests/script` | confirmado | test de conformidad: las mismas operaciones contra el arnés de node y el simulador, comparando claves, recortes de valores y códigos de error | M |
| F-02 | media | los tags de canal que faltan son `None` en el simulador y diccionarios centinela en el script, así que `track_info` difiere | `fake.py:575-583`, `core/base.py:189-199` | confirmado frente al arnés; sospechado frente a Cubase | verificar en Cubase; tratar `process == -1` como ausente | S |
| F-03 | media | `expectChannelTitle` significa cosas distintas en el simulador y en el script (y nada en `src` lo usa) | `fake.py:426-432`, script `:712-719` | confirmado | quitarlo de los dos (junto con S-01) | S |
| F-04 | media | tres copias de la lista de claves de control de automatización (solo se prueba la del script); lista de plugins copiada en el arnés de node; nada exige que cada operación tenga un manejador en el simulador | `fake.py:705-716`, script `:158-187` | confirmado | tests que comparen las listas; test `ALL_OPS` ↔ `_op_*` | S |
| F-05 | baja | una sola clase de ~980 líneas mezcla la emulación del protocolo, un modelo de edición y utilidades de test | `fake.py:79-1060` | confirmado | paquete `fake/` (`ops`, `model`, `doubles`) | M |
| F-06 | baja | los tests parchean métodos privados `fake._op_*` | varios tests | confirmado | gancho público `override(op, fn)` | S |

### 7. Tests

| ID | Grav. | Hallazgo | Ubicación | Estado | Corrección | Esfuerzo |
|---|---|---|---|---|---|---|
| T-01 | media | la suite no detecta: que `WritePolicy.from_config` pierda `save`; que se quite `code="NOT_ALLOWED"`; `check_fingerprint` `or` → `and`. Algunos tests usan `pytest.raises(PolicyError)` sin más | tests de `core/policy.py`, `core/refs.py` | confirmado (mutantes aplicados a mano) | comprobar los códigos de error; tests de huella con un solo campo; ida y vuelta de `from_config` | S |
| T-02 | media | las idas y vueltas del protocolo no cubren números de secuencia > 127 ni 0, ni el límite de fragmento de 15 360 bytes | tests de `protocol.py:49, 68, 109` | confirmado (sobrevivieron mutantes) | parametrizar seq {0, 127, 128, 16383} y tamaños {15360, 15361}; fuzzing basado en propiedades | S |
| T-03 | media | un test parametrizado comparte sockets simulados mutables, así que falla si se ejecuta dos veces en el mismo proceso (rompió la línea base de mutmut) | `tests/unit/test_bridge.py:226-238` | confirmado | construir los dobles dentro del test | S |
| T-07 | media | la edición de rangos, la exportación/importación, los presets y la automatización solo se prueban contra el modelo de Cubase del propio simulador; el comportamiento real solo está en el registro de verificación | `tests/unit/test_service_*` | confirmado | marcarlos como modelados por el simulador y enlazar cada regla con su experimento; más tests en vivo (TW-1411) | S |
| T-04 | baja | sincronización basada en tiempos (`sleep`) en los tests del host | `tests/unit/test_host.py:122, 187, 222` | sospechado inestable en CI | eventos o sondeo | S |
| T-05 | baja | el arnés de node lee sin timeout; no hay `pytest-timeout` | `tests/script/test_script_node.py:50` | confirmado | timeout | S |
| T-06 | baja | fixtures declaradas de nuevo en varios sitios; un módulo de test importa de otro | `tests/contract`, `tests/script` | confirmado | `conftest.py` compartido | S |
| T-08 | baja | la fixture de escritura en vivo permite todas las pistas | `tests/integration/test_live_cubase.py:43` | confirmado | `allowed_tracks=(TEST_TRACK,)` | S |
| T-09 | baja | `commandsBound >= 30` cuando hay 57 asignados | `tests/script/test_script_node.py` | confirmado | `== len(COMMANDS)` | S |
| T-10 | baja | los tests no pasan la comprobación de tipos | `pyproject.toml` | confirmado | añadir `tests` a mypy | S |

**Tests de política que faltan** (de la revisión del dominio): rechazos por `allowed_tracks` en `set_track_mix`, `rename_track`, `insert_plugin`, `plugin_preset`, `record_automation` e `import_audio`; `WRITES_DISABLED` en `rename_track`, `insert_plugin` y `split_at_locators`; la guarda de selección de `remove_selected_tracks` con una sola condición que no coincide; `edit_range` con límites iguales; fallos parciales en `set_track_mix` y `set_project`; un test de contrato que compruebe que toda herramienta que modifica el proyecto tiene `dry_run=true` por defecto.

**Cobertura de integración en vivo:** 6 de 32 herramientas (`status`, `list_tracks`, `list_inserts`, `get_transport`, `set_track_mix`, `set_position`). Las otras 26 se verificaron a mano (registro de verificación), pero no tienen un test en vivo repetible.

### 8. Diseño de la API MCP

| ID | Grav. | Hallazgo | Ubicación | Estado | Corrección | Esfuerzo |
|---|---|---|---|---|---|---|
| C-17 | media | las descripciones de herramientas y modelos siguen diciendo «las posiciones suponen 4/4», pero el código lee el compás | `server.py:460`, `core/models.py:236` | confirmado | corregir los textos que lee el modelo cliente | S |
| C-18 | baja | misma idea, distinta forma: `step: "prev"` frente a `direction: "previous"`; `split_at_locators` solo admite compases mientras otras herramientas aceptan segundos o compases; `remove_selected_tracks` está en plural pero elimina una pista; varios vocabularios de estado (`fired`, `done`, `saved`) | `server.py`, modelos | confirmado | alinear en una versión menor (incompatible para los clientes) | M |
| C-19 | baja | numeración de slots: las descripciones dicen 8 slots, los esquemas permiten 16, las claves de automatización aceptan 1–8 | `server.py:124-131, 195, 327` | confirmado | una única fuente de verdad | S |
| C-20 | baja | las clases de excepción no corresponden a sus códigos (`PreconditionFailedError` con `VERIFY_FAILED` o `NOT_FOUND`; `VerificationFailedError` sin usar) | `core/commanding.py:223`, `core/importing.py:44`, `core/project.py:85` | confirmado | usar la clase correspondiente | S |
| C-24 | baja | `"Compases+Tiempos"` (interfaz de Cubase en español) fijo en el código como formato de tiempo | `core/writing.py:358` | confirmado | leerlo de `transport.get` | S |

### 9. Malos olores y organización del código

| ID | Grav. | Hallazgo | Ubicación | Corrección | Esfuerzo |
|---|---|---|---|---|---|
| C-21 | media | el mismo bucle de paginación offset/limit escrito 5 veces | `core/base.py:247-253`, `core/project.py:87-110`, `core/presets.py:27-38`, `core/automation.py:148-157` | una función auxiliar `_paged()` | S |
| C-22 | media | funciones auxiliares de selección de pista, carpeta del proyecto y cursor copiadas entre mixins; las de compases están en `writing.py` pero las usan mixins que no heredan de él | `core/automation.py:93`, `core/ranges.py:70`, `core/writing.py:307`, … | `core/timefmt.py`; funciones auxiliares en `ServiceBase` | S |
| C-23 | baja | constantes de tags de Cubase dispersas y que colisionan (4101 significa entrada, visualización en segundos y editor de plugin) | `core/base.py:55-65`, `core/project.py:21`, `core/presets.py:20` | `core/tags.py` con espacios de nombres | S |
| C-25 | baja | código sin usar: `ObjectRef.decode`/`check_session`/`check_fingerprint` (solo en tests; el docstring dice que las herramientas los usan), `is_host_code`, `VerificationFailedError` | `core/refs.py:62-88`, `core/base.py:311`, `errors.py:106` | borrar o documentar como reservado | S |
| C-26 | baja | el compás viaja en estado local del hilo | `core/automation.py:131, 260` | pasarlo explícitamente | S |
| C-27 | baja | `_seconds_of` se ejecuta dos veces en la ruta de aplicación de la exportación (movimientos de cursor de más) | `core/exporting.py:86, 104-106` | calcularlo una vez | S |
| I-14 | baja | contadores del puente actualizados desde varios hilos sin cerrojo | `bridge.py:107-132` | cerrojo | S |
| I-16 | baja | `launcher.py` importa una función auxiliar privada de `bridge.py`; `JsonObject` se redefine en ~6 módulos | `launcher.py:22` | un pequeño módulo `ipc`/`types` | S |
| I-17 | baja | desempaquetado de respuestas duplicado | `hostport.py:70-74`, `bridge.py:277-281` | función auxiliar compartida | S |
| I-18 | baja | `except ConnectionRefusedError, FileNotFoundError, TimeoutError, OSError:` redundante (forma de PEP 758 que rompe radon/vulture/pylint/interrogate) | `bridge.py:95` | `except OSError:` | S |
| I-19 | baja | un `--log-level` no válido lanza un `ValueError` en bruto | `cli.py:192` | `choices` de argparse | S |

**Propuestas de organización** (sin cambio de arquitectura; YAGNI sobre varios DAW sigue vigente): `core/tags.py` y `core/timefmt.py`; un pequeño `ipc.py` para las funciones auxiliares del directorio del socket y de la comprobación de vida; un paquete `fake/`; fixtures de test compartidas en `conftest.py`. La organización actual en mixins es sólida: no hay dos mixins que definan un método con el mismo nombre.

### 10. Repositorio y herramientas

| ID | Grav. | Hallazgo | Corrección | Esfuerzo |
|---|---|---|---|---|
| R-01 | alta | el repositorio público de GitHub **no tiene CI**: todas las comprobaciones se ejecutan solo en el Mac del autor | GitHub Actions en `macos-latest` con `astral-sh/setup-uv`: `make check`, tests de node, build y `twine check` | S |
| R-02 | media | sin pre-commit, sin política de actualización de dependencias (Dependabot/Renovate), sin CONTRIBUTING, SECURITY ni plantillas de issue/PR | añadirlos (bilingües cuando son documentos) | S |
| R-03 | baja | `fail_under = 85` con una cobertura del 98 % | subirlo a 95 | S |
| R-04 | baja | a ruff le faltan `PT`, `PERF`, `FURB`, `ERA`, `TRY`, `ASYNC`; a pytest le faltan `xfail_strict`, `filterwarnings = error` y un timeout | añadirlos poco a poco | S |
| R-05 | baja | las dependencias de ejecución solo tienen límites inferiores; los usuarios de PyPI no reciben `uv.lock` | límites superiores en las versiones mayores (`mcp>=2.3,<3`) | S |
| R-06 | baja | `experiments/` no pasa el linter (un `__pycache__` obsoleto) | aceptarlo como desechable, o un lint relajado | S |

## Plan de pruebas de mutación

**Piloto** (clon del repositorio, mutmut 3.8.1 con `uv run --with`, nada añadido al proyecto): `protocol.py`, `core/policy.py` y `core/refs.py`, 416 mutantes en 27 s con 4 procesos, **70 % eliminados**. Unos 74 de los 124 supervivientes solo cambian textos de mensajes. Los supervivientes significativos dieron lugar a T-01 y T-02, y se volvieron a comprobar contra la suite completa.

**Herramienta:** mutmut 3 (funciona con Python 3.14 y uv, es rápido y no añade dependencias). cosmic-ray también funciona, pero es más lento de preparar. Para el script JavaScript, StrykerJS necesitaría npm, una cadena de herramientas que el proyecto hoy no usa: es una decisión del usuario, fuera de este plan.

**Cómo ejecutarlo:**

```sh
uv run --with mutmut==3.8.1 mutmut run --max-children 4
uv run --with mutmut==3.8.1 mutmut results
```

Configuración en `[tool.mutmut]` de `pyproject.toml` (solo configuración, sin dependencias): `source_paths` con los objetivos, un `pytest_add_cli_args_test_selection` acotado y `also_copy` con `docs/`, los archivos README y CHANGELOG, `CLAUDE.md` y `LICENSE` (los tests de documentación los leen). Un objetivo `make mutation` lo envuelve.

**Problemas encontrados:** T-03 rompió la línea base limpia y, con toda la selección de `tests/unit`, mutmut falló en sus procesos hijos (sospecha: tests que arrancan subprocesos, sockets o puertos CoreMIDI). Hay que acotar la selección por objetivo.

**Objetivos, por orden:** `protocol.py`, `core/policy.py`, `core/refs.py`, `ops.py`, `host.py`; después `core/writing.py`, `core/base.py`, `core/ranges.py`, `core/automation.py`; después `bridge.py`. **Excluidos:** `fake.py` (un doble de test), `coremidi.py` y `transport.py` (ctypes/rtmidi), `cli.py`, `launcher.py`, `installer.py`, `logs.py`, `server.py` (declarativo) y `__main__.py`.

**Frecuencia y metas:** bajo demanda y antes de cada versión, no en cada push (estimación de 5–15 min para todo el conjunto de objetivos; extrapolada, no medida). Meta: al menos un 85 % de mutantes eliminados en los módulos de seguridad (`policy`, `refs`, `protocol`, `host`, las rutas de escritura de `core/`), una vez excluidos los mutantes que solo cambian textos; cada mutante superviviente o lo elimina un test nuevo o se registra como equivalente.

**Mutantes concretos que eliminar primero:** `from_config` sin `save`; `NOT_ALLOWED` eliminado; huella `or` → `and`; la secuencia del protocolo `<< 8` y el límite de fragmento `>` → `>=`; guarda de selección de `remove_selected_tracks` `or` → `and`; `edit_range` `<` → `<=`; `set_track_mix` `all` → `any`; eliminación de `check_track` en `set_track_mix`, `rename_track` e `insert_plugin`; eliminación de `check_project_write` en `split_at_locators`; directorio del socket con escritura para el grupo (`& 0o077` → `& 0o007`); `open("x")` → `open("w")` en `setup`.

## Análisis adversarial: qué se probó

- **IPC:** un JSON anidado a 30 000 niveles (gestionado), 50 clientes inactivos con media línea (I-05), una ráfaga de 40 clientes (I-04), un segundo puente contra uno en marcha (I-01), una ruta de socket de 120 caracteres (I-08), un directorio del socket que es un enlace simbólico (I-11).
- **Protocolo:** 200 000 tramas aleatorias y casi válidas por el analizador, el reensamblador y el decodificador (solo `ProtocolError`, nunca un fallo; la tabla de pendientes acabó saturada, I-07), una trama suelta dentro de un ensamblado (I-07), 10 MB de SysEx sin `F7` (I-06).
- **Host:** una escritura en su plazo límite (I-03), sesiones renegociadas (I-02), respuestas duplicadas (I-10), ids de petición que no son cadenas (gestionado).
- **Script, en el arnés de node:** nombres de operación heredados (S-07), 2 000 tags (S-03).
- **La invariante «nunca reintentar una escritura» se mantuvo** en todas las rutas probadas; sus tests eliminan los mutantes pertinentes.

## Puntos fuertes

- Fijación de sesión, ningún reintento automático de escrituras y verificación por relectura con resultados `unknown` honestos.
- Los comandos informan de su clase (`dialog`, `ui_selection`), así que nunca se da por hecho un diálogo.
- Endurecimiento cuidadoso del IPC; lista exacta de operaciones permitidas; recursos acotados en el script (cachés, colas, ensamblados).
- Suite rápida con un 98 % de cobertura de ramas, mypy estricto, tests de contrato con un cliente MCP real y tests en vivo opcionales que revierten sus escrituras.
- El acuerdo del protocolo entre Python y el script se prueba con el script real en Node.
- Documentación exigida por tests (pares bilingües, todas las herramientas, claves de comando y claves de configuración documentadas).
