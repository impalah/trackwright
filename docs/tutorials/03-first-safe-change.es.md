# Tutorial 3 — Primer cambio seguro: ensayo, aplicación y restauración

[English](03-first-safe-change.md) · **Español**

> **Configuración probada.** Estos tutoriales usan **Claude Code** y **Cubase**: el comportamiento de las herramientas que describen se verificó con Claude Code y Cubase Elements 15.0.30 (ver el [registro de verificación](../verification.es.md)). Cualquier otro cliente MCP llama a las mismas herramientas; donde dice «el asistente», entiende el asistente de IA de tu cliente. Por ahora, Cubase es el único DAW que admite Trackwright.

**Objetivo:** cambiar el volumen y el mute de una pista **que no está seleccionada**, comprobar el cambio y dejarla como estaba.
**Necesitas:** el [tutorial 2](02-inspect-track.es.md), un proyecto desechable **guardado** y el transporte parado.

## Paso 1. Habilitar las escrituras, solo para la pista de pruebas

Crea `~/.config/trackwright/config.toml`:

```toml
[writes]
enabled = true
allowed_tracks = ["POC-TEST"]
```

Reinicia tu cliente MCP para que vuelva a lanzar `trackwright serve` con la configuración nueva. Comprueba con «¿Están habilitadas las escrituras en Trackwright?»: `cubase_status` debe decir `writes_enabled: true`.

## Paso 2. Seleccionar otra pista

En Cubase, haz clic en una pista que **no** sea POC-TEST. Así comprobarás que Trackwright modifica pistas no seleccionadas.

## Paso 3. Ensayo

> Silencia la pista POC-TEST, pero primero enséñame qué vas a cambiar.

El asistente llama a `cubase_set_track_mix` con `mute: true` y `dry_run: true`, el valor por defecto. Recibes el plan:
- `before`: el valor actual, `Desact.`;
- `requested`: el valor pedido, `1`;
- `verified: null`, porque no se ha aplicado nada.

En Cubase **no cambia nada**.

## Paso 4. Aplicar

> Adelante, aplícalo.

El asistente repite la llamada con `dry_run: false`. Trackwright escribe el valor, lo relee y devuelve `after: Activ.` y `verified: true`. El botón de mute de POC-TEST se enciende en Cubase.

## Paso 5. Volumen y restauración

> Baja el volumen de POC-TEST a 0.7 y luego déjalo como estaba.

El asistente anota el valor original que devuelve el ensayo, aplica 0.7, verifica y lo restaura. El volumen se expresa normalizado, entre 0 y 1: el volumen en dB aún no está disponible.

Desactiva el mute de la misma forma.

## Paso 6. Comprobar la política

> Silencia la pista POC-INSTR, sin ensayo.

El ensayo no consulta la política: siempre está permitido y no cambia nada. Al **aplicar**, en cambio, falla con `NOT_ALLOWED`, porque POC-INSTR no está en `allowed_tracks`. Así compruebas que la configuración te protege.

## Qué has aprendido

- Los cambios siguen siempre el ciclo **ensayo → confirmación → aplicación con verificación**.
- Trackwright modifica pistas sin necesidad de seleccionarlas.
- `allowed_tracks` limita qué pistas se pueden tocar.

**Siguiente:** [Tutorial 4 — Insertar un EQ y ajustar una banda](04-insert-eq.es.md).
