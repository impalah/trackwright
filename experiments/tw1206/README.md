# Experimento TW-1206 — grabar automatización de volumen

Issue: [TW-1206](../../docs/issues/E12-funcionalidades-ampliadas.md). Resultados: [docs/verificacion.md](../../docs/verificacion.md). Los datos de cada ejecución se guardan en `results.json`.

| Variante | Mecanismo | Estado |
|---|---|---|
| A | Escribir el parámetro de volumen por DirectAccess con la escritura activada | **No graba** (2026-11-13) |
| B1 | Cambiar el modo a Auto-Latch o Cross-Over por comando | **No disponible en Elements** (`canPerform=false`) |
| B2 | Fader de la superficie enlazado al volumen de la pista seleccionada, con su estado de toque controlado por el script | **Graba y se reproduce** (2026-11-13) |

## Variante B2

```sh
uv run python experiments/tw1206/build.py                                                       # genera 1.2.1+tw1206
uv run trackwright script install --file experiments/tw1206/Trackwright_Bridge.js --apply       # y reiniciar Cubase
uv run python experiments/tw1206/automation.py prepare     # estado inicial, escritura activada, cursor en el compás 1
uv run python experiments/tw1206/automation.py record-b2   # el usuario pulsa Play y, a los ~6 s, Stop
uv run python experiments/tw1206/automation.py readback    # el usuario pulsa Play y Stop otra vez
uv run python experiments/tw1206/automation.py cleanup
uv run trackwright script install --apply                  # vuelta al script publicado, y reiniciar Cubase
```

**Qué observar:**
- en la superficie MIDI Remote aparece un fader a la derecha del panel;
- durante la grabación, el fader y el volumen de la pista se mueven;
- después, ¿aparece una curva en el carril de automatización?;
- en la lectura, ¿el volumen repite la rampa sin que Trackwright lo toque?
