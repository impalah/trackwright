# Tutorial 1 — Primera conexión

[English](01-first-connection.md) · **Español**

> **Configuración probada.** Estos tutoriales usan **Claude Code** y **Cubase**: el comportamiento de las herramientas que describen se verificó con Claude Code y Cubase Elements 15.0.30 (ver el [registro de verificación](../verification.es.md)). Cualquier otro cliente MCP llama a las mismas herramientas; donde dice «el asistente», entiende el asistente de IA de tu cliente. Por ahora, Cubase es el único DAW que admite Trackwright.

**Objetivo:** pasar de cero a que el asistente te diga qué hay en tu proyecto de Cubase.
**Tiempo:** 15 minutos.
**Necesitas:** uv y Cubase 15.0.20 o posterior (ver el [manual de instalación](../manual/01-installation.es.md#1-requisitos)).

Los comandos son los de una instalación desde PyPI. Desde el código fuente, antepón `uv run`.

## Paso 1. Ensayo con el simulador

Antes de tocar Cubase, comprueba que tu cliente MCP habla con Trackwright usando el simulador, que no necesita nada instalado:

1. Registra el servidor simulado en Claude Code:
   ```sh
   claude mcp add trackwright-sim -- uvx trackwright serve --simulate
   ```
2. Abre Claude Code y pide:
   > ¿Qué pistas hay en mi proyecto de Cubase?
3. El asistente llamará a `cubase_list_tracks` y te dirá que hay `Stereo Out`, `POC-INSTR` y `POC-TEST`. Son las pistas del simulador.
4. Pide `cubase_status`. Debe mostrar `simulated: true`.

Si esto funciona, la parte MCP está bien. Quita el servidor simulado con `claude mcp remove trackwright-sim`.

**Con otro cliente MCP** (por ejemplo, GitHub Copilot en VS Code, aún sin probar): registra el comando `uvx trackwright serve --simulate` como servidor stdio, como se explica en el [manual de operación](../manual/02-operation.es.md#conectar-un-cliente-mcp).

## Paso 2. Instalar

```sh
uv tool install trackwright
trackwright setup
```

`setup` pregunta en cada paso. Para este tutorial:

- **el script:** sí;
- **las escrituras:** no; este tutorial solo lee, y puedes activarlas después;
- **crear la configuración:** sí;
- **registrar en Claude Code:** sí.

`setup` solo registra el servidor en Claude Code; para otro cliente, registra `trackwright serve` a mano (ver el [manual de operación](../manual/02-operation.es.md#conectar-un-cliente-mcp)).

Al final, `doctor` mostrará «bridge running» en rojo: es lo esperado, porque el puente arranca con el servidor MCP.

## Paso 3. Conectar con Cubase

1. **Reinicia Cubase** y abre un proyecto desechable que tenga al menos una pista de audio.
2. Reinicia Claude Code (o abre `/mcp`), o tu cliente MCP, para que arranque el servidor `trackwright`. El servidor arranca el puente, y la superficie **Trackwright – Bridge** aparece en la pestaña **MIDI Remote** de Cubase. Si no aparece, sigue el paso 6 del [manual de instalación](../manual/01-installation.es.md#6-activar-el-script-en-cubase).
3. En una terminal:
   ```sh
   trackwright doctor
   ```
   Todo debe salir con `"ok": true`, con la versión del script en «Cubase answers».
4. En Claude Code:
   > Comprueba el estado de Cubase con Trackwright.

   El asistente debe responder con `simulated: false`, la versión de Cubase y `writes_enabled: false`: estás en solo lectura.

## Paso 4. Explorar

Prueba estas peticiones:

- «Lista las pistas de Cubase con su volumen y si están en mute.»
- «¿Qué pista está seleccionada y qué secciones tiene?»
- «¿Dónde está el cursor y a qué tempo va el proyecto?»

## Qué has aprendido

- La cadena completa: cliente MCP → `serve` → puente → Cubase.
- El simulador sirve para practicar sin riesgo.
- Por defecto Trackwright solo lee.

**Siguiente:** [Tutorial 2 — Inspeccionar una pista y sus plugins](02-inspect-track.es.md).
