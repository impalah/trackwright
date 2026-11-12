# Cambios

## 0.1.0 — 2026-11-12

Primera versión, basada en el diseño verificado en la prueba de concepto `cubase-mcp-poc`.

- **Servidor MCP `trackwright`** con 21 herramientas: 9 de lectura, 7 de escritura y navegación, y 5 basadas en comandos.
- **Script MIDI Remote** `Trackwright_Bridge.js` 1.0.0, con su instalador (`trackwright script install`).
- **Puente** con puertos virtuales CoreMIDI e IPC por socket Unix privado.
- **Seguridad:** solo lectura por defecto, ensayo (`dry_run`) en todas las escrituras, verificación por relectura, sin reintentos y referencias opacas validadas.
- **Simulador** `FakeCubase` y modo `trackwright serve --simulate`.
- **Diagnóstico** `trackwright doctor`.
- **Pruebas:** unitarias, de contrato MCP, del script con Node.js, de extremo a extremo y de integración opcionales contra Cubase.
- **Documentación:** manuales, tutoriales, arquitectura, desarrollo e issues.
