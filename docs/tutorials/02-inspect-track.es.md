# Tutorial 2 — Inspeccionar una pista y sus plugins

[English](02-inspect-track.md) · **Español**

> **Configuración probada.** Estos tutoriales usan **Claude Code** y **Cubase**: el comportamiento de las herramientas que describen se verificó con Claude Code y Cubase Elements 15.0.30 (ver el [registro de verificación](../verification.es.md)). Cualquier otro cliente MCP llama a las mismas herramientas; donde dice «el asistente», entiende el asistente de IA de tu cliente. Por ahora, Cubase es el único DAW que admite Trackwright.

**Objetivo:** leer los inserts de una pista, el catálogo de plugins y los parámetros de un plugin, sin modificar nada.
**Necesitas:** el [tutorial 1](01-first-connection.es.md). Para que haya algo que leer, inserta a mano un plugin (por ejemplo, StudioEQ) en el slot 1 de una pista.

## Paso 1. Identificar la pista por su uid

Pide:

> Lista las pistas y dame el selector de la pista «POC-TEST».

El asistente usa `cubase_list_tracks` y te da algo como `uid:79CDBA14…`. **Ese selector no cambia aunque reinicies Cubase**, así que es la forma más segura de referirse a la pista.

## Paso 2. Ver los inserts

> ¿Qué plugins tiene POC-TEST en sus inserts?

`cubase_list_inserts` devuelve los 8 slots. En el slot 1 verás `StudioEQ` y su `plugin_uid`; el resto aparecerán vacíos.

## Paso 3. Consultar el catálogo

> ¿Qué ecualizadores puedo cargar en el slot 2?

`cubase_list_available_plugins` con `filter: "eq"` lista los plugins disponibles, con su `uid`. Lo necesitarás en el [tutorial 4](04-insert-eq.es.md).

## Paso 4. Leer parámetros

> Enséñame los parámetros de ganancia del plugin del slot 1.

El asistente usa `cubase_list_parameters` con `target: "insert:1"` y un filtro. Cada parámetro tiene:
- `tag`: su identificador estable;
- `title`: viene en el idioma de Cubase;
- `display`: el valor tal como lo muestra Cubase, por ejemplo `0.0 dB`;
- `process`: el valor normalizado, entre 0 y 1;
- `plain`: el valor en unidades reales, si el plugin lo proporciona.

> ¿Cuánto vale el parámetro 4207 del slot 1?

`cubase_get_parameter` devuelve ese parámetro concreto.

## Paso 5. El EQ del channel strip

> Muéstrame los parámetros del EQ del channel strip de POC-TEST.

Usa `target: "strip:eq"`.

## Qué has aprendido

- Los selectores `uid:` son la forma estable de designar una pista.
- `target` elige qué parte de la pista: `channel`, `insert:N` o `strip:eq`.
- Los títulos vienen localizados; el `tag` es lo que identifica un parámetro.

**Siguiente:** [Tutorial 3 — Primer cambio seguro](03-first-safe-change.es.md).
