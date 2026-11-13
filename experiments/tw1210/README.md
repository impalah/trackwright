# Experimento TW-1210: modificar propiedades del proyecto

**Fecha:** 2026-11-13.
**Entorno:** Cubase Elements 15.0.30 y script 1.5.4.
**Método:** `da.param.set` sobre los objetos «Transporte» y «Metronome» (TW-1209). Cada valor se leyó, se escribió el contrario, se releyó y se restauró.

## Interruptores (todos ✅: escritura, relectura y restauración)

| Objeto | Parámetro (tag) | Desact. → Activ. → Desact. |
|---|---|---|
| Transport | `cycle` (4022) | ✅ |
| Transport | `metronomeOn` (4099) | ✅ |
| Transport | `precountOn` (4100) | ✅ |
| Transport | `punchIn` (4020) / `punchOut` (4021) | ✅ / ✅ |
| Transport | `usePreRoll` (4037) / `usePostRoll` (4038) | ✅ / ✅ |
| Metronome | `tickInPlayback` / `tickInRecord` | ✅ / ✅ |

## Valores continuos

| Parámetro | Escrito | Mostrado | Conclusión |
|---|---|---|---|
| `clickLevel` (Metronome) | 0,5 / 0 | «64» / «0» | Escala 0–127 = valor × 127 ✅ (restaurado a 127) |
| `preRoll` (Transport) | 0,1 / 0,5 | «1. 2. 0. 0» / «7. 2. 0. 0» | 6 y 30 tiempos: ¿tiempos = valor × 60? **Hay pocos puntos medidos: queda fuera** |
| `postRoll` (Transport) | 0,1 | «1. 2. 0. 0» | Igual que el pre-roll |

- **Compás** (`signature`): su valor interno no está en [0, 1] (2621,48 con 4/4) y el script rechaza escrituras fuera de ese rango. **No se escribe.** Se cambia en «Configuración del proyecto» o en la barra de transporte, como hizo el usuario.

## Conclusión

`cubase_set_project` puede cambiar, con ensayo y relectura:
- ciclo, metrónomo, precuenta, punch in/out y uso de pre-roll y post-roll;
- clic al reproducir y al grabar;
- nivel del clic.
