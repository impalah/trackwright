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

## Resultados (2026-11-13, Cubase Elements 15.0.30, script 1.5.0, con el usuario mirando)

**Estado de partida:**
- POC-TEST con 5 eventos de audio, algunos solapados y compartiendo archivo;
- POC-INSTR con 4 partes MIDI en los compases 1–5;
- 120 BPM, 4/4 y proyecto guardado.

### 1. Posiciones en segundos

- **Cursor:** `set_position(cursor, 0:00:02.000, seconds)` funciona. `time2` del Transport lo relee exacto (`0:00:02.000`, `0:00:30.000`).
- **Localizadores, directamente: ❌ falla.** Al pedir `0:00:02.000` y `0:00:30.000` por la pantalla secundaria quedaron en `1. 1. 1. 0` y `1. 3. 2. 0`.
- **Localizadores, con rodeo: ✅ funciona.** Se pone el cursor en segundos y se lanza `Transport / Set Left Locator` o `Set Right Locator` (clase *direct*). El ciclo quedó en `2. 1. 1. 0` – `16. 1. 1. 0` (2–30 s).

### 2. Sondeo de eventos

- **`Locate Next Event`** recorre los bordes (inicios y finales mezclados) de los eventos de las **pistas seleccionadas**. Sin pista seleccionada no se mueve.
  - POC-TEST: `2.0, 2.4, 6.0, 6.8, 18.0, 22.0, 2:19.976` s.
  - Coincide con la captura del usuario: eventos solapados que empiezan en 0, 2, 6, 18 y 22 s.
- **`Locate Selection` / `Locate Selection End`** dan el inicio y el final de la selección completa. Con `Select All on Tracks`: 0 → 2:19,976.

### 3. Selección

- **Herramienta Objeto:** `Select in Loop` seleccionó solo el primer evento (0–2,4 s). No sirve.
- **Herramienta Selección de rango** (tecla 2, cambiada por el usuario): `Select in Loop` crea un **rango 2,000–30,000 s en todas las pistas**, no solo en la seleccionada (lo observó el usuario). Con rango, `Crop Range` pasa a poderse ejecutar.
- **El ciclo sigue a la selección de rango:** un clic con la herramienta de rango dejó los localizadores en `1. 3. 1. 0` – `1. 3. 1. 0`, y entonces `Select in Loop` no se podía ejecutar.

### 4. Acciones sobre el rango 2–30 s

Medidas con el sondeo de POC-TEST, y cada una deshecha antes de la siguiente:

| Acción | Clase | Bordes después | Interpretación | `Undo` |
|---|---|---|---|---|
| `Edit / Delete` | direct | `2.0, 30.0, 2:19.976` | Hueco entre 2 y 30 s; nada se mueve | ✅ exacto |
| `Edit / Delete Time` | direct | `2.0, 1:51.976` | Quita 28 s y adelanta lo posterior | ✅ exacto |
| `Edit / Cut Time` | direct | `2.0, 1:51.976` | Igual que Delete Time, y lo copia al portapapeles | ✅ exacto |
| `Edit / Insert Silence` | direct | todo +28 s, final `2:47.976` | Inserta 28 s de silencio en 2 s | ✅ exacto |
| `Edit / Crop Range` | direct | `2.0 … 30.0` | Deja solo el rango. El borde de 2,4 s no apareció: sin explicar | ✅ exacto |
| `Process / Silence` | **dialog** | sin cambios | Avisa de que hay eventos que comparten archivo («Continuar / Nueva versión / Cancelar», con «No volver a preguntar»). El usuario canceló sin marcar la casilla | — |

- Todas actúan sobre las **pistas incluidas en el rango**, que con `Select in Loop` son todas.
- Mientras hay un diálogo abierto, `Undo` informa `canPerform = false`. Sirve para detectar un diálogo pendiente.
- La selección de rango sobrevive a `Undo`.

## Conclusiones para `cubase_edit_range`

1. **Rango:** cursor en segundos o en compases, `Set Left/Right Locator`, herramienta de rango (`Tool / Range Tool`, que hay que añadir al script), `Select in Loop`, acción y vuelta a la herramienta anterior (`Tool / Select Tool`).
2. **Verificación:** sondeo con `Locate Next Event` sobre las pistas seleccionadas, antes y después, comparado con lo esperado para cada acción.
3. **Alcance:** todas las pistas. Es lo natural para cortar un podcast (`Delete Time`). Borrar solo en una pista necesita otra vía (por investigar).
4. **`Process / Silence`:** interactivo, porque el diálogo depende de que el archivo esté compartido.
5. **Deshacer:** `Undo` funciona como red de seguridad. Un `Undo` fallido (`canPerform = false`) indica un diálogo abierto.
