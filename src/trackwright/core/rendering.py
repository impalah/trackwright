"""Render processed audio into the project workspace (TW-1606).

A render is made from an export of a track (``cubase_export_mix`` with ``solo``): Python processes it and
writes ``Trackwright/renders/<name>.wav`` with its provenance; the skill then imports it on a new track at
the export's range start (``cubase_import_audio``, which checks the position against the provenance and
records the track as the skill's) and mutes the original track. Reading the source needs ``[analysis]
enabled``; writing the render needs ``[workspace] enabled`` and an existing workspace. Nothing is sent to
Cubase except, with ``track``, reading that track's name and uid.

Processes: ``gain`` (``gain_db``) and ``duck`` (TW-1614: the music under the voice, from a ``ducking``
specification; see :mod:`trackwright.core.ducking`). Other skills (leveling) add theirs here.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from trackwright import __version__
from trackwright.analysis import decoded, probe
from trackwright.core.analyzing import AnalyzingMixin
from trackwright.core.ducking import DuckingMixin, DuckingSpec, parse_spec
from trackwright.core.models import PreviewOut, RenderItemOut, RenderOut
from trackwright.core.refs import TrackSelector
from trackwright.core.timefmt import format_seconds, parse_seconds
from trackwright.errors import NotFoundError, PreconditionFailedError
from trackwright.jsontypes import JsonObject
from trackwright.renders import (
    RENDERS,
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
    render_file,
    renders_of,
    sha256,
    slug,
    write_audio,
    write_provenance,
)
from trackwright.workspace import Workspace


class PreviewSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    start: float = Field(default=0.0, ge=0, description="project time of the file's first sample")
    gain_db: float = Field(default=0.0, ge=-60, le=24)


PROCESSES = ("gain", "duck")
MAX_PREVIEW_SOURCES = 8
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
        source = self._audio_path(file)
        if not source.is_file():
            raise NotFoundError(f"not a file: {source}", code="NOT_FOUND")
        position = parse_seconds(start)
        if position is None:
            raise PreconditionFailedError("start looks like '2.5', '1:30' or '0:01:30.000'", code="BAD_TIME")
        replaced: JsonObject | None = None
        if track is not None:
            info = self.track_info(self.resolve_track(TrackSelector.parse(track)))
            replaced = {"name": info.name, "uid": info.uid}
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
        out = RenderOut(action="render", dry_run=dry_run, status="planned", workspace=str(space.path))
        notes = out.notes
        notes += duck_notes
        if dry_run:
            out.render = RenderItemOut(
                file=str(target), provenance=str(provenance_path(target)), skill=skill, run=run_id,
                process=process, parameters=parameters, position=format_seconds(position),
                position_seconds=position, seconds=round(info_in.seconds, 4), sample_rate=info_in.rate,
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
            _, peak = render_file(readable, target, effect)
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
