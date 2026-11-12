# E03 — Script MIDI Remote de Trackwright

Objetivo: el script ES5 que se ejecuta dentro de Cubase y expone las operaciones verificadas en la POC (script 0.2.2), con identidad propia.

## TW-0301 Port del script de la POC

- **Estado:** pendiente
- **Alcance:** `src/trackwright/cubase/Trackwright_Bridge.js`, que se distribuye como dato del paquete.
  - Fabricante `Trackwright` y dispositivo `Bridge`.
  - Puertos `Trackwright To Cubase` y `Trackwright From Cubase`.
  - Marca SysEx `TW`.
  - Mismas operaciones que la versión 0.2.2:
    - lecturas: `hello`, `ping`, `status`, `capabilities`, `events`, `transport.get` y `cmd.list`;
    - DirectAccess: `da.*`;
    - Plugin Manager: `pm.*`;
    - selección: `sel.step`;
    - transporte: `transport.setTime` y `transport.setTempo`;
    - comandos: `cmd.canPerform` y `cmd.run`.
  - Supresión de duplicados en curso, deduplicación del mezclador y protección del sondeo.
  - Se elimina la opción `raw`, que se verificó que no tiene efecto útil (`findings` 41).
- **Aceptación:**
  - `node --check` pasa sin errores.
  - Carga sin excepciones con una API simulada (TW-0302).

## TW-0302 Pruebas del script con Node.js

- **Estado:** pendiente
- **Alcance:**
  - Arnés en `tests/script/` que emula la API MIDI Remote: página, `mOnIdle`, DirectAccess con un árbol en memoria, Plugin Manager, transporte y comandos.
  - Ejecuta el script real sin Cubase.
  - Un test de pytest (marca `node`) lanza el arnés y valida el protocolo de extremo a extremo con el codificador de Python.
- **Aceptación:**
  - Cubre `hello`, lectura de parámetros, escritura y relectura, `INVALID_OBJECT`, `STALE_SESSION`, duplicado secuencial y en curso, deduplicación del mezclador y rechazo del sondeo no restaurable.
  - Se salta, con un motivo claro, si `node` no está instalado.

## TW-0303 Instalación del script

- **Estado:** pendiente
- **Alcance:** comando `trackwright script install`.
  - Por defecto, **ensayo**: muestra el destino (`~/Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/trackwright/bridge/Trackwright_Bridge.js`), si existe y si coincide.
  - Con `--apply`, copia el script.
  - `trackwright script status` compara el script instalado con el del paquete.
- **Aceptación:**
  - Tests con un directorio de destino temporal: ensayo, copia, ya actualizado y versión distinta.
  - Nunca escribe fuera del destino.
