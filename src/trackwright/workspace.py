"""The ``Trackwright/`` folder inside a project folder (TW-1602).

Skills that render audio, cache analyses or must remember what they created keep it here, next to the
project's ``Audio/`` and ``Mixdown/`` folders, so it travels with the project:

- ``renders/``: processed audio, imported back into Cubase (each with a provenance file, TW-1606);
- ``previews/``: short files to listen to before approving a change;
- ``analysis/``: analysis results tied to the export they come from (TW-1608);
- ``reports/``: quality-control and delivery reports;
- ``state.json``: what each skill created (tracks, plugins, renders…), so a re-run updates its own items
  instead of piling up new ones, and never touches the user's;
- ``profile.toml``: the episode profile (track roles, protected ranges, notes), edited by the user too.

Nothing outside ``Trackwright/`` is ever written, every path is checked to stay inside it (no ``..``, no
absolute paths, no symbolic links leading out), and files are written atomically. This module knows nothing
about Cubase or the write policy: the service checks ``[workspace] enabled`` first.
"""

from __future__ import annotations

import json
import os
import tempfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from trackwright.errors import PreconditionFailedError
from trackwright.jsontypes import JsonObject
from trackwright.profiles import Settings, profile_toml

FOLDER = "Trackwright"
SUBFOLDERS = ("renders", "previews", "analysis", "reports")
STATE_FILE = "state.json"
PROFILE_FILE = "profile.toml"
FORMAT_VERSION = 1

ItemKind = Literal["track", "plugin", "render", "preview", "marker", "automation", "report"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OwnedItem(_Model):
    """Something a skill created. Identified by ``kind`` and ``key`` (a track uid, ``<track uid>/slot:N``, a
    path inside the workspace…); a re-run of the same skill finds and updates it."""

    kind: ItemKind
    key: str = Field(min_length=1)
    skill: str = Field(min_length=1)
    run: str = Field(min_length=1, description="identifier of the skill run that created or last updated it")
    updated: datetime
    details: JsonObject = Field(default_factory=dict)


class State(_Model):
    version: int = FORMAT_VERSION
    items: list[OwnedItem] = Field(default_factory=list)

    def owned_by(self, skill: str, kind: ItemKind | None = None) -> list[OwnedItem]:
        return [i for i in self.items if i.skill == skill and (kind is None or i.kind == kind)]

    def find(self, kind: ItemKind, key: str) -> OwnedItem | None:
        return next((i for i in self.items if i.kind == kind and i.key == key), None)

    def record(self, item: OwnedItem) -> None:
        """Add ``item``, replacing the record with the same kind and key (another skill's record included:
        the newest creator owns it)."""
        self.items = [i for i in self.items if (i.kind, i.key) != (item.kind, item.key)]
        self.items.append(item)

    def forget(self, kind: ItemKind, key: str) -> bool:
        before = len(self.items)
        self.items = [i for i in self.items if (i.kind, i.key) != (kind, key)]
        return len(self.items) != before


class ProtectedRange(_Model):
    """A span of the project that skills must not change (seconds)."""

    start: float = Field(ge=0)
    end: float = Field(gt=0)
    note: str = ""

    @model_validator(mode="after")
    def _ordered(self) -> ProtectedRange:
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class EpisodeProfile(Settings):
    """Per-episode settings, confirmed by the user: the show's settings overridden for this episode (TW-1607),
    plus the show it belongs to and the ranges no skill may change. Track roles are keyed by track name."""

    version: int = FORMAT_VERSION
    show: str | None = Field(default=None, description="show profile name (~/.config/trackwright/shows/<show>.toml)")
    protected: list[ProtectedRange] = Field(default_factory=list)
    notes: str = ""


def now() -> datetime:
    return datetime.now(UTC)


def atomic_write(path: Path, data: bytes) -> None:
    """Write through a temporary file in the same folder and rename it, so a reader never sees half a file."""
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        Path(tmp).replace(path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class Workspace:
    """``<project folder>/Trackwright``. Creating it is explicit (:meth:`create`); reading never creates."""

    def __init__(self, project_folder: Path) -> None:
        if not project_folder.is_dir():
            raise PreconditionFailedError(
                f"the project folder does not exist: {project_folder}",
                code="NOT_FOUND",
                details={"project_folder": str(project_folder)},
            )
        self.project_folder = project_folder.resolve()
        self.path = self.project_folder / FOLDER

    @property
    def exists(self) -> bool:
        return self.path.is_dir() and not self.path.is_symlink()

    def missing(self) -> list[str]:
        """What :meth:`create` would create, relative to the project folder."""
        wanted = [FOLDER, *(f"{FOLDER}/{sub}" for sub in SUBFOLDERS)]
        return [rel for rel in wanted if not (self.project_folder / rel).is_dir()]

    def create(self) -> list[str]:
        """Create the folder and its subfolders (never anything else); return what was created."""
        if self.path.is_symlink() or (self.path.exists() and not self.path.is_dir()):
            raise PreconditionFailedError(
                f"{self.path} exists and is not a plain folder: Trackwright will not use it",
                code="BAD_WORKSPACE",
                details={"path": str(self.path)},
            )
        created = self.missing()
        for rel in created:
            (self.project_folder / rel).mkdir()
        return created

    def file(self, relative: str) -> Path:
        """``Trackwright/<relative>``, refusing anything that would land outside the workspace."""
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
            raise PreconditionFailedError(
                f"not a path inside the workspace: {relative!r}", code="BAD_REQUEST", details={"path": relative}
            )
        target = self.path / candidate
        resolved = target.resolve()
        if resolved != self.path.resolve() and self.path.resolve() not in resolved.parents:
            raise PreconditionFailedError(
                f"{relative!r} leads outside the workspace", code="BAD_REQUEST", details={"path": relative}
            )
        return target

    def _require(self) -> None:
        if not self.exists:
            raise PreconditionFailedError(
                "the project has no Trackwright/ folder yet: create it with cubase_workspace (action 'init')",
                code="NO_WORKSPACE",
                details={"path": str(self.path)},
            )

    # ------------------------------------------------------------------ state.json
    def load_state(self) -> State:
        path = self.path / STATE_FILE
        if not path.is_file():
            return State()
        try:
            return State.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, ValidationError) as exc:
            raise PreconditionFailedError(
                f"{path} is not a valid Trackwright state file: fix or remove it",
                code="BAD_WORKSPACE",
                details={"path": str(path), "reason": str(exc)[:500]},
            ) from exc

    def save_state(self, state: State) -> Path:
        self._require()
        path = self.path / STATE_FILE
        atomic_write(path, (state.model_dump_json(indent=2) + "\n").encode("utf-8"))
        return path

    # ------------------------------------------------------------------ profile.toml
    def load_profile(self) -> EpisodeProfile | None:
        path = self.path / PROFILE_FILE
        if not path.is_file():
            return None
        try:
            return EpisodeProfile.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
        except (tomllib.TOMLDecodeError, ValidationError) as exc:
            raise PreconditionFailedError(
                f"{path} is not a valid episode profile: fix or remove it",
                code="BAD_WORKSPACE",
                details={"path": str(path), "reason": str(exc)[:500]},
            ) from exc

    def save_profile(self, profile: EpisodeProfile) -> Path:
        self._require()
        path = self.path / PROFILE_FILE
        atomic_write(path, profile_toml(profile).encode("utf-8"))
        return path
