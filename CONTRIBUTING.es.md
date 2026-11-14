# Contribuir a Trackwright

[English](CONTRIBUTING.md) · **Español**

Gracias por ayudar. Trackwright controla un Cubase real, así que las normas de abajo tratan tanto de no estropear el trabajo del usuario como del estilo del código.

## Antes de empezar

- Abre o elige una issue. Todo cambio parte de una (`docs/issues/`) y su commit la cita (`TW-NNNN: ...`).
- Lee la [guía de desarrollo](docs/development.es.md): estructura, tipos de test y cómo añadir una herramienta.

## Preparar el entorno

Trackwright usa solo [uv](https://docs.astral.sh/uv/): nada de pip, venv, pipx, conda ni poetry.

```sh
uv sync
uvx pre-commit install   # opcional: ruff y mypy antes de cada commit
make check               # lint, formato, mypy strict, tests con cobertura >= 95 %
```

## Normas

- **Logs** con loguru, a stderr. `trackwright serve` nunca escribe en stdout: es el canal MCP.
- **Los tests** comprueban el código del error, esperan a eventos en lugar de dormir y usan el simulador (`trackwright.fake`). Un test que pasa contra el simulador no prueba nada sobre Cubase: los comportamientos del Cubase real van a `docs/verification.es.md` con lo observado.
- **Las escrituras** mantienen `dry_run`, la política de escritura y la verificación por relectura. Una escritura cuyo resultado se desconoce tras un timeout nunca se reintenta.
- **La documentación** es bilingüe: inglés `X.md` y castellano `X.es.md`, actualizados en el mismo cambio. `tests/unit/test_docs.py` lo comprueba.
- **Script de Cubase**: incrementa `SCRIPT_VERSION` en cada cambio; Cubase solo lo carga tras reiniciarse.
- **Commits** en inglés. Sin líneas de atribución a una IA.

## Pull requests

Rellena la plantilla. La integración continua (`.github/workflows/ci.yml`) debe estar en verde. Di claramente qué comprobaste en un Cubase real y qué no.

## Licencia

Al contribuir aceptas que tu contribución se licencie bajo la AGPL-3.0-or-later, como el resto del proyecto.
