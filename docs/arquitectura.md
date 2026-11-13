# Arquitectura

## Componentes

```text
┌──────────────┐  stdio (MCP)   ┌────────────────────┐  Unix socket 0600   ┌─────────────────────┐
│ Cliente MCP  │ ─────────────► │ trackwright serve  │ ──────────────────► │ trackwright bridge  │
│ (Claude)     │ ◄───────────── │ MCPServer          │ ◄────────────────── │ HostClient          │
└──────────────┘                │ CubaseService      │  JSON por línea     │ MidiTransport       │
                                │ WritePolicy        │                     └─────────┬───────────┘
                                └────────────────────┘                               │ SysEx "TW"
                                                                                     │ puertos virtuales CoreMIDI
                                                                           ┌─────────▼───────────┐
                                                                           │ Cubase              │
                                                                           │ Trackwright_Bridge.js│
                                                                           │ DirectAccess, Plugin│
                                                                           │ Manager, comandos   │
                                                                           └─────────────────────┘
```

| Componente | Responsabilidad |
|---|---|
| `trackwright serve` | Servidor MCP por stdio. Uno por sesión del cliente. Contiene la lógica de las herramientas (`core/`) y la política de escritura. |
| `trackwright bridge` | Proceso de larga vida y **único dueño** de los puertos MIDI. Correlaciona peticiones y respuestas, gestiona la sesión del script y nunca reintenta escrituras. |
| `Trackwright_Bridge.js` | Script ES5 dentro de Cubase. Responde en `mOnSysex` las operaciones sin DirectAccess y encola el resto para `page.mOnIdle`, que es donde está disponible `activeMapping`. |

## Flujo de una petición

Ejemplo: `cubase_set_track_mix(track="POC-TEST", mute=true, dry_run=false)`.

1. `server.py` recibe la llamada y la ejecuta en un hilo de trabajo, porque la petición es bloqueante.
2. `CubaseService.set_track_mix` resuelve la pista con `da.channels` sobre el mezclador completo, deduplicado. Después lee el valor actual (`da.param.get`), comprueba la política (`WritePolicy.check_track`) y escribe con `da.param.set`.
3. `BridgeHost` envía cada operación al puente por el socket. El puente la entrega al `HostClient`, que la fragmenta en tramas SysEx y espera la respuesta con el mismo `rid`.
4. El script encola la escritura, la ejecuta en el siguiente ciclo de idle (unos 112 ms), relee el valor y responde.
5. El servicio compara el valor releído con el pedido y devuelve `WriteOut(verified=true)`.

## Decisiones y la evidencia que las respalda

La evidencia está en `cubase-mcp-poc/docs/findings.md` y `progress.md`.

| Decisión | Motivo |
|---|---|
| Puente separado del servidor MCP | Los puertos virtuales tienen nombre fijo y solo puede haber un dueño; varias sesiones MCP los comparten a través del puente. Cubase vuelve a conectar solo si el puente se reinicia (verificado). |
| Sesión fijada durante cada herramienta | El puente renegocia la sesión de forma transparente en las lecturas; sin el fijado, una escritura posterior a una recarga podría llevar un identificador viejo que ahora nombra a otro objeto (hallazgo TW-1001). |
| Referencias opacas con sesión y huella | Los identificadores internos se reutilizan para otros objetos tras recargar el script (verificado: el ID 550 pasó de Compressor a Input Filter). |
| Selectores `uid:` para las pistas | `getObjectUniqueIDString` del canal se mantuvo entre reinicios (verificado). |
| DirectAccess sobre `mMixConsole` | Da acceso a todas las pistas sin seleccionarlas. Los identificadores valen en ambas instancias (verificado). |
| Deduplicación del mezclador | El último hijo de «VST Mixer» repite el último canal (verificado dos veces). |
| Escrituras sin reintento y plazo único | Tras un timeout, la escritura pudo ejecutarse (verificado con respuestas tardías). El tiempo de espera del cerrojo de escritura y la renegociación cuentan dentro del plazo; si el cerrojo no se libera a tiempo, `BUSY` sin enviar. |
| Supresión de duplicados en curso, en el script | Un duplicado en ráfaga se ejecutaba dos veces; corregido y verificado. |
| Rechazo de escrituras fuera de [0, 1] | Cubase las limita a ese rango; el enrutado (22) no se puede volver a escribir (verificado, con un incidente). |
| Automatización con controles de superficie «tocados» | Escribir el parámetro por DirectAccess mueve el valor pero no graba. Un fader de la superficie enlazado al parámetro, con su estado de toque controlado por el script, sí graba en modo Touch, como un controlador físico (TW-1206 y TW-1207, verificado en Elements). |
| Transporte CoreMIDI con `ctypes` | `python-rtmidi` solo se distribuye como código fuente para macOS y exige compilarlo (Xcode). Con `ctypes` sobre CoreMIDI, el paquete es Python puro. El transporte mido + rtmidi se conserva como alternativa (`[bridge] backend`). Verificado con Cubase (TW-1302). |
| Clases de comando | Los comandos no devuelven resultado; unos abren diálogos y otros actúan sobre la selección de la interfaz (verificado). |
| Política de escritura con solo lectura por defecto | El modelo puede cometer errores: el usuario decide qué se puede tocar. |
| Simulador `FakeCubase` | Tests rápidos y reproducibles; un modo `--simulate` para aprender sin riesgo. Nunca cuenta como evidencia sobre Cubase. |

## Rendimiento

Medido en la POC:

| Operación | Coste |
|---|---|
| Responder en `mOnSysex` (`hello`, `status`, `transport.get`) | 3–18 ms |
| Una operación DirectAccess | Un ciclo de idle: unos 110 ms en serie |
| `da.channels` (hasta 32 canales con sus parámetros principales) | Un solo ciclo, 134 ms |
| `cubase_list_inserts` | Unos 10 ciclos, alrededor de 1,1 s |

Agrupar operaciones dentro del script es la principal vía de mejora.

## Seguridad

- No se abre ningún puerto de red. El socket está en un directorio privado (0700) bajo `$TMPDIR`, con permisos 0600.
- El puente solo acepta las operaciones de una lista blanca, líneas de 64 KiB como máximo y timeouts acotados.
- Por defecto el servidor es de solo lectura. Las escrituras requieren configuración explícita y siempre se pueden ensayar antes.
- El script solo guarda el proyecto a petición explícita y con su propio permiso (`[writes] save`). Solo inicia la reproducción para grabar automatización, y nunca graba audio.

## Extensión a otros DAW (posible, no implementada)

**Decisión (2026-11-13):** por ahora Trackwright solo controla Cubase y **no se introduce una abstracción de DAW** (YAGNI). Una interfaz deducida de un solo DAW saldría con la forma de ese DAW. Se diseñará cuando haya un segundo DAW concreto, con un prototipo contra su API real, como se hizo con Cubase en la prueba de concepto. Llegado ese momento se acepta romper interfaces internas.

### Qué se puede reutilizar hoy

| Capa | Módulos | Reutilizable |
|---|---|---|
| Transporte MIDI y tramas SysEx | `coremidi.py`, `transport.py`, `protocol.py` | Sí, para cualquier DAW programable por MIDI |
| Puente y canal local | `bridge.py`, arranque automático, sesiones | Casi entero; la lista blanca (`ops.py`) es de Cubase |
| Puerto hacia el DAW | `HostPort.call(op, params)` | La forma sí; el vocabulario (`da.*`, `pm.*`, `cmd.run`) es la API MIDI Remote de Cubase |
| Dominio | `core/` (`CubaseService` y sus mixins) | No: *tags* de DirectAccess, secciones `Inserts` y `Strips`, comandos de Cubase y rodeos a su comportamiento (rangos con la herramienta de rango, sondeo de bordes…) |
| Herramientas MCP | `server.py` | No: recibe un `CubaseService` y las herramientas se llaman `cubase_*` |
| Transversal | `policy.py`, `errors.py`, `core/models.py` | Bastante: política de escrituras, errores con código, modelos de pista y parámetro |
| Instalación | `launcher.py`, `installer.py`, `doctor.py`, secciones `[cubase]` y `[script]` | La estructura; el contenido es de Cubase |

Lo más transferible son los **principios**: ensayo antes de escribir (`dry_run`), verificación por relectura, no reintentar escrituras de resultado incierto, sesión fijada durante cada operación y clasificación de cada comando por su comportamiento observado.

### Ruta prevista

1. Mover lo específico de Cubase a `trackwright/daws/cubase/`: servicio, operaciones, script, lanzador, simulador y comprobaciones de `doctor`.
2. Dejar en el núcleo el transporte, el puente, la política, los errores y los modelos comunes.
3. Un `HostPort` por DAW, con el transporte que su API permita.
4. `server.py` registra las herramientas del DAW configurado (por ejemplo, `[daw] kind = "cubase"`).
5. **Nombres de herramienta con prefijo por DAW** (`cubase_*`, `ableton_*`, `protools_*`), que reflejan lo que cada uno hace de verdad. Un conjunto común pequeño (pistas, transporte, marcadores, mezcla básica) puede añadirse después, con marcas de capacidad.

### Candidatos (sin verificar en este proyecto)

- **Ableton Live:** *Remote Scripts* en Python dentro de Live, sobre su modelo de objetos (pistas, dispositivos, parámetros, clips).
  - Podría reutilizar el transporte SysEx. Las alternativas habituales por OSC/UDP abren un puerto de red, lo que choca con la regla de seguridad.
  - Es fuerte en mezcla y dispositivos y más limitado en la edición de la línea de tiempo (*Arrangement*).
- **Pro Tools:** no tiene scripts MIDI; ofrece **PTSL** (Pro Tools Scripting Library), una API gRPC local.
  - Necesitaría otro `HostPort` y no usaría el puente MIDI.
  - Es fuerte en sesión, pistas, clips, edición, importación y exportación, y más limitado en el control de parámetros de plugins.

Antes de diseñar nada, cada candidato necesita su propia prueba de concepto que mida qué expone de verdad, como `cubase-mcp-poc` hizo con Cubase.
