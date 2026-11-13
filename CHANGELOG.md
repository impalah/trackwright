# Cambios

## Sin publicar

- **Ajustes del proyecto** (TW-1210):
  - herramienta `cubase_set_project`: ciclo, metrónomo, precuenta, punch, uso del pre-roll y post-roll, clic al reproducir y al grabar, y nivel del clic, con relectura;
  - `cubase_get_project` da el nivel del clic como 0–127.
- **Importar audio** (TW-1203):
  - herramienta `cubase_import_audio` en dos fases: pista, posición y selector de Cubase; después, la confirmación por sondeo de bordes y la copia en el proyecto;
  - **script 1.5.4**, con `File / Import Audio File`.
- **Guardar el proyecto** (TW-1202):
  - herramienta `cubase_save_project` (`save` o `new_version`), con permiso propio `[writes] save`, desactivado por defecto, y verificación por la fecha de los `.cpr`;
  - **script 1.5.3**, con `File / Save` y `Save New Version`.
- **Exportar la mezcla** (TW-1204):
  - herramienta `cubase_export_mix` en dos fases: el rango (o todo el audio) y el diálogo de Cubase; después, la confirmación del archivo y de su duración;
  - **script 1.5.2**, con `File / Export Audio Mixdown`.
- **Borrado en una sola pista** (TW-1212): `cubase_edit_range` con `track` y `action: "delete"`. Corta, borra los trozos uno a uno, verifica e informa de los pasos de deshacer.
- **Edición por rangos en segundos** (TW-1211):
  - herramienta `cubase_edit_range` (`delete`, `delete_time`, `cut_time`, `insert_silence`, `crop`), con verificación por sondeo de los bordes de los eventos;
  - **script 1.5.1**, con 14 comandos de edición, herramienta y sondeo.
- **`cubase_set_position` en segundos:** verifica con la pantalla de segundos de Cubase y coloca los localizadores mediante el cursor. **Corrige** los localizadores en segundos, que antes quedaban en otra posición.
- **Propiedades del proyecto** (TW-1209):
  - herramienta `cubase_get_project`: compás, ciclo, punch, pre-roll y post-roll, metrónomo, precuenta, estado del transporte, modos de grabación y carpeta del proyecto;
  - `cubase_record_automation` usa el compás del proyecto en lugar de suponer 4/4.
- **Arranque automático** (TW-1201):
  - `trackwright serve` arranca el puente si no está en marcha (`[bridge] autostart`, activado por defecto), sin duplicarlo;
  - herramienta `cubase_launch`, que abre Cubase (opcionalmente con un proyecto) y espera al script;
  - sección de configuración `[cubase]`.
- **Unidades reales en la automatización** (TW-1208):
  - los puntos de `cubase_record_automation` aceptan `plain` (dB, Hz…), que Cubase convierte con exactitud;
  - herramienta nueva `cubase_convert_value`, de solo lectura;
  - `cubase_list_automation_targets` indica si cada parámetro admite unidades reales (`converts_units`).
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
