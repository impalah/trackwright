"""Show, episode and delivery profiles (TW-1607).

Three layers, each overriding the one before:

1. **built-in:** Trackwright's defaults (the silence criteria of ``cubase_analyze_audio``; nothing about a
   show's sound is assumed);
2. **show:** ``~/.config/trackwright/shows/<show>.toml``, shared by every episode of a show (track roles by
   track **name**, since uids repeat across projects made from one template, TW-1604);
3. **episode:** ``Trackwright/profile.toml`` in the project folder, which also names its show.

Tables merge key by key (a role set by the episode replaces only that track's), lists are replaced whole.

**Delivery profiles** describe what a platform asks for. Every number in one must be covered by a source:
a URL and the date it was read (``covers`` names the fields it supports), so a value can always be traced
back to the platform's own words. The built-in ones are in ``delivery.toml`` next to this module; a show can
add its own (a host the user names), with the user's source.
"""

from __future__ import annotations

import re
import tomllib
from datetime import date
from importlib import resources
from typing import Any, Literal

import tomli_w
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from trackwright.errors import PreconditionFailedError

FORMAT_VERSION = 1
SHOW_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
LAYERS = ("built-in", "show", "episode")

TrackRole = Literal["voice", "music", "effects", "reference", "other"]
Layer = Literal["built-in", "show", "episode"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------- delivery profiles
SPEC_FIELDS = (
    "loudness_lufs",
    "loudness_tolerance_lu",
    "true_peak_dbtp",
    "normalizes",
    "normalization_lufs",
    "codecs",
    "channels",
    "sample_rates",
    "bitrate_kbps",
    "min_bitrate_kbps",
    "max_bitrate_kbps",
    "max_file_mb",
)


class DeliverySource(_Model):
    url: str = Field(min_length=1, description="the platform's page (or 'user' for a value the user gave)")
    retrieved: date
    covers: list[str] = Field(min_length=1, description="the profile fields this source supports")
    quote: str = Field(default="", description="the platform's words, short")

    @model_validator(mode="after")
    def _known_fields(self) -> DeliverySource:
        unknown = sorted(set(self.covers) - set(SPEC_FIELDS))
        if unknown:
            raise ValueError(f"unknown fields in covers: {unknown}")
        return self


class DeliveryProfile(_Model):
    """What a platform asks of a delivered file. ``None`` / empty means the platform publishes nothing."""

    title: str = Field(min_length=1)
    loudness_lufs: float | None = Field(default=None, ge=-40, le=0, description="integrated loudness target")
    loudness_tolerance_lu: float | None = Field(default=None, ge=0, le=10)
    true_peak_dbtp: float | None = Field(default=None, ge=-20, le=0, description="ceiling")
    normalizes: bool | None = Field(default=None, description="the platform normalizes loudness on playback")
    normalization_lufs: float | None = Field(default=None, ge=-40, le=0)
    codecs: list[str] = Field(default_factory=list, description="accepted or recommended, e.g. mp3, aac")
    channels: list[Literal["mono", "stereo"]] = Field(default_factory=list)
    sample_rates: list[int] = Field(default_factory=list)
    bitrate_kbps: int | None = Field(default=None, gt=0, description="recommended")
    min_bitrate_kbps: int | None = Field(default=None, gt=0)
    max_bitrate_kbps: int | None = Field(default=None, gt=0)
    max_file_mb: float | None = Field(default=None, gt=0)
    requirement: str = Field(default="", description="what is required and what only recommended")
    notes: str = ""
    sources: list[DeliverySource] = Field(min_length=1)

    @model_validator(mode="after")
    def _every_value_has_a_source(self) -> DeliveryProfile:
        covered = {name for source in self.sources for name in source.covers}
        stated = {name for name in SPEC_FIELDS if getattr(self, name) not in (None, [])}
        missing = sorted(stated - covered)
        if missing:
            raise ValueError(f"values without a source: {missing}")
        return self


def builtin_delivery() -> dict[str, DeliveryProfile]:
    """The delivery profiles shipped with Trackwright (``delivery.toml``)."""
    text = resources.files("trackwright").joinpath("delivery.toml").read_text(encoding="utf-8")
    raw = tomllib.loads(text)
    return {name: DeliveryProfile.model_validate(value) for name, value in raw.get("profiles", {}).items()}


# ---------------------------------------------------------------------------- show and episode settings
class VoiceSettings(_Model):
    pan: float | None = Field(default=None, ge=-100, le=100, description="-100 left .. 0 centre .. +100 right")


class MusicSettings(_Model):
    approved: list[str] | None = Field(default=None, description="music files approved for the show")


class DuckingSettings(_Model):
    depth_db: float | None = Field(default=None, ge=-60, le=0, description="music level under speech")
    pre_roll_seconds: float | None = Field(default=None, ge=0, le=5)
    hold_seconds: float | None = Field(default=None, ge=0, le=10)
    release_seconds: float | None = Field(default=None, ge=0, le=10)


class EditingSettings(_Model):
    min_silence_seconds: float | None = Field(default=None, gt=0, le=60)
    padding_seconds: float | None = Field(default=None, ge=0, le=5)


class DeliverySettings(_Model):
    targets: list[str] | None = Field(default=None, description="delivery profile names, built-in or the show's")
    profiles: dict[str, DeliveryProfile] = Field(default_factory=dict, description="the show's own hosts")


class Settings(_Model):
    """What a show or an episode may set. ``None`` means "not set here": the layer below decides."""

    track_roles: dict[str, TrackRole] = Field(default_factory=dict, description="by track name")
    voices: dict[str, VoiceSettings] = Field(default_factory=dict, description="by track name")
    music: MusicSettings = Field(default_factory=MusicSettings)
    ducking: DuckingSettings = Field(default_factory=DuckingSettings)
    editing: EditingSettings = Field(default_factory=EditingSettings)
    delivery: DeliverySettings = Field(default_factory=DeliverySettings)


class ShowProfile(Settings):
    """``~/.config/trackwright/shows/<show>.toml``."""

    version: int = FORMAT_VERSION
    title: str = ""
    notes: str = ""


BUILTIN = Settings(editing=EditingSettings(min_silence_seconds=2.0, padding_seconds=0.25))


def check_show_name(name: str) -> str:
    if not SHOW_NAME.match(name):
        raise PreconditionFailedError(
            f"not a show name: {name!r} (letters, digits, '-' and '_', up to 64)",
            code="BAD_REQUEST",
            details={"show": name},
        )
    return name


def _layer_dict(settings: Settings) -> dict[str, Any]:
    data = settings.model_dump(mode="json", exclude_none=True, include=set(Settings.model_fields))
    data["delivery"].pop("profiles", None)  # merged separately (whole profiles, never field by field)
    return data


def _merge(
    base: dict[str, Any], top: dict[str, Any], layer: str, origins: dict[str, str], prefix: str = ""
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in top.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value, layer, origins, f"{path}.")
        elif isinstance(value, dict):
            merged[key] = _merge({}, value, layer, origins, f"{path}.")
        else:
            merged[key] = value
            origins[path] = layer
    return merged


def resolve(
    show: Settings | None, episode: Settings | None
) -> tuple[Settings, dict[str, str], dict[str, DeliveryProfile]]:
    """Merge built-in < show < episode: the settings, where each value came from (dotted path -> layer), and
    the delivery profiles available (built-in, then the show's and the episode's own)."""
    origins: dict[str, str] = {}
    merged: dict[str, Any] = {}
    profiles = builtin_delivery()
    for layer, settings in zip(LAYERS, (BUILTIN, show, episode), strict=True):
        if settings is None:
            continue
        merged = _merge(merged, _layer_dict(settings), layer, origins)
        profiles.update(settings.delivery.profiles)
    try:
        resolved = Settings.model_validate(merged)
    except ValidationError as exc:  # pragma: no cover - each layer was valid and merging keeps types
        raise PreconditionFailedError("the profiles do not merge", code="BAD_PROFILE") from exc
    return resolved, origins, profiles


def _prune(value: Any) -> Any:
    if isinstance(value, dict):
        pruned = {k: _prune(v) for k, v in value.items()}
        return {k: v for k, v in pruned.items() if v not in ({}, None)}
    if isinstance(value, list):
        return [_prune(v) for v in value]
    return value


def profile_toml(profile: BaseModel) -> str:
    """A show or episode profile as TOML: unset values and empty tables left out, the version always kept."""
    data = _prune(profile.model_dump(mode="python", exclude_none=True))
    data.setdefault("version", FORMAT_VERSION)
    return tomli_w.dumps(data)
