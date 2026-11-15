# E16 — Skills de producción de podcast

[English](E16-podcast-production.md) · **Español**

**Estado de la épica: pendiente.** Origen: la lluvia de ideas de `01.podcast.production.ideas.md` (fuera del repositorio, 2026-11-15), evaluada frente a lo que Trackwright y Cubase Elements pueden hacer de verdad. Objetivo: un conjunto de skills de Claude Code que completen cada una un trabajo de producción (analizar, proponer, aplicar con límites, verificar), primero para podcasts y después para otras producciones habladas (audiolibros, locuciones, diálogo de vídeo).

## Decisiones (2026-11-15, con el usuario)

- **Solo Cubase Elements 15.** La lluvia de ideas suponía Artist 15 (SuperVision, sidechain, time stretch, VocalChain). Todo se diseña y verifica en Elements; las funciones de Artist o Pro solo pueden aparecer como caminos opcionales marcados como no probados.
- **Primero el procesado fuera de línea, después Cubase.** La API no puede escribir puntos de automatización, cambiar la ganancia de un evento, leer audio ni cambiar el enrutamiento. El ducking, la nivelación del diálogo, las camas musicales, el room tone y los fundidos se hacen por tanto **fuera de línea**: exportar la pista (solo + Stereo Out, alineada a la muestra, TW-1501), procesarla en Python, **importar el resultado como una pista nueva** y silenciar la original. Hacerlo dentro de Cubase (grabación de automatización en tiempo real, sidechain preparado por el usuario) viene después, donde poder editarlo compense el tiempo de reproducción.
- **Archivos en una subcarpeta `Trackwright/` de cada proyecto.** Allí van los renders, análisis, preescuchas, el perfil del episodio y el registro de lo que creó cada skill; los perfiles de programa compartidos por varios episodios van a `~/.config/trackwright/shows/`. Escribir ahí es un permiso nuevo (TW-1602).
- **Transcripción local, al final.** La revisión editorial (repeticiones, arranques fallidos, muletillas, indicaciones de grabación) usa un modelo Whisper local instalado con uv, en la última fase. El audio nunca sale del equipo.
- **Destinos de entrega:** Apple Podcasts (RSS), Spotify, YouTube, iVoox; otros servicios cuando el usuario los nombre. Cada número de un perfil de entrega se toma de la especificación publicada por la plataforma, citada con su URL y fecha de consulta; sin fuente, no hay perfil.
- **Material de prueba:** episodios completos que el usuario indique, solo en lectura; los resultados se anotan sin el audio. Señales sintéticas para los tests unitarios (la prueba de la puerta de ruido mostró cómo pueden ocultar errores, así que nunca solo sintéticas).
- **Orden:** el de la lluvia de ideas (control de calidad final, entrega, ducking, cama musical, nivelación del diálogo, suavizado de cortes, tono de voz, revisión editorial), con la auditoría de la sesión pronto porque alimenta al resto; los cimientos primero.
- **Biblioteca:** el usuario aún no tiene; la épica define su formato (TW-1620).

## Lo que Trackwright puede y no puede hacer (hechos sobre los que se apoya la épica)

- **Puede:** listar pistas, inserciones y plugins; leer y fijar cualquier parámetro de plugin o canal en unidades reales (con relectura); insertar plugins; mute, solo, volumen, panorama; marcadores (crear, saltar); edición de rangos en segundos en todas las pistas (`delete_time`…) o borrar en una pista; bordes de los eventos de una pista (sondeo); exportar Stereo Out entre localizadores con el usuario (diálogo); importar un archivo en una posición con el usuario (diálogo); reproducir y parar; grabar automatización reproduciendo (volumen, panorama, envíos 1–4, EQ del canal, prefiltro, slots de inserción 1–2); analizar un archivo exportado (ruido de fondo, niveles, silencios; TW-1503).
- **No puede (verificado):** leer audio, eventos, su ganancia, fundidos, curvas de automatización ni marcadores como datos; cambiar el enrutamiento (incluidas las fuentes de sidechain); completar diálogos; quitar plugins; exportar en Elements algo distinto de Stereo Out (sin exportación por canal ni por lotes: un diálogo por pista); el script no tiene hoy enlazados comandos de Cubase para fundidos ni para repetir o duplicar eventos.

## Viabilidad de las ideas

✅ viable con lo que existe · 🧪 necesita antes un experimento · 🔧 necesita una capacidad nueva del servidor · 👤 un paso que solo puede hacer el usuario · ⛔ imposible a través de la API (se indica la alternativa)

| Idea | Veredicto | Cómo |
|---|---|---|
| `podcast-final-qc` | ✅🔧 | Solo lectura: exportar y medir (sonoridad y true peak son nuevos, TW-1603). «Las pistas excluidas no están en el render» no se puede demostrar con una mezcla: queda como punto de la lista de comprobación, o como comparación de pistas. |
| `podcast-delivery` | ✅🧪👤 | Sonoridad medida en Python (BS.1770, sin SuperVision ni FFmpeg); ganancia en el fader de Stereo Out; limitador en Stereo Out si el true peak superaría el techo (Brickwall Limiter y Maximizer existen en Elements; insertar en Stereo Out está por verificar); el usuario exporta el MP3 en el diálogo; el archivo entregado se decodifica y se vuelve a medir (MP3 con soundfile; AAC con `afconvert` de macOS). |
| Ducking por sidechain (opción 1) | ⛔👤🧪 | El enrutamiento de un sidechain no está al alcance de la API. Como mucho, una preparación guiada que completa el usuario, si el Compressor de Elements tiene entrada de cadena lateral (TW-1601). |
| Ducking por envolvente (opción 2) | ✅🔧 | Fuera de línea: actividad vocal en la pista de voz, planificador de envolvente (pre-roll, hold, huecos unidos, recuperación, zonas protegidas, excepciones por región), música atenuada renderizada e importada como pista nueva. «Hazlo menos evidente / no subas la música entre esas dos frases» cambia el plan guardado, no toda la mezcla. |
| Respetar la automatización existente | ⛔ → ✅ | La automatización no se puede leer. El camino fuera de línea nunca la toca; un modo posterior en Cubase escribe solo un parámetro que pertenezca a la skill. |
| `podcast-music-bed` (región de bucle, extender, final) | ✅🔧🧪 | Fuera de línea: el análisis de pulso y repeticiones propone regiones de bucle, el usuario aprueba una, Python renderiza la cama con la duración necesaria con las uniones en los pulsos y fundidos cortos, conserva el final, renderiza preescuchas de cada unión y deja marcadores en las dudosas. |
| Time stretch | ⛔ | No está al alcance de la API; estirar fuera de línea queda fuera de esta épica (`allow_time_stretch: false`). |
| `podcast-session-audit` | ✅ parcial | Pistas, tipos, mute/solo, salidas, inserciones, bordes de eventos por pista, informe de capacidades. No puede ver la automatización, la ganancia de los eventos ni los marcadores del usuario; los roles los confirma el usuario y se guardan en el perfil del episodio; los rangos protegidos también (los marcadores no se pueden leer). |
| `podcast-edit-review` | ✅🔧 al final | Pausas y saltos de nivel sin transcripción; las repeticiones, arranques fallidos, muletillas e indicaciones de grabación necesitan la transcripción local (TW-1630). Salida: una lista de decisiones; nada se corta sin aprobación; los cortes aprobados con `cubase_edit_range` en todas las pistas, del último al primero. |
| `podcast-edit-smoothing` | ✅🧪 | Room tone extraído de pasajes tranquilos de la misma voz e importado para cubrir huecos; fundidos en los cortes solo si se pueden enlazar los comandos de Cubase necesarios (TW-1626), si no, renderizados fuera de línea; un único archivo de preescucha con todos los cortes. |
| `podcast-sync-sources` | ✅ diagnóstico | Correlación cruzada de dos pistas en varios puntos: desfase fijo frente a deriva. Mover eventos no es posible a través de la API: la corrección es una instrucción manual (o un render fuera de línea, más adelante). No se usa Audio Alignment (Pro). |
| `podcast-dialogue-leveling` | ✅🔧 | Sonoridad con puerta de voz por región y por persona, ganancias acotadas (sin normalizar cada frase), pistas niveladas renderizadas e importadas. La ganancia de los eventos no se puede fijar a través de la API. |
| `podcast-voice-cleanup` | ✅🔧 primero diagnóstico | Zumbido, ruido de banda ancha, plosivas, clics de boca, sibilancia y reverberación medidos fuera de línea; tratados solo con plugins que estén instalados (muescas con StudioEQ para el zumbido, Gate, DeEsser, paso alto del canal); si no, «detectado, requiere revisión u otra herramienta». |
| `podcast-voice-tone` | ✅🧪 | Objetivos, no presets: retumbe, resonancias, cuerpo, dinámica, sibilancia, con StudioEQ, Compressor y DeEsser; A/B reproduciendo un rango en ciclo en Cubase con Bypass alternado y la sonoridad igualada. VocalChain no está en Elements. |
| `podcast-section-transitions` | ✅👤 | Una cortinilla aprobada colocada en un marcador o tiempo (importación en una posición), nunca encima de la última frase (actividad vocal), fundidos renderizados fuera de línea. |
| `podcast-sound-effects` | ✅🔧👤 | Solo de una biblioteca local con licencias (TW-1620); colocación y ganancia como arriba; procedencia y licencia anotadas por episodio. Sin descargas. |
| `podcast-spatial-balance` | ✅ | Panorama leído y fijado por canal; criterio de colocación de voces en el perfil del programa; comprobación mono a partir de una exportación sumada en Python, con un archivo de preescucha mono. |
| Servicios de análisis (sonoridad, actividad vocal, regiones, comparación de renders, preescuchas) | 🔧 | Módulos nuevos en `trackwright.analysis` (puros, con tests), accesibles con herramientas MCP. |
| Transcripción con marcas de tiempo | 🔧 al final | Whisper local, extra opcional. |
| Análisis ligado a una versión del audio | 🔧 | Cada análisis anota el archivo y su hash; una caché en `Trackwright/analysis/`. |
| Contrato de las skills (requisitos, entradas, flujo, seguridad, salidas) y propiedad | 🔧 | Un contrato común comprobado por los tests del plugin; la propiedad anotada en `Trackwright/state.json` para que repetir una skill actualice sus propias pistas y plugins en lugar de acumularlos. |
| Perfil del programa | 🔧 | `~/.config/trackwright/shows/<programa>.toml` más `Trackwright/profile.toml` por episodio. |
| «Producir un podcast entero» | ⛔ | Fuera de alcance, como dice la propia lluvia de ideas. |

## Arquitectura común a las skills

```text
análisis (trackwright.analysis, Python, puro)   → medidas, regiones de voz, problemas candidatos, renders
skills (plugins/claude-code/skills/podcast-*)    → objetivos, preguntas, plan, aprobación, informe
herramientas MCP (Trackwright → Cubase)          → inspeccionar, exportar/importar con el usuario, aplicar, verificar
```

- **Pistas:** una exportación por pista (Elements no exporta por canal ni por lotes), con la pista o pistas en solo y el solo restaurado después. Las skills reutilizan los análisis en caché para no pedir dos veces la misma exportación.
- **Renderizar e importar:** el audio procesado se escribe en `Trackwright/renders/` como WAV de 32 bits float a la frecuencia del proyecto, con un archivo de procedencia (exportación de origen y su hash, procesado, parámetros, skill y ejecución). Se importa en una pista nueva al inicio del rango; la original se silencia, nunca se borra. La alineación se comprueba con los bordes de los eventos.
- **Estructura de `Trackwright/`:** `renders/`, `previews/`, `analysis/` (caché por hash del archivo y parámetros), `profile.toml` (episodio: roles de las pistas, rangos protegidos, excepciones), `state.json` (lo que creó cada skill: pistas, plugins y sus slots, renders), `reports/` (informes de control de calidad y de entrega).
- **Propiedad:** una skill solo actualiza o sustituye lo que `state.json` dice que creó; todo lo demás es del usuario.
- **Preescuchas:** archivos cortos renderizados fuera de línea (uniones, primeras palabras, puntos de corte) y, para el procesado hecho en Cubase, un rango en ciclo reproducido con Bypass alternado.
- **Seguridad, como en E15:** dry run y aprobación antes de cada cambio, no guardar si no se pide, no reintentar tras un timeout, el solo siempre restaurado, nada leído más allá de las exportaciones y episodios que indique el usuario.

## Normas para toda la épica

Las mismas que en E14 y E15: un test que falla antes de cada corrección; documentación en inglés y castellano; los resultados observados en Cubase en el registro de verificación; los experimentos en `experiments/twNNNN/` con un README en ambos idiomas. Los episodios reales se leen solo donde indique el usuario, y solo se anotan las medidas. Los números de las plataformas se citan, nunca se recuerdan.

## Fase 1 — Cimientos

### TW-1601 Experimento: lo que ofrece Cubase Elements para estas skills

- **Estado:** hecha (2026-11-15): ver `experiments/tw1601/` y el registro de verificación. Limitador en Stereo Out: sí; cadena lateral: el botón existe, la fuente la elige el usuario; automatización ~0,1 s tarde, cuantizada a ~110 ms; PreGain automatizable; comandos de fundido encontrados («Ajustar fundidos al rango», fundido cruzado, duplicar, repetir), ninguno enlazado aún; MP3 decodificable, sin exportación AAC; los renders se importan en su sitio; la reproducción en ciclo con Bypass para el A/B funciona sin clics
- **Preguntas:**
  1. ¿Se pueden insertar plugins en Stereo Out y fijar sus parámetros (Brickwall Limiter, Maximizer: techo, umbral)?
  2. ¿Tiene el Compressor de Elements (o VSTDynamics) entrada de cadena lateral, y qué parámetros se ven a través de la API? (El enrutamiento sigue siendo cosa del usuario.)
  3. Precisión de la grabación de automatización: desfase entre el inicio y el fin pedidos y los escritos de una curva (para un modo posterior de ducking dentro de Cubase).
  4. Qué parámetros del canal se pueden automatizar además del volumen y el panorama (¿pre-gain?), para dar a un modo dentro de Cubase un parámetro propio.
  5. Qué comandos de teclado de Cubase darían fundidos en el cursor, fundidos de eventos y repetición de eventos, y qué haría falta para enlazarlos (un cambio del script: permiso, instalación, reinicio de Cubase). Solo hallazgos; aquí no se cambia el script.
  6. Opciones de MP3 del diálogo de exportación; si soundfile decodifica el MP3 que escribe Cubase, y `afconvert` un AAC.
  7. Importar un WAV escrito por Trackwright en `Trackwright/renders/`: ¿lo copia Cubase a `Audio/`, y queda colocado a la muestra?
  8. `transport.start`/`stop` con un rango en ciclo mientras se alterna el Bypass de un plugin, para escuchar A/B.
- **Resultado:** registro de verificación; las decisiones se anotan en las issues que dependen de cada respuesta.

### TW-1602 El espacio de trabajo `Trackwright/` del proyecto

- **Estado:** hecha (2026-11-15): `trackwright/workspace.py` (estructura, rutas que no pueden salir, escrituras atómicas, `State`/`OwnedItem` para `state.json`, `EpisodeProfile` para `profile.toml`, escrito con la dependencia nueva `tomli-w`), `[workspace] enabled` (desactivado por defecto, `WORKSPACE_DISABLED`, comprobado antes que nada en `init`), herramienta `cubase_workspace` (`status`, `init`), `setup --workspace`, `cubase_status.workspace_enabled`, `doctor`; capítulos de configuración y de herramientas, y SECURITY. Tests en `tests/unit/test_workspace.py` y el test de contrato. En directo: `status` encontró la carpeta del proyecto de pruebas y el `Trackwright/` incompleto que dejó TW-1601; `init` rechazado con la configuración del usuario (escritura no activada), así que falta ver la creación en directo
- **Alcance:** la estructura de arriba; un interruptor `[workspace] enabled` (desactivado por defecto, como `[writes]` y `[analysis]`), mostrado en `cubase_status` y `doctor`; Trackwright solo crea `Trackwright/` dentro de la carpeta del proyecto que encuentra `project_folder()`, nunca otro archivo; una herramienta para mostrarlo y crearlo (`cubase_workspace`); `state.json` (propiedad) y `profile.toml` (episodio) con modelos pydantic; SECURITY y el capítulo de configuración actualizados.
- **Tests:** política, estructura, registros de propiedad, rechazo fuera de la carpeta del proyecto.

### TW-1603 Sonoridad y true peak

- **Estado:** hecha (2026-11-15): `trackwright/analysis/loudness.py` (ponderación K para cualquier frecuencia, sonoridad integrada con puertas, máximos momentáneo y a corto plazo, LRA, pico de muestra y true peak 4x, lectura por bloques) con scipy como dependencia nueva (`lfilter`, `resample_poly`; con numpy puro haría falta un bucle por muestra); herramienta `cubase_measure_loudness`; AAC decodificado con `afconvert` de macOS (`decoded()`, que usa también `cubase_analyze_audio`). Tests: tablas de coeficientes de BS.1770 a 48 kHz, casos 1-4 de EBU Tech 3341 (±0,1 LU), casos 1-3 de Tech 3342 (±1 LU), true peak entre muestras, mono, silencio, pyloudnorm a 44,1 y 48 kHz (±0,1 LU), MP3 y AAC. En nueve exportaciones reales del proyecto de pruebas coincide con pyloudnorm con menos de 0,07 LU de diferencia; 140 s medidos en 0,6 s
- **Alcance:** medidas ITU-R BS.1770 / EBU R128 en `trackwright.analysis`: sonoridad integrada (con puerta), máximos a corto plazo y momentáneos, rango de sonoridad, pico de muestra y true peak (sobremuestreo 4×). Expuestas con la herramienta de análisis o una nueva `cubase_measure_loudness`.
- **Validación:** señales de conformidad generadas en los tests (como describen EBU Tech 3341 y 3342; documentos citados) y comparación con `pyloudnorm` solo como dependencia de desarrollo; entregas MP3 y AAC decodificadas (soundfile, `afconvert`) y medidas.

### TW-1604 Detección de actividad vocal

- **Estado:** hecha (2026-11-15): `trackwright/analysis/speech.py` y herramienta `cubase_detect_speech`. Validada con un episodio real (46 min, una voz, `Pod Mic` exportada sola): 2,5 s para todo el episodio; ruido de fondo −61,8 dB, voz típica −13,1 dB. Un ruido de 0,37 s a −52 dB dentro de una pausa se tomó por voz y partía la pausa; corregido con `faint_db` (fragmentos 30 dB por debajo del nivel típico de la voz descartados **antes** de unir: descartarlos después no bastaba, ya habían unido pausas), que descartó 108 fragmentos así y dejó ver 35 pausas de más de 1 s en lugar de ocultarlas. El usuario escuchó los 10 primeros minutos con un tono que marcaba la voz detectada: entradas y salidas correctas. No comentó respiraciones ni falsos positivos
- **Alcance:** regiones de voz en una pista de voz: energía frente al ruido de fondo más un criterio de banda vocal, histéresis, región y hueco mínimos; regiones con nivel y confianza. Cada voz va en su propia pista, así que no hace falta separar locutores; una pista con varias voces queda fuera de alcance.
- **Validación:** en episodios completos que indique el usuario, comparada con unos minutos que marque a mano (rangos en ciclo o una lista de tiempos); la señal sintética de sílabas de TW-1507 en los tests unitarios.

### TW-1605 Exportar una pista con el solo restaurado

- **Estado:** hecho (2026-11-15): `cubase_export_mix` ganó `solo` (selectores de pista, respetando `allowed_tracks`) y una fase `cancel`; `start` recuerda todos los solos, quita los demás y pone en solo las pistas indicadas; `confirm` y `cancel` restauran todos los solos, y cualquier fallo antes de abrir el diálogo los restaura en el acto. Las dos skills lo usan. Tests en `tests/unit/test_export_solo_tw1605.py`. En directo en el proyecto de pruebas: una exportación con `confirm` y un diálogo cerrado con `cancel`, ambos con los solos como antes
- **Alcance:** un solo paso para exportar una pista: poner en solo las pistas indicadas (recordando el estado de solo anterior), fijar el rango, abrir el diálogo; al confirmar, restaurar exactamente el estado de solo, aunque la exportación haya fallado. Hoy cada skill lo hace a mano y podría dejar una pista en solo. Parámetros nuevos de `cubase_export_mix` o una herramienta nueva.
- **Tests:** estado de solo restaurado en todos los caminos; verificado en Cubase.

### TW-1606 Renderizar e importar

- **Estado:** hecho (2026-11-15), verificado en Cubase (un render a −6,02 dB de una pista, importado en una pista nueva y exportado solo, es igual al origen × 0,5 hasta −182 dB, sin desplazamiento; ver el registro de verificación): `trackwright/renders.py` (WAV de 32 bits float escrito por bloques a través de un archivo temporal, procedencia `<nombre>.json` con el SHA-256 del origen y del render, nombres nunca reutilizados), herramienta `cubase_render` (`render` con el proceso `gain`, `list` con los problemas encontrados y la pista a la que fue cada render) y `cubase_import_audio` consciente de los renders (posición comprobada con la procedencia, rechazo de la pista sustituida y de un render cambiado, propiedad del render y de su pista registrada en `state.json`, aviso de una pista de render anterior de la misma skill; una importación en la posición 0 se prueba por su borde final nuevo, porque el sondeo no ve un borde al inicio del proyecto). Tests en `tests/unit/test_render_tw1606.py`
- **Alcance:** escribir el audio procesado en `Trackwright/renders/` con su archivo de procedencia; importarlo en una pista nueva al inicio del rango con el usuario (`cubase_import_audio`); silenciar la original; comprobar la alineación con los bordes de los eventos; anotar la propiedad. Repetirla sustituye solo su propia pista de render (quitarla necesita la confirmación del usuario, como `cubase_remove_selected_track`).
- **Tests:** procedencia, comprobaciones de alineación; verificado en Cubase con una señal conocida.

### TW-1607 Perfiles de programa y de entrega

- **Estado:** hecho (2026-11-15), comprobado en directo en el proyecto de pruebas (ver el registro de verificación); el perfil del programa del usuario espera a sus roles y destinos: `trackwright/profiles.py` (ajustes de programa y episodio, `resolve` con el origen de cada valor, `DeliveryProfile` que rechaza un valor sin fuente que lo respalde), `delivery.toml` (Apple, Spotify, YouTube, iVoox, leídos el 2026-11-15 en las páginas de las plataformas: Apple −16 LUFS ±1 y −1 dBTP; Spotify, YouTube e iVoox no publican sonoridad ni pico real para podcasts, y los −14 LUFS de Spotify son para música; iVoox solo de un blog de 2022, su centro de ayuda no se pudo leer), `EpisodeProfile` con las mismas secciones, herramienta `cubase_profile` (`resolve`, `shows`, `delivery`, `write_show`, `write_episode`). Tests en `tests/unit/test_profiles_tw1607.py`
- **Alcance:** esquema pydantic para un perfil de programa (`~/.config/trackwright/shows/<programa>.toml`: roles de las pistas por nombre, voces, música aprobada, estilo de ducking, criterios de edición, perfiles de entrega) y un perfil de episodio (`Trackwright/profile.toml`), resueltos integrado < programa < episodio; herramientas para leerlos y para escribirlos tras aprobación.
- **Identidad de las pistas (visto en TW-1604):** los uid de las pistas no son únicos entre proyectos hechos con la misma plantilla (el episodio del usuario y el proyecto de pruebas comparten uno), así que un perfil de programa nombra las pistas por nombre; los uid, solo dentro de un proyecto (`state.json`).
- **Perfiles de entrega (investigación):** Apple Podcasts (RSS), Spotify, YouTube e iVoox, cada uno con objetivo de sonoridad y tolerancia, techo de true peak, códec, canales, frecuencia de muestreo y bitrate **solo como los publica la plataforma**, con la URL y la fecha de consulta. Una plataforma sin número publicado no recibe ninguno (por ejemplo, una plataforma que normaliza por su cuenta quizá solo reciba un techo). Otros servicios cuando el usuario los nombre.

### TW-1608 Análisis ligados a una versión del audio

- **Estado:** hecho (2026-11-15), comprobado en directo (ver el registro de verificación; en un episodio de 1,07 GB el hash tarda 0,39 s y la sonoridad 12,25 s): `trackwright/analysis/cache.py` (identidad del archivo con el SHA-256 recordado en `hashes.json` por ruta, tamaño y fecha de modificación; un JSON por resultado con clave de análisis, hash y parámetros) y las tres herramientas de análisis devolviendo `source` (archivo, hash, rango del proyecto, `project_saved_after` según las fechas de los `.cpr` de la carpeta) y `cache` (`hit`, `stored`, `off`); las dos skills nombran la exportación y piden otra cuando el proyecto se guardó después. Tests en `tests/unit/test_analysis_cache_tw1608.py`
- **Alcance:** cada resultado de análisis anota el archivo, su hash, su rango del proyecto y los parámetros; caché en `Trackwright/analysis/`; una skill dice de qué exportación salen sus números y pide una exportación nueva cuando el proyecto cambió después (cortes, procesado, automatización).

### TW-1609 Contrato común de las skills

- **Estado:** hecho (2026-11-15): el contrato en `docs/manual/07-skill-contract.es.md` (secciones Requires, Inputs, Workflow con las siete fases, Safety, Outputs, Ownership), comprobado por `contract_problems` en `tests/unit/test_plugin.py`; `cubase_workspace` ganó `record` y `forget` (y `status` lista los elementos) para que las skills sean dueñas de lo que crean; `podcast-silence-trim` (que ahora usa los valores de edición del perfil y nunca corta un rango protegido) y `noise-gate` (que registra su puerta como elemento `plugin` y la ajusta al repetirse) reescritas según el contrato
- **Alcance:** todas las skills de podcast tienen las mismas secciones (Requires, Inputs, Workflow: inspeccionar, analizar, proponer, preescuchar, aprobar, aplicar, verificar; Safety; Outputs; Ownership); `tests/unit/test_plugin.py` las comprueba; un documento de convenciones compartido en el manual. Las skills existentes (`podcast-silence-trim`, `noise-gate`) se adaptan.

## Fase 2 — Sesión, control de calidad y entrega

### TW-1610 Skill `podcast-session-audit`

- **Estado:** hecho (2026-11-15), probado en directo en el proyecto de pruebas (ver el registro de verificación; falta una ejecución en un episodio real con los roles del usuario): la skill (contrato de TW-1609) y la herramienta `cubase_track_edges` (bordes de eventos y extensión de una pista, cursor y selección devueltos a su sitio); `cubase_profile resolve` devuelve además `episode`, la capa del episodio tal como está guardada, para que una skill escriba el perfil del episodio sin copiar en él los valores del programa. Tests en `tests/unit/test_track_edges_tw1610.py`
- **Alcance:** inventario de pistas (tipo, mute, solo, salida, inserciones, bordes de eventos y la extensión del episodio), roles confirmados por el usuario y guardados en el perfil del episodio (nunca deducidos de un nombre ni de que sea estéreo), rangos protegidos y un informe de capacidades (lo que la API no puede ver: automatización, ganancia de los eventos, marcadores del usuario). Solo lectura salvo el perfil, tras aprobación.

### TW-1611 Skill `podcast-final-qc`

- **Estado:** pendiente (necesita TW-1603, TW-1607)
- **Alcance:** comprobaciones de solo lectura sobre el archivo entregado o una exportación nueva: se abre, formato, canales, frecuencia de muestreo, duración frente al rango aprobado; sonoridad y true peak frente al perfil elegido; pausas largas; cambios bruscos de nivel entre secciones; una lista de momentos para escuchar. Comprobaciones objetivas separadas de los avisos; lo que no se puede verificar con una mezcla (pistas excluidas) se lista como manual. Informe en `Trackwright/reports/`.

### TW-1612 Experimento: alcanzar un objetivo de sonoridad en Elements

- **Estado:** pendiente (necesita TW-1601, TW-1603)
- **Alcance:** en un episodio completo: ganancia en el fader de Stereo Out (su rango), Brickwall Limiter o Maximizer en Stereo Out (techo, liberación), medidos tras exportar; cuánto sube el true peak al codificar en MP3; cuántas vueltas de medir y ajustar hacen falta.

### TW-1613 Skill `podcast-delivery`

- **Estado:** pendiente (necesita TW-1611, TW-1612)
- **Alcance:** elegir un perfil, exportar y medir, calcular si la ganancia sola alcanza el objetivo sin romper el techo (el ejemplo −21 → −16 LUFS de la lluvia de ideas); si no, proponer un limitador (y avisar cuando la ganancia necesaria pide procesar la dinámica antes); aplicar tras aprobación; exportar el máster y medirlo; exportar el formato de entrega con el usuario; decodificar y validar el archivo entregado; informe. Como mucho tres vueltas; después, parar y explicar.

## Fase 3 — Música

### TW-1614 Planificador de ducking

- **Estado:** pendiente (necesita TW-1604)
- **Alcance:** funciones puras de regiones de voz a una envolvente de ganancia: atenuación, pre-roll antes de la primera palabra, hold, unión de huecos más cortos que un umbral, curva de recuperación, rangos protegidos y excepciones por región («no subas la música entre estas dos frases»); render de la música atenuada. Los valores de la lluvia de ideas son puntos de partida, no normas.
- **Tests:** envolventes sobre regiones sintéticas; continuidad (sin clics), atenuación exacta.

### TW-1615 Skill `podcast-music-ducking`

- **Estado:** pendiente (necesita TW-1605, TW-1606, TW-1614)
- **Alcance:** exportar juntas las pistas de voz, y la música; planificar; preescuchas en primeras palabras, pausas, cambios de sección y finales; aplicar importando la música atenuada y silenciando la original; las peticiones con palabras cambian el plan guardado y vuelven a renderizar solo los tramos afectados. Aceptación: la voz sigue clara y las recuperaciones no distraen, a juicio del usuario.

### TW-1616 Experimento: ducking dentro de Cubase

- **Estado:** pendiente (necesita TW-1601)
- **Alcance:** (a) una preparación guiada del sidechain que completa el usuario, si el Compressor de Elements lo permite; (b) la envolvente planificada escrita grabando automatización en tiempo real en un parámetro propio de la skill, con la precisión medida. Decidir si alguna de las dos pasa a ser un segundo modo de `podcast-music-ducking`.

### TW-1617 Análisis de bucles y finales

- **Estado:** pendiente
- **Alcance:** estimación de tempo y pulso, secciones repetidas (autosimilitud), regiones de bucle candidatas con una calidad de la unión, puntos de bucle en los pulsos y cerca de pasos por cero, duración del fundido cruzado; detección del final y su cola; render de una cama de una duración dada que conserva el final. Validado con camas reales que aporte el usuario.

### TW-1618 Skill `podcast-music-bed`

- **Estado:** pendiente (necesita TW-1606, TW-1617)
- **Alcance:** modos: un bucle preparado, una región que aprueba el usuario o regiones propuestas por el análisis (el usuario siempre aprueba); sin time stretch; preescuchas de cada unión; marcadores en las uniones dudosas; importación del resultado. No se impone un fundido cruzado: un bucle bien hecho puede no necesitarlo.

### TW-1619 Skill `podcast-section-transitions`

- **Estado:** pendiente (necesita TW-1604, TW-1606, TW-1620)
- **Alcance:** una cortinilla aprobada o una entrada/salida de música en un marcador o tiempo, nunca encima del final de la última frase, respetando su cola, fundidos renderizados fuera de línea; «la transición habitual» sale del perfil del programa.

### TW-1620 Biblioteca de audio con licencias

- **Estado:** pendiente
- **Alcance:** una carpeta local (o varias) con un archivo lateral por elemento: procedencia, licencia, atribución, usos permitidos, etiquetas; índice y búsqueda (`trackwright library` y una herramienta MCP); los elementos sin nota de licencia no se ofrecen. Nunca se descarga nada.

### TW-1621 Skill `podcast-sound-effects`

- **Estado:** pendiente (necesita TW-1606, TW-1620)
- **Alcance:** buscar en la biblioteca, colocar un efecto en un punto aprobado, ganancia y fundidos, solapes; procedencia y licencia anotadas en el episodio (`Trackwright/credits`).

## Fase 4 — Voz

### TW-1622 Skill `podcast-dialogue-leveling`

- **Estado:** pendiente (necesita TW-1603, TW-1604, TW-1606)
- **Alcance:** sonoridad con puerta de voz por región y por persona, distinguiendo diferencias entre personas, entre tomas y dentro de una intervención; ganancias acotadas (±6 dB por defecto) que conservan susurros, risas y énfasis; pistas niveladas renderizadas e importadas; compresión moderada opcional con Compressor; fragmentos representativos comparados antes y después. Nunca todas las frases al mismo valor.

### TW-1623 Diagnóstico de la voz

- **Estado:** pendiente
- **Alcance:** análisis puros, cada uno con su confianza: espectro a largo plazo, zumbido (50/60 Hz y armónicos), ruido de banda ancha, plosivas (ráfagas de baja frecuencia), clics de boca (transitorios cortos), sibilancia (energía en la banda alta), reverberación (caída tras el final de las frases). Validados en episodios completos.

### TW-1624 Skill `podcast-voice-cleanup`

- **Estado:** pendiente (necesita TW-1623)
- **Alcance:** un diagnóstico por problema; tratamiento solo con plugins instalados (descubrimiento dinámico como en `noise-gate`): muescas con StudioEQ para el zumbido, paso alto en el canal para el retumbe y las plosivas, DeEsser para la sibilancia, Gate o la skill `noise-gate` para el ruido en las pausas; clics, reverberación y sonidos intrusivos se informan para revisión o para otra herramienta. Ajustes suaves y preescuchas; los artefactos se nombran como riesgo.

### TW-1625 Skill `podcast-voice-tone`

- **Estado:** pendiente (necesita TW-1601 punto 8, TW-1623)
- **Alcance:** objetivos en lugar de presets (retumbe, resonancias molestas, cuerpo e inteligibilidad, dinámica, sibilancia) con StudioEQ o el EQ del canal, Compressor y DeEsser; cada cambio anota qué problema corrige; A/B reproduciendo un rango en ciclo en Cubase con Bypass alternado y la sonoridad igualada.

## Fase 5 — Edición

### TW-1626 Experimento: fundidos y room tone

- **Estado:** pendiente
- **Alcance:** si los fundidos en los puntos de corte se pueden hacer con comandos de teclado enlazados en el script (y la versión del script, el permiso y el reinicio que harían falta) o hay que renderizarlos; room tone extraído de pasajes tranquilos de una voz e importado para cubrir un hueco, y cuánto se notan las uniones.

### TW-1627 Skill `podcast-edit-smoothing`

- **Estado:** pendiente (necesita TW-1606, TW-1626)
- **Alcance:** puntos de corte de ejecuciones anteriores de `podcast-silence-trim` (`state.json`) o de los bordes de los eventos; cambios de ambiente a cada lado de un corte; room tone en lugar de silencio digital donde cae el fondo; fundidos según TW-1626; un archivo de preescucha con todos los cortes seguidos.

### TW-1628 Skill `podcast-sync-sources`

- **Estado:** pendiente (necesita TW-1605)
- **Alcance:** solo diagnóstico: desfase en varios puntos por correlación cruzada de dos pistas (una grabación local y una remota, o un respaldo), desfase fijo frente a deriva y qué corregir a mano; principio y final comprobados de nuevo cuando el usuario lo corrige.

### TW-1629 Skill `podcast-spatial-balance`

- **Estado:** pendiente
- **Alcance:** posiciones de panorama revisadas frente al perfil del programa (voces, música y efectos por separado), panoramas accidentales señalados; compatibilidad mono a partir de una exportación sumada en Python (diferencia de sonoridad, correlación) y un archivo de preescucha mono; panoramas creativos solo con instrucción explícita.

### TW-1630 Transcripción local

- **Estado:** pendiente
- **Alcance:** un extra opcional (`trackwright[transcribe]`) con un modelo Whisper local (whisper.cpp o faster-whisper, elegido con un experimento en episodios completos: velocidad, marcas de tiempo por palabra, castellano e inglés); el modelo se descarga solo cuando el usuario acepta; las transcripciones se guardan en `Trackwright/analysis/` ligadas a la exportación de la que salen.

### TW-1631 Skill `podcast-edit-review`

- **Estado:** pendiente (necesita TW-1604, TW-1630)
- **Alcance:** una lista de decisiones con tiempos, motivo y confianza: tomas repetidas, arranques fallidos, pausas inusualmente largas, muletillas, indicaciones de grabación, rangos que el usuario marcó para quitar (dados como tiempos o rangos en ciclo, porque los marcadores no se pueden leer); la acción por defecto es «revisar», nunca «cortar»; los cortes aprobados se aplican en todas las pistas, del último al primero, y se invalidan los análisis afectados.

### TW-1635 Corrección: `cubase_record_automation` tras TW-1601

- **Estado:** pendiente
- **Visto en TW-1601:** (1) tras una grabación que indicó `complete: true`, la primera exportación salió plana y el fader quedó en −1,43 dB en lugar del valor del último punto; una exportación posterior, con la curva presente y R activado, sí la tenía. (2) El dry run indica el título del parámetro de la pista **seleccionada** (`TW1507 / Volumen`) para otra pista de destino (`TW1501`).
- **Alcance:** encontrar la causa de (1) con un test que la reproduzca (modo de lectura tras grabar, valor final del fader); indicar en la salida el estado de lectura de la pista; dejar el fader en el último punto; tomar el título del dry run de la pista de destino. La tolerancia de la relectura debe tener en cuenta el tick de ~110 ms (sus propias lecturas llegan un tick tarde).

## Fase 6 — Integración

### TW-1632 Sesiones de prueba y plan de pruebas en directo

- **Estado:** pendiente
- **Alcance:** un generador de sesiones de podcast sintéticas (voces hechas de sílabas, una cama musical, cortinillas, ruido, una segunda fuente que deriva) para tests unitarios y en directo, y un plan de pruebas en directo por skill en el proyecto de pruebas y en episodios que indique el usuario.

### TW-1633 Más allá del podcast

- **Estado:** pendiente
- **Alcance:** perfiles de entrega para otras producciones habladas (audiolibros, locuciones, diálogo de vídeo), investigados con sus fuentes; skills parametrizadas por perfil en lugar de atadas a los números del podcast; decidir si se mantiene el prefijo `podcast-` o se añaden nombres generales.

### TW-1634 Documentación y publicación

- **Estado:** pendiente
- **Alcance:** un capítulo del manual «Skills de producción de podcast» en ambos idiomas, README, registro de cambios y una publicación cuando las skills de cada fase estén verificadas (cada fase se puede publicar por separado).

## Fuera de alcance

- Producir un episodio entero sin intervención.
- Time stretch, separación de locutores en una sola pista, descargar audio de Internet.
- Funciones de Artist y Pro como requisito (SuperVision, Audio Alignment, exportación por canal, VocalChain).
- Cualquier cambio de enrutamiento por parte de Trackwright.
