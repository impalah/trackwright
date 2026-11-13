# Tutorial 7 — Record automation

**English** · [Español](07-automation.es.md)

**Goal:** have Claude record a volume fade and a plugin parameter curve on a track, and check that they play back.
**You need:**
- writes enabled;
- script 1.4.0 or later;
- a track with audio in a **saved** project;
- **the monitor volume turned down**, because recording plays the project.

## Step 1. See what can be automated

> Which parameters of POC-TEST can I automate?

Claude uses `cubase_list_automation_targets`. You will see keys such as `volume`, `pan` or `eq1.gain` and, if there is a plugin in slot 1, `insert1.p1`, `insert1.p2`…, each with the actual parameter it corresponds to ("Compressor / Threshold", "Compressor / Ratio"…). The track is left selected.

## Step 2. A volume fade

> Do a fade-out on POC-TEST: volume from 0 dB at bar 5 to near silence at bar 9.

1. Claude prepares the curve **in dB**: the points carry `plain: 0` and `plain: -60`, and Cubase converts them exactly to normalized values (0 dB is 0.7891; the scale is not linear). It shows you the plan (`dry_run`): parameter, current value, points and the bar where playback starts, which is one bar before the first point.
2. After your confirmation, it applies it. You will see a fader on the surface and the track's fader move.
3. With verification enabled (the default), Trackwright plays again with automation read enabled and checks that the volume follows the curve: `verified: true`.

The curve will appear in Cubase in the volume automation lane.

## Step 3. A plugin parameter

> Move the Threshold of POC-TEST's compressor from −20 to −35 dB between bars 2 and 4.

Claude will look up the key (`insert1.p1`) and pass the points as `plain: -20` and `plain: -35`, which Cubase converts. If you want to check a conversion without recording anything, ask for example "what normalized value is −20 dB of volume?": Claude will use `cubase_convert_value`.

## Step 4. Put things back

- **The recorded automation stays in the project.** To stop it from taking effect, disable read (R) on the track, or delete it in Cubase.
- **If something goes wrong, Undo** in Cubase. That is why you saved first.

## What you have learned

- Trackwright records automation by playing the project, just as you would with a controller.
- The curve is defined with points (position in bars and value) and verified with a second pass.

## Further reading

- [Tutorial 8 — Edit a podcast by seconds](08-podcast.md).
