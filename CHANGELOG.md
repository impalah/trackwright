# Cambios

## Sin publicar

- **Script 1.0.1:** incluye el panel de estado de la superficie MIDI Remote (TW-1101), **desactivado** (`PANEL_ENABLED = false`). Las operaciones no cambian.
- **Experimento TW-1101** en `experiments/tw1101/`: genera una versión de prueba con el panel activado.
- **`trackwright script install --file <script>`:** instala otro script, como el del experimento.
- **Simulador:** «Locate Next Marker» sin marcador siguiente va al final del último evento, como en Cubase 15.

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
- **Endurecimiento** tras una revisión independiente (épica E10):
  - sesión fijada durante cada herramienta;
  - borrado solo con selección única;
  - paginación del filtro de parámetros sin pérdidas;
  - plazo único con `BUSY` en el puente;
  - `INTERNAL_ERROR` con resultado desconocido;
  - cambios ya aplicados en los errores parciales;
  - `expectTitle` comprobado en el script.
