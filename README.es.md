# Trackwright

[English](README.md) · **Español**

[![PyPI version](https://badge.fury.io/py/trackwright.svg)](https://pypi.org/project/trackwright/)
[![CI](https://github.com/impalah/trackwright/actions/workflows/ci.yml/badge.svg)](https://github.com/impalah/trackwright/actions/workflows/ci.yml)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL v3+](https://img.shields.io/badge/License-AGPL%20v3%2B-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Coverage 98%](https://img.shields.io/badge/coverage-98%25-brightgreen.svg)](https://github.com/impalah/trackwright)
![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)
![DAW: Cubase 15.0.20+](https://img.shields.io/badge/DAW-Cubase%2015.0.20+-red.svg)
[![MCP](https://img.shields.io/badge/MCP-server-8A2BE2.svg)](https://modelcontextprotocol.io)

**Trackwright** es un servidor [MCP](https://modelcontextprotocol.io) independiente para controlar estaciones de trabajo de audio digital (DAW).

Permite a un asistente de IA (Claude, GitHub Copilot o cualquier otro cliente MCP) **inspeccionar y controlar tu DAW**: pistas, mezcla, plugins y sus parámetros, transporte, marcadores, automatización y edición por rangos de tiempo, pensada para podcasts.

La primera implementación es para **Cubase**. Funciona con un script MIDI Remote que se ejecuta dentro de Cubase y no necesita controladores físicos ni puertos IAC. Podrán llegar otros DAW: buena parte del núcleo (transporte MIDI, puente, política de escrituras, verificación por relectura) no depende de Cubase.

| | |
|---|---|
| Paquete | `trackwright` |
| Ejecutable | `trackwright` |
| Servidor MCP | `trackwright` (stdio) |
| Clientes MCP | Cualquiera que admita servidores stdio. Probado con Claude Code |
| Plataforma | macOS. Verificado en macOS 27.2 (Apple Silicon) |
| DAW | Cubase 15.0.20 o posterior (API MIDI Remote 1.3). Verificado en Cubase Elements 15.0.30 |
| Licencia | AGPL-3.0-or-later |

> Trackwright es un proyecto independiente. No está afiliado a Steinberg ni respaldado por ella; Cubase es una marca de Steinberg Media Technologies GmbH.

## Requisitos

- **[uv](https://docs.astral.sh/uv/)** 0.13 o posterior (`brew install uv`). No hace falta instalar Python: uv descarga el adecuado. No hay nada que compilar.
- **Cubase** 15.0.20 o posterior.
- Un cliente MCP: **Claude Code** (probado), Claude Desktop, **GitHub Copilot** en VS Code o cualquier otro cliente que admita servidores stdio.

## Instalación

```sh
uv tool install trackwright
trackwright setup
```

Si el terminal no encuentra `trackwright`, ejecuta `uv tool update-shell` y abre otro terminal.

`trackwright setup` es una instalación guiada. En cada paso **muestra lo que va a hacer y pregunta** antes de aplicarlo (la respuesta por defecto es «no»):

1. copia el script `Trackwright_Bridge.js` en la carpeta MIDI Remote de Cubase (`~/Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/trackwright/bridge/`);
2. crea `~/.config/trackwright/config.toml` si no existe, preguntando si se permiten las escrituras y el guardado del proyecto (por defecto, no);
3. registra el servidor en Claude Code (`claude mcp add --scope user trackwright …`) o, si no encuentra `claude`, te muestra el comando;
4. comprueba todo con `trackwright doctor`.

Nunca usa `sudo` ni cambia ajustes de Cubase o del sistema. Para no preguntar en un paso: `--yes script`, `--yes config` o `--yes claude`.

### Activar el script en Cubase

1. **Reinicia Cubase** (no recarga los scripts por sí mismo) y abre un proyecto. Para las primeras pruebas, mejor uno desechable.
2. En la pestaña **MIDI Remote** de la zona inferior debe aparecer la superficie **Trackwright – Bridge**. Los puertos virtuales los crea Trackwright al arrancar, y el servidor MCP lo arranca tu cliente MCP. Si no aparece, pulsa **+ Añadir superficie de controlador MIDI** y elige `Trackwright` / `Bridge`, con entrada `Trackwright To Cubase` y salida `Trackwright From Cubase`.
3. **Recomendado:** en *Estudio > Configuración de estudio > Configuración de puertos MIDI*, desmarca **«En 'All MIDI Inputs'»** para `Trackwright To Cubase`.

### Comprobar

```sh
trackwright doctor   # revisa cada eslabón y dice qué hacer si algo falla
```

Después, en tu cliente MCP (por ejemplo, Claude Code): «Comprueba el estado de Cubase con Trackwright».

### Probar sin Cubase

Trackwright incluye un Cubase simulado. Para probarlo desde Claude Code sin instalar nada más:

```sh
claude mcp add trackwright-sim -- uvx trackwright serve --simulate
```

### Otros clientes MCP

`trackwright setup` registra el servidor en Claude Code. Cualquier otro cliente MCP necesita el mismo comando: `trackwright serve` por stdio. Las aplicaciones de escritorio no heredan el `PATH` del terminal, así que usa la ruta absoluta que muestra `which trackwright`.

**GitHub Copilot en VS Code** (aún sin probar): ejecuta **MCP: Open User Configuration** y añade:

```json
{
  "servers": {
    "trackwright": {
      "type": "stdio",
      "command": "/Users/<tu-usuario>/.local/bin/trackwright",
      "args": ["serve"]
    }
  }
}
```

Después usa Copilot Chat en modo agente. Las herramientas de Trackwright aparecen en su lista de herramientas.

## Actualizar y desinstalar

- **Actualizar:** `uv tool upgrade trackwright` y después `trackwright setup`, que actualiza el script si cambió. Reinicia Cubase.
- **Desinstalar:**
  1. `claude mcp remove trackwright -s user`;
  2. `pkill -f "trackwright bridge"`;
  3. `uv tool uninstall trackwright`;
  4. borra `~/Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/trackwright/` y `~/.config/trackwright/`, y quita la superficie en la pestaña MIDI Remote de Cubase.

## Qué puede hacer (Cubase)

32 herramientas, todas con salida estructurada:

- **Lectura:** estado, pistas del mezclador, canal seleccionado, inserts, catálogo de plugins, parámetros, transporte y cambios recientes.
- **Escritura**, siempre con ensayo previo (`dry_run`) y verificación por relectura: parámetros (en valor normalizado o en unidades reales), inserción de plugins, volumen, mute, solo, armado, nombre de pista y tempo.
- **Navegación:** seleccionar pistas y mover el cursor y los localizadores.
- **Automatización:** graba curvas de volumen, panorama, envíos, EQ del canal, pre-filtro y parámetros de plugins, reproduciendo el proyecto, con valores en unidades reales (dB, Hz) que convierte Cubase. Verificado en Cubase Elements.
- **Edición de podcasts:** borrar, cortar o insertar silencio en un rango en segundos, en todas las pistas o en una, con verificación del resultado.
- **Ajustes del proyecto:** leer compás, ciclo, metrónomo, precuenta, punch…; cambiar ciclo, metrónomo, precuenta, punch, pre-roll y post-roll y nivel del clic.
- **Presets de plugins:** siguiente o anterior, verificados por el cambio de parámetros. El nombre no está disponible en la API.
- **Guardar el proyecto:** solo a petición, con permiso propio (`[writes] save`), ensayo y verificación por la fecha del archivo.
- **Importar audio:** en la pista y la posición indicadas, con el selector de Cubase, y verificación por los bordes del evento nuevo.
- **Exportar la mezcla:** de un rango o del proyecto completo, con el diálogo de Cubase, y confirmación del archivo creado.
- **Comandos de Cubase:** marcadores, borrado de pistas, división en los localizadores, creación de pistas con ayuda del usuario y una lista de comandos permitidos. Cada comando indica cómo se comporta: si actúa directamente, si abre un diálogo o si pide confirmación.

Por defecto **solo lee**. Las escrituras se habilitan en la configuración y se pueden limitar a pistas concretas.

## Seguridad

- **Solo lectura por defecto.** Las escrituras se habilitan en `~/.config/trackwright/config.toml` (`[writes] enabled = true`) y se pueden limitar a pistas concretas (`allowed_tracks`). Guardar el proyecto tiene su propio permiso (`[writes] save`).
- Cada escritura admite un **ensayo** (`dry_run`) y se **verifica releyendo** el estado. Una escritura cuyo resultado es incierto no se reintenta.
- **No abre puertos de red:** el servidor habla con el cliente MCP por stdio y con el puente por un socket Unix privado.
- No cierra Cubase, no graba audio y no guarda nada si no se le pide.

## Configuración

```toml
# ~/.config/trackwright/config.toml
[writes]
enabled = true                   # permitir cambios en el proyecto abierto
save = false                     # permitir guardar el proyecto a petición
# allowed_tracks = ["Voz"]       # limitar las escrituras a estas pistas

[cubase]
app = "Cubase 15"                # nombre de la aplicación para cubase_launch
```

`trackwright config` muestra la configuración efectiva.

## Limitaciones conocidas

- **No es posible por la API** cambiar el enrutado (entradas, salidas o envíos), leer el contenido de las pistas (eventos, audio o automatización) ni completar diálogos de Cubase.
- **Solo se ven** las pistas que tienen canal de mezclador.
- Importar audio, exportar la mezcla y cambiar de preset usan diálogos o ventanas de Cubase: Trackwright los abre y prepara, y tú completas el diálogo.
- Por ahora, **solo macOS** y **solo Cubase**.

## Estado

Versión alfa. Todas las herramientas se han ejecutado contra Cubase Elements 15.0.30 en macOS 27.2, con confirmación visual donde la API no puede observar el resultado. Además, tiene tests unitarios, de contrato MCP, del script con Node.js y de extremo a extremo, con una cobertura del 98 %.

## Documentación

Manuales y tutoriales en la [carpeta `docs/`](docs/README.es.md) del repositorio: en inglés, con traducción al castellano en los archivos `*.es.md`. Código e incidencias: [github.com/impalah/trackwright](https://github.com/impalah/trackwright).

## Licencia

Copyright (C) 2026 impalah.

Este programa es software libre: puedes redistribuirlo o modificarlo según los términos de la **GNU Affero General Public License** publicada por la Free Software Foundation, versión 3 o, a tu elección, cualquier versión posterior (`AGPL-3.0-or-later`). Se distribuye sin ninguna garantía. Consulta el archivo [`LICENSE`](LICENSE).
