"""The project workspace tool (TW-1602): report and create ``Trackwright/`` inside the open project's folder.

The project folder comes from the files Cubase has open (``project_folder()``, no request to Cubase) and is
never guessed between several projects. Creating the folder needs ``[workspace] enabled``; reporting does not.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from trackwright.core.base import ServiceBase
from trackwright.core.models import WorkspaceOut
from trackwright.errors import PreconditionFailedError
from trackwright.workspace import PROFILE_FILE, STATE_FILE, Workspace


class WorkspaceMixin(ServiceBase):
    def workspace(self, action: Literal["status", "init"] = "status", *, dry_run: bool = True) -> WorkspaceOut:
        if action not in ("status", "init"):
            raise PreconditionFailedError("action must be 'status' or 'init'", code="BAD_REQUEST")
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
