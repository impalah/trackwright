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
