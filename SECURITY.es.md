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

Los informes sobre estos límites (otro usuario local que alcanza el socket, un cliente que se salta la política de escritura, un comando que escribe cuando solo debería leer) son los más útiles.
