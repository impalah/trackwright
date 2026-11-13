# E07 — Herramientas basadas en comandos de Cubase

[English](E07-command-tools.md) · **Español**

Los comandos se disparan desde el script y **no devuelven resultado**. Cada comando tiene una clase observada, que la herramienta expone:

| Clase | Comportamiento |
|---|---|
| `direct` | actúa directamente |
| `dialog` | abre un diálogo; el usuario debe completarlo |
| `confirm` | puede pedir confirmación |
| `unknown` | sin evidencia |

| Issue | Herramienta | Diseño | Evidencia (POC) | Estado |
|---|---|---|---|---|
| TW-0701 | Registro de comandos con clases | principios 10–11 | fase 4 y 2b | hecha |
| TW-0702 | `cubase_run_command` | n.º 18 | findings 35 | hecha |
| TW-0703 | `cubase_markers` | n.º 16 | findings 37 | hecha |
| TW-0704 | `cubase_remove_selected_tracks` | n.º 17 | findings 38 | hecha |
| TW-0705 | `cubase_split_at_locators` | n.º 20 | findings 45 | hecha |
| TW-0706 | `cubase_add_track_interactive` | n.º 21 | findings 42 | hecha |

## Criterios de aceptación comunes

- Política de escritura y `dry_run` como en E06.
- **Nunca se presenta como completado un comando de clase `dialog`.** La herramienta devuelve `awaiting_user` y una instrucción para el usuario.
- Si el efecto se puede leer, se verifica (pistas, selección, transporte). Si no, `verified: "not_observable"`, de forma explícita.
- `canPerform = false` se convierte en `CANNOT_PERFORM`, salvo `force`, que solo admite `cubase_run_command`.

## Notas

- **`cubase_remove_selected_tracks`:**
  - exige `expect_selected` y comprueba que coincide **exactamente** con la selección (`SELECTION_MISMATCH`);
  - si tras el comando la pista sigue en el listado, devuelve `pending_confirmation`, porque Cubase pide confirmación cuando hay eventos.
- **`cubase_add_track_interactive`:**
  - en dos fases: `start` lanza el comando y devuelve `awaiting_user`; `confirm` busca la pista nueva por nombre;
  - las carpetas no tienen canal de mezclador, así que en ese caso la verificación es visual.
- **`cubase_split_at_locators`:**
  - escribe y relee los localizadores antes de disparar `Split Loop`;
  - avisa de que afecta a **todas** las pistas con eventos en el rango.
