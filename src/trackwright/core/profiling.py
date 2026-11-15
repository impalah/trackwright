"""The profiles tool (TW-1607): read the resolved show/episode settings and delivery profiles; write a show
or an episode profile after the user approves it.

The show profiles live in ``shows/`` next to the configuration file; the episode profile in the open
project's ``Trackwright/profile.toml``. Writing either needs ``[workspace] enabled`` (files skills write for
the user) and is a dry run by default: the plan shows the TOML before and after. Nothing is sent to Cubase.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from trackwright.config import config_path
from trackwright.core.base import ServiceBase
from trackwright.core.models import DeliveryProfileOut, ProfileOut
from trackwright.errors import NotFoundError, PreconditionFailedError
from trackwright.jsontypes import JsonObject
from trackwright.profiles import (
    DeliveryProfile,
    Settings,
    ShowProfile,
    builtin_delivery,
    check_show_name,
    profile_toml,
    resolve,
)
from trackwright.workspace import PROFILE_FILE, EpisodeProfile, Workspace, atomic_write

ProfileAction = Literal["resolve", "shows", "delivery", "write_show", "write_episode"]
ACTIONS = ("resolve", "shows", "delivery", "write_show", "write_episode")


def _invalid(what: str, exc: ValidationError) -> PreconditionFailedError:
    errors = [{"loc": ".".join(str(p) for p in e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    return PreconditionFailedError(f"not a valid {what}", code="BAD_PROFILE", details={"errors": errors[:20]})


def _delivery_out(
    name: str, profile: DeliveryProfile, origin: Literal["built-in", "show/episode"]
) -> DeliveryProfileOut:
    return DeliveryProfileOut(name=name, origin=origin, **profile.model_dump(mode="json"))


class ProfilesMixin(ServiceBase):
    def shows_dir(self) -> Path:
        return self._shows_dir if self._shows_dir is not None else config_path()[0].parent / "shows"

    def profile(
        self,
        action: ProfileAction = "resolve",
        *,
        show: str | None = None,
        data: JsonObject | None = None,
        dry_run: bool = True,
    ) -> ProfileOut:
        if action not in ACTIONS:
            raise PreconditionFailedError(f"action must be one of {list(ACTIONS)}", code="BAD_REQUEST")
        if action == "shows":
            return self._list_shows()
        if action in ("write_show", "write_episode"):
            return self._write_profile(action, show=show, data=data, dry_run=dry_run)
        return self._resolve_profile(action, show=show)

    # ------------------------------------------------------------------ reading
    def _load_show(self, name: str) -> tuple[Path, ShowProfile]:
        path = self.shows_dir() / f"{check_show_name(name)}.toml"
        if not path.is_file():
            raise NotFoundError(
                f"no show profile {name!r} ({path})", code="NOT_FOUND", details={"show": name, "path": str(path)}
            )
        try:
            return path, ShowProfile.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
        except tomllib.TOMLDecodeError as exc:
            raise PreconditionFailedError(
                f"{path} is not valid TOML: {exc}", code="BAD_PROFILE", details={"path": str(path)}
            ) from exc
        except ValidationError as exc:
            raise _invalid(f"show profile ({path})", exc) from exc

    def _episode_space(self) -> tuple[Workspace | None, str | None]:
        folder, why = self.project_folder()
        if folder is None:
            return None, why
        return Workspace(folder), None

    def _resolve_profile(self, action: str, *, show: str | None) -> ProfileOut:
        out = ProfileOut(action=action, dry_run=True, status="read", shows_dir=str(self.shows_dir()))  # type: ignore[arg-type]
        space, why = self._episode_space()
        episode: EpisodeProfile | None = None
        if space is None:
            out.notes.append(f"no episode profile: {why}")
        else:
            out.episode_path = str(space.path / PROFILE_FILE)
            episode = space.load_profile() if space.exists else None
            if episode is None:
                out.notes.append("the project has no Trackwright/profile.toml")
        name = show or (episode.show if episode is not None else None)
        show_profile: ShowProfile | None = None
        if name is not None:
            path, show_profile = self._load_show(name)
            out.show, out.show_path = name, str(path)
            if episode is not None and episode.show not in (None, name):
                out.notes.append(f"the episode names the show {episode.show!r}; {name!r} was used as asked")
        else:
            out.notes.append("no show: give 'show' or set it in the episode profile")
        resolved, origins, profiles = resolve(show_profile, episode)
        builtin = set(builtin_delivery())
        own = {
            **(show_profile.delivery.profiles if show_profile else {}),
            **(episode.delivery.profiles if episode else {}),
        }
        if action == "delivery":
            out.delivery = [
                _delivery_out(n, p, "show/episode" if n in own else "built-in") for n, p in sorted(profiles.items())
            ]
            return out
        out.settings = resolved.model_dump(mode="json", exclude_none=True)
        out.origins = origins
        for target in resolved.delivery.targets or []:
            if target in profiles:
                out.delivery.append(
                    _delivery_out(target, profiles[target], "show/episode" if target in own else "built-in")
                )
            else:
                out.notes.append(f"unknown delivery target {target!r} (known: {sorted(builtin | set(own))})")
        if episode is not None:
            out.protected = [r.model_dump(mode="json") for r in episode.protected]
        return out

    def _list_shows(self) -> ProfileOut:
        folder = self.shows_dir()
        out = ProfileOut(action="shows", dry_run=True, status="read", shows_dir=str(folder))
        out.shows = sorted(p.stem for p in folder.glob("*.toml")) if folder.is_dir() else []
        if not out.shows:
            out.notes.append(f"no show profiles in {folder}")
        return out

    # ------------------------------------------------------------------ writing
    def _write_profile(self, action: str, *, show: str | None, data: JsonObject | None, dry_run: bool) -> ProfileOut:
        self.policy.check_workspace()
        if data is None:
            raise PreconditionFailedError("give the whole profile in 'data'", code="BAD_REQUEST")
        out = ProfileOut(action=action, dry_run=dry_run, status="planned", shows_dir=str(self.shows_dir()))  # type: ignore[arg-type]
        profile: Settings
        episode_space: Workspace | None = None
        if action == "write_show":
            if show is None:
                raise PreconditionFailedError("give the show name", code="BAD_REQUEST")
            path = self.shows_dir() / f"{check_show_name(show)}.toml"
            try:
                profile = ShowProfile.model_validate(data)
            except ValidationError as exc:
                raise _invalid("show profile", exc) from exc
            out.show, out.show_path = show, str(path)
        else:
            space, why = self._episode_space()
            if space is None:
                raise PreconditionFailedError(
                    f"cannot find the project: {why}", code="NO_PROJECT_FOLDER", details={"reason": why}
                )
            path = space.path / PROFILE_FILE
            out.episode_path = str(path)
            try:
                profile = EpisodeProfile.model_validate(data)
            except ValidationError as exc:
                raise _invalid("episode profile", exc) from exc
            episode_space = space
        out.before = path.read_text(encoding="utf-8") if path.is_file() else None
        out.after = profile_toml(profile)
        out.changed = out.before != out.after
        if dry_run:
            out.notes.append("dry run: show the user 'after' and write it only once they agree")
            return out
        if isinstance(profile, EpisodeProfile) and episode_space is not None:
            episode_space.save_profile(profile)  # refuses without a workspace (NO_WORKSPACE)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(path, out.after.encode("utf-8"))
        out.status = "written"
        return out
