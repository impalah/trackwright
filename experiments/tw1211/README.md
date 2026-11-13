# Experimento TW-1211: edición por rangos en segundos

**Requisitos:**
- script **1.5.0**, que añade 12 comandos de edición de rangos y de sondeo de eventos;
- el proyecto de pruebas **guardado**;
- el usuario mirando Cubase.

**Herramienta:** `uv run python experiments/tw1211/probe.py <paso>` (ver la ayuda del script). Los pasos destructivos solo actúan con `--apply`.

## Plan

1. **Segundos:** `seconds cursor 0:00:02.000` y `seconds cycle_left/right`. Se relee `time2` del Transport.
2. **Sondeo de eventos:** `events`. ¿`Locate Next Event` recorre los bordes de los eventos? ¿Los de todas las pistas o solo los de las seleccionadas?
3. **Alcance de `Select in Loop`:** con POC-TEST seleccionada y el ciclo en 2–30 s, ¿qué pistas quedan con selección de rango? Lo observa el usuario.
4. **Acciones**, una cada vez, y deshaciendo entre una y otra:
   - `Delete` sobre la selección;
   - `Delete Time`, `Cut Time`, `Process / Silence`, `Insert Silence` y `Crop Range`.

   Para cada una: si actúa sin diálogo, qué cambia (lo observa el usuario, y con `events` si el sondeo funciona) y si `Undo` lo deshace.

## Resultados

(pendiente)
