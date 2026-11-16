"""Sound effects (TW-1621): what an effect at an approved point lands on and the level it needs, read-only.

The point is the user's (an effect goes where the story needs it, over speech or not); this plan only says
what is there: the speech under it (from the voice export, as for transitions), the effects this skill
placed earlier that it would overlap (from ``state.json`` and their renders' provenance), and a gain that
puts it ``relative_db`` from the voice's typical level. The level is a starting value; the preview decides.
"""

from __future__ import annotations

import soundfile as sf

from trackwright.analysis import decoded, probe
from trackwright.analysis.transitions import active_level_db, audible_seconds, overlaps
from trackwright.core.models import EffectOverlapOut, EffectPlanOut
from trackwright.core.timefmt import format_seconds, parse_seconds
from trackwright.core.transitioning import TransitionMixin
from trackwright.errors import NotFoundError, PreconditionFailedError
from trackwright.renders import load_provenance
from trackwright.workspace import Workspace

SKILL = "podcast-sound-effects"
UNDER_SPEECH_DB = -12.0  # an effect under the voice: well below it (starting value)
IN_A_PAUSE_DB = -3.0  # an effect on its own: near the voice's level (starting value)


class EffectsMixin(TransitionMixin):
    def effect_plan(
        self,
        effect_file: str,
        at: str,
        *,
        voice_file: str | None = None,
        voice_start: float = 0.0,
        relative_db: float | None = None,
    ) -> EffectPlanOut:
        start = parse_seconds(at)
        if start is None:
            raise PreconditionFailedError("at looks like '2.5', '1:30' or '0:01:30.000'", code="BAD_TIME")
        self.policy.check_analysis()
        effect = self._audio_path(effect_file)
        if not effect.is_file():
            raise NotFoundError(f"not a file: {effect}", code="NOT_FOUND")
        with decoded(effect) as readable:
            info = probe(readable)
            self.policy.check_analysis(info.seconds)
            data, rate = sf.read(str(readable), dtype="float64", always_2d=True)
        audible, level = audible_seconds(data, rate), active_level_db(data, rate)
        if audible <= 0 or level is None:
            raise PreconditionFailedError("the effect is silent", code="SILENT_SOURCE")
        end = round(start + audible, 3)
        out = EffectPlanOut(
            start=start, start_time=format_seconds(start), end=end, effect_seconds=round(info.seconds, 3),
            audible_seconds=audible, sample_rate=info.rate, effect_level_db=level, speech_level_db=None,
            relative_db=relative_db, suggested_gain_db=None,
            preview=[round(max(0.0, start - 3.0), 2), round(end + 3.0, 2)],
        )  # fmt: skip
        if voice_file is not None:
            speech = self.voice_activity(voice_file)
            regions = [(voice_start + r.start, voice_start + r.end) for r in speech.regions]
            under = overlaps(regions, start, end)
            out.under_speech = [[round(a, 3), round(b, 3)] for a, b in under]
            out.under_speech_seconds = round(sum(b - a for a, b in under), 3)
            out.speech_level_db = speech.speech_level_db
            if out.relative_db is None:
                out.relative_db = UNDER_SPEECH_DB if under else IN_A_PAUSE_DB
            if speech.speech_level_db is not None:
                out.suggested_gain_db = round(speech.speech_level_db + out.relative_db - level, 1)
            out.notes.append(
                f"it lands on {out.under_speech_seconds:g} s of speech: keep it well under the voice"
                if under
                else "it lands in a pause: nothing is covered"
            )
        else:
            out.notes.append("no voice export: the speech under it and the level against the voice are unknown")
        out.overlaps = self._earlier_effects(start, end)
        if out.overlaps:
            out.notes.append(f"it overlaps {len(out.overlaps)} earlier effect(s) of this skill: on the same track "
                             "the events would overlap; use another effects track or move it")  # fmt: skip
        if audible < info.seconds - 0.05:
            out.notes.append(f"the file lasts {info.seconds:.2f} s but its sound ends at {audible:.2f} s")
        return out

    def _earlier_effects(self, start: float, end: float) -> list[EffectOverlapOut]:
        """This skill's effects already placed (state.json) whose sound overlaps start..end."""
        folder, _ = self.project_folder()
        if folder is None:
            return []
        space = Workspace(folder)
        if not space.exists:
            return []
        found: list[EffectOverlapOut] = []
        for item in space.load_state().owned_by(SKILL, "render"):
            render = space.path / item.key
            position = item.details.get("position")
            if not render.is_file() or not isinstance(position, int | float):
                continue
            seconds = item.details.get("audible_seconds")
            length = float(seconds) if isinstance(seconds, int | float) else load_provenance(render).seconds
            a, b = float(position), float(position) + length
            if a < end and b > start:
                uid = item.details.get("track_uid")
                found.append(EffectOverlapOut(file=str(render), start=round(a, 3), end=round(b, 3),
                                              track_uid=str(uid) if uid else None))  # fmt: skip
        return found
