# Tutorial 6 — Create a track with the help of the dialog, and delete it

**English** · [Español](06-track-with-dialog.es.md)

**Goal:** create a group channel with a custom name in collaboration with Claude, and then delete it safely.
**You need:** writes enabled, and to be in front of the Cubase screen.

## Why your help is needed

When adding audio tracks, group tracks or folders, Cubase opens the "Add Track" dialog and waits for your response. The API cannot fill it in. That is why this tool works in two phases: Trackwright opens the dialog, you complete it, and then Trackwright checks the result.

## Step 1. `start` phase

> Create a group channel called POC-GROUP.

Claude calls `cubase_add_track_interactive` with `phase: "start"`, `kind: "group"` and `suggested_name: "POC-GROUP"`. The response includes `status: "awaiting_user"` and some instructions.

The "Add Track" dialog opens in Cubase. **Type the name `POC-GROUP`** and accept.

If you accept without typing a name, Cubase calls it "Group 01" and the confirmation phase will not find it.

## Step 2. `confirm` phase

> I've created it.

Claude calls again with `phase: "confirm"`. Trackwright looks for the track in the mixer and returns:
- `status: "done"` and `verified: true`, with the `uid:` selector of the new group;
- or `not_found`, if you canceled the dialog or used a different name.

## Step 3. Delete safely

> Delete POC-GROUP.

Claude should:
1. select it with `cubase_select_track`;
2. dry-run `cubase_remove_selected_tracks` with `expect_selected: "POC-GROUP"`, which only acts if the selection matches **exactly** (otherwise, `SELECTION_MISMATCH`);
3. with your confirmation, apply it.

Possible responses:
- `status: "done"`: the track has disappeared from the mixer;
- `status: "pending_confirmation"`: the track had events and Cubase is asking for confirmation on screen. Answer it yourself.

## What you have learned

- Commands of class `dialog` need your intervention, and Trackwright never considers them finished.
- Deletions require stating which track is expected to be selected.

## Further reading

- [Tutorial 7 — Record automation](07-automation.md).
- [Tool reference](../manual/04-tools.md): all the tools and their limitations.
- [Troubleshooting](../manual/05-troubleshooting.md).
