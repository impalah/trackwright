# Tutorial 3 — First safe change: dry run, apply and restore

**English** · [Español](03-first-safe-change.es.md)

**Goal:** change the volume and mute of a track **that is not selected**, check the change and put it back the way it was.
**You need:** [tutorial 2](02-inspect-track.md), a **saved** throwaway project and the transport stopped.

## Step 1. Enable writes, only for the test track

Create `~/.config/trackwright/config.toml`:

```toml
[writes]
enabled = true
allowed_tracks = ["POC-TEST"]
```

Restart your MCP client so that it relaunches `trackwright serve` with the new configuration. Check with "Are writes enabled in Trackwright?": `cubase_status` should say `writes_enabled: true`.

## Step 2. Select another track

In Cubase, click a track that is **not** POC-TEST. This way you will confirm that Trackwright modifies unselected tracks.

## Step 3. Dry run

> Mute the POC-TEST track, but first show me what you are going to change.

Claude calls `cubase_set_track_mix` with `mute: true` and `dry_run: true`, the default. You get the plan:
- `before`: the current value, `Desact.`;
- `requested`: the requested value, `1`;
- `verified: null`, because nothing has been applied.

**Nothing changes** in Cubase.

## Step 4. Apply

> Go ahead, apply it.

Claude repeats the call with `dry_run: false`. Trackwright writes the value, reads it back and returns `after: Activ.` and `verified: true`. POC-TEST's mute button lights up in Cubase.

## Step 5. Volume and restore

> Lower POC-TEST's volume to 0.7 and then put it back the way it was.

Claude notes the original value returned by the dry run, applies 0.7, verifies and restores it. Volume is expressed normalized, between 0 and 1: volume in dB is not available yet.

Unmute it the same way.

## Step 6. Check the policy

> Mute the POC-INSTR track, without a dry run.

The dry run does not check the policy: it is always allowed and changes nothing. When **applying**, however, it fails with `NOT_ALLOWED`, because POC-INSTR is not in `allowed_tracks`. This shows that the configuration protects you.

## What you have learned

- Changes always follow the cycle **dry run → confirmation → apply with verification**.
- Trackwright modifies tracks without needing to select them.
- `allowed_tracks` limits which tracks can be touched.

**Next:** [Tutorial 4 — Insert an EQ and adjust a band](04-insert-eq.md).
