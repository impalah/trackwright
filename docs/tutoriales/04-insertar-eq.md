# Tutorial 4 — Insertar un EQ y ajustar una banda

**Objetivo:** cargar StudioEQ en un slot vacío, subir 3 dB la ganancia de una banda en unidades reales y restaurarla.
**Necesitas:** el [tutorial 3](03-primer-cambio-seguro.md), con las escrituras habilitadas para POC-TEST.

## Paso 1. Elegir un slot vacío

> ¿Qué slots de inserción tiene libres POC-TEST?

Supongamos que el slot 2 está vacío. Trackwright **nunca sustituye un plugin cargado**: en un slot ocupado responde `SLOT_OCCUPIED`.

## Paso 2. Insertar con ensayo previo

> Inserta StudioEQ en el slot 2 de POC-TEST. Enséñame antes el plan.

1. Claude busca el `uid` de StudioEQ con `cubase_list_available_plugins`: es `946051208E29496E804F64A825C8A047`.
2. Llama a `cubase_insert_plugin` con `dry_run: true` y te enseña la pista, el slot y el plugin.
3. Tras tu confirmación, lo aplica.

La respuesta incluye `inserted: true` y `verified: true`: el slot contiene un plugin con ese `uid`.

## Paso 3. Localizar el parámetro

> En el EQ del slot 2, ¿qué parámetro controla la ganancia de la banda 1?

Con `cubase_list_parameters`, `target: "insert:2"` y un filtro, Claude encuentra el parámetro `GainP1L` (tag 4207). Su valor está en `0.0 dB`.

## Paso 4. Escribir en unidades reales

> Sube esa ganancia a +3 dB.

Claude usa `cubase_set_parameter` con `unit: "plain"` y `value: 3`. Cubase convierte los 3 dB a su valor normalizado (0,5625), y Trackwright verifica con una tolerancia de 1e-3. En el ensayo verás el valor normalizado que se va a escribir.

## Paso 5. Restaurar

> Vuelve a dejar la ganancia en 0 dB.

## Paso 6. Quitar el plugin

La API no tiene una forma verificada de quitar plugins. **Quítalo tú a mano** en Cubase.

Después pide «Lista los inserts de POC-TEST». Si guardabas alguna `ref` del plugin y la usas, Trackwright responderá `INVALID_OBJECT` o `STALE_REF` en lugar de actuar sobre otro objeto.

## Qué has aprendido

- Los plugins se cargan por su `uid`, nunca sobre un slot ocupado.
- Con `unit: "plain"` trabajas en unidades reales y Cubase hace la conversión.
- Las referencias a objetos eliminados se detectan.

**Siguiente:** [Tutorial 5 — Marcadores y posición del cursor](05-marcadores-cursor.md).
