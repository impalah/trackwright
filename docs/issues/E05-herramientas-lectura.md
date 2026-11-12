# E05 — Herramientas de lectura

Las herramientas siguen la numeración de `mcp-design.md`. Ninguna modifica el proyecto.

| Issue | Herramienta | Diseño | Evidencia (POC) | Estado |
|---|---|---|---|---|
| TW-0501 | `cubase_status` | n.º 1 | findings 1–3 | pendiente |
| TW-0502 | `cubase_list_tracks` | n.º 10 | findings 28–29 | pendiente |
| TW-0503 | `cubase_get_selected_channel` | n.º 2 | findings 4–5 | pendiente |
| TW-0504 | `cubase_list_inserts` | n.º 3 | findings 6, 8 | pendiente |
| TW-0505 | `cubase_list_available_plugins` | n.º 4 | findings 7 | pendiente |
| TW-0506 | `cubase_list_parameters` | n.º 6 | findings 9–10 | pendiente |
| TW-0507 | `cubase_get_parameter` | n.º 7 | findings 9–10 | pendiente |
| TW-0508 | `cubase_get_transport` | n.º 14 | findings 33 | pendiente |
| TW-0509 | `cubase_poll_changes` | n.º 9 | findings 16 | pendiente |

## Criterios de aceptación comunes

- La entrada y la salida son modelos pydantic, y el esquema que se publica coincide con el diseño.
- Las pistas se direccionan con `TrackRef`. Los objetos se devuelven con `ref` opaco, **nunca** con IDs de runtime sueltos.
- Hay tests contra `FakeCubase` para el caso correcto, los errores (pista inexistente, slot vacío, objeto eliminado, puente no disponible) y la paginación.
- Hay un test de contrato con el cliente MCP en memoria para cada herramienta.

## Notas por herramienta

- **`cubase_list_tracks`:**
  - deduplica por ID;
  - no muestra pistas sin canal de mezclador (marcadores, carpetas) y lo documenta.
- **`cubase_get_transport`:**
  - usa la pantalla **primaria**;
  - avisa si aún no ha llegado ningún callback (`UNAVAILABLE`).
- **`cubase_list_inserts`:**
  - un slot vacío tiene `children == 0`;
  - el UID del plugin es el `uniqueName` sin el sufijo `-N`.
