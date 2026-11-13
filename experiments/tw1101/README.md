# Experimento TW-1101 — panel de estado en la superficie MIDI Remote

> **Concluido el 2026-11-13.** Resultados en [`docs/verificacion.md`](../../docs/verificacion.md). Desde el script 1.1.0, el panel forma parte del script publicado con lo que funcionó: título, pista seleccionada y lámpara de actividad. El generador `build.py` se retiró. Este documento queda como registro del protocolo.

Objetivo: averiguar qué puede mostrar Cubase en la superficie «Trackwright – Bridge». El experimento usa una versión de prueba del script con el panel activado (`PANEL_ENABLED = true`, versión `1.0.1+tw1101`). **Las operaciones no cambian:** todas las herramientas siguen funcionando igual.

## Qué incluye la versión de prueba

| Fila | Elemento | Mecanismo de la API | Qué debería verse |
|---|---|---|---|
| 0 | Campo de texto fijo | `page.setLabelFieldText` | «Trackwright 1.0.1+tw1101» |
| 1 | Campo de texto ligado a la pista seleccionada | `page.setLabelFieldHostObject(…, mTrackSelection.mMixerChannel)` | El nombre de la pista seleccionada, que cambia al seleccionar otra |
| 2 | Campo de texto asociado a una lámpara (`relateTo`) | `lamp.mSurfaceValue.setDisplayValue` | «activo» al activarse, y luego `hh:mm:ss <operación>` con cada petición, por ejemplo `20:15:03 ping hola panel` |
| 2 | Lámpara redonda | `lamp.mSurfaceValue.setProcessValue` cada 9 ciclos de idle | Parpadeo de aproximadamente un segundo |

Cada llamada está protegida. Si alguna falla, el script sigue funcionando y el error aparece en `capabilities.panel.errors`.

## Preparación

Desde la raíz del repositorio:

```sh
uv run python experiments/tw1101/build.py
uv run trackwright script install --file experiments/tw1101/Trackwright_Bridge.js           # ensayo
uv run trackwright script install --file experiments/tw1101/Trackwright_Bridge.js --apply   # instalar
```

Después, **reinicia Cubase**.

## Protocolo

Anota, o captura, lo que se ve en la pestaña MIDI Remote en cada paso:

| Paso | Acción | Pregunta |
|---|---|---|
| E1 | Cubase abierto, **con el puente parado** | ¿Qué dibujo aparece ahora? ¿Ha desaparecido el recuadro con la barra blanca? ¿Se ven el título, el campo de la pista, el de estado y la lámpara? |
| E2 | Arranca el puente (`uv run trackwright bridge`) | ¿El campo de estado dice «activo»? ¿Parpadea la lámpara? |
| E3 | `uv run trackwright ping --echo "hola panel"` | ¿El campo de estado muestra la hora, `ping` y `hola panel`? |
| E4 | Selecciona otra pista en Cubase | ¿Cambia el nombre de la fila 1? |
| E5 | `uv run trackwright doctor` y `uv run trackwright ping` | ¿Todo sigue funcionando igual? Comparar la latencia del `ping` con la habitual (unos 15 ms). |
| E6 | `uv run python -c` con `capabilities` (lo lanza Claude) | ¿Hay errores en `panel.errors`? |

## Vuelta al script normal

```sh
uv run trackwright script install --apply
```

Y reinicia Cubase. Los resultados se anotan en `docs/verificacion.md` y en la issue TW-1101.
