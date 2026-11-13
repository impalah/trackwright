# Experimento TW-1212: borrar un rango en una sola pista

**Fecha:** 2026-11-13.
**Entorno:** Cubase Elements 15.0.30, script 1.5.1, proyecto de pruebas guardado y herramienta de objetos.
**Medios:** sondeo de bordes de eventos (TW-1211) y «Locate Selection / Selection End» para medir la selección. Se usaron `experiments/tw1211/probe.py` y scripts sueltos.

## Alcance de las selecciones

| Comando | Prueba | Resultado |
|---|---|---|
| `Select Events under Cursor` | POC-INSTR seleccionada, cursor a 5 s. POC-INSTR tiene una parte de 4 a 6 s; POC-TEST, un evento de 2 a 6,8 s | Selección **4–6 s**: **solo la pista seleccionada** ✅ |
| `Select All on Tracks` | POC-INSTR seleccionada | Selección medida 0–2 s; con POC-TEST había dado 0–2:19,976. Ambiguo, no se usa |
| `Select Events under Cursor` sin evento bajo el cursor | — | `canPerform = false` |

## Flujo completo: borrar 2–30 s solo en POC-TEST

1. **Cortes:** en 2 s y en 30 s: `Select None`, cursor, `Select Events under Cursor` y `Split at Cursor`. Los bordes de POC-TEST pasan a `2.0, 6.0, 6.8, 18.0, 22.0, 30.0, 2:19.976`. POC-INSTR no cambia.
2. **Borrados:** en el punto medio de cada tramo entre bordes dentro del rango: `Select None`, cursor, `Select Events under Cursor` (si se puede) y `Delete`.
3. **Un trozo oculto:** al quitar el evento de encima reapareció un borde en 2,4 s. Era el final del primer evento, oculto bajo el segundo: el sondeo no ve los bordes de los trozos tapados del todo. Hizo falta **otra ronda**.
4. **Resultado:**
   - POC-TEST: bordes `2.0, 30.0, 2:19.976`, el hueco exacto ✅;
   - POC-INSTR: `2, 4, 6, 8`, sin cambios ✅.
5. **Deshacer:** **7 pasos** (2 cortes y 5 borrados) devolvieron POC-TEST exactamente a su estado inicial ✅.

## Conclusiones

- **Borrar dejando hueco** (`delete`) en una pista se puede hacer con la herramienta de objetos:
  1. cortar en los extremos solo esa pista;
  2. borrar por rondas, sondeando hasta que no quede nada dentro;
  3. verificar con el sondeo.
- **Seguridad:** antes de cada borrado se mide la selección con «Locate Selection / Selection End». Si sale del rango, porque el corte falló, no se borra.
- **Deshacer** necesita varios pasos. La herramienta debe informar de cuántos.
- **Cerrar el hueco** (`delete_time`) o **insertar silencio** en una sola pista desincronizaría esa pista del resto. No se ofrece.
