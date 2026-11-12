# Tutorial 1 — Primera conexión

**Objetivo:** pasar de cero a que Claude te diga qué hay en tu proyecto de Cubase.
**Tiempo:** 15 minutos.
**Necesitas:** haber completado el [manual de instalación](../manual/01-instalacion.md) hasta el paso 3.

## Paso 1. Ensayo con el simulador

Antes de tocar Cubase, comprueba que tu cliente MCP habla con Trackwright usando el simulador.

1. Registra el servidor en Claude Code en modo simulado:
   ```sh
   claude mcp add trackwright-sim -- uv --directory /Volumes/Data/projects/sound/trackwright run trackwright serve --simulate
   ```
2. Abre Claude Code y pide:
   > ¿Qué pistas hay en mi proyecto de Cubase?
3. Claude llamará a `cubase_list_tracks` y te dirá que hay `Stereo Out`, `POC-INSTR` y `POC-TEST`. Son las pistas del simulador.
4. Pide `cubase_status`. Debe mostrar `simulated: true`.

Si esto funciona, la parte MCP está bien. Quita el servidor simulado con `claude mcp remove trackwright-sim`.

## Paso 2. Conectar con Cubase

1. Instala el script (manual de instalación, paso 4):
   ```sh
   uv run trackwright script install --apply
   ```
2. Arranca el puente y deja la terminal abierta:
   ```sh
   uv run trackwright bridge
   ```
3. Abre Cubase con un proyecto desechable que tenga al menos una pista de audio.
4. En otra terminal:
   ```sh
   uv run trackwright ping
   ```
   Espera `"ok": true` y `"scriptVersion": "1.0.0"`.

## Paso 3. Registrar el servidor real

```sh
claude mcp add trackwright -- uv --directory /Volumes/Data/projects/sound/trackwright run trackwright serve
```

En Claude Code:

> Comprueba el estado de Cubase con Trackwright.

Claude debe responder con `simulated: false`, la versión de Cubase y `writes_enabled: false`: estás en solo lectura.

## Paso 4. Explorar

Prueba estas peticiones:

- «Lista las pistas de Cubase con su volumen y si están en mute.»
- «¿Qué pista está seleccionada y qué secciones tiene?»
- «¿Dónde está el cursor y a qué tempo va el proyecto?»

## Qué has aprendido

- La cadena completa: cliente MCP → `serve` → puente → Cubase.
- El simulador sirve para practicar sin riesgo.
- Por defecto Trackwright solo lee.

**Siguiente:** [Tutorial 2 — Inspeccionar una pista y sus plugins](02-inspeccionar-pista.md).
