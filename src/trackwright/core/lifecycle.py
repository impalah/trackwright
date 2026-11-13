"""Opening Cubase (TW-1201). Trackwright never closes Cubase, forces it to quit or saves projects."""

from __future__ import annotations

import time
from pathlib import Path

from trackwright.core.base import ServiceBase, operation
from trackwright.core.models import LaunchOut
from trackwright.errors import PreconditionFailedError, TrackwrightError

POLL_SECONDS = 1.0


class LifecycleMixin(ServiceBase):
    def _script_version(self) -> str | None:
        """The script's version when it answers, else ``None`` (Cubase closed, loading or showing a dialog)."""
        try:
            return str(self.call("hello").get("scriptVersion") or "?")
        except TrackwrightError:
            return None

    @operation
    def launch_cubase(
        self, project: str | None = None, *, dry_run: bool = True, timeout: float | None = None
    ) -> LaunchOut:
        if self.launcher is None:
            raise TrackwrightError("this server cannot open applications", code="UNSUPPORTED")
        app = self.launcher.app
        project_path = self._project_path(project)
        version = self._script_version()
        running = self.launcher.is_running()
        if version is not None:
            return LaunchOut(status="already_running", app=app, dry_run=dry_run, process_running=True,
                             script_version=version, project=None)  # fmt: skip
        if running:
            return LaunchOut(
                status="running_without_script", app=app, dry_run=dry_run, process_running=True,
                script_version=None, project=None,
                instructions="Cubase is open but the Trackwright script does not answer. Open or create a project, "
                "close any dialog, and check Studio > MIDI Remote Manager (run 'trackwright doctor'). "
                "A second instance is not opened.",
            )  # fmt: skip
        plan = LaunchOut(status="planned", app=app, dry_run=dry_run, process_running=False, script_version=None,
                         project=str(project_path) if project_path else None)  # fmt: skip
        if dry_run:
            return plan
        self.policy.check_project_write()
        self.launcher.launch(project_path)
        deadline = time.monotonic() + (timeout if timeout is not None else self.launcher.launch_timeout)
        while time.monotonic() < deadline:
            self._sleep(POLL_SECONDS)
            version = self._script_version()
            if version is not None:
                plan.status, plan.script_version, plan.process_running = "ready", version, True
                return plan
        plan.process_running = self.launcher.is_running()
        plan.status = "awaiting_user"
        plan.instructions = (
            "Cubase is starting but the script has not answered yet. Look at Cubase: answer any dialog "
            "(Steinberg Hub, project choice, audio device) and open a project; then call cubase_status."
        )
        return plan

    @staticmethod
    def _project_path(project: str | None) -> Path | None:
        if project is None:
            return None
        path = Path(project).expanduser()
        if path.suffix.lower() != ".cpr":
            raise PreconditionFailedError("project must be a Cubase .cpr file", code="BAD_REQUEST")
        if not path.is_file():
            raise PreconditionFailedError(f"project not found: {path}", code="NOT_FOUND")
        return path.resolve()
