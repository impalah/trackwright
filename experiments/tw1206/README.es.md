# Experimento TW-1206 — grabar automatización de volumen

[English](README.md) · **Español**

Issue: [TW-1206](../../docs/issues/E12-extended-features.es.md). Resultados: [docs/verification.es.md](../../docs/verification.es.md). Los datos de cada ejecución se guardan en `results.json`.

| Variante | Mecanismo | Estado |
|---|---|---|
| A | Escribir el parámetro de volumen por DirectAccess con la escritura activada | **No graba** (2026-11-13) |
| B1 | Cambiar el modo a Auto-Latch o Cross-Over por comando | **No disponible en Elements** (`canPerform=false`) |
| B2 | Fader de la superficie enlazado al volumen de la pista seleccionada, con su estado de toque controlado por el script | **Graba y se reproduce** (2026-11-13) |
| B3 (TW-1207) | Lo mismo, generalizado: 45 controles (volumen, panorama, envíos, EQ, pre-filtro, Quick Controls, parámetros de los slots de inserción 1 y 2). Reproducción con `Transport / Start` y `Stop` desde Trackwright | **7 de 8 graban** (el Quick Control sin asignar, no). Desde el script 1.4.0 los controles forman parte del script publicado |

## Variante B2

> El generador `build.py` se retiró con el script 1.4.0, que trae los controles activos. Estos comandos quedan como registro.

```sh
uv run trackwright script install --apply                  # script 1.4.0 o posterior; reiniciar Cubase
uv run python experiments/tw1206/automation.py prepare     # estado inicial, escritura activada, cursor en el compás 1
uv run python experiments/tw1206/automation.py record-b2   # el usuario pulsa Play y, a los ~6 s, Stop
uv run python experiments/tw1206/automation.py readback    # el usuario pulsa Play y Stop otra vez
uv run python experiments/tw1206/automation.py cleanup
uv run trackwright script install --apply                  # vuelta al script publicado, y reiniciar Cubase
```

## Variante B3 (automática)

```sh
uv run trackwright script install --apply    # script 1.4.0 o posterior (los controles ya vienen activos); reiniciar Cubase
uv run python experiments/tw1206/controls.py list    # controles, valor actual y parámetro enlazado
uv run python experiments/tw1206/controls.py run     # graba, comprueba y restaura cada control (sin pulsar nada)
```

**Qué observar en la variante B2:**
- en la superficie MIDI Remote aparece un fader a la derecha del panel;
- durante la grabación, el fader y el volumen de la pista se mueven;
- después, ¿aparece una curva en el carril de automatización?;
- en la lectura, ¿el volumen repite la rampa sin que Trackwright lo toque?
