# E15 — Skills de productor: plugin de Claude Code y análisis de audio

[English](E15-producer-skills.md) · **Español**

**Estado de la épica: pendiente.** Objetivo: peticiones prácticas como «corta los silencios de más de 3 segundos de la pista X» o «añade una puerta de ruido a la pista de voz», construidas sobre el servidor MCP. Dos partes: un **analizador de audio** en el servidor (la API de Cubase no puede leer el contenido de las pistas, así que los silencios y los niveles de ruido se miden fuera de Cubase) y un **plugin de Claude Code** con skills en el formato abierto Agent Skills, publicado desde este mismo repositorio.

**Decisiones (2026-11-14):**
- **El mismo repositorio.** Las skills nombran las herramientas y dependen de sus contratos; en un solo repositorio, un test detecta una herramienta renombrada en el mismo commit. Se reconsiderará solo si las skills se independizan de Trackwright (varios DAW, otros servidores) o necesitan otra licencia; hasta entonces son AGPL-3.0-or-later como el resto.
- **Servidor y skills, cada uno con su trabajo.** El servidor hace las operaciones seguras y atómicas y el análisis determinista, y mantiene la seguridad (dry run, política de escritura, verificación por relectura): una skill solo da instrucciones al modelo y no puede imponer nada. Las skills aportan el criterio de productor: el orden de los pasos, los umbrales, qué enseñar al usuario y cuándo preguntar.
- **Skills estándar.** `SKILL.md` usa solo los campos del estándar Agent Skills (`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`), no los exclusivos de Claude Code, para poder probar los mismos archivos más adelante en otros clientes. Las skills nombran las herramientas por su nombre corto (`cubase_edit_range`): dentro de un plugin, el nombre completo lleva un prefijo (`mcp__plugin_<plugin>_<servidor>__<herramienta>`).
- **Analizar una exportación, no los archivos del proyecto.** El archivo de la carpeta Audio del proyecto no es lo que suena en la línea de tiempo (desplazamientos, recortes, varios eventos, ganancia de clip, fundidos, plugins), y la API no puede leer los eventos para convertir el tiempo del archivo en tiempo del proyecto. Una exportación entre localizadores está alineada con el proyecto desde el localizador izquierdo y contiene lo que suena de verdad (verificado en TW-1204: Cubase Elements exporta entre los localizadores).
- **numpy + soundfile.** soundfile lee WAV, AIFF y FLAC, incluido float de 32 bits (el módulo estándar `wave` no), y trae libsndfile dentro de su wheel: se instala con uv, sin compilar ni instalar nada en el sistema. Descartados: ffmpeg (un binario del sistema, fuera de «solo uv»), pydub (necesita ffmpeg), librosa (pesada para esto), detección de voz con redes neuronales (torch, cientos de MB).
- **VS Code y GitHub Copilot: fuera de esta épica.** Los plugins ya funcionan en la extensión de Claude Code para VS Code (documentado). La prueba con Copilot y una posible extensión de VS Code quedan para más adelante (ver «Fuera de alcance»).

**Referencias (comprobadas el 2026-11-14):** plugins de Claude Code ([visión general](https://code.claude.com/docs/en/plugins/overview.md), [manifiesto](https://code.claude.com/docs/en/plugins/manifest-reference.md), [marketplace](https://code.claude.com/docs/en/plugins/create-marketplace.md), [CLI](https://code.claude.com/docs/en/plugins/cli-reference.md)), [skills](https://code.claude.com/docs/en/skills.md) y [MCP](https://code.claude.com/docs/en/mcp.md).

**Normas para toda la épica:** las mismas que en E14 (un test que falla antes de cada corrección, documentación bilingüe, los resultados vistos en Cubase anotados en el registro de verificación). Las skills se prueban contra el proyecto de pruebas desechable y su pista `POC-TEST`; nada se aplica sin la confirmación del usuario.

## Fase 1 — Análisis de audio en el servidor

### TW-1501 Exportar una sola pista, comprobado en Cubase

- **Estado:** hecha (2026-11-14), ver `experiments/tw1501/` y el registro de verificación: solo se puede exportar Stereo Out, así que la pista va en solo; alineación exacta a la muestra (`proyecto = localizador izquierdo + tiempo del archivo`); niveles desplazados por la ley de panorama (−3 dB), así que los umbrales deben ser relativos al ruido de fondo; el silencio digital debe quedar fuera de la estimación del ruido de fondo. `cubase_export_mix` no necesita cambios; el solo es un paso de la skill
- **Por qué primero:** el plan del análisis depende de ello, y hoy no se sabe.
- **Alcance (experimento en `experiments/tw1501/`, con su README):**
  1. Si el diálogo «Exportar mezcla de audio» de Cubase Elements 15 puede exportar el canal de una pista en lugar de Stereo Out. Si no: Stereo Out con la pista en solo (y el solo deshecho después), o que elija el usuario.
  2. Alineación: la muestra 0 del archivo exportado = el localizador izquierdo (medido con un clic o un borde conocido del proyecto de pruebas).
  3. El formato y la frecuencia de muestreo que propone Cubase, y si hay WAV de 32 bits float.
  4. Si se incluyen los plugins de inserción y el fader del canal (cambiarían los niveles medidos).
- **Resultado:** anotado en `docs/verification.es.md`; decide el paso de exportación de TW-1506 y lo que necesita `cubase_export_mix` (quizá nada).

### TW-1502 Leer audio: una capacidad nueva con su propio interruptor

- **Estado:** hecha (2026-11-14): `[analysis] enabled` (por defecto `false`, `ANALYSIS_DISABLED`) y `max_seconds` (por defecto 14400 s, `TOO_LONG`), comprobados por `WritePolicy.check_analysis()`; independiente de `[writes]`; `setup` lo pregunta (`--analysis`); `cubase_status.analysis_enabled` y una comprobación en `doctor`; capítulo de configuración y SECURITY. No se añadió un límite de tamaño: el analizador lee por bloques, así que la duración acota el trabajo. Tests en `tests/unit/test_analysis_policy_tw1502.py`; el test de contrato de la herramienta va con TW-1504
- **Por qué:** hoy Trackwright nunca lee audio (`cubase_export_mix` solo lee nombre, tamaño, fecha y duración). Leer las muestras de un archivo es una capacidad nueva y debe ser explícita.
- **Alcance:**
  1. `[analysis] enabled` en la configuración, `false` por defecto; `ANALYSIS_DISABLED` cuando está desactivado. `trackwright setup` lo pregunta como un paso más.
  2. Solo archivos que el usuario exportó y Trackwright confirmó, o una ruta dada explícitamente; solo lectura; nunca se envían a ningún sitio, solo se devuelven las medidas.
  3. Límites: duración y tamaño máximos, rechazados con un código claro en lugar de llenar la memoria (lectura por bloques).
  4. SECURITY.md (+ `.es`) y el capítulo de configuración del manual.
- **Tests:** tests de política como los de `[writes]`; un test de contrato de que la herramienta se rechaza cuando está desactivada.

### TW-1503 Módulo analizador

- **Estado:** hecha (2026-11-14): `trackwright.analysis` (`reader.py`: `probe` y `measure` por bloques de 500 ventanas; `detect.py`: `noise_floor`, `SilenceCriteria`, `find_silences`). Decisiones: el nivel de una ventana es el RMS sobre sus muestras y todos los canales (los canales en contrafase no se anulan); el ruido de fondo es el percentil 10 sin el silencio digital; el umbral relativo (ruido de fondo + 10 dB por defecto) solo se aplica si queda por debajo del percentil 90; si no, solo cuenta el silencio digital (un tono continuo o un archivo de puro ruido no tiene silencios que encontrar); los márgenes no se aplican en los extremos del archivo. Valores por defecto: ventanas de 20 ms, mínimo 2 s, margen 0,25 s, unión de huecos de 0,3 s. Tests en `tests/unit/test_analysis.py` (100 % del paquete, propiedades con Hypothesis). Ejecutado sobre la exportación real de TW-1501: los tres silencios de 3 s o más encontrados donde están en el proyecto, el de 1 s ignorado, ruido de fondo −63 dB
- **Alcance:** `trackwright/analysis/`, sin dependencia de Cubase (funciones puras sobre muestras):
  1. Lectura por bloques con soundfile; mezcla a mono para la medida.
  2. RMS en ventanas de unos 20 ms, en dBFS; pico.
  3. Ruido de fondo: un percentil bajo de los niveles de las ventanas (por ejemplo el 10).
  4. Silencios: tramos por debajo de un umbral (absoluto en dBFS, o relativo al ruido de fondo) que duren al menos un mínimo; margen conservado antes y después de cada corte para no comerse palabras; tramos unidos cuando el hueco entre ellos es más corto que un mínimo.
  5. Dependencias: `numpy` y `soundfile`, con límite superior en la siguiente versión mayor como el resto.
- **Tests:** señales sintéticas (tono, silencio, ruido a un nivel conocido): tramos exactos con un margen de una ventana; tests de propiedades (Hypothesis): tramos ordenados, sin solaparse, dentro del archivo, todos de al menos la duración mínima; un archivo sin silencios y otro que es todo silencio.

### TW-1504 Herramienta `cubase_analyze_audio`

- **Estado:** hecha (2026-11-15): `core/analyzing.py` (`AnalyzingMixin`), `AnalysisOut`/`SilenceOut`, herramienta registrada como `READ`; el límite de duración se comprueba con la cabecera antes de leer muestras. Tests en `tests/unit/test_service_analysis.py` y el test de contrato. Verificada por MCP sobre la exportación de TW-1501 (ver el registro de verificación)
- **Alcance:**
  1. **Entrada:** el archivo (de la fase `confirm` de `cubase_export_mix`) y el tiempo del proyecto en que empieza (el localizador izquierdo, que esa herramienta conoce); umbral, duración mínima y margen, con valores por defecto documentados para voz hablada.
  2. **Salida:** silencios en **segundos del proyecto** (inicio, fin, duración, nivel), ruido de fondo, pico y RMS de todo el archivo, y los parámetros usados. Una lista limitada como en las demás herramientas (`clamp_limit`), con el total.
  3. Anotaciones: `READ` (no cambia nada en Cubase).
  4. Sección en `docs/manual/04-tools.md` (+ `.es`); el número de herramientas en la documentación pasa a 33.
- **Tests:** del servicio y de contrato con un WAV generado en el test; en directo: una exportación del proyecto de pruebas, comparando los silencios encontrados con la línea de tiempo.

## Fase 2 — Plugin de Claude Code

### TW-1505 Estructura del plugin y del marketplace

- **Estado:** hecha (2026-11-15): plugin en `plugins/claude-code/` (`plugin.json` con la versión del paquete, README en ambos idiomas), marketplace en la raíz, `.mcp.json` con `uvx --from ${TRACKWRIGHT_FROM:-trackwright==<versión>} trackwright serve` (`uvx` funciona; la variable permite usar un repositorio durante el desarrollo, porque la 0.4.0 publicada rechaza una configuración con `[analysis]`). `claude plugin validate --strict` pasa para el plugin y el marketplace (solo un aviso por falta de icono, que solo importa para el catálogo de Anthropic); no está en la integración continua, que no tiene la CLI `claude`: es un paso de la publicación. Registro duplicado: documentado en el README del plugin con la orden para quitar el manual; `doctor` no lo detecta, porque Claude Code no documenta dónde registra los plugins. Verificado: `TRACKWRIGHT_FROM=$PWD claude --plugin-dir plugins/claude-code mcp list` muestra `plugin:trackwright:trackwright` conectado
- **Alcance:**
  1. `plugins/claude-code/` con `.claude-plugin/plugin.json` (`name: "trackwright"`, versión, descripción, autor, homepage, repositorio, licencia) y `skills/`.
  2. `.mcp.json` del plugin: el servidor arrancado como `uvx trackwright==X.Y.Z serve`, con la versión que corresponde al plugin. **Por comprobar:** la documentación muestra `npx` pero no dice nada de `uvx`; si falla, documentar la alternativa.
  3. `.claude-plugin/marketplace.json` en la raíz del repositorio (el repositorio es el marketplace), con `"source": "./plugins/claude-code"`. Instalación: `claude plugin marketplace add impalah/trackwright` y `claude plugin install trackwright@<marketplace>`.
  4. **Conflicto con la instalación actual:** un usuario que registró `trackwright` con `claude mcp add` tendría dos servidores con las mismas herramientas. Documentar cuál quitar (ambos comparten el puente gracias a su bloqueo, pero el cliente vería herramientas duplicadas) y hacer que `trackwright doctor` avise si puede detectarlo.
  5. **Tests en `tests/unit/test_plugin.py`:** cada herramienta que nombra una skill existe en `server.py`; el frontmatter usa solo campos estándar; la versión del plugin y la fijada en `trackwright==` de `.mcp.json` coinciden con `pyproject.toml`; `plugin.json` y `marketplace.json` son JSON válidos con el mismo nombre.
  6. `claude plugin validate plugins/claude-code --strict` antes de cada publicación (documentado en el procedimiento de publicación). Aquí se decide si la integración continua puede ejecutarlo (necesita la CLI `claude` en el runner).
- **Verificación:** `claude --plugin-dir plugins/claude-code` en una sesión contra el Cubase real: las skills aparecen (`/trackwright:<skill>`) y las herramientas responden.

### TW-1506 Skill `podcast-silence-trim`

- **Estado:** hecha (2026-11-15): `plugins/claude-code/skills/podcast-silence-trim/SKILL.md`. Decisiones: analizar por defecto toda la mezcla, porque `delete_time` corta todas las pistas y solo un tramo silencioso en la mezcla lo es en todas; si el usuario nombra una pista, explicarlo y ofrecer la mezcla, esa pista en solo o `delete` solo en esa pista (quedan huecos); una música de fondo hace que la mezcla nunca esté en silencio; el silencio digital en los extremos del rango queda fuera de la propuesta. El flujo se siguió paso a paso contra el proyecto de pruebas (ver el registro de verificación): cuatro cortes aprobados y verificados. Después, el usuario hizo la petición a través del plugin en una sesión nueva (`claude --plugin-dir`) e indicó que funcionó
- **Flujo:**
  1. Identificar la pista y el rango (todo el proyecto por defecto) con las herramientas de lectura; confirmarlos con el usuario.
  2. Exportar (`cubase_export_mix`, dos fases: el usuario completa el diálogo) y confirmar.
  3. `cubase_analyze_audio` con el criterio del usuario (por ejemplo «más de 3 s») o los valores por defecto para voz.
  4. Enseñar los cortes propuestos (lista, tiempo total eliminado) y preguntar. Nada se corta sin un sí.
  5. Aplicar con `cubase_edit_range` (`delete_time`) **del final hacia el principio**, para que las posiciones anteriores no se muevan; dry run primero, como dicen las instrucciones del servidor.
  6. Informar de lo cortado; explicar cómo deshacerlo (Edición > Deshacer, una vez por corte).
- **Decisiones que anotar:** si el corte actúa sobre todas las pistas (podcast con varias voces sincronizadas, el caso habitual: `cubase_edit_range` actúa sobre todas las pistas del rango) o solo sobre una; qué pasa con las músicas de fondo.
- **Verificación:** en el proyecto de pruebas, con un número conocido de silencios; deshecho después.

### TW-1507 Skill `noise-gate`

- **Estado:** pendiente (necesita de TW-1503 a TW-1505)
- **Flujo:**
  1. Buscar una puerta entre los plugins disponibles (`cubase_list_available_plugins`); cuál trae Cubase Elements **no se sabe** y se comprueba aquí, sin suponerlo.
  2. Medir el ruido de fondo de la pista (exportación y `cubase_analyze_audio`) y proponer el umbral unos dB por encima.
  3. `cubase_insert_plugin` y `cubase_set_parameter` con dry run, el umbral en unidades reales; relectura.
  4. Explicar al usuario cómo escuchar y ajustar (ataque, liberación), algo que Trackwright no puede juzgar.
- **Verificación:** en `POC-TEST`; el plugin se quita después.

### TW-1508 Documentación y publicación

- **Estado:** pendiente
- **Alcance:** un capítulo del manual «Plugin de Claude Code y skills» (+ inglés): instalación, las skills y lo que preguntan, cómo se relacionan con las herramientas; sección en el README; CHANGELOG; CLAUDE.md (mapa del código). Publicación: la versión que incluya esta épica (puede ser la 0.5.0 junto con los cambios de API de E14, si se publican a la vez).

### TW-1509 Esperar a Cubase tras arrancar el puente

- **Estado:** hecha (2026-11-15); tests en `tests/unit/test_autostart_wait_tw1509.py`; verificada en Cubase (ver el registro de verificación)
- **Por qué:** visto durante TW-1504: justo después de arrancar el puente automáticamente, la primera petición agotó el tiempo porque Cubase aún no se había enlazado a los puertos virtuales nuevos; la segunda funcionó. El primer paso de una skill fallaría sin motivo real.
- **Decisión:** tras arrancar el puente, `BridgeHost` repite `hello` (solo lee, así que reintentarlo es seguro) hasta que Cubase responde o se agota `[bridge] autostart_timeout`, con una pausa de 0,5 s entre intentos; después envía una vez la petición original, que nunca llegó al puente. Si Cubase no responde, `TIMEOUT` con `outcome: not_executed` y un mensaje que dice que la petición no se envió. Los demás errores no se reintentan. La norma «nunca reintentar una escritura de resultado incierto» no cambia.

## Fuera de alcance (posibles épicas posteriores)

- **GitHub Copilot en VS Code:** probar las mismas skills y el servidor con `.vscode/mcp.json`, sin extensión; anotar el resultado y actualizar la nota de «no probado».
- **Extensión de VS Code:** solo si lo anterior funciona y la instalación con un clic para otras personas compensa un proyecto en TypeScript con sus propias versiones.
- **Prompts MCP** en el servidor, para flujos que deban funcionar en cualquier cliente MCP.
- **Detección de voz** (habla frente a respiraciones), **sonoridad** (LUFS para podcast, `pyloudnorm`) y otras skills de productor.
