"""The project workspace tool (TW-1602): report and create ``Trackwright/`` inside the open project's folder,
and record what a skill created in ``state.json`` (TW-1609: ``record``, ``forget``).

The project folder comes from the files Cubase has open (``project_folder()``, no request to Cubase) and is
never guessed between several projects. Creating the folder needs ``[workspace] enabled``; reporting does not.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal, get_args

from pydantic import ValidationError
from pydantic_core import PydanticSerializationError

from trackwright.core.base import ServiceBase
from trackwright.core.models import WorkspaceOut
from trackwright.errors import PreconditionFailedError
from trackwright.jsontypes import JsonObject
from trackwright.workspace import PROFILE_FILE, STATE_FILE, ItemKind, OwnedItem, Workspace, now

WorkspaceAction = Literal["status", "init", "record", "forget"]
MAX_ITEMS = 200


class WorkspaceMixin(ServiceBase):
    def workspace(
        self,
        action: WorkspaceAction = "status",
        *,
        dry_run: bool = True,
        kind: str | None = None,
        key: str | None = None,
        skill: str | None = None,
        run: str | None = None,
        details: JsonObject | None = None,
    ) -> WorkspaceOut:
        if action not in get_args(WorkspaceAction):
            raise PreconditionFailedError(
                f"action must be one of {list(get_args(WorkspaceAction))}", code="BAD_REQUEST"
            )
        if action in ("record", "forget"):
            return self._own(action, kind=kind, key=key, skill=skill, run=run, details=details, dry_run=dry_run)
        if action == "init":
            self.policy.check_workspace()  # the permission first: it is what the user must change
        folder, why = self.project_folder()
        out = WorkspaceOut(action=action, dry_run=dry_run, enabled=self.policy.workspace, status="unknown_project")
        if folder is None:
            out.notes.append(why or "the project folder is unknown")
            if action == "init":
                raise PreconditionFailedError(
                    f"cannot create the workspace: {why}", code="NO_PROJECT_FOLDER", details={"reason": why}
                )
            return out
        space = Workspace(folder)
        out.project_folder, out.path = str(space.project_folder), str(space.path)
        out.missing = space.missing()
        if action == "init":
            if dry_run:
                out.status = "planned" if out.missing else "exists"
                return out
            out.created = space.create()
            out.missing = space.missing()
        out.exists = space.exists
        out.status = "exists" if out.exists else "absent"
        if out.created:
            out.status = "created"
        if out.exists:
            state = space.load_state()
            out.has_state = (space.path / STATE_FILE).is_file()
            out.owned = dict(Counter(f"{i.skill}:{i.kind}" for i in state.items))
            out.items = [i.model_dump(mode="json") for i in state.items[:MAX_ITEMS]]
            profile = space.load_profile()
            out.has_profile = (space.path / PROFILE_FILE).is_file()
            if profile is not None:
                out.profile = {
                    "show": profile.show,
                    "track_roles": len(profile.track_roles),
                    "protected_ranges": len(profile.protected),
                }
        if not self.policy.workspace:
            out.notes.append("writing is disabled: set [workspace] enabled = true to let skills use this folder")
        return out

    def _own(
        self,
        action: Literal["record", "forget"],
        *,
        kind: str | None,
        key: str | None,
        skill: str | None,
        run: str | None,
        details: JsonObject | None,
        dry_run: bool,
    ) -> WorkspaceOut:
        """Record (or forget) one item a skill created, so a re-run finds and updates it (TW-1609)."""
        self.policy.check_workspace()
        if kind not in get_args(ItemKind) or not key:
            raise PreconditionFailedError(
                f"give 'kind' (one of {list(get_args(ItemKind))}) and 'key'", code="BAD_REQUEST"
            )
        folder, why = self.project_folder()
        if folder is None:
            raise PreconditionFailedError(
                f"cannot find the workspace: {why}", code="NO_PROJECT_FOLDER", details={"reason": why}
            )
        space = Workspace(folder)
        out = WorkspaceOut(
            action=action,
            dry_run=dry_run,
            enabled=True,
            status="planned",
            project_folder=str(space.project_folder),
            path=str(space.path),
            exists=space.exists,
        )
        state = space.load_state()
        item_kind: ItemKind = kind  # type: ignore[assignment]  # checked above
        before = state.find(item_kind, key)
        out.before = before.model_dump(mode="json") if before is not None else None
        if action == "record":
            if not skill or not run:
                raise PreconditionFailedError("give 'skill' and 'run' to record an item", code="BAD_REQUEST")
            try:
                item = OwnedItem(kind=item_kind, key=key, skill=skill, run=run, updated=now(), details=details or {})
                out.after = item.model_dump(mode="json")
            except (ValidationError, PydanticSerializationError) as exc:
                reason = {"reason": str(exc)[:500]}
                raise PreconditionFailedError("not a valid item", code="BAD_REQUEST", details=reason) from exc
            if before is not None and before.skill != skill:
                out.notes.append(f"recorded by {before.skill!r} until now: the newest creator owns it")
            state.record(item)
        else:
            out.after = None
            if before is None:
                out.notes.append("nothing recorded under that kind and key")
            state.forget(item_kind, key)
        if dry_run:
            return out
        space.save_state(state)  # NO_WORKSPACE when the folder does not exist
        out.status = "recorded" if action == "record" else "forgotten"
        out.has_state = True
        out.has_profile = (space.path / PROFILE_FILE).is_file()
        out.owned = dict(Counter(f"{i.skill}:{i.kind}" for i in state.items))
        out.items = [i.model_dump(mode="json") for i in state.items[:MAX_ITEMS]]
        return out
