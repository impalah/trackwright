# Experiment TW-1206 — recording volume automation

**English** · [Español](README.es.md)

Issue: [TW-1206](../../docs/issues/E12-extended-features.md). Results: [docs/verification.md](../../docs/verification.md). The data from each run is saved in `results.json`.

| Variant | Mechanism | Status |
|---|---|---|
| A | Write the volume parameter through DirectAccess with write enabled | **Does not record** (2026-11-13) |
| B1 | Change the mode to Auto-Latch or Cross-Over by command | **Not available in Elements** (`canPerform=false`) |
| B2 | Surface fader bound to the volume of the selected track, with its touch state controlled by the script | **Records and plays back** (2026-11-13) |
| B3 (TW-1207) | The same, generalized: 45 controls (volume, pan, sends, EQ, pre-filter, Quick Controls, parameters of insert slots 1 and 2). Playback with `Transport / Start` and `Stop` from Trackwright | **7 out of 8 record** (the unassigned Quick Control does not). Since script 1.4.0 the controls are part of the published script |

## Variant B2

> The `build.py` generator was retired with script 1.4.0, which ships with the controls enabled. These commands remain as a record.

```sh
uv run trackwright script install --apply                  # script 1.4.0 or later; restart Cubase
uv run python experiments/tw1206/automation.py prepare     # initial state, write enabled, cursor at bar 1
uv run python experiments/tw1206/automation.py record-b2   # the user presses Play and, after ~6 s, Stop
uv run python experiments/tw1206/automation.py readback    # the user presses Play and Stop again
uv run python experiments/tw1206/automation.py cleanup
uv run trackwright script install --apply                  # back to the published script, and restart Cubase
```

## Variant B3 (automatic)

```sh
uv run trackwright script install --apply    # script 1.4.0 or later (the controls already come enabled); restart Cubase
uv run python experiments/tw1206/controls.py list    # controls, current value and bound parameter
uv run python experiments/tw1206/controls.py run     # records, checks and restores each control (without pressing anything)
```

**What to observe in variant B2:**
- on the MIDI Remote surface a fader appears to the right of the panel;
- during recording, the fader and the track volume move;
- afterwards, does a curve appear in the automation lane?;
- during read, does the volume repeat the ramp without Trackwright touching it?
