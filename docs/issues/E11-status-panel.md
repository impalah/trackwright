# E11 — Status panel on the MIDI Remote surface

**English** · [Español](E11-status-panel.es.md)

**Goal.** Today the Cubase MIDI Remote tab shows an empty rectangle for "Trackwright – Bridge": the script's only element is `makeLabelField(0, 0, 4, 1)`, which was added only so that Cubase would display the surface. The idea is to use that space as an **informational status panel**: whether Trackwright is connected, which script version is installed, which track is selected and what the last operation was.

It is a visual and debugging aid. **It does not change how anything works:** the MCP tools do not depend on the panel.

## Starting observation (user's screenshot, 2026-11-12)

In the MIDI Remote tab, Cubase shows:
- **Title "Trackwright - Bridge":** comes from `makeDeviceDriver('Trackwright', 'Bridge', …)`.
- **"Mapping Page: Bridge":** comes from `makePage('Bridge')`.
- **In the center:** a rounded, almost square box, with a small white bar inside and a horizontal line on each side.

**Open question:** it is not known whether that drawing is the `makeLabelField(0, 0, 4, 1)` text field scaled (the white bar) with Cubase decoration, or a generic placeholder that Cubase draws when the surface has no controls. A 4×1 field should look wide and short, which is not what appears. The first experiment in the scope (item 2) resolves it: add easily recognizable elements and see what changes.

## TW-1101 Status panel on the surface

- **Status:** done (script 1.1.0)
- **Priority:** low (user experience improvement)

### What the API says (local typings v1)

The surface is **drawn from the elements the script declares**. There is no way to add images, icons or colors: no image API appears in the typings.

| Need | Mechanism | Confidence |
|---|---|---|
| Fixed text ("Trackwright 1.0.0") | `page.setLabelFieldText(field, text)`. Used by factory scripts (Korg nanoKONTROL); set when the script loads | Documented |
| Name of the selected track | `page.setLabelFieldHostObject(field, mTrackSelection.mMixerChannel)`. Shows the object's title and follows it | Documented; behavior unverified |
| Texts that change at runtime (connected, last operation) | `setDisplayValue(activeDevice, text)` (API 1.3) on the value of an element or a variable, with a field related to that element via `field.relateTo(element)` | **No evidence**: there is no record of a text field showing an element's `displayValue` |
| Activity (request in progress) | `makeLamp(…)` and `lamp.mSurfaceValue.setProcessValue(activeDevice, 1 or 0)` | Unverified whether the lamp lights up on screen when the value is changed from the script |

### Proposed scope

1. **Design** of the surface, on a grid of about 8×3 units:
   - **Row 1:** fixed text "Trackwright" and the script version.
   - **Row 2:** name of the selected track (`setLabelFieldHostObject`).
   - **Row 3:** dynamic status ("connected", the last operation with its result and time) and an activity lamp.
2. **Proof of concept in Cubase**, before committing to the design. Verify, one by one, the four mechanisms in the table and record in the log what is seen.
3. **Implementation** of those that work.
   - The panel is updated in `mOnSysex` and `mOnIdle` at no noticeable cost: at most one update per idle cycle.
   - It must be **passive**: no panel element is bound to commands or to Cubase values that the user could change by accident by clicking on the surface.
4. **If the dynamic texts do not work:** keep the fixed text and the selected track, and document the limitation.

### Experiment preparation (done, 2026-11-13)

- **Panel in the main script, disabled** (`PANEL_ENABLED = false`): the published script does not change. A test checks that it still has a single 4×1 field and `capabilities.panel.enabled = false`.
- **Test version:** `experiments/tw1101/build.py` generates `1.0.1+tw1101` with the panel enabled.
- **Installation:** `trackwright script install --file <script>` (with a prior dry run) installs the test version, and `script install --apply` returns to the published one.
- **Node.js harness:** emulates the fields, `relateTo`, the lamps and `setLabelFieldText` / `setLabelFieldHostObject`. The tests check the layout, the text with each request, the blinking and that all operations still respond. **This only shows that the script calls the API as intended; what Cubase draws can only be known in Cubase.**
- **Protocol:** steps E1 to E6 in [`experiments/tw1101/README.md`](../../experiments/tw1101/README.md).

### Experiment results (2026-11-13)

Details in [`docs/verification.md`](../verification.md#2026-11-13--tw-1101-experiment-status-panel-script-101tw1101).

| Mechanism | Result |
|---|---|
| Fixed text (`setLabelFieldText`) | ✅ works |
| Selected track (`setLabelFieldHostObject`) | ✅ works and updates on its own |
| Lamp (`setProcessValue`) | ✅ blinks according to what the script sets |
| Dynamic text (`relateTo` + `setDisplayValue`) | ❌ always "-" |

The **open question** is resolved: the initial drawing was the empty 4×1 text field.

### Decision and implementation (script 1.1.0)

What was verified is adopted (option chosen by the user):
- **Row 0:** "Trackwright <version>" (`setLabelFieldText`) and, to the right, an **activity lamp**. It lights up when a request arrives and goes off when the queue is empty, after a minimum of 3 idle cycles (about 0.3 s), so that it is visible.
- **Row 1:** the selected track (`setLabelFieldHostObject`).
- **Discarded:** the status row (`relateTo` + `setDisplayValue`, which is not displayed) and continuous blinking.

Tests in `tests/script/test_panel.py`: layout, exclusive use of verified mechanisms, lamp on and off, a single toggle with several queued requests, and non-blocking operations. The experiment generator was removed, and its protocol remains in `experiments/tw1101/README.md`.

### Risks

- **Mapping Assistant:** visible elements appear in the Cubase Mapping Assistant, and the user could assign functions to them. Use text fields and lamps, which cannot be assigned, and never knobs or buttons.
- **An error in the surface prevents the script from loading.** Every call to the surface API goes inside `try/catch`, and a failure is recorded in `status.lastError` without affecting the rest.
- **Compatibility:** `setDisplayValue` belongs to API 1.3 (Cubase 15.0.20 or later). Check that it exists before using it.

### Acceptance criteria

- The script still loads and all existing operations pass the Node.js harness tests. The harness is extended to emulate the new elements.
- Test in real Cubase recorded in `docs/verification.md`: what is seen in each state (bridge stopped, connected and operation in progress), with the user's description.
- No Trackwright operation slows down: the latencies of `ping` and `da.channels` are compared before and after.
- The installation manual (step 6) describes what the user should see in the panel.

### Out of scope

- Images, logos or colors: the API does not allow them.
- Interactive controls on the panel, such as buttons that trigger actions.
