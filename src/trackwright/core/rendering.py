"""Render processed audio into the project workspace (TW-1606).

A render is made from an export of a track (``cubase_export_mix`` with ``solo``): Python processes it and
writes ``Trackwright/renders/<name>.wav`` with its provenance; the skill then imports it on a new track at
the export's range start (``cubase_import_audio``, which checks the position against the provenance and
records the track as the skill's) and mutes the original track. Reading the source needs ``[analysis]
enabled``; writing the render needs ``[workspace] enabled`` and an existing workspace. Nothing is sent to
Cubase except, with ``track``, reading that track's name and uid.

Processes: ``gain`` (``gain_db``) and ``duck`` (TW-1614: the music under the voice, from a ``ducking``
specification; see :mod:`trackwright.core.ducking`) and ``bed`` (TW-1617: a music bed of a given length, see
:mod:`trackwright.analysis.music`). Other skills (leveling) add theirs here.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from trackwright import __version__
from trackwright.analysis import decoded, probe
from trackwright.analysis.music import (
    BedPlan,
    Loop,
    estimate_tempo,
    mono,
    plan_bed,
    refine_end,
    render_bed,
    seam_score,
    seam_times,
)
from trackwright.core.analyzing import AnalyzingMixin
from trackwright.core.ducking import DuckingMixin, DuckingSpec, parse_spec
from trackwright.core.models import PreviewOut, RenderItemOut, RenderOut
from trackwright.core.refs import TrackSelector
from trackwright.core.timefmt import format_seconds, parse_seconds
from trackwright.errors import NotFoundError, PreconditionFailedError
from trackwright.jsontypes import JsonObject
from trackwright.renders import (
    RENDERS,
    SILENT_DBFS,
    Process,
    Provenance,
    SourceInfo,
    envelope_gain,
    gain,
    load_provenance,
    mix_range,
    next_name,
    problems,
    provenance_path,
    range_level_db,
    render_file,
    renders_of,
    sha256,
    slug,
    write_audio,
    write_provenance,
)
from trackwright.workspace import Workspace


class BedSpec(BaseModel):
    """A bed of a given length from a music file (TW-1617): intro, the loop repeated, the ending."""

    model_config = ConfigDict(extra="forbid")

    loop_start: float = Field(ge=0, description="seconds in the music file")
    loop_end: float = Field(gt=0)
    ending_start: float | None = Field(
        default=None, ge=0, description="jump to this ending; null: the last pass carries on to the end of the file"
    )
    target_seconds: float = Field(gt=0, le=3 * 3600, description="the bed's length; never exceeded")
    crossfade: float = Field(default=0.1, ge=0, le=4, description="equal-power crossfade at every seam")
    align: bool = Field(
        default=False, description="line loop_end up with loop_start by correlation (a region the user marked)"
    )


def parse_bed(raw: JsonObject | None) -> BedSpec:
    if raw is None:
        raise PreconditionFailedError("give the bed (loop_start, loop_end, ending_start, target_seconds)",
                                      code="BAD_REQUEST")  # fmt: skip
    try:
        bed = BedSpec.model_validate(raw)
    except ValidationError as exc:
        raise PreconditionFailedError("not a valid bed", code="BAD_REQUEST",
                                      details={"reason": str(exc)[:500]}) from exc  # fmt: skip
    if bed.loop_end <= bed.loop_start:
        raise PreconditionFailedError("loop_end must be after loop_start", code="BAD_REQUEST")
    if bed.ending_start is not None and bed.ending_start < bed.loop_end:
        raise PreconditionFailedError("the ending must start after the loop ends", code="BAD_REQUEST")
    if bed.crossfade * 2 >= bed.loop_end - bed.loop_start:
        raise PreconditionFailedError("the crossfade is too long for the loop", code="BAD_REQUEST")
    return bed


class PreviewSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    start: float = Field(default=0.0, ge=0, description="project time of the file's first sample")
    gain_db: float = Field(default=0.0, ge=-60, le=24)


PROCESSES = ("gain", "duck", "bed")
MAX_PREVIEW_SOURCES = 8
DOUBTFUL_SEAM = 0.5  # TW-1618: under this seam score a bed's seams are pointed out for a listen
MAX_PREVIEW_SECONDS = 120.0
PREVIEWS = "previews"
MAX_GAIN_DB = 40.0


def _peak_db(linear: float) -> float | None:
    return round(20 * math.log10(linear), 2) if linear > 0 else None


def item_out(render: Path, provenance: Provenance, *, check: bool = True) -> RenderItemOut:
    return RenderItemOut(
        file=str(render),
        provenance=str(provenance_path(render)),
        skill=provenance.skill,
        run=provenance.run,
        process=provenance.process,
        parameters=provenance.parameters,
        position=format_seconds(provenance.position),
        position_seconds=provenance.position,
        seconds=provenance.seconds,
        sample_rate=provenance.rate,
        channels=provenance.channels,
        peak_dbfs=provenance.peak_dbfs,
        replaces=provenance.track,
        source=provenance.source.path,
        problems=problems(render, provenance) if check else [],
    )


class RenderingMixin(DuckingMixin, AnalyzingMixin):
    def render(
        self,
        action: Literal["render", "list"] = "render",
        *,
        file: str | None = None,
        start: str = "0",
        process: str = "gain",
        gain_db: float = 0.0,
        ducking: JsonObject | None = None,
        bed: JsonObject | None = None,
        name: str | None = None,
        track: str | None = None,
        skill: str = "manual",
        run: str | None = None,
        dry_run: bool = True,
    ) -> RenderOut:
        if action == "list":
            return self._list_renders()
        if action != "render":
            raise PreconditionFailedError("action must be 'render' or 'list'", code="BAD_REQUEST")
        self.policy.check_workspace()  # the permissions first: they are what the user must change
        self.policy.check_analysis()
        self._check_render_request(file, process, gain_db, skill)
        assert file is not None  # checked above
        spec = parse_spec(ducking) if process == "duck" else None
        bed_spec = parse_bed(bed) if process == "bed" else None
        source = self._audio_path(file)
        if not source.is_file():
            raise NotFoundError(f"not a file: {source}", code="NOT_FOUND")
        position = parse_seconds(start)
        if position is None:
            raise PreconditionFailedError("start looks like '2.5', '1:30' or '0:01:30.000'", code="BAD_TIME")
        replaced = self._replaced_track(track)
        space = self._render_workspace()
        folder = space.path / RENDERS
        base = (name.removesuffix(".wav") if name else None) or "-".join(
            p for p in (str(replaced["name"]) if replaced else source.stem, process) if p
        )
        target = folder / next_name(folder, slug(base)) if folder.is_dir() else folder / f"{slug(base)}.wav"
        with decoded(source) as readable:
            info_in = probe(readable)
        self.policy.check_analysis(info_in.seconds)
        run_id = run or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        effect, parameters, duck_notes = self._render_effect(spec, gain_db, position, info_in.seconds, info_in.rate)
        bed_plan = None
        if bed_spec is not None:
            bed_plan, parameters, duck_notes = self._bed_plan(bed_spec, source, info_in.seconds)
        out = RenderOut(action="render", dry_run=dry_run, status="planned", workspace=str(space.path))
        notes = out.notes
        notes += duck_notes
        if dry_run:
            out.render = RenderItemOut(
                file=str(target), provenance=str(provenance_path(target)), skill=skill, run=run_id,
                process=process, parameters=parameters, position=format_seconds(position),
                position_seconds=position, seconds=bed_plan.seconds if bed_plan else round(info_in.seconds, 4),
                sample_rate=info_in.rate,
                channels=info_in.channels, peak_dbfs=None, replaces=replaced["name"] if replaced else None,
                source=str(source),
            )  # fmt: skip
            notes.append("dry run: nothing written; the render is 32-bit float WAV at the source's rate")
            return out
        if not folder.is_dir():
            raise PreconditionFailedError(
                "the workspace has no renders/ folder: create it with cubase_workspace (action 'init')",
                code="NO_WORKSPACE",
                details={"path": str(folder)},
            )
        with decoded(source) as readable:
            source_info = SourceInfo(
                path=str(source), sha256=sha256(source), size=source.stat().st_size,
                seconds=round(info_in.seconds, 6), rate=info_in.rate, channels=info_in.channels,
            )  # fmt: skip
            peak = self._write_render(readable, target, effect, bed_plan)
        written = probe(target)
        provenance = Provenance(
            file=target.name,
            created=datetime.now(UTC),
            trackwright=__version__,
            skill=skill,
            run=run_id,
            process=process,
            parameters=parameters,
            position=position,
            track=replaced["name"] if replaced else None,
            track_uid=replaced["uid"] if replaced else None,
            seconds=round(written.seconds, 6),
            rate=written.rate,
            channels=written.channels,
            sha256=sha256(target),
            peak_dbfs=_peak_db(peak),
            source=source_info,
        )
        write_provenance(target, provenance)
        out.status = "done"
        out.render = item_out(target, provenance, check=False)
        if peak > 1.0:
            notes.append(
                f"the render peaks at {_peak_db(peak)} dBFS: fine in 32-bit float, but lower a fader before export"
            )
        replaces = f" and mute {replaced['name']!r} (cubase_set_track_mix)" if replaced else ""
        out.instructions = (
            f"Create an audio track for it (cubase_add_track_interactive), then import {target} on that new "
            f"track at {format_seconds(position)} with cubase_import_audio (start, then confirm){replaces}. "
            "In Cubase's import options untick 'Copy file to project folder' (it already is in the project "
            "folder) and do not convert to 24 bit."
        )
        return out

    @staticmethod
    def _check_render_request(file: str | None, process: str, gain_db: float, skill: str) -> None:
        if file is None:
            raise PreconditionFailedError("give the file to render from (an export)", code="BAD_REQUEST")
        if process not in PROCESSES:
            raise PreconditionFailedError(
                f"unknown process {process!r}", code="BAD_REQUEST", details={"processes": list(PROCESSES)}
            )
        if abs(gain_db) > MAX_GAIN_DB:
            raise PreconditionFailedError(f"gain_db must be within ±{MAX_GAIN_DB:.0f} dB", code="BAD_REQUEST")
        if not skill.strip():
            raise PreconditionFailedError("skill cannot be empty", code="BAD_REQUEST")

    def _replaced_track(self, track: str | None) -> JsonObject | None:
        """Name and uid of the track a render replaces, when given."""
        if track is None:
            return None
        info = self.track_info(self.resolve_track(TrackSelector.parse(track)))
        return {"name": info.name, "uid": info.uid}

    @staticmethod
    def _bed_plan(bed: BedSpec, source: Path, total: float) -> tuple[BedPlan, JsonObject, list[str]]:
        """Intro, the loop repeated and the ending, as near the target as the loop allows (TW-1617), with the
        seams' places in the bed and the loop's seam score (TW-1618)."""
        if bed.loop_end > total or (bed.ending_start is not None and bed.ending_start >= total):
            raise PreconditionFailedError("the loop or the ending is beyond the end of the file", code="BAD_REQUEST")
        with decoded(source) as readable:
            data, rate = sf.read(str(readable), dtype="float64", always_2d=True)
        x = mono(data)
        loop_end = refine_end(x, rate, bed.loop_start, bed.loop_end) if bed.align else bed.loop_end
        if loop_end > total or loop_end <= bed.loop_start:
            raise PreconditionFailedError("the aligned loop does not fit in the file", code="BAD_REQUEST")
        score = seam_score(x, rate, estimate_tempo(x, rate), bed.loop_start, loop_end)
        plan = plan_bed(Loop(bed.loop_start, loop_end, 1.0, bed.crossfade), total, bed.target_seconds,
                        ending_start=bed.ending_start)  # fmt: skip
        short = round(bed.target_seconds - plan.seconds, 3)
        parameters: JsonObject = {**bed.model_dump(mode="json"), "loop_end_used": loop_end, "seam_score": score,
                                  "repeats": plan.repeats, "seconds": plan.seconds, "short_by": short,
                                  "seams": seam_times(plan)}  # fmt: skip
        seams = ", ".join(f"{t:g}" for t in seam_times(plan)) or "none"
        notes = [f"{plan.repeats} repeats of the loop: {plan.seconds:g} s, {short:g} s short of the target "
                 f"(no stretch); seams at {seams} s of the bed"]  # fmt: skip
        if bed.align:
            notes.append(f"loop_end lined up with loop_start: {bed.loop_end:g} -> {loop_end:g} s")
        if score is not None and score < DOUBTFUL_SEAM:
            notes.append(f"seam score {score:g}: listen to the seams before using the bed")
        return plan, parameters, notes

    @staticmethod
    def _write_render(readable: Path, target: Path, effect: Process, bed: BedPlan | None) -> float:
        """Write the render; return its sample peak (linear)."""
        if bed is None:
            _, peak = render_file(readable, target, effect)
            return peak
        data, rate = sf.read(str(readable), dtype="float64", always_2d=True)  # a bed is minutes, not hours
        rendered = render_bed(data, rate, bed)
        write_audio(target, rendered, rate)
        return float(np.abs(rendered).max(initial=0.0))

    def _render_effect(
        self, spec: DuckingSpec | None, gain_db: float, position: float, seconds: float, rate: int
    ) -> tuple[Process, JsonObject, list[str]]:
        """The block function of the process, the parameters recorded in the provenance, and notes."""
        if spec is None:
            return gain(gain_db), {"gain_db": gain_db}, []
        env, regions, protected, notes = self.ducking_envelope(spec, start=position, seconds=seconds)
        parameters: JsonObject = {
            **spec.model_dump(mode="json"),
            "voice_sha256": sha256(Path(spec.voice_file).expanduser()),
            "speech_regions": regions,
            "protected_used": [[a, b] for a, b in protected],
            "ducked_spans": len(env.spans),
            "ducked_seconds": round(env.ducked_seconds, 3),
        }
        return envelope_gain(env.gain_db, rate, position), parameters, notes

    # ------------------------------------------------------------------ previews (TW-1615)
    def preview(
        self,
        sources: list[JsonObject],
        *,
        start: str,
        end: str,
        name: str | None = None,
        skill: str = "manual",
        dry_run: bool = True,
    ) -> PreviewOut:
        """A short mix of exports over a project range, written to ``Trackwright/previews/`` to listen to."""
        self.policy.check_workspace()
        self.policy.check_analysis()
        try:
            parsed = [PreviewSource.model_validate(item) for item in sources]
        except ValidationError as exc:
            raise PreconditionFailedError("not a valid list of sources", code="BAD_REQUEST",
                                          details={"reason": str(exc)[:500]}) from exc  # fmt: skip
        if not 1 <= len(parsed) <= MAX_PREVIEW_SOURCES:
            raise PreconditionFailedError(f"give 1 to {MAX_PREVIEW_SOURCES} sources", code="BAD_REQUEST")
        first, last = parse_seconds(start), parse_seconds(end)
        if first is None or last is None:
            raise PreconditionFailedError("start and end look like '2.5' or '1:30'", code="BAD_TIME")
        if not 0 < last - first <= MAX_PREVIEW_SECONDS:
            raise PreconditionFailedError(f"a preview lasts 0 to {MAX_PREVIEW_SECONDS:.0f} s", code="BAD_REQUEST")
        paths = [self._audio_path(src.file) for src in parsed]
        for path in paths:
            if not path.is_file():
                raise NotFoundError(f"not a file: {path}", code="NOT_FOUND")
        space = self._render_workspace()
        folder = space.path / PREVIEWS
        base = slug((name or f"preview-{first:.0f}s").removesuffix(".wav"))
        target = folder / next_name(folder, base) if folder.is_dir() else folder / f"{base}.wav"
        names = [f"{p.name} ({src.gain_db:+g} dB)" for p, src in zip(paths, parsed, strict=True)]
        out = PreviewOut(dry_run=dry_run, status="planned", file=str(target), start=format_seconds(first),
                         end=format_seconds(last), seconds=round(last - first, 3), sources=names)  # fmt: skip
        if dry_run:
            return out
        if not folder.is_dir():
            raise PreconditionFailedError("the workspace has no previews/ folder: run cubase_workspace init",
                                          code="NO_WORKSPACE", details={"path": str(folder)})  # fmt: skip
        placed = [(path, src.start, src.gain_db) for path, src in zip(paths, parsed, strict=True)]
        mix, rate = mix_range(placed, first, last)
        write_audio(target, mix, rate)
        out.levels_db = [range_level_db(path, origin, first, last) for path, origin, _ in placed]
        for label, level in zip(names, out.levels_db, strict=True):
            if level is None or level < SILENT_DBFS:
                out.notes.append(f"{label} is silent in this range: the preview does not show it (TW-1615)")
        peak = float(np.abs(mix).max(initial=0.0))
        out.status, out.peak_dbfs = "done", _peak_db(peak)
        out.notes.append(f"{skill}: listen to it in the Finder (Quick Look) or any player; it is not in the project")
        if peak > 1.0:
            out.notes.append("the preview peaks above 0 dBFS (32-bit float keeps it; lower the volume to listen)")
        return out

    def _render_workspace(self) -> Workspace:
        folder, why = self.project_folder()
        if folder is None:
            raise PreconditionFailedError(
                f"cannot find the workspace: {why}", code="NO_PROJECT_FOLDER", details={"reason": why}
            )
        space = Workspace(folder)
        if not space.exists:
            raise PreconditionFailedError(
                "the project has no Trackwright/ folder yet: create it with cubase_workspace (action 'init')",
                code="NO_WORKSPACE",
                details={"path": str(space.path)},
            )
        return space

    def _list_renders(self) -> RenderOut:
        space = self._render_workspace()
        state = space.load_state()
        out = RenderOut(action="list", dry_run=True, status="listed", workspace=str(space.path))
        for render in renders_of(space):
            item = item_out(render, load_provenance(render))
            owned = state.find("render", f"{RENDERS}/{render.name}")
            uid = owned.details.get("track_uid") if owned is not None else None
            if isinstance(uid, str):
                item.imported_on = uid
                item.track_present = self._uid_present(uid)
            out.renders.append(item)
        if not out.renders:
            out.notes.append("no renders in the workspace")
        return out

    def _uid_present(self, uid: str) -> bool:
        try:
            self.resolve_track(TrackSelector.parse(f"uid:{uid}"))
        except NotFoundError:
            return False
        return True
