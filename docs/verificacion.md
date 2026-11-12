# Registro de verificación contra Cubase

Cada entrada registra una ejecución **real** contra Cubase. Las pruebas con el simulador no se registran aquí.

## 2026-11-12 — primera verificación de Trackwright 0.1.0 (script 1.0.0)

- **Entorno:** macOS 27.2 (arm64), Cubase **Elements** 15.0.30, proyecto de pruebas con `POC-INSTR` (instrumento, con StudioEQ en el slot 1) y `POC-TEST` (audio).
- **Instalación:** `trackwright script install --apply` (tras corregir TW-1014). Cubase reiniciado. La superficie «Trackwright – Bridge» apareció sola al arrancar el puente.
- **`trackwright doctor`:** todas las comprobaciones correctas (script `up_to_date`, puente en marcha, Cubase responde con el script 1.0.0 y la aplicación 15.0.30).
- **`trackwright ping`:** correcto en 16 ms, con el eco Unicode `hola-ñ-✓`.
- **Tests de integración de lectura** (`TRACKWRIGHT_INTEGRATION=1`): 3 superados. Los 2 de escritura se saltaron: no se pidieron.
- **Las 9 herramientas de lectura**, ejecutadas sobre el servicio real:

| Herramienta | Resultado | Tiempo |
|---|---|---|
| `cubase_status` | sesión `dv06ye6vc1gb`, script 1.0.0, acceso al mezclador | 36 ms |
| `cubase_list_tracks` | 3 canales (Stereo Out, POC-INSTR, POC-TEST), sin el duplicado del final | 129 ms |
| `cubase_get_selected_channel` | `track: null`: no había ninguna pista con canal seleccionada | 108 ms |
| `cubase_list_inserts` (POC-INSTR) | slot 1 = StudioEQ, del 2 al 8 vacíos | 449 ms |
| `cubase_list_available_plugins` (filtro «eq») | colección «Por defecto», 53 plugins, 3 coincidencias (CurveEQ, DJ-Eq, StudioEQ) | 562 ms |
| `cubase_list_parameters` (channel, límite 5) | 39 parámetros; `next_offset` = 5, `truncated` = true | 224 ms |
| `cubase_list_parameters` (filtro «vol») | `Volumen` (1025) y `clickVolume` (4117) | 339 ms |
| `cubase_get_parameter` (strip:eq, 4232) | «EQ 1 Gain» = 0,5 («0.0dB», plain 0,0) | 554 ms |
| `cubase_get_transport` | cursor en 1. 1. 1. 0; ciclo entre los compases 2 y 4 | 17 ms |
| `cubase_poll_changes` | 2 eventos | 207 ms |

### Escrituras reversibles (tests de integración)

Comando: `TRACKWRIGHT_ALLOW_WRITES=1 TRACKWRIGHT_TEST_TRACK="POC-TEST"`. Resultado: **5 superados** en 1,52 s.

- **`test_mute_roundtrip`:** `cubase_set_track_mix` activa el mute de POC-TEST, lo verifica releyendo y lo restaura.
- **`test_cursor_roundtrip`:** `cubase_set_position` lleva el cursor al compás 3, lo verifica y lo devuelve a su posición.
- **Estado antes y después,** leído de forma independiente: mute `False` → `False`; cursor `1. 1. 1.  0` → `1. 1. 1.  0`. Nada quedó cambiado.

**Pendiente:** el resto de herramientas de escritura y las de comandos (tutoriales 3 a 6).
