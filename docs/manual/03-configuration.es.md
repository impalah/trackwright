# Referencia de configuración

[English](03-configuration.md) · **Español**

Trackwright funciona **sin archivo de configuración**. Por defecto es de solo lectura: ninguna herramienta modifica el proyecto hasta que habilites las escrituras.

## Dónde se busca el archivo

| Orden | Ubicación |
|---|---|
| 1 | La ruta indicada con `--config <archivo>` en la línea de comandos |
| 2 | La ruta de la variable de entorno `TRACKWRIGHT_CONFIG` (si la defines, el archivo debe existir) |
| 3 | `~/.config/trackwright/config.toml` (opcional) |

Para ver la configuración efectiva, ya combinada:

```sh
uv run trackwright config
```

## Ejemplo completo

```toml
# ~/.config/trackwright/config.toml

[bridge]
to_cubase_port = "Trackwright To Cubase"
from_cubase_port = "Trackwright From Cubase"
# socket_dir = "/private/tmp/mi-directorio"   # por defecto: $TMPDIR/trackwright-<uid>
request_timeout = 3.0
write_timeout = 5.0
backend = "auto"           # coremidi en macOS (sin compilar); rtmidi como alternativa
autostart = true            # serve arranca el puente si no está en marcha
autostart_timeout = 10.0

[cubase]
app = "Cubase 15"
launch_timeout = 120.0

[writes]
enabled = true
allowed_tracks = ["POC-TEST", "Voz"]   # vacío = todas las pistas
save = false                           # true = cubase_save_project puede guardar el .cpr

[logging]
level = "INFO"
file = "~/Library/Logs/trackwright/trackwright.log"

[script]
# install_dir = "~/Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/trackwright/bridge"
```

Las claves desconocidas se rechazan con `CONFIG_ERROR`, para que una errata no pase desapercibida.

## `[bridge]`

| Clave | Por defecto | Descripción |
|---|---|---|
| `to_cubase_port` | `"Trackwright To Cubase"` | Puerto virtual por el que Python escribe. Cubase lo ve como **entrada** del script. |
| `from_cubase_port` | `"Trackwright From Cubase"` | Puerto virtual por el que Python lee. Cubase lo ve como **salida** del script. |
| `socket_dir` | `$TMPDIR/trackwright-<uid>` | Directorio privado (permisos 0700) del socket local `bridge.sock`. No uses un volumen montado con `noowners`. |
| `request_timeout` | `3.0` | Segundos de espera de una lectura (entre 0,05 y 30). |
| `write_timeout` | `5.0` | Segundos de espera de una escritura (entre 0,05 y 30). Tras un timeout, el resultado es desconocido: Trackwright no reintenta. |
| `backend` | `"auto"` | Transporte MIDI. `coremidi`: CoreMIDI desde Python con `ctypes`; es Python puro, sin compilar nada (macOS). `rtmidi`: mido + python-rtmidi, para otras plataformas o como alternativa; hay que descomentar esas dependencias en `pyproject.toml`. `auto`: `coremidi` en macOS y `rtmidi` en el resto. |
| `autostart` | `true` | Si `trackwright serve` no encuentra el puente, lo arranca como proceso independiente. No lo duplica si ya existe, y su log va a `bridge.log` dentro de `socket_dir`. |
| `autostart_timeout` | `10.0` | Segundos de espera a que el puente arrancado acepte conexiones (entre 0,5 y 60). |

Si cambias los nombres de los puertos, el script de Cubase no los encontrará, porque también los lleva escritos. Déjalos como están salvo que sepas lo que haces.

## `[cubase]`

| Clave | Por defecto | Descripción |
|---|---|---|
| `app` | `"Cubase 15"` | Nombre de la aplicación para `open -a` y del proceso para `pgrep -x`. Cámbialo si usas otra versión, por ejemplo `"Cubase 14"`. |
| `launch_timeout` | `120.0` | Segundos que `cubase_launch` espera a que el script responda tras abrir Cubase (entre 5 y 600). |

## `[writes]`

| Clave | Por defecto | Descripción |
|---|---|---|
| `enabled` | `false` | Interruptor general. Con `false`, las escrituras fallan con `WRITES_DISABLED`; los ensayos (`dry_run`) y la navegación siguen funcionando. |
| `allowed_tracks` | `[]` | Nombres de pista que se pueden modificar. Vacío significa todas. Fuera de la lista: `NOT_ALLOWED`. |
| `save` | `false` | Permite que `cubase_save_project` **guarde el archivo del proyecto en disco**. Es independiente de `enabled`, y hacen falta las dos. Sin él: `SAVE_DISABLED`. Los ensayos funcionan siempre. |

Qué cuenta como escritura:
- **Escritura** (sujeta a `[writes]`): parámetros, mezcla, nombre, plugins, tempo, marcadores, borrado y división de eventos, comandos.
- **Navegación** (siempre permitida): seleccionar una pista, mover el cursor o los localizadores, saltar entre marcadores.

## `[logging]`

| Clave | Por defecto | Descripción |
|---|---|---|
| `level` | `"INFO"` | `TRACE`, `DEBUG`, `INFO`, `SUCCESS`, `WARNING`, `ERROR` o `CRITICAL`. También con `--log-level`. |
| `file` | sin archivo | Archivo de log adicional. Rota a los 10 MB y conserva 5 archivos. |

Los logs van siempre a **stderr**, nunca a stdout, porque con `trackwright serve` stdout transporta el protocolo MCP.

## `[script]`

| Clave | Por defecto | Descripción |
|---|---|---|
| `install_dir` | `~/Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/trackwright/bridge` | Carpeta donde `trackwright script install` copia `Trackwright_Bridge.js`. |

## Variables de entorno

| Variable | Uso |
|---|---|
| `TRACKWRIGHT_CONFIG` | Ruta del archivo de configuración. |
| `TMPDIR` | Base del directorio del socket por defecto. |
| `TRACKWRIGHT_INTEGRATION`, `TRACKWRIGHT_ALLOW_WRITES`, `TRACKWRIGHT_TEST_TRACK` | Solo para los tests de integración (ver [desarrollo](../development.es.md)). |
