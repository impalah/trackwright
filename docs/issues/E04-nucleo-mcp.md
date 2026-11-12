# E04 — Núcleo del servidor MCP

Objetivo: la capa común que comparten todas las herramientas. Implementa los principios de `mcp-design.md`.

## TW-0401 Puerto hacia el host y simulador de Cubase

- **Estado:** pendiente
- **Alcance:**
  - Protocolo `HostPort` (`call(op, params, timeout) -> dict`), con dos implementaciones:
    - `BridgeHost`, mediante IPC con el puente;
    - `FakeCubase`, un simulador en memoria que reproduce los comportamientos observados en la POC:
      - árbol del mezclador con el último hijo duplicado;
      - IDs reutilizados al reiniciar;
      - centinelas de objetos eliminados;
      - escrituras limitadas a [0, 1];
      - selección única;
      - comandos de clase `direct`, `dialog` y `confirm`;
      - transporte con formato de compases.
- **Aceptación:** el simulador tiene sus propios tests. Se declara siempre como **simulado**: `capabilities.simulated = true`.

## TW-0402 Referencias opacas y resolución de pistas

- **Estado:** pendiente
- **Alcance:**
  - `TrackRef`: `{uid}`, `{name}` o `"selected"`.
  - Resolución contra `da.channels` (alcance del mezclador, con deduplicación).
  - Errores `TRACK_NOT_FOUND` y `TRACK_AMBIGUOUS`.
  - `ObjectRef`: cadena opaca con la sesión, el ID y una huella (`type` y `uniqueName`). Se valida antes de cada uso:
    - si la sesión ha cambiado o la huella no coincide, `STALE_REF`;
    - si el objeto ya no existe (`children == -1`), `INVALID_OBJECT`.
  - Rutas semánticas dentro de una pista: `insert:N`, `strip:eq` y `channel`.
- **Aceptación:**
  - Tests de resolución: por uid, por nombre, ambiguo, inexistente y seleccionada sin selección.
  - Tests de referencias: válida, sesión distinta, huella distinta (la reutilización de IDs de `findings` 8) y objeto eliminado.

## TW-0403 Política de escritura y ensayo

- **Estado:** pendiente
- **Alcance:**
  - `WritePolicy`, construida desde la configuración:
    - escrituras deshabilitadas → `WRITES_DISABLED`;
    - pista fuera de `allowed_tracks` → `NOT_ALLOWED`.
  - Todas las herramientas de escritura reciben `dry_run` (por defecto `true`) y devuelven el plan sin tocar nada.
  - Las escrituras **nunca se reintentan**. Un timeout se informa como resultado desconocido y se relee el estado si es posible.
- **Aceptación:** tests de cada rama de la política y del ensayo, que verifican que no se llama a ninguna operación de escritura.

## TW-0404 Servidor MCP

- **Estado:** pendiente
- **Alcance:** `trackwright.server`.
  - `MCPServer` con nombre `trackwright` e instrucciones para el modelo: ensayar primero, confirmar con el usuario y explicar los comandos de diálogo.
  - Registro de herramientas.
  - Conversión de `TrackwrightError` en `ToolError` con el formato `CÓDIGO: mensaje`.
  - Transporte stdio con `trackwright serve`.
- **Aceptación:** tests con `mcp.client.Client` en memoria:
  - lista de herramientas, con su nombre y esquemas;
  - llamada correcta;
  - error de herramienta con `is_error`.
