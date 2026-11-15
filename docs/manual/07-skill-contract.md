# The skill contract

**English** · [Español](07-skill-contract.es.md)

Every Trackwright skill (TW-1609) has the same shape, so that each one can be read, reviewed and trusted the same way, and so that a skill never touches what is not its own. `tests/unit/test_plugin.py` checks the shape of every `SKILL.md` in `plugins/claude-code/skills/`.

## Sections

A `SKILL.md` has these sections (`## …`), in this order. Other sections may come before or between them (for example an explanation of what the job does).

| Section | What it says |
|---|---|
| `Requires` | What must be true before starting: `cubase_status` fields (`connected`, `writes_enabled`, `analysis_enabled`, `workspace_enabled`, `allowed_tracks`), plugins that must be installed, and what to say when one is missing. |
| `Inputs` | What the skill needs from the user, and what it takes from the show and episode profiles (`cubase_profile`): defaults it proposes, track roles, protected ranges. It asks only for what is missing. |
| `Workflow` | The job, in seven phases (below). |
| `Safety` | What the skill must never do. |
| `Outputs` | What the user gets: the report, the files left behind (exports, renders, reports), how to undo, and that the project is not saved. |
| `Ownership` | What the skill creates (tracks, plugins, renders, markers…), how it records them in `Trackwright/state.json`, and how a re-run finds and updates its own items instead of adding new ones. Everything not recorded as the skill's is the user's. |

## Workflow phases

Inside `Workflow`, one step per phase (`### N. Phase`), in this order:

1. **Inspect:** read the project (tracks, inserts, solos, what `state.json` says the skill created before).
2. **Analyze:** export with the user and measure; name the export the numbers come from (`source`), and export again when `source.project_saved_after` says the project was saved after it.
3. **Propose:** a short plan with the numbers it comes from.
4. **Preview:** what the user can hear before (or right after) the change: a preview file, a cycle range with Bypass, or a dry run. When there is no preview, the step says why and what replaces it.
5. **Approve:** an explicit yes from the user. Nothing is changed before it.
6. **Apply:** every write with a dry run first, never retried after a timeout; record what was created (`cubase_workspace`, action `record`).
7. **Verify:** check the result (read back, edges, a new export and analysis) and ask the user to listen.

## Ownership in `state.json`

`cubase_workspace` with `action: "record"` keeps one item per thing a skill created: `kind` (`track`, `plugin`, `render`, `preview`, `marker`, `automation`, `report`), `key` (a track uid, `<track uid>/slot:N`, a path inside the workspace…), `skill`, `run_id` and free `details`. `action: "forget"` removes it when the thing is gone. `cubase_import_audio` records a render's track by itself. The rules:

- a skill updates or replaces only items recorded under its own name;
- a plugin or track not recorded is the user's: changed only when the user asks for that one, and never recorded as the skill's;
- recording needs `[workspace] enabled` and the workspace created (`cubase_workspace`, action `init`); without it the skill works but cannot recognize its items on a later run, and says so.

## Common rules

- Speak to the user in their language; keep them informed, since they are in front of Cubase.
- Dry run first; apply only what the user approved in this conversation.
- Restore every solo (`cubase_export_mix` with `solo`, and `cancel` if the export is abandoned).
- Never retry a write after a timeout: read the state back instead.
- Never save the project unless asked (`cubase_save_project`).
- Read only the exports and files the user points to.
