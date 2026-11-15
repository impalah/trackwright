# Política de seguridad

[English](SECURITY.md) · **Español**

## Versiones con soporte

Solo la última versión publicada en PyPI recibe correcciones.

## Informar de una vulnerabilidad

No abras una issue pública. Usa el informe privado de vulnerabilidades de GitHub: **Security → Report a vulnerability** en el repositorio. Indica la versión, qué puede hacer un atacante y cómo reproducirlo.

Recibirás respuesta lo antes posible. Es un proyecto personal mantenido en el tiempo libre, así que no hay un plazo de respuesta fijo.

## Qué expone Trackwright

- Ningún puerto de red. `trackwright serve` habla con su cliente MCP por stdio; el puente escucha en un socket Unix dentro de un directorio privado (modo 0700) del usuario.
- Dos puertos MIDI virtuales, usados solo por el script de Cubase. Trackwright nunca envía a dispositivos físicos ni a «All MIDI Inputs».
- Las escrituras en el proyecto de Cubase están desactivadas por defecto (`[writes] enabled = false`), se pueden limitar a algunas pistas, y guardar necesita su propio interruptor (`[writes] save`).
- La lectura de audio está desactivada por defecto (`[analysis] enabled = false`). Si se activa, Trackwright lee las muestras de los archivos que se le pide analizar (exportaciones hechas por el usuario), solo en lectura y con una duración limitada (`[analysis] max_seconds`); del proceso solo salen las medidas, como respuestas al cliente MCP.
- Escribir en la carpeta de un proyecto está desactivado por defecto (`[workspace] enabled = false`). Si se activa, Trackwright escribe solo dentro de una carpeta `Trackwright/` en ella; cada ruta se comprueba para que quede dentro, y se rechaza un `Trackwright` que sea un enlace simbólico.

Los informes sobre estos límites (otro usuario local que alcanza el socket, un cliente que se salta la política de escritura, un comando que escribe cuando solo debería leer) son los más útiles.
