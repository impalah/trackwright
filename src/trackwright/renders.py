"""Renders (TW-1606): processed audio in ``Trackwright/renders/``, each with its provenance file.

A render is made from a file the user exported (a track alone, between the locators), so its first sample
belongs at the export's range start. The provenance file next to it (``<name>.json``) says where it came from
and where it goes: the source file and its SHA-256, the process and its parameters, the project position,
the track it replaces, and the SHA-256 of the render itself, so a render changed after it was made is caught
before it is imported.

Renders are never overwritten: Cubase may still reference an older one (in the project or its undo history),
so a new render of the same thing gets the next free number (``voice-gain-2.wav``). Written as 32-bit float
WAV at the source's rate and channels, through a temporary file renamed at the end. Nothing here knows about
Cubase: the service checks the policy and finds the workspace.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from trackwright.analysis.reader import AudioInfo, probe
from trackwright.errors import PreconditionFailedError
from trackwright.jsontypes import JsonObject
from trackwright.workspace import FOLDER, OwnedItem, State, Workspace, now

RENDERS = "renders"
SUFFIX = ".wav"
PROVENANCE_SUFFIX = ".json"
FORMAT_VERSION = 1
READ_SECONDS = 10.0
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
MAX_NAME = 64

Block = npt.NDArray[np.float64]
Process = Callable[[Block], Block]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceInfo(_Model):
    path: str
    sha256: str
    size: int
    seconds: float
    rate: int
    channels: int


class Provenance(_Model):
    """The ``<name>.json`` next to a render."""

    version: int = FORMAT_VERSION
    file: str = Field(description="the render's file name inside renders/")
    created: datetime
    trackwright: str
    skill: str = Field(min_length=1)
    run: str = Field(min_length=1)
    process: str
    parameters: JsonObject = Field(default_factory=dict)
    position: float = Field(ge=0, description="project seconds of the render's first sample")
    track: str | None = Field(default=None, description="name of the track the render replaces")
    track_uid: str | None = None
    seconds: float
    rate: int
    channels: int
    sha256: str
    peak_dbfs: float | None
    source: SourceInfo


def slug(text: str) -> str:
    """A file-name-safe version of ``text`` (letters, digits, ``.``, ``_``, ``-``)."""
    cleaned = _UNSAFE.sub("-", text).strip("-.")[:MAX_NAME].strip("-.")
    return cleaned or "render"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def provenance_path(render: Path) -> Path:
    return render.with_suffix(PROVENANCE_SUFFIX)


def next_name(folder: Path, base: str) -> str:
    """``<base>.wav`` or the first free ``<base>-N.wav``: an existing render is never replaced."""
    base = slug(base)
    candidate, number = base, 1
    while (folder / f"{candidate}{SUFFIX}").exists() or (folder / f"{candidate}{PROVENANCE_SUFFIX}").exists():
        number += 1
        candidate = f"{base}-{number}"
    return f"{candidate}{SUFFIX}"


def gain(db: float) -> Process:
    factor = 10 ** (db / 20)
    return lambda block: block * factor


def _blocks(path: Path, rate: int) -> Iterator[Block]:
    size = max(1, round(rate * READ_SECONDS))
    try:
        for chunk in sf.blocks(str(path), blocksize=size, dtype="float64", always_2d=True):
            yield np.asarray(chunk, dtype=np.float64)
    except RuntimeError as exc:  # soundfile read errors
        raise PreconditionFailedError(
            f"could not read {path.name} to the end", code="BAD_AUDIO", details={"path": str(path), "reason": str(exc)}
        ) from exc


def render_file(source: Path, target: Path, process: Process) -> tuple[AudioInfo, float]:
    """Apply ``process`` block by block from ``source`` to a new 32-bit float WAV at ``target``.

    Returns the source's header and the render's sample peak (linear). ``target`` appears only when complete.
    """
    info = probe(source)
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=SUFFIX, dir=target.parent)
    peak = 0.0
    try:
        with (
            os.fdopen(fd, "wb") as handle,
            sf.SoundFile(
                handle, "w", samplerate=info.rate, channels=info.channels, format="WAV", subtype="FLOAT"
            ) as out,
        ):
            for block in _blocks(source, info.rate):
                processed = process(block)
                peak = max(peak, float(np.abs(processed).max(initial=0.0)))
                out.write(processed.astype(np.float32))
        Path(tmp).replace(target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return info, peak


def write_provenance(render: Path, provenance: Provenance) -> Path:
    path = provenance_path(render)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(provenance.model_dump_json(indent=2) + "\n")
        Path(tmp).replace(path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def is_render(path: Path) -> bool:
    """A file in ``…/Trackwright/renders/`` with its provenance file next to it."""
    return (
        path.is_file()
        and path.parent.name == RENDERS
        and path.parent.parent.name == FOLDER
        and provenance_path(path).is_file()
    )


def load_provenance(render: Path) -> Provenance:
    path = provenance_path(render)
    try:
        return Provenance.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, ValidationError) as exc:
        raise PreconditionFailedError(
            f"{path} is not a valid render provenance file",
            code="BAD_RENDER",
            details={"path": str(path), "reason": str(exc)[:500]},
        ) from exc


def problems(render: Path, provenance: Provenance) -> list[str]:
    """What no longer matches the provenance: the render changed, the source changed or is gone."""
    found = []
    if not render.is_file():
        return [f"the render {render.name} is missing"]
    if provenance.file != render.name:
        found.append(f"the provenance names {provenance.file}, not {render.name}")
    if sha256(render) != provenance.sha256:
        found.append(f"{render.name} changed after it was rendered")
    source = Path(provenance.source.path)
    if not source.is_file():
        found.append(f"the source {source.name} is gone (the render itself is still usable)")
    elif source.stat().st_size != provenance.source.size or sha256(source) != provenance.source.sha256:
        found.append(f"the source {source.name} changed after the render was made")
    return found


def renders_of(space: Workspace) -> list[Path]:
    folder = space.path / RENDERS
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob(f"*{SUFFIX}") if not p.name.startswith(".") and is_render(p))


def record_import(space: Workspace, render: Path, provenance: Provenance, track_uid: str, track_name: str) -> State:
    """Record the render and the track it was imported on as the skill's (a re-run finds and replaces them)."""
    state = space.load_state()
    when = now()
    key = f"{RENDERS}/{render.name}"
    state.record(
        OwnedItem(
            kind="render",
            key=key,
            skill=provenance.skill,
            run=provenance.run,
            updated=when,
            details={"track_uid": track_uid, "position": provenance.position},
        )
    )
    state.record(
        OwnedItem(
            kind="track",
            key=track_uid,
            skill=provenance.skill,
            run=provenance.run,
            updated=when,
            details={
                "name": track_name,
                "render": key,
                "replaces": provenance.track,
                "replaces_uid": provenance.track_uid,
            },
        )
    )
    space.save_state(state)
    return state
