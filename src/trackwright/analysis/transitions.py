"""Section transitions (TW-1619): where a stinger goes between two sections without covering any speech.

Pure functions, in project seconds. The user gives an approximate time (the API cannot read markers); the
transition goes in the pause between speech nearest to it:

- it starts ``pre_gap`` after the **end of the last phrase** before the pause, never earlier, so the phrase
  is never covered;
- it must end, **tail included** (the stinger's audible length, not its file length), ``post_gap`` before the
  next phrase;
- when it does not fit, the plan says by how much and what can be done: open the pause (insert silence before
  the next section), fade the tail out under the voice, or choose a shorter stinger. Nothing is cut silently.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

Span = tuple[float, float]


@dataclass(frozen=True, slots=True)
class Gap:
    start: float
    """End of the last phrase before the pause."""
    end: float | None
    """Start of the next phrase (None: no more speech)."""

    @property
    def seconds(self) -> float | None:
        return None if self.end is None else self.end - self.start


@dataclass(frozen=True, slots=True)
class Placement:
    gap: Gap
    start: float
    """Where the stinger starts (project seconds)."""
    end: float
    """Where its audible tail ends."""
    fits: bool
    overlap: float
    """Seconds the tail (plus the post gap) would run into the next phrase; 0 when it fits."""
    options: list[str] = field(default_factory=list)


def find_gap(regions: Sequence[Span], at: float, *, min_gap: float = 0.3) -> Gap:
    """The pause between speech nearest to ``at`` (containing it when ``at`` falls in one)."""
    spans = sorted(regions)
    gaps: list[Gap] = []
    if not spans or spans[0][0] > min_gap:
        gaps.append(Gap(0.0, spans[0][0] if spans else None))
    for (_, end), (start, _) in itertools.pairwise(spans):
        if start - end >= min_gap:
            gaps.append(Gap(end, start))
    if spans:
        gaps.append(Gap(spans[-1][1], None))

    def distance(gap: Gap) -> float:
        if gap.start <= at and (gap.end is None or at <= gap.end):
            return 0.0
        return gap.start - at if at < gap.start else at - (gap.end if gap.end is not None else gap.start)

    return min(gaps, key=distance)


def plan_transition(
    regions: Sequence[Span],
    at: float,
    stinger_seconds: float,
    *,
    pre_gap: float = 0.3,
    post_gap: float = 0.3,
) -> Placement:
    """Where a stinger of audible length ``stinger_seconds`` goes in the pause nearest to ``at``."""
    if stinger_seconds <= 0:
        raise ValueError("the stinger has no audible length")
    gap = find_gap(regions, at)
    start = gap.start + (pre_gap if gap.start > 0 else 0.0)  # before the first phrase there is none to protect
    end = start + stinger_seconds
    if gap.end is None:
        return Placement(gap, round(start, 3), round(end, 3), True, 0.0)
    overlap = max(0.0, end + post_gap - gap.end)
    options: list[str] = []
    if overlap > 0:
        options = [
            f"open the pause by {overlap:.2f} s: insert silence at {gap.end:.2f} s (cubase_edit_range "
            "insert_silence; every track moves later from there)",
            f"fade the tail out from {gap.end - post_gap - min(1.0, stinger_seconds / 2):.2f} s so it ends before "
            "the next phrase (rendered with process 'clip')",
            f"a stinger of at most {max(0.0, gap.end - post_gap - start):.2f} s",
        ]
    return Placement(gap, round(start, 3), round(end, 3), overlap == 0, round(overlap, 3), options)


AUDIBLE_DB = -60.0


def audible_seconds(data: npt.NDArray[np.float64], rate: int, window: float = 0.01) -> float:
    """Where the sound really ends: the end of the last ``window`` above -60 dBFS (a stinger's tail, without
    the silence a file may carry after it)."""
    x = data.mean(axis=1) if data.ndim == 2 else data
    step = max(1, round(window * rate))
    count = len(x) // step
    if count == 0:
        return 0.0
    rms = np.sqrt(np.mean(x[: count * step].reshape(count, step) ** 2, axis=1))
    loud = np.flatnonzero(rms > 10 ** (AUDIBLE_DB / 20))
    return round(float((loud[-1] + 1) * step / rate), 3) if len(loud) else 0.0


def render_clip(
    data: npt.NDArray[np.float64],
    rate: int,
    *,
    gain_db: float = 0.0,
    trim_end: float | None = None,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
) -> npt.NDArray[np.float64]:
    """A stinger or an effect made ready to place: gain, cut at ``trim_end`` seconds, linear fades at both
    ends (the fade out ends at the new end, so a cut tail dies away instead of stopping)."""
    out = data * 10 ** (gain_db / 20)
    if trim_end is not None:
        out = out[: max(1, round(trim_end * rate))]
    n = len(out)
    fin = min(n, round(fade_in * rate))
    if fin > 0:
        out[:fin] *= np.linspace(0.0, 1.0, fin, endpoint=False)[:, None]
    fout = min(n, round(fade_out * rate))
    if fout > 0:
        out[n - fout :] *= np.linspace(1.0, 0.0, fout)[:, None]
    return out
