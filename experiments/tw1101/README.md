# Experiment TW-1101 — status panel on the MIDI Remote surface

**English** · [Español](README.es.md)

> **Concluded on 2026-11-13.** Results in [`docs/verification.md`](../../docs/verification.md). Since script 1.1.0, the panel is part of the published script with what worked: title, selected track and activity lamp. The `build.py` generator was retired. This document remains as a record of the protocol.

Goal: find out what Cubase can display on the «Trackwright – Bridge» surface. The experiment uses a test version of the script with the panel enabled (`PANEL_ENABLED = true`, version `1.0.1+tw1101`). **Operations do not change:** all tools keep working the same way.

## What the test version includes

| Row | Element | API mechanism | What should be seen |
|---|---|---|---|
| 0 | Fixed text field | `page.setLabelFieldText` | «Trackwright 1.0.1+tw1101» |
| 1 | Text field bound to the selected track | `page.setLabelFieldHostObject(…, mTrackSelection.mMixerChannel)` | The name of the selected track, which changes when another one is selected |
| 2 | Text field associated with a lamp (`relateTo`) | `lamp.mSurfaceValue.setDisplayValue` | «activo» (*active*) when activated, and then `hh:mm:ss <operation>` with each request, for example `20:15:03 ping hola panel` |
| 2 | Round lamp | `lamp.mSurfaceValue.setProcessValue` every 9 idle cycles | Blinking of roughly one second |

Each call is guarded. If any of them fails, the script keeps working and the error appears in `capabilities.panel.errors`.

## Preparation

From the repository root:

```sh
uv run python experiments/tw1101/build.py
uv run trackwright script install --file experiments/tw1101/Trackwright_Bridge.js           # dry run
uv run trackwright script install --file experiments/tw1101/Trackwright_Bridge.js --apply   # install
```

Then **restart Cubase**.

## Protocol

Write down, or capture, what is seen in the MIDI Remote tab at each step:

| Step | Action | Question |
|---|---|---|
| E1 | Cubase open, **with the bridge stopped** | What drawing appears now? Has the box with the white bar disappeared? Are the title, the track field, the status field and the lamp visible? |
| E2 | Start the bridge (`uv run trackwright bridge`) | Does the status field say «activo» (*active*)? Does the lamp blink? |
| E3 | `uv run trackwright ping --echo "hola panel"` | Does the status field show the time, `ping` and `hola panel`? |
| E4 | Select another track in Cubase | Does the name in row 1 change? |
| E5 | `uv run trackwright doctor` and `uv run trackwright ping` | Does everything keep working the same? Compare the `ping` latency with the usual one (about 15 ms). |
| E6 | `uv run python -c` with `capabilities` (run by Claude) | Are there errors in `panel.errors`? |

## Back to the normal script

```sh
uv run trackwright script install --apply
```

And restart Cubase. The results are recorded in `docs/verification.md` and in issue TW-1101.
