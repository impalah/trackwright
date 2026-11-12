# Tutorial 6 — Crear una pista con ayuda del diálogo, y borrarla

**Objetivo:** crear un canal de grupo con nombre propio colaborando con Claude, y después borrarlo de forma segura.
**Necesitas:** las escrituras habilitadas, y estar delante de la pantalla de Cubase.

## Por qué hace falta tu ayuda

Al añadir pistas de audio, de grupo o carpetas, Cubase abre el diálogo «Añadir pista» y espera tu respuesta. La API no puede rellenarlo. Por eso esta herramienta trabaja en dos fases: Trackwright abre el diálogo, tú lo completas y después Trackwright comprueba el resultado.

## Paso 1. Fase `start`

> Crea un canal de grupo llamado POC-GROUP.

Claude llama a `cubase_add_track_interactive` con `phase: "start"`, `kind: "group"` y `suggested_name: "POC-GROUP"`. La respuesta trae `status: "awaiting_user"` y unas instrucciones.

En Cubase se abre el diálogo «Añadir pista». **Escribe el nombre `POC-GROUP`** y acepta.

Si aceptas sin escribir nombre, Cubase lo llama «Group 01» y la fase de confirmación no lo encontrará.

## Paso 2. Fase `confirm`

> Ya lo he creado.

Claude llama de nuevo con `phase: "confirm"`. Trackwright busca la pista en el mezclador y devuelve:
- `status: "done"` y `verified: true`, con el selector `uid:` del grupo nuevo;
- o `not_found`, si cancelaste el diálogo o usaste otro nombre.

## Paso 3. Borrar con seguridad

> Borra POC-GROUP.

Claude debería:
1. seleccionarlo con `cubase_select_track`;
2. ensayar `cubase_remove_selected_tracks` con `expect_selected: "POC-GROUP"`, que solo actúa si la selección coincide **exactamente** (si no, `SELECTION_MISMATCH`);
3. con tu confirmación, aplicarlo.

Respuestas posibles:
- `status: "done"`: la pista ha desaparecido del mezclador;
- `status: "pending_confirmation"`: la pista tenía eventos y Cubase pide confirmación en pantalla. Respóndele tú.

## Qué has aprendido

- Los comandos de clase `dialog` necesitan tu intervención, y Trackwright nunca los da por terminados.
- Los borrados exigen indicar qué pista se espera que esté seleccionada.

## Para seguir

- [Referencia de herramientas](../manual/04-herramientas.md): todas las herramientas y sus limitaciones.
- [Resolución de problemas](../manual/05-problemas.md).
