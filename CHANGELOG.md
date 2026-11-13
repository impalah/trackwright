# Cambios

## Sin publicar

- **Automatización** (TW-1207):
  - herramientas `cubase_list_automation_targets` y `cubase_record_automation`: graban curvas de volumen, panorama, envíos, EQ del canal, pre-filtro y parámetros de plugins de inserción, reproduciendo el proyecto, con verificación opcional;
  - **script 1.4.0**, con 45 controles de automatización activos en la superficie y las operaciones `auto.control` y `auto.list`;
  - el simulador reproduce y graba automatización.
- **Script 1.2.2:** comandos `Transport / Start` y `Stop` (`transport.start`, `transport.stop`), para reproducir sin intervención del usuario. Nunca graba.
- **Script 1.2.1:** fader de automatización experimental (TW-1206, variante B2), **desactivado** (`AUTOMATION_FADER_ENABLED = false`), y la operación `auto.fader`, que responde `UNSUPPORTED` mientras esté desactivado. La versión de prueba se genera con `experiments/tw1206/build.py`.
- **Script 1.2.0:** comandos de automatización (modos Touch, Auto-Latch y Cross-Over, siguiente modo y escritura en las pistas seleccionadas) para el experimento TW-1206. Clase `unknown` hasta observarlos.
- **Script 1.1.0:** panel de estado en la superficie MIDI Remote (TW-1101): título con la versión, pista seleccionada y lámpara de actividad. Solo usa mecanismos verificados en Cubase 15. Las operaciones no cambian.
- **Experimento TW-1101** (`experiments/tw1101/README.md`): protocolo y resultados, en `docs/verificacion.md`.
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
