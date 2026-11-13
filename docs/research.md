# Research on extended features

**English** · [Español](research.es.md)

The user's questions of 2026-11-13 about what else Trackwright can do. Each answer states its **provenance**:

| Label | Meaning |
|---|---|
| **[VER]** | Verified in Cubase Elements 15.0.30 (see [verification.md](verification.md)) |
| **[CMD]** | The command exists in the official command list ([reference/cubase-commands.txt](reference/cubase-commands.txt), Cubase/Nuendo 13), but **has not been tested** |
| **[API]** | Appears in the local typings of the MIDI Remote API; not tested |
| **[NE]** | Not found |

Derived issues: epic [E12](issues/E12-extended-features.md).

## 1. Can Trackwright start Cubase?

- **MIDI Remote cannot do it:** it only exists while Cubase is open.
- **Trackwright can do it from macOS:**
  - check whether Cubase is open, through the process or because the script responds;
  - open it with `open -a "Cubase 15"`, or with a project: `open -a "Cubase 15" <project>.cpr`.
- **Limitations:**
  - startup takes time;
  - it may show dialogs that have to be handled by hand. Observed: the MediaBay access prompt **[VER]**; possibly also the Steinberg Hub.
- In the same way, `trackwright serve` could start the bridge if it is not running.
- **Issue:** TW-1201.

## 2. General operations: open, save…?

- **Existing commands [CMD]**, category `File`: `New`, `New Empty`, `Open`, `Save`, `Save As`, `Save New Version`, `Save as Template`, `Close`, `Revert`, `Quit` and `Back up Project`.
- **Expected behavior, not verified:**
  - `Save`, on an already saved project, and `Save New Version` act without a dialog;
  - `Open`, `Save As` and `New` open a dialog, and a path cannot be passed to them.
- **Risk:** `Close`, `Revert` and `Quit` can lose unsaved work. They must be treated as destructive.
- **Opening a specific project:** from macOS (point 1).
- **Issue:** TW-1202.

## 3. Importing audio into a track?

- **Already possible [VER]:** selecting the track and placing the cursor.
- **The command exists [CMD]:** `File / Import Audio File`. It presumably opens the file chooser, and **the API does not allow passing it the path [NE]**.
- **Possible flow:** Trackwright prepares the track and the position, and opens the dialog; the user picks the file; Trackwright verifies what it can.
- Without user intervention it would only be possible by automating the graphical interface, which the design rules out.
- Other import commands [CMD]: `Import MIDI File`, `Import Tracks from Project`, `Import Track Archive`…
- **Issue:** TW-1203.

## 4. Insert presets?

- **There is no preset parameter [VER]:** neither StudioEQ (40 parameters) nor Compressor (46) exposes any with "prog" or "preset" in its title (query of 2026-11-13).
- **Commands [CMD]:** `Preset / Next`, `Preset / Previous` and `Preset / Open Browser`, plus their track preset equivalents (`Track Preset: …`) and `AddTrack / From Track Presets`.
  - **Do not exist [NE]:** loading a preset by name, saving presets, or program change.
  - It is unknown what they act on. Probably on the plugin editor that has focus.
- **Proposed experiment:** open the plugin editor from the API, through the slot's edit parameter; trigger `Preset / Next`; check whether the parameters change. This would allow stepping through presets, not choosing them by name.
- **Issue:** TW-1205.

## 5. Groups and joint control?

- **Routing an output or a send to a group through the API is not possible [VER]:** it stays at "Sin bus" (*No Bus*) (POC findings 39 and 41).
- **Commands [CMD]:**
  - `Mixer / Add Track To Selected: Group Channel`: creates a group and routes the selected channels to it;
  - `Mixer / Add Track To Selected: VCA Fader`: creates a VCA fader for the selected ones;
  - `Mixer / Link Channels`, `Unlink Channels` and `Q-Link`.
- **Limitation:** the API selects **one** track at a time **[VER]**. Multiple selection would be done by the user. These commands may open dialogs.
- **Issue:** not requested for now; a candidate for a future epic.

## 6. Exporting audio?

- **Command [CMD]:** `File / Export Audio Mixdown`. It presumably opens its dialog.
- **Possible flow:** Trackwright sets the locators **[VER]**, which delimit the range, and opens the dialog; the user reviews the options and clicks Export.
- Others [CMD]: `Export Selected Tracks` and `Export Selected Events`.
- **Issue:** TW-1204.

## 7. Automation (for example, of volume)?

- **Access to automation curves or points: [NE].**
- **Channel parameters [VER]:** 4013 "Escribir automatización" (*Write Automation*), 4014 "Leer automatización" (*Read Automation*) and 4105 "Medidores de automatización" (*Automation Meters*).
- **Commands [CMD]:**
  - **modes:** `Automation Mode - Touch`, `- Auto-Latch`, `- Cross-Over`, `- Trim` and `Next Automation Mode`;
  - **enabling:** `Toggle Read/Write Enable All/Selected Tracks`;
  - **filling:** `Fill Gaps`, `Fill Loop`, `Fill To End`, `Fill To Start`…;
  - **deleting:** `Delete Automation in Range` and `Delete Automation of Selected Tracks`;
  - **visibility:** `Show/Hide Automation`;
  - **suspension:** `Suspend Reading/Writing …`.
- **Transport:** commands `Transport / Start`, `Stop` and `Cycle` [CMD], and values `mTransport.mValue.mStart`, `mStop`, `mRecord` and `mCycleActive` [API].
- **Possible approach:** **record** the automation: write enabled + playback + value changes from Trackwright during playback.
- **Issue:** TW-1206 (experiment).

## 8. Inserts on Stereo Out and other outputs?

- **Yes [VER]:** Stereo Out (`OutputChannel`) appears in the mixer, with 8 insert slots and the full catalog of 53 plugins (query of 2026-11-13).
- **They presumably work the same way,** because they use the same operations: inserting plugins and writing parameters on the output. Not tested yet.
- Group and FX channels also appear in the mixer **[VER]** (seen with "Group 01" and "POC-GROUP").
