"""Ducking from the voice (TW-1614): the plan, read-only, and the envelope a ``duck`` render applies.

The voice is an export of the voice tracks (soloed together), the music an export of the music track, both
placed in project time by their range starts. Speech regions come from :mod:`trackwright.analysis.speech`;
the episode profile's protected ranges are added unless told otherwise; the planner is
:mod:`trackwright.analysis.ducking`. The same specification gives the same envelope in the plan and in the
render, and is stored in the render's provenance.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from trackwright.analysis import decoded, probe
from trackwright.analysis.ducking import DuckingParams, Envelope, Override, changed_spans, plan
from trackwright.analysis.speech import SpeechCriteria, detect_speech
from trackwright.core.models import DuckingPlanOut, DuckMomentOut, DuckSpanOut
from trackwright.core.profiling import ProfilesMixin
from trackwright.core.timefmt import format_seconds, parse_seconds
from trackwright.errors import NotFoundError, PreconditionFailedError
from trackwright.jsontypes import JsonObject
from trackwright.renders import SILENT_DBFS, range_level_db

MAX_SPANS = 500
MOMENT_WINDOW = 3.0  # seconds around a moment where the music must be audible


class OverrideSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0, description="project seconds")
    end: float = Field(gt=0)
    mode: Literal["hold", "free", "depth"]
    depth_db: float | None = Field(default=None, ge=-60, le=0)
    note: str = ""


class DuckingSpec(BaseModel):
    """What a ducking plan or render needs; stored as the render's parameters."""

    model_config = ConfigDict(extra="forbid")

    voice_file: str = Field(description="absolute path of the voice export (the voice tracks soloed together)")
    voice_start: float = Field(default=0.0, ge=0, description="project time of its first sample")
    attenuation_db: float = Field(default=-10.0, ge=-60, le=0)
    pre_roll: float = Field(default=0.25, ge=0, le=5)
    hold: float = Field(default=0.8, ge=0, le=10)
    recovery: float = Field(default=1.2, ge=0, le=10)
    merge_gap: float = Field(default=0.9, ge=0, le=10)
    overrides: list[OverrideSpec] = Field(default_factory=list)
    use_protected: bool = Field(default=True, description="keep the episode profile's protected ranges up")

    def params(self) -> DuckingParams:
        return DuckingParams(self.attenuation_db, self.pre_roll, self.hold, self.recovery, self.merge_gap)


def parse_spec(raw: JsonObject | None) -> DuckingSpec:
    if raw is None:
        raise PreconditionFailedError("give the ducking specification (at least voice_file)", code="BAD_REQUEST")
    try:
        spec = DuckingSpec.model_validate(raw)
    except ValidationError as exc:
        errors = [{"loc": ".".join(str(p) for p in e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        raise PreconditionFailedError("not a valid ducking specification", code="BAD_REQUEST",
                                      details={"errors": errors[:20]}) from exc  # fmt: skip
    for override in spec.overrides:
        if override.end <= override.start:
            raise PreconditionFailedError("an override must end after it starts", code="BAD_REQUEST")
        if override.mode == "depth" and override.depth_db is None:
            raise PreconditionFailedError("a 'depth' override needs depth_db", code="BAD_REQUEST")
    return spec


class DuckingMixin(ProfilesMixin):
    def _audible_moments(
        self, moments: list[DuckMomentOut], music_file: str, origin: float, notes: list[str]
    ) -> list[DuckMomentOut]:
        """Only the moments where the music has sound to hear (TW-1615: two previews fell in a gap of the
        music track and showed nothing)."""
        music = Path(music_file).expanduser()
        if not music.is_absolute() or not music.is_file():
            raise NotFoundError(f"not a file: {music}", code="NOT_FOUND")
        kept = []
        for moment in moments:
            level = range_level_db(music, origin, max(origin, moment.at - MOMENT_WINDOW), moment.at + MOMENT_WINDOW)
            if level is not None and level >= SILENT_DBFS:
                kept.append(moment.model_copy(update={"music_db": level}))
        if len(kept) < len(moments):
            notes.append(f"{len(moments) - len(kept)} moments left out: the music is silent around them")
        return kept

    def ducking_envelope(
        self, spec: DuckingSpec, *, start: float = 0.0, seconds: float | None = None
    ) -> tuple[Envelope, int, list[tuple[float, float]], list[str]]:
        """The envelope over the music's span (``start`` .. ``start + seconds``, project time), the number of
        speech regions, the protected ranges used, and notes."""
        self.policy.check_analysis()
        voice = Path(spec.voice_file).expanduser()
        if not voice.is_absolute():
            raise PreconditionFailedError("voice_file must be an absolute path", code="BAD_REQUEST")
        if not voice.is_file():
            raise NotFoundError(f"not a file: {voice}", code="NOT_FOUND")
        stat = voice.stat()
        key = (str(voice), stat.st_size, stat.st_mtime_ns)
        speech = self._speech_memo.get(key)
        if speech is None:  # one detection per version of the voice export (a plan and its edit share it)
            with decoded(voice) as readable:
                self.policy.check_analysis(probe(readable).seconds)
                speech = detect_speech(readable, SpeechCriteria())
            self._speech_memo.clear()
            self._speech_memo[key] = speech
        regions = [(spec.voice_start + r.start, spec.voice_start + r.end) for r in speech.regions]
        notes: list[str] = []
        protected: list[tuple[float, float]] = []
        if spec.use_protected:
            resolved = self.profile("resolve")
            protected = [(float(r["start"]), float(r["end"])) for r in resolved.protected]
        if speech.contrast_db is not None and speech.contrast_db < SpeechCriteria().on_db:
            notes.append("little contrast in the voice export: is it the voice tracks alone?")
        overrides = [Override(o.start, o.end, o.mode, o.depth_db, o.note) for o in spec.overrides]
        end = None if seconds is None else start + seconds
        envelope = plan(regions, spec.params(), overrides=overrides, protected=protected, total=end)
        return envelope, len(regions), protected, notes

    def ducking_plan(
        self,
        ducking: JsonObject,
        *,
        music_start: str = "0",
        music_seconds: float | None = None,
        music_file: str | None = None,
        previous: JsonObject | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> DuckingPlanOut:
        """The ducked spans the render would apply, read-only (TW-1614); with ``previous``, the spans an edit
        changes (TW-1615)."""
        spec = parse_spec(ducking)
        origin = parse_seconds(music_start)
        if origin is None:
            raise PreconditionFailedError("music_start looks like '2.5' or '1:30'", code="BAD_TIME")
        env, regions, protected, notes = self.ducking_envelope(spec, start=origin, seconds=music_seconds)
        limit = max(1, min(limit, MAX_SPANS))
        changed: list[list[float]] | None = None
        if previous is not None:
            before, _, _, _ = self.ducking_envelope(parse_spec(previous), start=origin, seconds=music_seconds)
            last = max([0.0, *(p[0] for p in env.points), *(p[0] for p in before.points)])
            end = origin + music_seconds if music_seconds is not None else last + 1.0
            changed = [[round(a, 2), round(b, 2)] for a, b in changed_spans(before, env, start=origin, end=end)]
        page = env.spans[offset : offset + limit]
        moments = [m for s in page for m in (
            DuckMomentOut(at=round(s.fall_from, 3), why="the music goes down for the first word"),
            DuckMomentOut(at=round(s.end, 3), why="the music comes back up after the last word"),
        )]  # fmt: skip
        if music_file is not None:
            moments = self._audible_moments(moments, music_file, origin, notes)
        return DuckingPlanOut(
            changed=changed,
            moments=moments,
            parameters=asdict(spec.params()),
            speech_regions=regions,
            protected=[[a, b] for a, b in protected],
            total=len(env.spans),
            ducked_seconds=round(env.ducked_seconds, 3),
            spans=[
                DuckSpanOut(
                    start=format_seconds(s.start),
                    end=format_seconds(s.end),
                    start_seconds=round(s.start, 3),
                    end_seconds=round(s.end, 3),
                    depth_db=s.depth_db,
                    fall_from=round(s.fall_from, 3),
                    rise_to=round(s.rise_to, 3),
                )
                for s in env.spans[offset : offset + limit]
            ],
            points=len(env.points),
            notes=notes,
        )
