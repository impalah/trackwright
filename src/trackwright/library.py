"""The licensed audio library (TW-1620): music, effects and stingers the user may use, with their licence.

The library is one or more local folders (``[library] folders`` in the configuration). Every usable sound has a
**sidecar** next to it, ``<file>.toml`` (``march.mp3`` -> ``march.mp3.toml``), with its title, kind, licence,
source, attribution, allowed uses and tags. A sound without a sidecar, or whose sidecar names no licence, is
**never offered**: :func:`check` lists it so the user can complete it. Trackwright only reads these folders and
never downloads anything.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

import soundfile as sf
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

SIDECAR = ".toml"
AUDIO = frozenset({".wav", ".wave", ".aif", ".aiff", ".flac", ".mp3", ".m4a", ".ogg"})
Kind = Literal["music", "stinger", "effect", "ambience", "voice", "other"]


class Sidecar(BaseModel):
    """``<file>.toml``: what the user knows about a sound and the terms it may be used under."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    kind: Kind
    license: str = Field(min_length=1, description="the licence's name, e.g. 'CC-BY-4.0' or 'Storyblocks'")
    license_url: str = ""
    source: str = Field(default="", description="where it came from: a URL, a shop, 'own recording'")
    attribution: str = Field(default="", description="the credit the licence asks for (empty: none)")
    allowed_uses: list[str] = Field(default_factory=list, description="e.g. podcast, youtube, commercial")
    restrictions: str = ""
    tags: list[str] = Field(default_factory=list)
    acquired: date | None = None
    notes: str = ""

    @field_validator("license")
    @classmethod
    def _real_licence(cls, value: str) -> str:
        if value.strip().lower() in {"unknown", "none", "?", "-", "tbd", "todo"}:
            raise ValueError("the licence is not known: the sound cannot be offered until it is")
        return value.strip()


@dataclass(frozen=True, slots=True)
class Item:
    path: Path
    sidecar: Sidecar
    seconds: float | None


@dataclass(slots=True)
class Problems:
    """What keeps sounds out of the library."""

    no_sidecar: list[Path] = field(default_factory=list)
    invalid: dict[Path, str] = field(default_factory=dict)
    orphan_sidecars: list[Path] = field(default_factory=list)
    missing_folders: list[Path] = field(default_factory=list)


def sidecar_path(audio: Path) -> Path:
    return audio.with_name(audio.name + SIDECAR)


def _duration(path: Path) -> float | None:
    try:
        info = sf.info(str(path))
    except RuntimeError, sf.LibsndfileError:
        return None  # AAC: soundfile cannot read the header; the duration is not needed to offer it
    return info.frames / info.samplerate if info.samplerate else None


def scan(folders: list[Path]) -> tuple[list[Item], Problems]:
    """Every licensed sound under ``folders`` (recursively), and what kept the others out."""
    items: list[Item] = []
    problems = Problems()
    for folder in folders:
        root = folder.expanduser()
        if not root.is_dir():
            problems.missing_folders.append(root)
            continue
        for audio in sorted(p for p in root.rglob("*") if p.suffix.lower() in AUDIO and p.is_file()):
            if audio.name.startswith("."):
                continue
            side = sidecar_path(audio)
            if not side.is_file():
                problems.no_sidecar.append(audio)
                continue
            try:
                data = tomllib.loads(side.read_text(encoding="utf-8"))
                items.append(Item(audio, Sidecar.model_validate(data), _duration(audio)))
            except ValidationError as exc:  # which field, and why
                problems.invalid[side] = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc']) or 'file'}: {e['msg']}" for e in exc.errors()
                )[:300]
            except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
                problems.invalid[side] = f"not valid TOML: {exc}"[:300]
        for side in sorted(root.rglob(f"*{SIDECAR}")):
            audio = side.with_name(side.name.removesuffix(SIDECAR))
            if audio.suffix.lower() in AUDIO and not audio.is_file():
                problems.orphan_sidecars.append(side)
    return items, problems


def search(
    items: list[Item],
    query: str = "",
    *,
    kind: str | None = None,
    use: str | None = None,
    min_seconds: float | None = None,
    max_seconds: float | None = None,
) -> list[Item]:
    """Items whose title, tags, kind or file name contain every word of ``query``, with the filters."""
    words = [w for w in query.lower().split() if w]
    found = []
    for item in items:
        s = item.sidecar
        text = " ".join([s.title, s.kind, *s.tags, item.path.stem, s.notes]).lower()
        if any(w not in text for w in words):
            continue
        if kind is not None and s.kind != kind:
            continue
        if use is not None and use.lower() not in {u.lower() for u in s.allowed_uses}:
            continue
        if min_seconds is not None and (item.seconds is None or item.seconds < min_seconds):
            continue
        if max_seconds is not None and (item.seconds is None or item.seconds > max_seconds):
            continue
        found.append(item)
    return found


def template(audio: Path) -> str:
    """A sidecar to fill in for ``audio`` (printed, never written by Trackwright)."""
    return (
        f"# {sidecar_path(audio).name}: what you know about {audio.name}. Fill in the licence before using it.\n"
        f'title = "{audio.stem}"\n'
        'kind = "music"            # music, stinger, effect, ambience, voice, other\n'
        'license = ""              # the licence\'s name; required (a sound without one is never offered)\n'
        'license_url = ""\n'
        'source = ""               # where it came from: a URL, a shop, "own recording"\n'
        'attribution = ""          # the credit the licence asks for, if any\n'
        'allowed_uses = []         # e.g. ["podcast", "youtube", "commercial"]\n'
        'restrictions = ""\n'
        "tags = []\n"
    )
