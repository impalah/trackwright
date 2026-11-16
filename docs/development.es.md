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
- **Calidad obligatoria:** ruff (lint y formato, también sobre `experiments/`), mypy `strict` (sobre `src` y `tests`) y cobertura ≥ 95 %. pytest convierte los avisos en errores (un archivo o proceso sin cerrar hace fallar la suite) y detiene un test a los 120 s (pytest-timeout). `uvx pre-commit install` ejecuta ruff y mypy antes de cada commit.
- **Contribuir y seguridad:** [CONTRIBUTING.es.md](../CONTRIBUTING.es.md) y [SECURITY.es.md](../SECURITY.es.md). Dependabot abre cada semana pull requests de actualización para `uv.lock` y las acciones de CI; las dependencias de ejecución tienen un límite superior en la siguiente versión mayor.
- **Convenciones de los tests:** comprobar el **código** del error, no solo la clase de la excepción; esperar a eventos (`tests.support.wait_for`), nunca un `sleep` fijo; los dobles compartidos están en `tests/support.py`, `tests/conftest.py` y `tests/script/node_harness.py`, para que los módulos de test no se importen entre sí. El entramado tiene tests basados en propiedades (Hypothesis) y el script de Cubase una comprobación de sintaxis ES5 (`tests/script/test_es5.py`).
- **Issues:** cada cambio parte de una issue en [`docs/issues/`](issues/README.es.md), que se cierra con su commit.

## Integración continua

Cada push a `main`, cada etiqueta y cada pull request ejecutan `.github/workflows/ci.yml` en GitHub Actions (macOS, porque el transporte por defecto es CoreMIDI): `uv sync --locked`, `make check`, `make test-node`, `make build` y `make dist-check`. Una ejecución en rojo se arregla antes de publicar.

## Comandos

El `Makefile` agrupa las tareas habituales, siempre a través de uv; `make help` las lista:

| Objetivo | Hace |
|---|---|
| `make sync` | `uv sync` |
| `make check` | lint, comprobación de formato, mypy y tests con cobertura (igual que `scripts/check.sh`) |
| `make lint`, `make format`, `make typecheck` | ruff check, ruff fix + format, mypy |
| `make test`, `make test-cov`, `make test-node` | tests, con cobertura, solo los del script de Cubase |
| `make test-integration`, `make test-integration-write TEST_TRACK=…` | contra el Cubase real (opcionales; las escrituras se deshacen, pista por defecto `POC-TEST`) |
| `make build`, `make dist-check` | `uv build` en un `dist/` limpio, y `uvx twine check --strict` |
| `make publish-test`, `make publish` | subir a TestPyPI o PyPI con `uv publish` (necesita `UV_PUBLISH_TOKEN`) |
| `make doctor`, `make ping`, `make bridge`, `make bridge-status`, `make serve-sim` | ejecutar Trackwright |
| `make script-status`, `make script-install`, `make script-install-apply`, `make setup` | el script de Cubase y la instalación guiada |
| `make clean` | borra `dist/`, cachés y archivos de cobertura |

Los comandos de debajo:

```sh
uv sync                         # entorno
scripts/check.sh                # todo: lint, formato, tipos y tests con cobertura
uv run ruff check src tests     # lint
uv run ruff format src tests    # formatear
uv run mypy                     # tipos (strict)
uv run pytest                   # tests (los de integración se saltan solos)
uv run pytest --cov             # con cobertura (falla por debajo del 95 %)
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
  fake/             # FakeCubase, el simulador para tests y --simulate: núcleo, edición, automatización, escrituras, lecturas
  commands.py       # comandos de Cubase con su clase observada
  workspace.py      # la carpeta Trackwright/ dentro de un proyecto: estructura, rutas seguras, state.json, profile.toml
  analysis/         # análisis de audio (numpy, scipy, soundfile): niveles, ruido de fondo, silencios, sonoridad BS.1770; sin Cubase
  jsontypes.py      # JsonObject, el único alias de tipo JSON
  core/             # dominio: servicio (base + mixins), política, modelos, referencias
    tags.py         # tags de parámetros de Cubase por objeto (Channel, Transport, Slot...)
    timefmt.py      # formatos de compases y segundos de los visores de Cubase
  server.py         # servidor MCP: registro de las 45 herramientas
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

`tests/script/test_conformance.py` mantiene honesto al simulador: envía las mismas operaciones al script real (con Node) y a `FakeCubase` y compara las respuestas por estructura, códigos de error y recortes de valores, además de las listas copiadas entre ambos lados (claves de automatización, tags por defecto de los canales, un manejador del simulador por operación). Cuando un test necesite que Cubase se comporte de otra forma, usa `fake.override(op, handler)` en lugar de sustituir métodos privados.

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
   - impleméntala en el paquete `fake/` (lecturas en `reads.py`, escrituras en `writes.py`), con la misma forma de resultado; `tests/script/test_conformance.py` la compara con el script;
   - cúbrela en `tests/script/test_script_node.py`. El test `test_script_ops_match_python_ops` falla si las listas no coinciden.
3. **Lógica** en el mixin adecuado de `core/`: `reading.py`, `writing.py` o `commanding.py`.
   - Las escrituras usan `dry_run`, la política y la verificación por relectura.
4. **Modelo de salida** en `core/models.py`.
5. **Registro** en `server.py`, con descripción y anotaciones (`READ`, `NAVIGATE`, `WRITE` o `DESTRUCTIVE`).
6. **Tests:** unitarios del servicio y de contrato.
7. **Documentación:** una sección en `docs/manual/04-tools.md` y la misma en su traducción, `docs/manual/04-tools.es.md`. `tests/unit/test_docs.py` falla si falta. Todo documento se escribe en inglés (`X.md`) con su traducción al castellano (`X.es.md`), y se actualizan a la vez.
8. `scripts/check.sh` en verde y commit que cite la issue.


## Mutation testing

`make mutation` ejecuta mutmut 3 (con `uv run --with`, no es una dependencia del proyecto) sobre los módulos de seguridad listados en `[tool.mutmut]` de `pyproject.toml`: `protocol`, `core/policy`, `core/refs`, `ops`, `host` y `hostport`. Tarda un par de minutos; ejecútalo antes de publicar, no en cada push. Después:

- `uv run --with mutmut==3.8.1 mutmut results` lista los mutantes supervivientes; `mutmut show <nombre>` muestra uno;
- un superviviente que cambia el comportamiento necesita un test (ver `tests/unit/test_mutation_edges.py` y `test_mutation_host.py`); uno que solo cambia el texto de un mensaje, un argumento de un log o algo equivalente en Python se anota como tal;
- un archivo de tests nuevo para uno de estos módulos debe añadirse a `pytest_add_cli_args_test_selection`, o mutmut no lo ejecuta: en la 0.5.0 faltaban los tests de TW-1502 y TW-1509 y la puntuación parecía del 82 % en lugar del 87 %;
- los tests que arrancan subprocesos o sockets reales (`test_launcher.py`, `test_bridge.py`, `test_robustness_tw1405.py`) hacen fallar a los trabajadores de mutmut: déjalos fuera de `pytest_add_cli_args_test_selection`.

Objetivo: al menos el 85 % de los mutantes muertos en estos módulos. Las puntuaciones de cada ejecución están en el registro de verificación.

## Publicar una versión

1. Actualiza `version` en `pyproject.toml` y el registro de cambios (`CHANGELOG.md` y `CHANGELOG.es.md`); `uv sync` actualiza `uv.lock`. Actualiza la misma versión en el plugin de Claude Code: `version` en `plugins/claude-code/.claude-plugin/plugin.json` y la versión fijada `trackwright==` en `plugins/claude-code/.mcp.json` (si no, falla `tests/unit/test_plugin.py`).
2. `make check`, `make mutation` (ver la sección anterior) y `claude plugin validate plugins/claude-code --strict` y `claude plugin validate . --strict` (la integración continua no puede ejecutarlos: no tiene la CLI `claude`), y commit.
3. Publica (lo hace el usuario, con su propio token):
   ```sh
   UV_PUBLISH_TOKEN="$(security find-generic-password -a "$USER" -s pypi-token -w)" make publish
   ```
   `make publish-test` hace lo mismo contra TestPyPI (entrada del Llavero `testpypi-token`).
4. Etiqueta el commit publicado (del que se construyó `dist/`): `git tag -a vX.Y.Z -m "Trackwright X.Y.Z"`.

Una versión nunca se puede volver a subir, aunque se borre de PyPI.

**Guardar el token en el Llavero de macOS.** Copia el token desde la página de PyPI y ejecuta:

```sh
security add-generic-password -U -a "$USER" -s pypi-token -w "$(pbpaste)"
pbcopy < /dev/null
```

No uses la petición interactiva (`-w` sin valor): solo conserva 128 caracteres y los tokens de PyPI son más largos, así que la subida falla con `403 Invalid or non-existent authentication information`. Tras la primera publicación, usa un token limitado al proyecto `trackwright`.

## Cambiar el script de Cubase

- Incrementa `SCRIPT_VERSION` en el script; los tests comprueban la versión.
- Cubase no recarga los scripts por sí mismo: instala con `uv run trackwright script install --apply` y reinicia Cubase.
- Valida con los tests de integración antes de dar el cambio por bueno.
