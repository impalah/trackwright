"""Dialogue leveling (TW-1622): the plan, read-only, and the specification a ``level`` render applies.

Each voice is an export of one voice track alone (``cubase_export_mix`` with that track soloed), placed in
project time by its range start. The planner is :mod:`trackwright.analysis.leveling`; the plan gives each
voice a ``level`` object (its gains over time) that ``cubase_render`` applies, recorded in the provenance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from trackwright.analysis import decoded, probe
from trackwright.analysis.leveling import (
    BINS_PER_SECOND,
    Gain,
    LevelingParams,
    gain_curve,
    k_power_bins,
    plan_leveling,
)
from trackwright.core.analyzing import AnalyzingMixin
from trackwright.core.ducking import DuckingMixin
from trackwright.core.models import LevelingPlanOut, LevelSegmentOut, LevelVoiceOut
from trackwright.errors import NotFoundError, PreconditionFailedError
from trackwright.jsontypes import JsonObject

MAX_VOICES = 8
MAX_SEGMENTS = 500


class VoiceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str = Field(description="absolute path of the export of this voice track alone")
    start: float = Field(default=0.0, ge=0, description="project time of the export's first sample")
    name: str = Field(default="", max_length=64, description="the voice (the track's name)")


class LevelSpec(BaseModel):
    """What a ``level`` render applies: gains over project time, ramped in the pauses (TW-1622)."""

    model_config = ConfigDict(extra="forbid")

    gains: list[tuple[float, float, float]] = Field(min_length=1, description="[start, end, gain_db] each")
    ramp: float = Field(default=0.2, ge=0, le=2)
    max_gain_db: float = Field(default=12.0, gt=0, le=24)


def parse_level(raw: JsonObject | None) -> LevelSpec:
    try:
        spec = LevelSpec.model_validate(raw or {})
    except ValidationError as exc:
        raise PreconditionFailedError("not a valid level object (take it from cubase_leveling_plan)",
                                      code="BAD_REQUEST", details={"reason": str(exc)[:500]}) from exc  # fmt: skip
    for start, end, db in spec.gains:
        if end <= start or abs(db) > spec.max_gain_db:
            raise PreconditionFailedError(f"bad gain [{start}, {end}, {db}]: end after start, within "
                                          f"±{spec.max_gain_db:g} dB", code="BAD_REQUEST")  # fmt: skip
    return spec


def level_gains(spec: LevelSpec) -> list[Gain]:
    return [Gain(a, b, db) for a, b, db in spec.gains]


class LevelingMixin(DuckingMixin, AnalyzingMixin):
    def leveling_plan(
        self,
        voices: list[JsonObject],
        *,
        target_lufs: float | None = None,
        max_gain_db: float = 6.0,
        tolerance_db: float = 2.0,
        join_gap: float = 1.5,
        min_segment: float = 3.0,
        ramp: float = 0.2,
        offset: int = 0,
        limit: int = 100,
    ) -> LevelingPlanOut:
        specs = self._voice_specs(voices)
        params = LevelingParams(target_lufs, max_gain_db, tolerance_db, join_gap, min_segment, ramp)
        measured = []
        for i, spec in enumerate(specs):
            path = self._audio_path(spec.file)
            if not path.is_file():
                raise NotFoundError(f"not a file: {path}", code="NOT_FOUND")
            speech = self.voice_activity(spec.file)
            regions = [(spec.start + r.start, spec.start + r.end) for r in speech.regions]
            with decoded(path) as readable:
                self.policy.check_analysis(probe(readable).seconds)
                power = k_power_bins(readable)
            measured.append((spec.name or Path(spec.file).stem or f"voice {i + 1}", power, BINS_PER_SECOND,
                             spec.start, regions))  # fmt: skip
        target, levels = plan_leveling(measured, params)
        out = LevelingPlanOut(target_lufs=target, parameters={
            "target_lufs": target_lufs, "max_gain_db": max_gain_db, "tolerance_db": tolerance_db,
            "join_gap": join_gap, "min_segment": min_segment, "ramp": ramp}, voices=[])  # fmt: skip
        limit = max(1, min(limit, MAX_SEGMENTS))
        for spec, level in zip(specs, levels, strict=True):
            segs = level.segments
            totals = [s.gain_db for s in segs] or [level.voice_gain_db]
            corrected = [s for s in segs if s.segment_gain_db != 0]
            voice = LevelVoiceOut(
                name=level.name, file=spec.file, start=spec.start, loudness_lufs=level.loudness_lufs,
                voice_gain_db=level.voice_gain_db, segments_total=len(segs), corrected=len(corrected),
                bounded=sum(1 for s in segs if "bounded" in s.reason), gain_range_db=[min(totals), max(totals)],
                segments=[LevelSegmentOut(**_fields(s)) for s in segs[offset : offset + limit]],
                compare=_compare(segs), level=_level_object(level.gains, ramp, max_gain_db),
            )  # fmt: skip
            out.voices.append(voice)
            if level.loudness_lufs is None:
                out.notes.append(f"{level.name}: no speech found; it is left as it is")
        if len(specs) == 1 and target_lufs is None:
            out.notes.append("one voice and no target: its own loudness is the target, so only its segments "
                             "that stray from it change")  # fmt: skip
        out.notes.append("the gains are the plan's starting values: compare the fragments before and after")
        return out

    @staticmethod
    def _voice_specs(voices: list[JsonObject]) -> list[VoiceSpec]:
        if not voices or len(voices) > MAX_VOICES:
            raise PreconditionFailedError(f"give 1 to {MAX_VOICES} voices (one export per voice track)",
                                          code="BAD_REQUEST")  # fmt: skip
        try:
            return [VoiceSpec.model_validate(v) for v in voices]
        except ValidationError as exc:
            raise PreconditionFailedError("not a valid voice", code="BAD_REQUEST",
                                          details={"reason": str(exc)[:500]}) from exc  # fmt: skip


def _fields(segment: Any) -> dict[str, Any]:
    return {k: getattr(segment, k) for k in LevelSegmentOut.model_fields}


def _compare(segments: list[Any]) -> list[list[float]]:
    """Up to three fragments to compare: the most raised, the most lowered and the most typical segment."""
    corrected = [s for s in segments if s.segment_gain_db != 0]
    picks = []
    if corrected:
        picks += [max(corrected, key=lambda s: s.segment_gain_db), min(corrected, key=lambda s: s.segment_gain_db)]
    plain = [s for s in segments if s.segment_gain_db == 0 and s.deviation_db is not None]
    if plain:
        picks.append(min(plain, key=lambda s: abs(s.deviation_db)))
    seen: list[list[float]] = []
    for s in picks:
        span = [s.start, round(min(s.end, s.start + 10.0), 3)]
        if span not in seen:
            seen.append(span)
    return seen


def _level_object(gains: list[Gain], ramp: float, max_gain_db: float) -> dict[str, Any]:
    return {"gains": [[g.start, g.end, g.gain_db] for g in gains], "ramp": ramp, "max_gain_db": max_gain_db}


__all__ = ["LevelSpec", "LevelingMixin", "gain_curve", "level_gains", "parse_level"]
