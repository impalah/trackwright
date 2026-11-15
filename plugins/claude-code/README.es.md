# Plugin de Trackwright para Claude Code

[English](README.md) · **Español**

Skills de productor para Cubase, sobre el servidor MCP [Trackwright](../../README.es.md). El plugin arranca el servidor por sí mismo (`uvx trackwright==<versión> serve`), así que el servidor y las skills siempre van en versiones que encajan.

> **Estado:** en desarrollo (épica E15). Las skills llegan con TW-1506 y TW-1507; la primera versión que incluya el plugin será la siguiente de Trackwright después de la 0.4.0.

## Instalación

1. **Lado de Cubase, una vez:** instala el script de MIDI Remote y crea la configuración con `uvx trackwright setup`. Cuando ofrezca registrar el servidor MCP en Claude Code, responde **no**: lo hace el plugin.
2. **En Claude Code:**
   ```text
   /plugin marketplace add impalah/trackwright
   /plugin install trackwright@trackwright
   ```
   Lo mismo funciona en la extensión de Claude Code para VS Code (`/plugins`).

El análisis de audio necesita `[analysis] enabled = true` en `~/.config/trackwright/config.toml`; las escrituras necesitan `[writes] enabled = true` (ver el [capítulo de configuración](../../docs/manual/03-configuration.es.md)).

## Si antes registraste el servidor a mano

Con `claude mcp add trackwright …` (o `trackwright setup`) **y** el plugin, Claude Code ejecuta dos servidores Trackwright con las mismas herramientas. Comparten el puente, pero las herramientas duplicadas confunden al modelo. Quédate solo con el plugin:

```sh
claude mcp remove trackwright --scope user
```

Trackwright no puede detectarlo por sí mismo: Claude Code no documenta dónde registra los plugins instalados.

## Versiones

La versión del plugin es la del paquete, y `.mcp.json` fija `trackwright==<esa versión>` (salvo que se defina `TRACKWRIGHT_FROM`, ver abajo); `tests/unit/test_plugin.py` lo comprueba. Un servidor más antiguo que el que escribió tu configuración la rechaza (las secciones desconocidas son errores, para detectar erratas), así que no fijes a mano otra versión.

## Skills

Cada skill de `skills/` usa solo los campos del estándar abierto [Agent Skills](https://agentskills.io) y nombra las herramientas por su nombre corto (`cubase_edit_range`). Los tests comprueban que cada herramienta que nombra una skill existe en el servidor.

## Desarrollo

`TRACKWRIGHT_FROM` hace que el plugin arranque el servidor desde otro origen (un repositorio, un wheel) en lugar de la versión fijada; es solo para desarrollo.

```sh
TRACKWRIGHT_FROM=$PWD claude --plugin-dir plugins/claude-code   # probarlo con el servidor de este repositorio
claude plugin validate plugins/claude-code --strict
claude plugin validate . --strict              # el marketplace
```
