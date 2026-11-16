# Steinberg plugins for voice cleanup: what was measured

Observed on Cubase Elements 15.0.30 (TW-1624), through `cubase_list_parameters` and `cubase_set_parameter`, with the user's Cubase in Spanish (plugin parameter titles stay in English). Other editions and versions may differ: always check the titles with `cubase_list_parameters` and pass `expect_title`.

## StudioEQ (uid `946051208E29496E804F64A825C8A047`)

Four bands: LF, P1, P2, HF. Titles end in `L` (the left/linked channel).

| Band | On | Frequency | Gain | Q | Type |
|---|---|---|---|---|---|
| LF | `On1L` (4201) | `FreqLFL` (4202) | `GainLFL` (4203) | `QLFL` (4204) | `LFTypeL` (4218) |
| P1 | `On2L` (4205) | `FreqP1L` (4206) | `GainP1L` (4207) | `QP1L` (4208) | always a peak |
| P2 | `On3L` (4209) | `FreqP2L` (4210) | `GainP2L` (4211) | `QP2L` (4212) | always a peak |
| HF | `On4L` (4213) | `FreqHFL` (4214) | `GainHFL` (4215) | `QHFL` (4216) | `HFTypeL` (4219) |

- `LFTypeL`, plain value: 0 `Shelv I`, 1 `Shelv II`, 2 `Shelv III`, **3 `Cut`** (the high-pass), 4 `Peak`.
- Frequency from 20 Hz (a plain value under the range is refused: `NO_UNIT_CONVERSION`); gain −24 to +24 dB; Q up to 10 (at 50 Hz, about 5 Hz wide).
- Also `Bypass` (4242), `Auto Gain` (4239), `OutputL` (4217).
- **Measured response (TW-1624, from a voice exported before and after, coherence 0.98-1.00):** LF `Cut` 80 Hz, P1 100 Hz −6 dB Q 10, P2 150 Hz −24 dB Q 10 gave −14.5 dB at 40 Hz, −8.4 at 80, −14.3 at 100, −14.7 at 130, −26.1 at 150, −7.7 at 200, −3.9 at 250, −2.4 at 300, −1.2 at 400, −0.2 at 1 kHz. A textbook model of the same settings (12 dB/octave high-pass, peaking filters of Q 10) predicts 5-7 dB less cut between 80 and 200 Hz: at low frequencies the cut is wider than the settings suggest (the bands were measured together, not one by one, so which band adds it is not known). Keep notches shallow near the voice, and check on export.

## DeEsser (uid `75FD13A528D24880982197D541BC582A`)

| Parameter | Tag | Default |
|---|---|---|
| `Reduction` | 4201 | 4.0 |
| `Threshold` | 4202 | AUTO (−25) |
| `Auto Threshold` | 4207 | On |
| `Release` | 4206 | 150 ms |
| `LowFreq` | 4240 | 4.50 kHz |
| `HighFreq` | 4241 | 15.00 kHz |
| `Solo` (hear only the band) | 4242 | Off |
| `Bypass` | 4209 | Off |

## The channel strip

- `strip:eq`: four bands (`EQ 1 Type`…`EQ 4 Type`, gain, frequency, Q); band 1 defaults to `Low Shelf II`.
- The input filter (low cut, high cut) is not among the channel parameters; it can only be automated (TW-1601). A high-pass is therefore done with StudioEQ's LF band set to `Cut`.
