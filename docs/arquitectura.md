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
- El script no guarda proyectos ni controla la reproducción.
