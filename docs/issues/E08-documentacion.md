# E08 — Documentación de usuario: manuales y tutoriales

Objetivo: que una persona que no conoce el proyecto pueda instalarlo, ponerlo en marcha y operarlo siguiendo los documentos, sin ayuda.

## TW-0801 Manual de instalación

- **Estado:** pendiente
- **Alcance:** `docs/manual/01-instalacion.md`.
  - Requisitos: macOS, Cubase 12 o posterior (verificado en Elements 15.0.30) y uv.
  - Clonar el repositorio y ejecutar `uv sync`.
  - Instalar el script en Cubase (`trackwright script install`).
  - Activar la superficie MIDI Remote en Cubase.
  - Comprobar con `trackwright doctor`.

## TW-0802 Manual de operación

- **Estado:** pendiente
- **Alcance:** `docs/manual/02-operacion.md`.
  - Arrancar y parar el puente.
  - Consultar su estado.
  - Conectar el servidor MCP a Claude Code y a Claude Desktop, con ejemplos de configuración.
  - Habilitar las escrituras.
  - Logs.

## TW-0803 Referencia de configuración

- **Estado:** pendiente
- **Alcance:** `docs/manual/03-configuracion.md`. Todas las claves del TOML y las variables de entorno, con sus valores por defecto y ejemplos.

## TW-0804 Referencia de herramientas MCP

- **Estado:** pendiente
- **Alcance:** `docs/manual/04-herramientas.md`.
  - Cada herramienta con su entrada, salida, errores, si escribe o no, su clase de comando y sus limitaciones conocidas.
  - Generada o validada contra el esquema real por un test (TW-0905).

## TW-0805 Resolución de problemas

- **Estado:** pendiente
- **Alcance:** `docs/manual/05-problemas.md`. Síntomas, causa y solución para:
  - puente no disponible;
  - Cubase no ve los puertos;
  - `STALE_SESSION`;
  - timeouts;
  - diálogos abiertos;
  - salida en «Sin bus»;
  - el script no recarga.

## TW-0806 Tutoriales paso a paso

- **Estado:** pendiente
- **Alcance:** `docs/tutoriales/`.
  1. Primera conexión, de cero a `cubase_status`.
  2. Inspeccionar una pista y sus plugins.
  3. Primer cambio seguro: ensayo, aplicación y restauración del volumen.
  4. Insertar un EQ y ajustar una banda.
  5. Marcadores y posición del cursor.
  6. Crear una pista con ayuda del diálogo.

## TW-0807 Documentación de desarrollo y arquitectura

- **Estado:** pendiente
- **Alcance:**
  - `docs/desarrollo.md`: comandos `uv`, tests, cobertura, pruebas con node, pruebas de integración opcionales y cómo añadir una herramienta.
  - `docs/arquitectura.md`: componentes, flujo de una petición y decisiones.
  - `README.md` con un inicio rápido y enlaces.
