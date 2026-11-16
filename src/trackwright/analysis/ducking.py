"""The ducking planner (TW-1614): from the voice's speech regions to a gain envelope for the music.

Pure functions, in seconds on one time line (project time when the regions are):

1. **Join** speech regions closer than ``merge_gap`` (pauses between phrases) and keep each joined span
   ducked ``hold`` seconds after its last word.
2. **Overrides** from the user: ``hold`` keeps the music down over a span ("do not bring it up between these
   two phrases"), ``free`` leaves it up ("no ducking under the intro"), ``depth`` uses another attenuation.
3. **No pumping** (before the holes of step 4 are cut, so a short ``free`` span is kept): two spans whose
   gap would not let the music come up and go down again (``recovery`` plus
   ``pre_roll``) become one.
4. **Protected ranges** (the episode profile's) and ``free`` spans are never ducked: next to one, the duck
   ends ``recovery`` before it and starts ``pre_roll`` after it, so the music is at full level all through it
   (a duck with no room left is dropped).
5. **Envelope:** the music starts going down ``pre_roll`` before the first word of a span, is at the span's
   depth from that word to the end of its hold, and comes back up over ``recovery``. The envelope is a list of
   (time, gain in dB) points joined by straight lines in dB: continuous everywhere (no clicks), exactly the
   span's depth on its flat part, 0 dB outside the spans.

The defaults are the brainstorm's starting values (-10 dB, 250 ms, 800 ms, 1200 ms, 900 ms), not norms.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import numpy.typing as npt

from trackwright.errors import PreconditionFailedError

DEPTH_RAMP = 0.3  # seconds between two depths inside a span
Span = tuple[float, float]


@dataclass(frozen=True, slots=True)
class DuckingParams:
    attenuation_db: float = -10.0
    pre_roll: float = 0.25
    hold: float = 0.8
    recovery: float = 1.2
    merge_gap: float = 0.9

    def check(self) -> None:
        if not -60.0 <= self.attenuation_db <= 0.0:
            raise PreconditionFailedError("attenuation_db must be between -60 and 0", code="BAD_REQUEST")
        if min(self.pre_roll, self.hold, self.recovery, self.merge_gap) < 0:
            raise PreconditionFailedError("pre_roll, hold, recovery and merge_gap cannot be negative",
                                          code="BAD_REQUEST")  # fmt: skip


@dataclass(frozen=True, slots=True)
class Override:
    start: float
    end: float
    mode: Literal["hold", "free", "depth"]
    depth_db: float | None = None
    """For ``depth``: the attenuation inside the span."""
    note: str = ""


@dataclass(frozen=True, slots=True)
class DuckSpan:
    start: float
    """The first word: the music is at ``depth_db`` from here."""
    end: float
    """The end of the hold: the music starts coming back up."""
    depth_db: float
    fall_from: float
    """Where the music starts going down (``start`` minus the pre-roll, shortened next to a protected range)."""
    rise_to: float
    """Where it is back at full level."""


@dataclass(frozen=True, slots=True)
class Envelope:
    points: list[tuple[float, float]]
    """(seconds, gain in dB), increasing in time; linear in dB between points, 0 dB before and after."""
    spans: list[DuckSpan] = field(default_factory=list)

    @property
    def ducked_seconds(self) -> float:
        return sum(s.end - s.start for s in self.spans)

    def gain_db(self, times: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        if not self.points:
            return np.zeros_like(times)
        xs = np.array([p[0] for p in self.points])
        ys = np.array([p[1] for p in self.points])
        return np.asarray(np.interp(times, xs, ys, left=0.0, right=0.0), dtype=np.float64)


def merge(spans: Iterable[Span], gap: float) -> list[Span]:
    """Sorted spans, joined where the gap between them is shorter than ``gap``."""
    merged: list[Span] = []
    for start, end in sorted(spans):
        if end <= start:
            continue
        if merged and start - merged[-1][1] < gap:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def subtract(spans: Sequence[Span], holes: Sequence[Span]) -> list[Span]:
    """``spans`` without the parts inside ``holes``."""
    result = list(spans)
    for hole_start, hole_end in holes:
        cut: list[Span] = []
        for start, end in result:
            if end <= hole_start or start >= hole_end:
                cut.append((start, end))
                continue
            if start < hole_start:
                cut.append((start, hole_start))
            if end > hole_end:
                cut.append((hole_end, end))
        result = cut
    return result


def plan_spans(
    regions: Sequence[Span],
    params: DuckingParams,
    *,
    overrides: Sequence[Override] = (),
    protected: Sequence[Span] = (),
    total: float | None = None,
) -> list[DuckSpan]:
    """The ducked spans, each with its depth and the reach of its ramps."""
    params.check()
    spans = [(start, end + params.hold) for start, end in merge(regions, params.merge_gap)]
    spans = merge([*spans, *((o.start, o.end) for o in overrides if o.mode == "hold")], 0.0)
    spans = merge(spans, params.recovery + params.pre_roll)  # no pumping
    # Holes: where the music stays up, ramps included: the user's "free" spans and the protected ranges.
    holes = merge([*((o.start, o.end) for o in overrides if o.mode == "free"), *protected], 0.0)
    spans = subtract(spans, holes)
    if total is not None:
        spans = [(max(0.0, s), min(total, e)) for s, e in spans if s < total and e > 0]
    depths = [o for o in overrides if o.mode == "depth"]
    planned: list[DuckSpan] = []
    for span_start, span_end in spans:
        start, end = span_start, span_end
        # Next to a hole the duck itself moves, so that its full ramps fit outside the hole.
        floor, ceiling = 0.0, math.inf
        for hole_start, hole_end in holes:
            if hole_end <= start < hole_end + params.pre_roll:
                start, floor = hole_end + params.pre_roll, hole_end
            if hole_start - params.recovery < end <= hole_start:
                end, ceiling = hole_start - params.recovery, hole_start
        if end <= start:
            continue  # too close to a hole to duck at all
        fall = max(start - params.pre_roll, floor)  # exactly at the hole's edge, not a rounding error inside it
        rise = min(end + params.recovery, ceiling)
        if total is not None:
            rise = min(rise, total)
        if planned and fall < planned[-1].rise_to:  # cannot happen after the no-pumping merge; kept safe
            fall = planned[-1].rise_to
        fall = min(start, max(fall, 0.0))
        planned += _with_depths((start, end), fall, rise, default=params.attenuation_db, depths=depths)
    return planned


def _with_depths(span: Span, fall: float, rise: float, *, default: float, depths: Sequence[Override]) -> list[DuckSpan]:
    """One span, split where a ``depth`` override starts or ends inside it."""
    start, end = span
    cuts = sorted({start, end, *(t for o in depths for t in (o.start, o.end) if start < t < end)})
    pieces = []
    for index, (a, b) in enumerate(itertools.pairwise(cuts)):
        middle = (a + b) / 2
        depth = next((o.depth_db for o in depths if o.start <= middle < o.end and o.depth_db is not None), default)
        pieces.append(DuckSpan(start=a, end=b, depth_db=depth,
                               fall_from=fall if index == 0 else a, rise_to=rise if b == end else b))  # fmt: skip
    return pieces


def envelope(spans: Sequence[DuckSpan]) -> Envelope:
    """The points of the gain curve for ``spans`` (as :func:`plan_spans` returns them)."""
    points: list[tuple[float, float]] = []
    for index, span in enumerate(spans):
        joined = index > 0 and spans[index - 1].end == span.start  # a depth change inside one span
        if joined:
            ramp = min(DEPTH_RAMP, (span.end - span.start) / 2)
            points.append((span.start + ramp, span.depth_db))
        else:
            if span.fall_from < span.start:
                points.append((span.fall_from, 0.0))
            points.append((span.start, span.depth_db))
        nxt = spans[index + 1] if index + 1 < len(spans) else None
        if nxt is not None and nxt.start == span.end:
            points.append((span.end, span.depth_db))
            continue
        points.append((span.end, span.depth_db))
        if span.rise_to > span.end:
            points.append((span.rise_to, 0.0))
    return Envelope(points=_strictly_increasing(points), spans=list(spans))


def _strictly_increasing(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Drop a point at the same time as the one before it (a ramp of zero length): the later wins."""
    out: list[tuple[float, float]] = []
    for time, gain in points:
        if out and time <= out[-1][0]:
            out[-1] = (out[-1][0], gain)
        else:
            out.append((time, gain))  # exact: rounding would move a flat part off its depth
    return out


def plan(
    regions: Sequence[Span],
    params: DuckingParams | None = None,
    *,
    overrides: Sequence[Override] = (),
    protected: Sequence[Span] = (),
    total: float | None = None,
) -> Envelope:
    """Speech regions to the music's gain envelope."""
    params = params or DuckingParams()
    return envelope(plan_spans(regions, params, overrides=overrides, protected=protected, total=total))


def changed_spans(
    before: Envelope, after: Envelope, *, start: float, end: float, step: float = 0.01, tolerance_db: float = 0.05
) -> list[Span]:
    """Where two envelopes differ by more than ``tolerance_db`` between ``start`` and ``end``: the spans an edit
    of the plan changes, to preview and check again (joined across gaps shorter than half a second)."""
    if end <= start:
        return []
    grid = np.arange(start, end + step / 2, step)
    differs = np.abs(before.gain_db(grid) - after.gain_db(grid)) > tolerance_db
    spans: list[Span] = []
    edges = np.flatnonzero(np.diff(np.concatenate([[0], differs.astype(np.int8), [0]])))
    for first, last in zip(edges[::2], edges[1::2], strict=True):
        spans.append((float(grid[first]), float(grid[min(last, len(grid) - 1)])))
    return merge(spans, 0.5)
