# TW-1616 — Ducking inside Cubase

**English** · [Español](README.es.md)

Run on 2026-11-16 on the test project (Cubase Elements 15.0.30, 48 kHz, 120 BPM). Part (b) first: the planned ducking envelope written by real-time automation recording on the music track's **PreGain** (`prefilter.gain`, a parameter the skill could own without touching the user's volume fader). Part (a), a side-chain the user sets up, below.

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

## Part (a): a side-chained compressor

A Compressor on `TW1616 signal` (the steady pink noise, Read off so the PreGain curve does not act): Threshold −30 dB, Ratio 8:1 (its maximum), Attack 10 ms, Release 300 ms, AutoMakeUp off, all set and read back through the API. The Compressor's 46 parameters include no side-chain switch: the user turned it on in its window and fed it with the voice, `TW1612 episode`. The voice and the noise exported together, and the voice alone; the compressor's gain is the mix minus the voice over the original noise, in 10 ms windows (`sidechain.py`):

- the side-chain works: −17.9 dB median while the voice speaks (−20.5 to −10.1 dB), 0.0 dB in its silences (57.5 s), correlation −0.72 with the voice's level;
- it drops **with** the first syllable (55.16 s, 80.66 s: no pre-roll), comes back within 0.3–0.8 s of the last one (no hold), and inside a phrase follows the syllables: 1.8 dB median change per 100 ms, 5.8 dB at the 95th percentile;
- its depth depends on how loud the voice is, not on a chosen value.

The offline plan does what a producer asks of ducking: down 0.25 s before the first word, a chosen depth held over the phrase, up only after a real pause. A side-chain is live and needs no render, but it pumps with the syllables, and the user must set up its routing by hand. Decision: no second mode for `podcast-music-ducking` now; offline rendering stays its only mode.

## Found on the way (part a)

- **Cubase's silence is not zero.** The export of the voice had −166 dBFS residue (about 5e-9) between its events, not exact zeros, and the speech detector took it as the noise floor (−1082 dB) and found speech everywhere. Fixed in the speech detector and in the levels of the silence analysis: frames under −120 dBFS count as digital silence.
- **A soloed track sounds even when muted.** `TW1507`, muted, exported with solo had its audio (−20.92 dBFS at 20–26 s, exactly what the TW-1615 voice export had there). The voice export of TW-1615 therefore carried a muted track, and the ducked music of that test is planned on it at 20–28 s and around 40 s. Fixed: `cubase_export_mix` leaves muted tracks out of `solo`, with a note, unless `include_muted`.

## Files

- `measure.py`: the gain an export applied, window by window, against the plan (lag, error on the flat parts, transitions).
- `sidechain.py`: the gain of a side-chained compressor on a steady signal, against the voice and the offline plan.
- `probe_binding.py`: which track's PreGain the automation control moves once a track is selected (no playback, the value put back).
