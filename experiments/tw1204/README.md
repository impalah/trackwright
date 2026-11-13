# Experimento TW-1204: exportar la mezcla

**Fecha:** 2026-11-13.
**Entorno:** Cubase Elements 15.0.30, script 1.5.2 y proyecto de pruebas.

## Resultados

1. **`File / Export Audio Mixdown`:**
   - `canPerform = true`;
   - abre el diálogo «Exportar mezcla de audio» (clase **dialog**);
   - con el diálogo abierto, el script sigue respondiendo y `Undo` informa `canPerform = false`.
2. **Diálogo, en Elements y según la captura del usuario:**
   - **canal:** Stereo Out;
   - **nombre:** el del proyecto (`X0001`);
   - **ruta:** `<carpeta del proyecto>/Mixdown`;
   - **formato propuesto:** MP3, 44,1 kHz, 128 kB/s;
   - **conflictos:** «Preguntar siempre»;
   - **no hay campo de rango:** se exporta entre los localizadores.
3. **Exportación con los localizadores en 2–30 s** (puestos por Trackwright en segundos): `Mixdown/X0001.mp3`, de 447 986 bytes y **27,99 s** (`afinfo`), que son los 28 s del rango ✅.
4. **Proyecto completo:** `Edit / Select All`, `Transport / Locators to Selection` y `Select None` dejan los localizadores en `1. 1. 1. 0` – `70. 4. 4. 97`, es decir, 0 → 2:19,976 s, el final del último evento ✅. Sin cambios en el proyecto.

## Conclusiones para `cubase_export_mix`

- **Fase `start`:**
  1. colocar los localizadores en el rango pedido, o en todo el audio;
  2. abrir el diálogo;
  3. devolver `awaiting_user`, con la carpeta prevista (`<proyecto>/Mixdown`, deducida con `lsof`), la duración esperada y la marca de tiempo.
- **Fase `confirm`:** buscar en la carpeta los archivos de audio creados después de esa marca y comprobar su duración (`afinfo`). Se leen solo nombre, tamaño, fecha y duración.
- **Trackwright nunca exporta:** el usuario elige el formato y pulsa «Exportar audio».
