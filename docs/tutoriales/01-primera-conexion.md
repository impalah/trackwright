# Tutorial 1 — Primera conexión

**Objetivo:** pasar de cero a que Claude te diga qué hay en tu proyecto de Cubase.
**Tiempo:** 15 minutos.
**Necesitas:** uv y Cubase 15.0.20 o posterior (ver el [manual de instalación](../manual/01-instalacion.md#1-requisitos)).

Los comandos son los de una instalación desde PyPI. Desde el código fuente, antepón `uv run`.

## Paso 1. Ensayo con el simulador

Antes de tocar Cubase, comprueba que Claude habla con Trackwright usando el simulador, que no necesita nada instalado:

1. Registra el servidor simulado en Claude Code:
   ```sh
   claude mcp add trackwright-sim -- uvx trackwright serve --simulate
   ```
2. Abre Claude Code y pide:
   > ¿Qué pistas hay en mi proyecto de Cubase?
3. Claude llamará a `cubase_list_tracks` y te dirá que hay `Stereo Out`, `POC-INSTR` y `POC-TEST`. Son las pistas del simulador.
4. Pide `cubase_status`. Debe mostrar `simulated: true`.

Si esto funciona, la parte MCP está bien. Quita el servidor simulado con `claude mcp remove trackwright-sim`.

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

Al final, `doctor` mostrará «bridge running» en rojo: es lo esperado, porque el puente arranca con el servidor MCP.

## Paso 3. Conectar con Cubase

1. **Reinicia Cubase** y abre un proyecto desechable que tenga al menos una pista de audio.
2. Reinicia Claude Code (o abre `/mcp`) para que arranque el servidor `trackwright`. El servidor arranca el puente, y la superficie **Trackwright – Bridge** aparece en la pestaña **MIDI Remote** de Cubase. Si no aparece, sigue el paso 6 del [manual de instalación](../manual/01-instalacion.md#6-activar-el-script-en-cubase).
3. En una terminal:
   ```sh
   trackwright doctor
   ```
   Todo debe salir con `"ok": true`, con la versión del script en «Cubase answers».
4. En Claude Code:
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
