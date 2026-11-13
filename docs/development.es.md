# Guía de desarrollo

[English](development.md) · **Español**

## Normas

- **Solo uv.**
  - Dependencias: `uv add <paquete>`, o `uv add --dev <paquete>` para las de desarrollo.
  - Ejecución: `uv run <comando>`.
  - Prohibidos: `pip`, `uv pip`, `python -m venv`, `virtualenv`, `pipx`, `conda`, `poetry` y `requirements.txt`.
- **Logs con loguru** (`from loguru import logger`).
  - El módulo `logging` solo se toca en `trackwright/logs.py`, para redirigir el de las dependencias.
  - Nunca se escribe en stdout, que pertenece al protocolo MCP con `serve`.
- **Calidad obligatoria:** ruff (lint y formato), mypy `strict` y cobertura ≥ 85 %.
- **Issues:** cada cambio parte de una issue en [`docs/issues/`](issues/README.es.md), que se cierra con su commit.

## Comandos

```sh
uv sync                         # entorno
scripts/check.sh                # todo: lint, formato, tipos y tests con cobertura
uv run ruff check src tests     # lint
uv run ruff format src tests    # formatear
uv run mypy                     # tipos (strict)
uv run pytest                   # tests (los de integración se saltan solos)
uv run pytest --cov             # con cobertura (falla por debajo del 85 %)
uv run pytest -m node           # solo los del script de Cubase (necesita node)
uv build                        # wheel y sdist en dist/
```

## Estructura

```text
src/trackwright/
  cli.py            # comandos: bridge, serve, setup, doctor, script, ping, config...
  installer.py      # trackwright setup: instalación guiada con confirmación por paso (TW-1301)
  doctor.py         # diagnóstico de la cadena (doctor y último paso de setup)
  config.py         # configuración (TOML + entorno, pydantic)
  logs.py           # loguru, stderr, intercepción de logging
  errors.py         # jerarquía de errores con código estable
  protocol.py       # tramas SysEx "TW" y reensamblado
  coremidi.py       # puertos virtuales CoreMIDI con ctypes (por defecto en macOS; sin compilar)
  transport.py      # interfaz Transport y transporte alternativo mido + python-rtmidi
  host.py           # cliente del script: correlación, sesiones, timeouts
  ops.py            # operaciones del script (lecturas, escrituras)
  bridge.py         # daemon con socket Unix y su cliente
  hostport.py       # puerto hacia Cubase usado por el servidor (BridgeHost)
  fake.py           # FakeCubase: simulador para tests y --simulate
  commands.py       # comandos de Cubase con su clase observada
  core/             # dominio: referencias, política, modelos, servicio
  server.py         # servidor MCP: registro de las 21 herramientas
  cubase/           # Trackwright_Bridge.js e instalador
tests/
  unit/             # tests unitarios (simulador, sockets reales en /tmp)
  contract/         # cliente MCP en memoria contra el servidor
  script/           # el script real ejecutado con Node.js y una API emulada
  e2e/              # proceso real por stdio y construcción del paquete
  integration/      # contra Cubase real, de forma voluntaria
```

## Tipos de test

| Tipo | Dónde | Qué demuestra | Cuándo se ejecuta |
|---|---|---|---|
| Unitarios | `tests/unit` | Cada módulo; el servicio contra `FakeCubase` | Siempre |
| Contrato MCP | `tests/contract` | Herramientas, esquemas, anotaciones y errores vistos por un cliente MCP | Siempre |
| Script | `tests/script` | El script ES5 real habla el mismo protocolo que Python | Si hay `node` |
| Extremo a extremo | `tests/e2e` | El ejecutable arranca por stdio; el wheel incluye el script | Siempre (`slow`) |
| Integración | `tests/integration` | Comportamiento con Cubase real | `TRACKWRIGHT_INTEGRATION=1` |

`FakeCubase` reproduce los comportamientos verificados en la POC. Un test que pasa contra el simulador **no** prueba nada sobre Cubase real: para eso están los tests de integración.

## Tests de integración

Necesitan el puente en marcha y Cubase abierto con un proyecto desechable.

```sh
TRACKWRIGHT_INTEGRATION=1 uv run pytest tests/integration -v
TRACKWRIGHT_INTEGRATION=1 TRACKWRIGHT_ALLOW_WRITES=1 TRACKWRIGHT_TEST_TRACK="POC-TEST" uv run pytest tests/integration -v
```

Las escrituras se restauran al terminar. Estos tests usan tu configuración real: no aplican el aislamiento de `tests/conftest.py`.

## Añadir una herramienta

1. **Issue** en la épica correspondiente, con la evidencia de runtime en la que se apoya.
2. Si necesita una operación nueva del script:
   - añádela en `cubase/Trackwright_Bridge.js`;
   - añádela en `ops.py`;
   - impleméntala en `fake.py`, con la misma forma de resultado;
   - cúbrela en `tests/script/test_script_node.py`. El test `test_script_ops_match_python_ops` falla si las listas no coinciden.
3. **Lógica** en el mixin adecuado de `core/`: `reading.py`, `writing.py` o `commanding.py`.
   - Las escrituras usan `dry_run`, la política y la verificación por relectura.
4. **Modelo de salida** en `core/models.py`.
5. **Registro** en `server.py`, con descripción y anotaciones (`READ`, `NAVIGATE`, `WRITE` o `DESTRUCTIVE`).
6. **Tests:** unitarios del servicio y de contrato.
7. **Documentación:** una sección en `docs/manual/04-tools.md` y la misma en su traducción, `docs/manual/04-tools.es.md`. `tests/unit/test_docs.py` falla si falta. Todo documento se escribe en inglés (`X.md`) con su traducción al castellano (`X.es.md`), y se actualizan a la vez.
8. `scripts/check.sh` en verde y commit que cite la issue.

## Cambiar el script de Cubase

- Incrementa `SCRIPT_VERSION` en el script; los tests comprueban la versión.
- Cubase no recarga los scripts por sí mismo: instala con `uv run trackwright script install --apply` y reinicia Cubase.
- Valida con los tests de integración antes de dar el cambio por bueno.
