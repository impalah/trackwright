# E06 — Herramientas de escritura

[English](E06-write-tools.md) · **Español**

Todas aplican la política de escritura (TW-0403): `dry_run` por defecto, sin reintentos y con verificación por relectura.

| Issue | Herramienta | Diseño | Evidencia (POC) | Estado |
|---|---|---|---|---|
| TW-0601 | `cubase_set_parameter` | n.º 8 | findings 11–12 | hecha |
| TW-0602 | `cubase_insert_plugin` | n.º 5 | findings 8 | hecha |
| TW-0603 | `cubase_set_track_mix` | n.º 11 | findings 30 | hecha |
| TW-0604 | `cubase_rename_track` | n.º 12 | findings 31 | hecha |
| TW-0605 | `cubase_select_track` | n.º 13 | findings 32 | hecha |
| TW-0606 | `cubase_set_position` | n.º 15 | findings 34 | hecha |
| TW-0607 | `cubase_set_tempo` | n.º 19 | findings 43 | hecha |

## Criterios de aceptación comunes

- Con `dry_run=true`, la salida contiene el plan (valor actual, valor pedido y objetivo resuelto) y no se llama a ninguna operación de escritura.
- Con `dry_run=false`:
  - se escribe;
  - se relee;
  - la salida trae `before`, `after` y `verified`.
- Errores:
  - `WRITES_DISABLED` y `NOT_ALLOWED`, de la política;
  - `PRECONDITION_FAILED`, `VERIFY_FAILED` y `STALE_REF`;
  - `TIMEOUT`, con `outcome: unknown`.
- Hay tests para cada error y para el caso correcto, contra `FakeCubase`.

## Notas por herramienta

- **`cubase_set_parameter`:**
  - valor en unidades process [0, 1], o `plain` mediante `da.convert`;
  - tolerancia de 1e-3.
- **`cubase_insert_plugin`:**
  - el slot debe estar vacío;
  - se verifica por el `uniqueName` del hijo, que es `<UID>-0`.
- **`cubase_set_track_mix`:**
  - tags 1025 (volumen, process), 1027 (mute), 1028 (solo) y 4002 (armado);
  - el volumen en dB **no** se ofrece: no está verificado.
- **`cubase_rename_track`:**
  - `setParameterDisplayValue(1024)`;
  - antes, rechaza nombres que ya usa otra pista (`NAME_CONFLICT`).
- **`cubase_select_track`:**
  - tag 4000 = 1, o la acción siguiente/anterior;
  - se verifica con `da.base`.
- **`cubase_set_position`:**
  - compases por la pantalla primaria y segundos por la secundaria;
  - la relectura llega siempre en compases;
  - con segundos, se verifica con el tempo.
- **`cubase_set_tempo`:**
  - 20–300 BPM;
  - la relectura es float32, con una tolerancia de 0,01.
