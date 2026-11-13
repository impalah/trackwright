# Trackwright

**Trackwright** es un servidor [MCP](https://modelcontextprotocol.io) que permite a un asistente como Claude **inspeccionar y controlar Cubase**: pistas, mezcla, plugins de inserción y sus parámetros, transporte, marcadores y comandos. Funciona a través de un script MIDI Remote que se ejecuta dentro de Cubase.

| | |
|---|---|
| Paquete | `trackwright-mcp` |
| Ejecutable | `trackwright` |
| Servidor MCP | `trackwright` (stdio) |
| Plataforma | macOS, Cubase 15.0.20 o posterior (verificado en Elements 15.0.30) |

## Inicio rápido

```sh
cd /Volumes/Data/projects/sound/trackwright
uv sync
uv run trackwright script install --apply   # copia el script a Cubase; después reinicia Cubase
uv run trackwright bridge                   # en una terminal aparte; déjala abierta
uv run trackwright doctor                   # comprueba toda la cadena
claude mcp add trackwright -- uv --directory "$PWD" run trackwright serve
```

¿Sin Cubase a mano? `uv run trackwright serve --simulate` responde desde un Cubase simulado.

## Qué puede hacer

30 herramientas, todas con salida estructurada:

- **Lectura:** estado, pistas del mezclador, canal seleccionado, inserts, catálogo de plugins, parámetros, transporte y cambios recientes.
- **Escritura**, siempre con ensayo previo (`dry_run`) y verificación por relectura: parámetros (en valor normalizado o en unidades reales), inserción de plugins, volumen, mute, solo, armado, nombre de pista y tempo.
- **Navegación:** seleccionar pistas y mover el cursor y los localizadores.
- **Automatización:** graba curvas de volumen, panorama, envíos, EQ del canal, pre-filtro y parámetros de plugins, reproduciendo el proyecto, con valores en unidades reales (dB, Hz) que convierte Cubase. Verificado en Cubase Elements.
- **Edición de podcasts:** borrar, cortar o insertar silencio en un rango en segundos, en todas las pistas o en una, con verificación del resultado.
- **Guardar el proyecto:** solo a petición, con permiso propio (`[writes] save`), ensayo y verificación por la fecha del archivo.
- **Importar audio:** en la pista y la posición indicadas, con el selector de Cubase, y verificación por los bordes del evento nuevo.
- **Exportar la mezcla:** de un rango o del proyecto completo, con el diálogo de Cubase, y confirmación del archivo creado.
- **Comandos de Cubase:** marcadores, borrado de pistas, división en los localizadores, creación de pistas con ayuda del usuario y una lista de comandos permitidos. Cada comando indica cómo se comporta: si actúa directamente, si abre un diálogo o si pide confirmación.

Por defecto **solo lee**. Las escrituras se habilitan en la configuración y se pueden limitar a pistas concretas.

## Documentación

- **Manuales**
  - [Instalación](docs/manual/01-instalacion.md)
  - [Operación y conexión con Claude Code o Claude Desktop](docs/manual/02-operacion.md)
  - [Configuración](docs/manual/03-configuracion.md)
  - [Referencia de herramientas](docs/manual/04-herramientas.md)
  - [Resolución de problemas](docs/manual/05-problemas.md)
- **Tutoriales**
  1. [Primera conexión](docs/tutoriales/01-primera-conexion.md)
  2. [Inspeccionar una pista](docs/tutoriales/02-inspeccionar-pista.md)
  3. [Primer cambio seguro](docs/tutoriales/03-primer-cambio-seguro.md)
  4. [Insertar un EQ](docs/tutoriales/04-insertar-eq.md)
  5. [Marcadores y cursor](docs/tutoriales/05-marcadores-cursor.md)
  6. [Pista con diálogo](docs/tutoriales/06-pista-con-dialogo.md)
  7. [Grabar automatización](docs/tutoriales/07-automatizacion.md)
  8. [Editar un podcast por segundos](docs/tutoriales/08-podcast.md)
- **Proyecto**
  - [Arquitectura](docs/arquitectura.md)
  - [Desarrollo](docs/desarrollo.md)
  - [Épicas e issues](docs/issues/README.md)
  - [Investigación de funcionalidades ampliadas](docs/investigacion.md)

## Estado

- El diseño procede de la prueba de concepto `cubase-mcp-poc`, cuyas capacidades se verificaron contra Cubase Elements 15.0.30.
- El script `Trackwright_Bridge.js` deriva de esa versión. La verificación se hizo con la 1.0.0; la 1.1.0 añade el panel de estado de la superficie, verificado a la vista el 2026-11-13. Su verificación contra Cubase real se anota en el [registro de verificación](docs/verificacion.md). A 2026-11-12, **las 21 herramientas** se han ejecutado contra Cubase Elements 15.0.30, con confirmación visual del usuario donde la API no puede observar el resultado.
- El resto se prueba con tests unitarios, de contrato MCP, del script con Node.js y de extremo a extremo, con una cobertura superior al 95 %.

## Limitaciones conocidas

- **No es posible por la API** cambiar el enrutado (entradas, salidas o envíos), leer el contenido de las pistas (eventos, audio o automatización) ni completar diálogos de Cubase.
- **Solo se ven** las pistas que tienen canal de mezclador.
