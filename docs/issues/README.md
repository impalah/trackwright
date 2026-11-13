# Issues y épicas de Trackwright

Las issues documentan cada unidad de trabajo **antes** de implementarla. Al cerrarla se actualiza su estado y se enlaza el commit.

- **Fuente de requisitos:** `docs/mcp-design.md` y `docs/findings.md` de la POC (`../cubase-mcp-poc/`). Cada issue de herramienta cita la evidencia de runtime en la que se apoya.
- **Estados:** `pendiente` → `en curso` → `hecha` (con commit) · `bloqueada` (con motivo).
- **Identificadores:** `TW-<épica><número>`, por ejemplo `TW-0203` (épica 02, issue 03).

## Épicas

| Épica | Título | Archivo |
|---|---|---|
| E01 | Fundaciones del proyecto | [E01-fundaciones.md](E01-fundaciones.md) |
| E02 | Comunicación con Cubase (protocolo, transporte, cliente, puente) | [E02-comunicacion.md](E02-comunicacion.md) |
| E03 | Script MIDI Remote de Trackwright | [E03-script-midi-remote.md](E03-script-midi-remote.md) |
| E04 | Núcleo del servidor MCP | [E04-nucleo-mcp.md](E04-nucleo-mcp.md) |
| E05 | Herramientas de lectura | [E05-herramientas-lectura.md](E05-herramientas-lectura.md) |
| E06 | Herramientas de escritura | [E06-herramientas-escritura.md](E06-herramientas-escritura.md) |
| E07 | Herramientas basadas en comandos de Cubase | [E07-herramientas-comandos.md](E07-herramientas-comandos.md) |
| E08 | Documentación de usuario: manuales y tutoriales | [E08-documentacion.md](E08-documentacion.md) |
| E09 | Calidad y pruebas | [E09-calidad-pruebas.md](E09-calidad-pruebas.md) |
| E10 | Endurecimiento tras la revisión independiente | [E10-endurecimiento.md](E10-endurecimiento.md) |
| E11 | Panel de estado en la superficie MIDI Remote | [E11-panel-estado.md](E11-panel-estado.md) |
| E12 | Funcionalidades ampliadas (arranque, guardar, importar y exportar, presets, automatización, propiedades del proyecto) | [E12-funcionalidades-ampliadas.md](E12-funcionalidades-ampliadas.md) |

## Criterios comunes a todas las issues

- **Herramientas:** solo `uv`.
  - Dependencias con `uv add`; ejecución con `uv run`.
  - Prohibidos `pip`, `uv pip`, `venv`, `virtualenv`, `pipx`, `conda`, `poetry` y `requirements.txt`.
- **Logs:** con `loguru`. El módulo `logging` de la biblioteca estándar solo se toca para redirigir los logs de dependencias hacia loguru (E01).
- **Calidad:**
  - `uv run ruff check` y `uv run ruff format --check` sin errores;
  - `uv run mypy` en modo `strict` sin errores;
  - cobertura de tests unitarios ≥ 85 % (`fail_under` en `pyproject.toml`).
- **Documentación:** cada funcionalidad visible para el usuario se refleja en los manuales (E08).
- **Honestidad de la evidencia:** lo que solo se ha probado con el simulador se marca así; no se declara verificado contra Cubase sin una ejecución real registrada.
