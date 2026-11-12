# Manual de instalación

Al terminar este manual tendrás Trackwright instalado, el script cargado en Cubase y una comprobación de que Python y Cubase se hablan. Calcula unos 15 minutos.

> **Estado de la verificación.** El protocolo y las operaciones del script se verificaron contra Cubase Elements 15.0.30 en la prueba de concepto (`cubase-mcp-poc`). El script `Trackwright_Bridge.js` 1.0.0 deriva de esa versión. Antes de usarlo en serio, ejecuta los tests de integración del paso 9.

## Cómo encajan las piezas

```text
Cliente MCP (Claude) ──stdio──► trackwright serve ──socket local──► trackwright bridge ──MIDI virtual──► Cubase (script MIDI Remote)
```

- **`trackwright bridge`:** un proceso que dejas abierto en una terminal. Crea los puertos MIDI virtuales por los que habla con Cubase.
- **`trackwright serve`:** el servidor MCP. No lo arrancas tú: lo lanza tu cliente MCP (Claude Code o Claude Desktop) cuando lo necesita.
- **El script `Trackwright_Bridge.js`:** se ejecuta dentro de Cubase y responde a las peticiones.

## 1. Requisitos

| Requisito | Versión | Cómo comprobarlo |
|---|---|---|
| macOS | Verificado en 27.2 (Apple Silicon) | ` > Acerca de este Mac` |
| Cubase | 15.0.20 o posterior (API MIDI Remote 1.3). Verificado en Elements 15.0.30 | `Ayuda > Acerca de Cubase` |
| uv | 0.13 o posterior | `uv --version` |
| git | cualquiera | `git --version` |

Si no tienes uv, instálalo con Homebrew: `brew install uv`. **No hace falta instalar Python**: uv descarga la versión adecuada (3.14) la primera vez.

## 2. Obtener el código

El repositorio es local, sin remoto todavía:

```sh
cd /Volumes/Data/projects/sound/trackwright
```

Si lo copias a otra ubicación, sustituye esa ruta en el resto de los manuales.

## 3. Crear el entorno

```sh
uv sync
```

uv crea `.venv/` dentro del proyecto con todas las dependencias. Compruébalo:

```sh
uv run trackwright version
```

Debe responder algo como `{"trackwright": "0.1.0"}`.

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

En una terminal que dejarás abierta:

```sh
cd /Volumes/Data/projects/sound/trackwright
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
4. **Recomendado:** en *Estudio > Configuración de estudio > Configuración de puertos MIDI* (*Studio > Studio Setup > MIDI Port Setup*), desmarca la columna **«En 'All MIDI Inputs'»** de `Trackwright To Cubase`. Así los mensajes de control no llegan nunca a una pista.

Los nombres exactos de los menús en español pueden variar ligeramente según la versión.

## 7. Comprobar la conexión

```sh
uv run trackwright ping
```

Debe responder `"ok": true`, con la versión del script (`1.0.0`) y el eco `hola-ñ-✓`. Después ejecuta el diagnóstico completo:

```sh
uv run trackwright doctor
```

`doctor` revisa cada eslabón y, si algo falla, indica qué hacer (`fix`). Todo debe salir con `"ok": true`.

## 8. Conectar tu cliente MCP

Sigue el [manual de operación](02-operacion.md#conectar-un-cliente-mcp).

## 9. Verificación contra tu Cubase (recomendado)

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
3. Borra el directorio del repositorio y, si lo creaste, `~/.config/trackwright/`.
