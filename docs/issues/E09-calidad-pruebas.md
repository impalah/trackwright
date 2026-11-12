# E09 — Calidad y pruebas

## TW-0901 Tests unitarios y cobertura ≥ 85 %

- **Estado:** hecha
- **Alcance:**
  - Tests en `tests/unit/` para cada módulo.
  - `uv run pytest --cov` falla si la cobertura total baja del 85 %.

## TW-0902 Tests de contrato MCP

- **Estado:** hecha
- **Alcance:** `tests/contract/`.
  - Cliente MCP en memoria (`mcp.client.Client`) contra el servidor con `FakeCubase`.
  - Lista de herramientas esperada y anotaciones de solo lectura o destructiva.
  - Una llamada correcta y una de error por herramienta.

## TW-0903 Tests del script con Node.js

- **Estado:** hecha
- **Alcance:** ver TW-0302 (marca `node`).

## TW-0904 Tests de integración opcionales contra Cubase

- **Estado:** hecha
- **Alcance:** `tests/integration/`.
  - **Lecturas** con `TRACKWRIGHT_INTEGRATION=1`: puente en marcha y Cubase abierto.
  - **Escrituras reversibles**, solo con además `TRACKWRIGHT_ALLOW_WRITES=1` y una pista que el usuario indique en `TRACKWRIGHT_TEST_TRACK`. Cada escritura se restaura.
- **Aceptación:** sin esas variables se saltan, con un motivo claro.

## TW-0905 Coherencia de la documentación

- **Estado:** hecha
- **Alcance:**
  - Un test comprueba que cada herramienta registrada aparece en `docs/manual/04-herramientas.md`.
  - Un test comprueba que cada clave de configuración aparece en `docs/manual/03-configuracion.md`.

## TW-0906 Puesta en marcha desde el paquete

- **Estado:** hecha
- **Alcance:** `tests/e2e/test_package_build.py` construye el wheel con `uv build` y comprueba que incluye el script de Cubase, `py.typed` y el ejecutable `trackwright` (marca `slow`).
- **Añadido:** `tests/e2e/test_stdio_server.py` arranca el proceso real `trackwright serve --simulate` y le habla un cliente MCP por stdio. Demuestra que los logs (incluso en DEBUG) no contaminan stdout.
