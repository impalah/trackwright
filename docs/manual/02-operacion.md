# Manual de operación

## Rutina diaria

1. **Arranca el puente** en una terminal y déjala abierta:
   ```sh
   cd /Volumes/Data/projects/sound/trackwright && uv run trackwright bridge
   ```
2. **Abre Cubase.** El orden no importa: si el puente arranca después, Cubase vuelve a conectar solo cuando aparecen los puertos.
3. **Usa tu cliente MCP.** Lanza `trackwright serve` cuando lo necesita.
4. **Al terminar,** pulsa **Ctrl+C** en la terminal del puente.

## Estado del puente

```sh
uv run trackwright bridge-status   # pid, peticiones, sesión del script, respuestas tardías, errores
uv run trackwright ping            # ida y vuelta Python → Cubase → Python
uv run trackwright doctor          # diagnóstico completo con soluciones
```

## Conectar un cliente MCP

El servidor se llama **`trackwright`** y usa el transporte **stdio**. El comando que debe lanzar el cliente es:

```sh
uv --directory /Volumes/Data/projects/sound/trackwright run trackwright serve
```

### Claude Code

```sh
claude mcp add trackwright -- uv --directory /Volumes/Data/projects/sound/trackwright run trackwright serve
```

- Añade `--scope user` para tenerlo en todos tus proyectos.
- Para comprobarlo: `claude mcp list`, o `/mcp` dentro de una sesión.

### Claude Desktop

Edita `~/Library/Application Support/Claude/claude_desktop_config.json` y añade:

```json
{
  "mcpServers": {
    "trackwright": {
      "command": "/opt/homebrew/bin/uv",
      "args": ["--directory", "/Volumes/Data/projects/sound/trackwright", "run", "trackwright", "serve"]
    }
  }
}
```

- Claude Desktop no hereda el `PATH` de tu terminal, así que usa la **ruta absoluta** de uv (la que muestre `which uv`).
- Reinicia Claude Desktop después de guardar el archivo.

### Probar sin Cubase: el simulador

```sh
uv --directory /Volumes/Data/projects/sound/trackwright run trackwright serve --simulate
```

Responde desde un Cubase simulado en memoria, con dos pistas: `POC-INSTR` y `POC-TEST`. Sirve para aprender las herramientas o depurar el cliente. `cubase_status` devuelve `simulated: true`, y nada de lo que responde dice nada sobre el Cubase real.

## Habilitar las escrituras

Por defecto, Trackwright **solo lee**. Para permitir cambios, crea `~/.config/trackwright/config.toml`:

```toml
[writes]
enabled = true
allowed_tracks = ["POC-TEST"]   # opcional: limita qué pistas se pueden modificar
```

No hace falta reiniciar el puente, porque la política la aplica el servidor MCP. Sí hay que reiniciar el cliente MCP, que es quien lanza `serve`. Detalles en la [referencia de configuración](03-configuracion.md).

Cómo trabaja el modelo con las escrituras:
1. Llama a la herramienta con `dry_run=true`, que es el valor por defecto, y te muestra el plan.
2. Tras tu conformidad, la llama con `dry_run=false`.
3. Trackwright aplica el cambio, lo relee y devuelve `verified`.

## Logs

- Van a stderr. Con `serve`, el cliente MCP suele guardarlos (por ejemplo, Claude Desktop en `~/Library/Logs/Claude/`).
- Para tener un archivo propio: `[logging] file = "~/Library/Logs/trackwright/trackwright.log"`.
- Más detalle: `--log-level DEBUG` o `[logging] level = "DEBUG"`.

## Qué pasa cuando algo se reinicia

| Situación | Efecto | Qué hacer |
|---|---|---|
| Reinicias el puente | Cubase vuelve a conectar solo. Las `ref` siguen siendo válidas. | Nada. |
| Reinicias Cubase o recargas el script | Nueva sesión: las `ref` anteriores dan `STALE_REF`. | Volver a listar. Los selectores `uid:` siguen valiendo. |
| Actualizas Trackwright | Puede traer un script nuevo. | `uv run trackwright script install --apply` y reiniciar Cubase. |
| Una escritura vence por tiempo | Resultado desconocido; no se reintenta. | Revisar el `read_back` del error. |

## Buenas prácticas

- Trabaja con el **transporte parado** mientras el modelo cambia parámetros.
- **Guarda el proyecto antes** de sesiones con escrituras. Trackwright no guarda nunca.
- Para tareas largas, limita las escrituras con `allowed_tracks`.
- Ante un `dialog` o un `ui_selection`, mira la pantalla de Cubase: Trackwright no puede verla.
