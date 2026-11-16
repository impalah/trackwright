# TW-1616 — Ducking inside Cubase

**English** · [Español](README.es.md)

Run on 2026-11-16 on the test project (Cubase Elements 15.0.30, 48 kHz, 120 BPM). Part (b) first: the planned ducking envelope written by real-time automation recording on the music track's **PreGain** (`prefilter.gain`, a parameter the skill could own without touching the user's volume fader). Part (a), a side-chain the user sets up, is still to do.

## What happened

1. **Controls bound to the previous track.** Read right after selecting `POC-TEST`, `cubase_list_automation_targets` reported the volume of `POC-TEST ducked` and the inserts of Stereo Out; a second reading was right. The automation controls follow a new selection a moment later, and the tools read (and could write) the previous track's. Fixed: the tools wait until the volume control carries the track's name, or stop with `CONTROLS_NOT_BOUND` (this is also TW-1635 (2)).
2. **A recorded curve that does not play.** The envelope recorded on `POC-TEST` (14 points, 1,255 values written, `complete: true`) exported flat at −10 dB: after recording, the tool restored Read (R) to its state before, off, so Cubase played the parameter's last value. With R on, the curve played (the recovery at 67.6–68.8 s reached 0 dB). Fixed: R stays on after a recording, and the result reports it (`read_automation`). This was TW-1635 (1).
3. **PreGain is before the inserts.** On `POC-TEST` the flat −10 dB parts exported at −7 to −9 dB: its Compressor (threshold −20 dB, ratio 2:1, auto make-up) compresses less when PreGain lowers the level, and gives some of it back. Ducking on PreGain is only exact on a track without dynamics after it.
4. **No recording on a track created during the session.** On `TW1616 signal`, a stereo track created today with a 140 s pink-noise file (−20 dBFS RMS) and no plugins, a 54-point envelope (1,252 values written) left no automation at all: the export equals the source to 0.00 dB, and the user found no PreGain lane on any track. A probe (`probe_binding.py`) showed the PreGain control does move that track's PreGain (0.5 → 0.4479, no other track), so the binding is right; a short curve with `verify` read back 0 dB where −10 dB was written (`verified: false`). The same short curve on `TW1501` (an older track, no PreGain lane before) recorded and verified at −10.0 dB. So a lane does not need to exist; what differs is that `TW1616 signal` was created after the script loaded. To confirm: reload the MIDI Remote scripts and repeat the short curve on `TW1616 signal`.

## Files

- `measure.py`: the gain an export applied, window by window, against the plan (lag, error on the flat parts, transitions).
- `probe_binding.py`: which track's PreGain the automation control moves once a track is selected (no playback, the value put back).
