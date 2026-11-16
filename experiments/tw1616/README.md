# TW-1616 — Ducking inside Cubase

**English** · [Español](README.es.md)

Run on 2026-11-16 on the test project (Cubase Elements 15.0.30, 48 kHz, 120 BPM). Part (b) first: the planned ducking envelope written by real-time automation recording on the music track's **PreGain** (`prefilter.gain`, a parameter the skill could own without touching the user's volume fader). Part (a), a side-chain the user sets up, is still to do.

## What happened

1. **Controls bound to the previous track.** Read right after selecting `POC-TEST`, `cubase_list_automation_targets` reported the volume of `POC-TEST ducked` and the inserts of Stereo Out; a second reading was right. The automation controls follow a new selection a moment later, and the tools read (and could write) the previous track's. Fixed: the tools wait until the volume control carries the track's name, or stop with `CONTROLS_NOT_BOUND` (this is also TW-1635 (2)).
2. **A recorded curve that does not play.** The envelope recorded on `POC-TEST` (14 points, 1,255 values written, `complete: true`) exported flat at −10 dB: after recording, the tool restored Read (R) to its state before, off, so Cubase played the parameter's last value. With R on, the curve played (the recovery at 67.6–68.8 s reached 0 dB). Fixed: R stays on after a recording, and the result reports it (`read_automation`). This was TW-1635 (1).
3. **PreGain is before the inserts.** On `POC-TEST` the flat −10 dB parts exported at −7 to −9 dB: its Compressor (threshold −20 dB, ratio 2:1, auto make-up) compresses less when PreGain lowers the level, and gives some of it back. Ducking on PreGain is only exact on a track without dynamics after it.
4. **No recording on a track created during the session.** On `TW1616 signal`, a stereo track created today with a 140 s pink-noise file (−20 dBFS RMS) and no plugins, a 54-point envelope (1,252 values written) left no automation at all: the export equals the source to 0.00 dB, and the user found no PreGain lane on any track. A probe (`probe_binding.py`) showed the PreGain control does move that track's PreGain (0.5 → 0.4479, no other track), so the binding is right; a short curve with `verify` read back 0 dB where −10 dB was written (`verified: false`). The same short curve on `TW1501` (an older track, no PreGain lane before) recorded and verified at −10.0 dB. So a lane does not need to exist; what differs is that `TW1616 signal` was created after the script loaded. 

5. **Confirmed: a script reload fixes it.** After the user restarted Cubase, the same short curve on `TW1616 signal` recorded and verified (`verified: true`, `read_automation: true`). Tracks created after the MIDI Remote script loaded record no automation from it until the scripts are reloaded.
6. **The precision, measured on a clean signal.** On `TW1616 signal` (pink noise, no plugins, R on), an envelope of 13 cycles (falls of 10 ms, 0.1, 0.25, 0.5 and 1 s to −10 dB, 5 s down, rises of 0.25, 0.5, 1.2 and 2 s), 1,255 values written, exported alone (`measure.py`):
   - a constant **delay of +0.22 s** (0.135 to 0.335 s over the 26 transitions);
   - the flat parts exact (median error 0.000 dB); after shifting the plan by 0.22 s, 0.35 dB RMS of error;
   - a 10 ms step comes out as a 0.08–0.09 s change (10 to 90 %): Cubase smooths it, no click; ramps of 0.25 to 2 s keep their length and are smooth, with no 110 ms staircase.

## Conclusion of part (b)

Real-time automation reproduces a planned envelope to a fraction of a dB with a constant 0.22 s delay that recording the points early could compensate. But it plays the whole range in real time (46 minutes for a whole episode), needs a script reload for tracks created during the session, and PreGain acts before the inserts. The offline render is exact, immediate and leaves the original untouched: it stays the only mode of `podcast-music-ducking`; automation is worth it only when the user wants a curve to edit by hand in Cubase.

## Files

- `measure.py`: the gain an export applied, window by window, against the plan (lag, error on the flat parts, transitions).
- `probe_binding.py`: which track's PreGain the automation control moves once a track is selected (no playback, the value put back).
