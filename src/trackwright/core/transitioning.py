"""Section transitions (TW-1619): where a stinger goes between two sections, read-only.

The voice is an export of the voice tracks (as for ducking), placed in project time by ``voice_start``; the
stinger is a file the user chose (usually from the licensed library). The planner is
:mod:`trackwright.analysis.transitions`.
"""

from __future__ import annotations

import soundfile as sf

from trackwright.analysis import decoded, probe
from trackwright.analysis.transitions import audible_seconds, find_gap, plan_transition
from trackwright.core.analyzing import AnalyzingMixin
from trackwright.core.ducking import DuckingMixin
from trackwright.core.models import TransitionPlanOut
from trackwright.core.timefmt import format_seconds, parse_seconds
from trackwright.errors import NotFoundError, PreconditionFailedError

FAR = 5.0  # seconds: a pause this far from the time asked for is pointed out


class TransitionMixin(DuckingMixin, AnalyzingMixin):
    def transition_plan(
        self,
        voice_file: str,
        at: str,
        stinger_file: str,
        *,
        voice_start: float = 0.0,
        pre_gap: float = 0.3,
        post_gap: float = 0.3,
    ) -> TransitionPlanOut:
        moment = parse_seconds(at)
        if moment is None:
            raise PreconditionFailedError("at looks like '2.5', '1:30' or '0:01:30.000'", code="BAD_TIME")
        speech = self.voice_activity(voice_file)
        regions = [(voice_start + r.start, voice_start + r.end) for r in speech.regions]
        stinger = self._audio_path(stinger_file)
        if not stinger.is_file():
            raise NotFoundError(f"not a file: {stinger}", code="NOT_FOUND")
        with decoded(stinger) as readable:
            info = probe(readable)
            self.policy.check_analysis(info.seconds)
            data, rate = sf.read(str(readable), dtype="float64", always_2d=True)
        audible = audible_seconds(data, rate)
        if audible <= 0:
            raise PreconditionFailedError("the stinger is silent", code="SILENT_SOURCE")
        place = plan_transition(regions, moment, audible, pre_gap=pre_gap, post_gap=post_gap)
        gap = place.gap
        notes: list[str] = []
        far = max(0.0, gap.start - moment, moment - (gap.end if gap.end is not None else gap.start))
        if far > FAR:
            notes.append(f"the nearest pause is {far:.1f} s from {at}: check it is the right place")
        if find_gap(regions, moment).start == 0.0 and regions:
            notes.append("the pause is before the first phrase: the stinger opens the episode")
        if audible < info.seconds - 0.05:
            notes.append(f"the file lasts {info.seconds:.2f} s but its sound ends at {audible:.2f} s: the "
                         "silence after it does not count")  # fmt: skip
        if not place.fits:
            notes.append(f"it does not fit: the tail runs {place.overlap:.2f} s into the next phrase; nothing is "
                         "cut without the user's choice")  # fmt: skip
        before = max(0.0, gap.start - 3.0)
        after = (gap.end if gap.end is not None else place.end) + 3.0
        return TransitionPlanOut(
            at=moment, pause_start=round(gap.start, 3),
            pause_end=round(gap.end, 3) if gap.end is not None else None, start=place.start,
            start_time=format_seconds(place.start), end=place.end, fits=place.fits, overlap=place.overlap,
            stinger_seconds=round(info.seconds, 3), audible_seconds=audible, sample_rate=info.rate,
            options=place.options, preview=[round(before, 2), round(max(after, place.end + 1.0), 2)], notes=notes,
        )  # fmt: skip
