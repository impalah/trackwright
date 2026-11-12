# E02 — Comunicación con Cubase

Objetivo: transportar peticiones y respuestas entre Python y el script MIDI Remote de forma fiable, con la robustez verificada en el hito H de la POC.

Evidencia de la POC: `docs/protocol.md` y `findings.md`, secciones 8 a 10 (reconexión, timeouts, duplicados, sesiones, Identity Request).

## TW-0201 Protocolo SysEx

- **Estado:** pendiente
- **Alcance:** `trackwright.protocol`.
  - Trama `F0 7D 54 57 <ver> <seq_hi> <seq_lo> <idx> <count> <payload ASCII> F7`, con la marca **`TW`** (0x54 0x57). Es distinta de la de la POC (`CP`), para que no se confundan.
  - Fragmentos de 240 bytes como máximo, y 64 fragmentos por mensaje.
  - Reensamblado desordenado, con duplicados ignorados, 16 mensajes pendientes como máximo y caducidad de 5 s.
  - Payload JSON en ASCII, con `\uXXXX` para los caracteres no ASCII.
- **Aceptación:**
  - Tests de ida y vuelta (incluidos Unicode y el tamaño máximo).
  - Tests de rechazo: bytes > 127, cabecera corta, versión, índices, recuentos y tramas ajenas como el Identity Request `F0 7E 7F 06 01 F7`.
  - Tests de caducidad y límite de pendientes.

## TW-0202 Transporte MIDI virtual

- **Estado:** pendiente
- **Alcance:**
  - `trackwright.transport.MidiTransport`: mido + rtmidi, con dos puertos virtuales de CoreMIDI, `Trackwright To Cubase` y `Trackwright From Cubase`.
  - Contadores de tramas enviadas, recibidas y ajenas.
  - Rechaza abrir si ya existen puertos con esos nombres (otro puente en marcha).
- **Aceptación:**
  - Tests con un mido simulado: apertura, envío, recepción, filtrado de mensajes que no son SysEx y conflicto de nombres.
  - Una prueba manual con CoreMIDI real queda documentada en el manual de resolución de problemas.

## TW-0203 Cliente del host

- **Estado:** pendiente
- **Alcance:** `trackwright.host.HostClient`.
  - Correlación por `rid`.
  - Timeout por petición; las escrituras tienen resultado desconocido y **no se reintentan**.
  - Registro de respuestas tardías y no solicitadas.
  - Negociación de sesión (`hello`) y renegociación automática ante `STALE_SESSION` **solo en lecturas**.
  - Escrituras serializadas.
- **Aceptación:** tests con un transporte simulado que reproduce:
  - correlación concurrente;
  - timeout de lectura y de escritura;
  - respuesta tardía sin atribución errónea;
  - sesión caducada;
  - duplicados.

## TW-0204 Puente (daemon) e IPC local

- **Estado:** pendiente
- **Alcance:**
  - `trackwright.bridge`: proceso de larga vida, dueño de los puertos y del `HostClient`.
  - Servidor de Unix socket en `$TMPDIR/trackwright-<uid>/bridge.sock`, con directorio 0700 y socket 0600. **Sin puerto de red.**
  - Petición: una línea JSON de 64 KiB como máximo.
  - Lista blanca de operaciones y validación del timeout (0,05–30 s).
  - Operación local `bridge.status`.
  - Cliente `BridgeClient`, que el servidor MCP usa para hablar con el puente.
- **Aceptación:** tests con un socket real en un directorio temporal y un host simulado:
  - permisos;
  - lista blanca;
  - línea demasiado larga;
  - JSON inválido;
  - puente no disponible;
  - segundo puente sobre el mismo socket.
