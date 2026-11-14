# Manual de instalación

[English](01-installation.md) · **Español**

Trackwright es un servidor MCP para DAW; esta primera versión es para Cubase. Al terminar este manual tendrás Trackwright instalado, el script cargado en Cubase y una comprobación de que Python y Cubase se hablan. Calcula unos 15 minutos.

> **Estado de la verificación.** El protocolo y las operaciones del script se verificaron contra Cubase Elements 15.0.30 en la prueba de concepto (`cubase-mcp-poc`). El script `Trackwright_Bridge.js` deriva de esa versión. Antes de usarlo en serio, ejecuta los tests de integración del paso 9.

## Cómo encajan las piezas

```text
Cliente MCP (Claude, Copilot…) ──stdio──► trackwright serve ──socket local──► trackwright bridge ──MIDI virtual──► Cubase (script MIDI Remote)
```

- **`trackwright bridge`:** el puente. Crea los puertos MIDI virtuales por los que habla con Cubase. `trackwright serve` lo arranca solo si no está en marcha; también puedes lanzarlo a mano en una terminal.
- **`trackwright serve`:** el servidor MCP. No lo arrancas tú: lo lanza tu cliente MCP (Claude Code, Claude Desktop, GitHub Copilot…) cuando lo necesita.
- **El script `Trackwright_Bridge.js`:** se ejecuta dentro de Cubase y responde a las peticiones.

## 1. Requisitos

| Requisito | Versión | Cómo comprobarlo |
|---|---|---|
| macOS | Verificado en 27.2 (Apple Silicon) | ` > Acerca de este Mac` |
| Cubase | 15.0.20 o posterior (API MIDI Remote 1.3). Verificado en Elements 15.0.30 | `Ayuda > Acerca de Cubase` |
| uv | 0.13 o posterior | `uv --version` |
| git | cualquiera (solo para instalar desde el código fuente) | `git --version` |

Si no tienes uv, instálalo con Homebrew: `brew install uv`. **No hace falta instalar Python**: uv descarga la versión adecuada (3.14) la primera vez. Tampoco hay nada que compilar.

## 2. Instalar Trackwright

### Desde PyPI (recomendado)

```sh
uv tool install trackwright
trackwright version
```

uv instala el ejecutable `trackwright` en `~/.local/bin`. Si el terminal no lo encuentra, ejecuta `uv tool update-shell` y abre otro terminal. Con esta instalación, **escribe los comandos de los manuales sin `uv run`**: `trackwright setup`, `trackwright doctor`…

Para actualizar: `uv tool upgrade trackwright`, después `trackwright setup` (actualiza el script de Cubase si cambió) y reinicia Cubase.

Sigue en la [instalación guiada](#instalación-guiada-recomendada).

### Desde el código fuente (desarrollo)

```sh
git clone https://github.com/impalah/trackwright.git
cd trackwright
```

Los manuales escriben `/ruta/a/trackwright` para la carpeta donde lo clonaste: sustitúyela por la tuya.

## 3. Crear el entorno (solo desde el código fuente)

```sh
uv sync
```

uv crea `.venv/` dentro del proyecto con todas las dependencias. Compruébalo:

```sh
uv run trackwright version
```

Debe responder algo como `{"trackwright": "0.2.0"}`.

## Instalación guiada (recomendada)

Un solo comando hace los pasos 4 y 8 y la comprobación del 7:

```sh
trackwright setup          # instalado desde PyPI
uv run trackwright setup   # desde el código fuente
```

El servidor queda registrado en Claude Code con el comando que corresponde a cada caso: la ruta absoluta de `trackwright` si lo instalaste con `uv tool`, o `uv --directory <repositorio> run trackwright serve` desde el código fuente.

Recorre tres pasos. En cada uno **muestra lo que va a hacer y pregunta** antes de aplicarlo (la respuesta por defecto es «no»):

1. **Script de Cubase:** el destino, la versión y, si ya había uno, la versión que se reemplaza. Si ya está al día, no hace nada.
2. **Configuración:** si `~/.config/trackwright/config.toml` no existe, pregunta si se permiten las escrituras y el guardado (por defecto, no), enseña el contenido y lo crea con permisos `600`. **Un archivo que ya existe no se toca.**
3. **Claude Code:** si `claude` está en el `PATH` y el servidor no está registrado, enseña el comando `claude mcp add --scope user trackwright -- …` y lo ejecuta. Si no encuentra `claude`, solo muestra el comando. **Un registro existente no se reemplaza.**

Al final ejecuta `doctor` y lista lo que queda por hacer, por ejemplo reiniciar Cubase. Justo después de instalar es normal que falle «bridge running»: el puente arranca con el servidor MCP.

Las preguntas salen por la salida de error; por la salida estándar, un resumen en JSON. Opciones:

| Opción | Efecto |
|---|---|
| `--yes script`, `--yes config`, `--yes claude` | Aplica ese paso sin preguntar. Se repite para varios pasos; no hay un «sí a todo» implícito. |
| `--writes` / `--no-writes` | Al crear la configuración, permite o no las escrituras. Con `--yes config` y sin esta opción: no. |
| `--save` / `--no-save` | Igual para el guardado del proyecto. Solo cuenta con las escrituras permitidas. |
| `--config RUTA` (antes de `setup`) | Crea o usa la configuración en otra ruta. |

`setup` nunca usa `sudo`, ni cambia ajustes de Cubase, IAC o Accesibilidad. Después sigue en el paso 6 (activar el script en Cubase).

Si prefieres hacerlo a mano, sigue los pasos 4 a 8.

## 4. Instalar el script en Cubase

Primero un ensayo, que no copia nada y solo muestra el destino:

```sh
uv run trackwright script install
```

Verás el destino, por defecto `~/Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/trackwright/bridge/Trackwright_Bridge.js`, y su estado: `missing`, `different` o `up_to_date`. Si es correcto, cópialo:

```sh
uv run trackwright script install --apply
```

Cubase **no recarga** los scripts cambiados por sí mismo. Si estaba abierto, reinícialo en el paso 6.

## 5. Arrancar el puente

**Normalmente no hace falta:** el servidor MCP arranca el puente cuando lo necesita (`[bridge] autostart`). Arrancarlo a mano sirve para hacer las comprobaciones del paso 7 antes de conectar tu cliente MCP, o para ver su log en directo. En una terminal que dejarás abierta:

```sh
cd /ruta/a/trackwright
uv run trackwright bridge
```

Verás `virtual MIDI ports open` y `bridge listening on …/bridge.sock`. Mientras esta terminal siga abierta, existen los puertos `Trackwright To Cubase` y `Trackwright From Cubase`.

## 6. Activar el script en Cubase

1. Abre Cubase o reinícialo, y abre un proyecto. Para las primeras pruebas, mejor un proyecto vacío y desechable.
2. Cubase detecta solo la superficie **Trackwright – Bridge** cuando los puertos existen. Para comprobarlo, abre la pestaña **MIDI Remote** de la zona inferior de la ventana de proyecto.
3. Si no aparece, en esa pestaña pulsa **+ Añadir superficie de controlador MIDI** (*Add MIDI Controller Surface*) y elige:
   - Fabricante: `Trackwright`;
   - Modelo: `Bridge`;
   - Entrada MIDI: `Trackwright To Cubase`;
   - Salida MIDI: `Trackwright From Cubase`.
4. **Qué verás en la superficie** cuando el puente esté en marcha:
   - **Fila 1:** «Trackwright» con la versión del script cargado, y una **lámpara** a la derecha. La lámpara se enciende un instante cada vez que Trackwright envía una petición a Cubase.
   - **Fila 2:** el nombre de la pista seleccionada. Muestra «-» si la seleccionada no tiene canal de mezclador (marcadores, carpetas) o si no hay ninguna seleccionada.

   - **A la derecha:** decenas de faders. Son los controles de automatización (volumen, panorama, envíos, EQ, pre-filtro, Quick Controls y parámetros de plugins de la pista seleccionada) que usa `cubase_record_automation`. No los asignes a otras funciones en el asistente de asignación.

   Con el puente parado, solo se ve la lámpara: los textos aparecen cuando la página «Bridge» se activa.
5. **Recomendado:** en *Estudio > Configuración de estudio > Configuración de puertos MIDI* (*Studio > Studio Setup > MIDI Port Setup*), desmarca la columna **«En 'All MIDI Inputs'»** de `Trackwright To Cubase`. Así los mensajes de control no llegan nunca a una pista.

Los nombres exactos de los menús en español pueden variar ligeramente según la versión.

## 7. Comprobar la conexión

```sh
uv run trackwright ping
```

Debe responder `"ok": true`, con la versión del script (por ejemplo, `1.0.1`) y el eco `hola-ñ-✓`. Después ejecuta el diagnóstico completo:

```sh
uv run trackwright doctor
```

`doctor` revisa cada eslabón y, si algo falla, indica qué hacer (`fix`). Todo debe salir con `"ok": true`.

## 8. Conectar tu cliente MCP

Sigue el [manual de operación](02-operation.es.md#conectar-un-cliente-mcp).

## 9. Verificación contra tu Cubase (desde el código fuente)

Con el puente en marcha y Cubase abierto:

```sh
TRACKWRIGHT_INTEGRATION=1 uv run pytest tests/integration -v
```

Para probar también escrituras reversibles sobre una pista de pruebas (usa un proyecto desechable):

```sh
TRACKWRIGHT_INTEGRATION=1 TRACKWRIGHT_ALLOW_WRITES=1 TRACKWRIGHT_TEST_TRACK="POC-TEST" \
  uv run pytest tests/integration -v
```

Cada escritura se deshace al terminar la prueba.

## Desinstalar

1. Borra la carpeta `~/Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/trackwright/`.
2. En Cubase, elimina la superficie **Trackwright – Bridge** de la pestaña MIDI Remote.
3. Quita el servidor de Claude Code (`claude mcp remove trackwright -s user`), para el puente (`trackwright bridge-stop`) y desinstala Trackwright: `uv tool uninstall trackwright`, o borra el repositorio si lo instalaste desde el código fuente.
4. Si lo creaste, borra `~/.config/trackwright/`.
