# E13 — Distribución

Origen: pregunta del usuario del 2026-11-13. Hoy Trackwright se usa desde el código fuente (`uv --directory … run trackwright`); el objetivo es instalarlo con **uv como único requisito**.

**Comprobado antes de abrir la épica** (2026-11-13, sin publicar nada; pruebas en un directorio temporal, ya borrado):
- `uv build` genera `trackwright_mcp-0.2.0-py3-none-any.whl`, con `trackwright/cubase/Trackwright_Bridge.js` dentro y el ejecutable `trackwright`;
- `uvx --from <wheel> trackwright version` y `script status` funcionan fuera del repositorio;
- `uv tool install <wheel>`, en un directorio aislado: `trackwright version` y `doctor` correctos contra el puente en marcha;
- **obstáculo:** el lock solo tiene **código fuente** de `python-rtmidi` 1.5.8. En un Mac limpio habría que compilarlo, y eso exige las herramientas de Xcode. Funciona en el Mac del usuario porque uv ya lo tiene compilado en caché.

## TW-1301 Instalación guiada: `trackwright setup`

- **Estado:** hecha (2026-11-13). Verificada en el Mac del usuario; detalle en [verificacion.md](../verificacion.md)
- **Implementación:** `trackwright/installer.py` (pasos, preguntas por stderr y resumen JSON por stdout) y `trackwright/doctor.py` (el diagnóstico, compartido con `doctor`). El comando que registra en Claude Code depende de cómo se ejecuta: desde el repositorio, `uv --directory <repo> run trackwright serve`; instalado con `uv tool`, la ruta absoluta de `trackwright`.
- **Objetivo:** que, tras instalar el paquete, un solo comando deje todo listo.
- **Pasos**, cada uno con lo que se va a hacer (destino, contenido y archivo que se reemplazaría) y **confirmación** antes de aplicarlo:
  1. instalar o actualizar el script en la carpeta MIDI Remote de Cubase (lo que hoy hace `script install --apply`);
  2. crear `~/.config/trackwright/config.toml` si no existe, preguntando si se habilitan las escrituras y el guardado (por defecto, no);
  3. registrar el servidor en Claude Code (`claude mcp add --scope user trackwright -- trackwright serve`), solo si `claude` está en el PATH, y si no, mostrar el comando;
  4. comprobación final con `doctor`.
- **Modo no interactivo:** `--yes` para cada paso por separado; nunca por defecto.
- **No hace:** instalar o cambiar nada de Cubase aparte del script; activar IAC o Accesibilidad; usar `sudo`.
- **Pruebas:** unitarias con los destinos en directorios temporales y las respuestas simuladas.

## TW-1302 Transporte MIDI con CoreMIDI vía `ctypes` (sin compilación)

- **Estado:** hecha (2026-11-13). Verificada con Cubase; detalle en [verificacion.md](../verificacion.md)
- **Objetivo:** que en macOS no haga falta compilar nada: el paquete pasa a ser Python puro.
- **Alcance:**
  1. un transporte nuevo, `CoreMidiTransport`, con `ctypes` sobre `CoreMIDI.framework` y `CoreFoundation.framework`:
     - un puerto virtual de salida (`MIDISourceCreate`) y uno de entrada (`MIDIDestinationCreate`, con callback);
     - envío de SysEx;
     - comprobación de nombres duplicados, como ahora;
  2. la misma interfaz `Transport` que el actual; `run_bridge` usa el nuevo en macOS.
- **Requisito del usuario: conservar el código de `rtmidi`.**
  - `MidiTransport` (mido + python-rtmidi) **no se borra**: queda como alternativa (por ejemplo, para probar en Windows) y se puede elegir con configuración (`[bridge] backend = "coremidi" | "rtmidi"`);
  - solo se cambian los imports necesarios: el de `mido` sigue siendo perezoso, dentro de `MidiTransport`;
  - en `pyproject.toml`, las dependencias `mido` y `python-rtmidi` quedan **comentadas**, no borradas, con una nota de cómo reactivarlas;
  - los tests de `MidiTransport`, con el backend simulado, se mantienen.
- **Verificación en Cubase**, obligatoria antes de cerrar:
  - Cubase ve los puertos «Trackwright To/From Cubase» y el script se conecta;
  - `ping`, `doctor` y una lectura y una escritura de las herramientas;
  - mensajes grandes (fragmentación SysEx), como en E02.
- **Riesgos:** el callback de entrada en un hilo de CoreMIDI (no bloquear y no lanzar excepciones al exterior) y la vida de los objetos `ctypes` (evitar que el recolector libere el callback).

## TW-1303 Canal de distribución

- **Estado:** pendiente; depende de TW-1302
- **Objetivo:** documentar e implementar la forma de instalar sin el repositorio.
- **Alcance:**
  1. **wheel local:** `uv build` y `uv tool install dist/trackwright_mcp-<versión>-py3-none-any.whl`; actualizar con `--reinstall`;
  2. **`uvx`:** registrar el servidor como `uvx --from <origen> trackwright serve`;
  3. un alias de ejecutable `trackwright-mcp`, para que funcione `uvx trackwright-mcp serve` si se publica;
  4. **decisión del usuario,** sin la que no se hace nada: publicar en PyPI (público), en un *release* de un repositorio remoto (hoy no hay ninguno) o solo con el wheel local. Antes de publicar, revisar los metadatos (autor, enlaces) para no exponer datos personales;
  5. manual de instalación reescrito para el usuario final, más un tutorial.
