# Experimento TW-1203: importar audio

[English](README.md) · **Español**

**Fecha:** 2026-11-13.
**Entorno:** Cubase Elements 15.0.30, script 1.5.4 y proyecto de pruebas (`X0001-02.cpr`).
**Archivo de prueba:** un tono de 440 Hz, mono, de 48 kHz y 16 bits y **3,000 s**, generado por Claude en su directorio temporal. No es audio del usuario.

## Pasos y resultados

1. **Preparación:** POC-TEST seleccionada y cursor en 150 s (relectura `0:02:30.000`). Bordes de POC-TEST: `2.0, 2.4, 6.0, 6.8, 18.0, 22.0, 139.976`.
2. **`File / Import Audio File`:** `canPerform = true`; abre el selector de archivos.
3. **Con el selector abierto, Cubase deja de responder al script:** la consulta siguiente dio `TIMEOUT` (3 s). Con el diálogo de exportación no pasaba. El selector es nativo de macOS y bloquea Cubase hasta cerrarse.
4. **El usuario** eligió el archivo (Cmd+Shift+G y la ruta) y aceptó las opciones tal como venían.
5. **Resultado:**
   - POC-TEST con bordes nuevos en **150.0 y 153.0**: el audio entra **en la pista seleccionada y en el cursor** ✅;
   - Cubase **copió** el archivo a `<proyecto>/Audio/tw1203-tono-3s.wav` (288 044 bytes) ✅.
6. **`Undo`** quitó el evento: los bordes volvieron a los originales ✅. **La copia en disco se queda.**

**Aparte:** en `Audio/` apareció `POC-TEST_01.wav`, de 0 bytes, creado a las 14:05:24, antes de la importación. Probablemente lo creó Cubase porque POC-TEST tiene la grabación activada. Trackwright no graba; no se tocó.

## Diseño de `cubase_import_audio`

- **Fase `start`:**
  1. seleccionar la pista;
  2. poner el cursor (en segundos o compases);
  3. si se da la ruta del archivo, comprobar que existe y leer su duración (`afinfo`);
  4. abrir el selector y **no hacer más llamadas a Cubase**, porque está bloqueado;
  5. devolver `awaiting_user`, con la ruta para Cmd+Shift+G.
- **Fase `confirm`:**
  - si Cubase aún no responde, el selector sigue abierto: `awaiting_user`;
  - si responde, sondear la pista: debe haber bordes en la posición y en la posición más la duración;
  - buscar la copia en `<proyecto>/Audio` posterior al inicio (solo nombre y fecha).
- **Deshacer** quita el evento, pero no la copia en disco.
