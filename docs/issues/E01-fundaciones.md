# E01 — Fundaciones del proyecto

Objetivo: dejar un esqueleto de proyecto reproducible, con calidad automática, logs, configuración y errores comunes, sobre el que construir el resto.

## TW-0101 Esqueleto del proyecto con uv

- **Estado:** hecha
- **Alcance:**
  - Repositorio git `trackwright` (rama `main`, sin remoto).
  - Paquete de distribución `trackwright-mcp`, módulo `trackwright` y ejecutable `trackwright`.
  - `pyproject.toml` con backend `uv_build` y Python ≥ 3.14.
  - Dependencias: `mcp`, `mido`, `python-rtmidi`, `loguru` y `pydantic`.
  - Dependencias de desarrollo: `pytest`, `pytest-cov`, `ruff`, `mypy` y `anyio`.
  - `.gitignore`.
- **Aceptación:**
  - `uv sync` crea `.venv`.
  - `uv run trackwright --help` funciona.
  - No hay `requirements.txt`.

## TW-0102 Calidad automática

- **Estado:** hecha
- **Alcance:**
  - Configuración de ruff (lint y formato), mypy `strict` y cobertura con `fail_under = 85`.
  - Script `scripts/check.sh`, que se ejecuta con `uv run`, para lanzar todo de una vez.
- **Aceptación:** `scripts/check.sh` termina con código 0 en un árbol limpio.

## TW-0103 Logs con loguru

- **Estado:** hecha
- **Alcance:** módulo `trackwright.logging`.
  - Configura loguru con nivel, archivo opcional y formato.
  - **Nunca escribe en stdout**, porque con transporte stdio stdout pertenece al protocolo MCP.
  - Redirige a loguru los logs de `logging` de las dependencias (`mcp`, `anyio`), mediante un *intercept handler*.
- **Aceptación:**
  - Un test demuestra que un log de una dependencia acaba en el sumidero de loguru.
  - Un test demuestra que tras `configure_logging` no se escribe nada en stdout.

## TW-0104 Configuración

- **Estado:** hecha
- **Alcance:** `trackwright.config`, con modelos pydantic.
  - Origen: archivo TOML en `~/.config/trackwright/config.toml`, o la ruta de `TRACKWRIGHT_CONFIG`.
  - Secciones:
    - `[bridge]`: nombres de puerto, directorio del socket y timeout;
    - `[writes]`: `enabled` (por defecto `false`) y `allowed_tracks`;
    - `[logging]`.
  - Valores por defecto seguros: **solo lectura** mientras no se habiliten las escrituras.
- **Aceptación:**
  - Tests de valores por defecto, de carga desde archivo, de variable de entorno y de rechazo de valores inválidos (timeout fuera de rango, claves desconocidas).

## TW-0105 Jerarquía de errores

- **Estado:** hecha
- **Alcance:** `trackwright.errors`, con `TrackwrightError(code, message, details)` y sus subclases:
  - transporte: `TransportError`;
  - protocolo: `ProtocolError`;
  - tiempo de espera: `RequestTimeoutError`, que indica si el resultado es desconocido;
  - sesión: `StaleSessionError`;
  - host: `HostError`, con el código del script;
  - puente: `BridgeUnavailableError`;
  - política y referencias: `PolicyError`, `NotFoundError`, `StaleReferenceError`, `PreconditionFailedError`.
- **Aceptación:**
  - Cada error se serializa a un diccionario estable.
  - El servidor MCP lo convierte en un error de herramienta legible (E04).
