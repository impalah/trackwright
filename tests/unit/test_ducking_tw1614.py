"""TW-1614: the ducking planner, from speech regions to the music's gain envelope."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from trackwright.analysis.ducking import DuckingParams, Override, merge, plan, plan_spans, subtract
from trackwright.errors import PreconditionFailedError


def gain(env_points: list[tuple[float, float]], t: float) -> float:
    xs, ys = zip(*env_points, strict=True)
    return float(np.interp(t, xs, ys, left=0.0, right=0.0))


def test_one_phrase() -> None:
    env = plan([(10.0, 12.0)])
    assert env.points == [(9.75, 0.0), (10.0, -10.0), (12.8, -10.0), (14.0, 0.0)]
    assert gain(env.points, 11.0) == -10.0  # exact on the flat part
    assert gain(env.points, 9.875) == pytest.approx(-5.0)  # halfway down the pre-roll
    assert gain(env.points, 13.4) == pytest.approx(-5.0)  # halfway up the recovery
    assert env.ducked_seconds == pytest.approx(2.8)


def test_phrases_are_joined_and_the_music_does_not_pump() -> None:
    close = plan([(10.0, 12.0), (12.5, 14.0)])  # a pause of 0.5 s: one span
    assert len(close.spans) == 1
    breath = plan([(10.0, 12.0), (13.5, 15.0)])  # 1.5 s apart, 0.7 s after the hold: still one (no pumping)
    assert len(breath.spans) == 1
    assert gain(breath.points, 13.0) == -10.0
    apart = plan([(10.0, 12.0), (20.0, 22.0)])
    assert [(s.start, s.end) for s in apart.spans] == [(10.0, 12.8), (20.0, 22.8)]
    assert gain(apart.points, 16.0) == 0.0


def test_hold_free_and_depth_overrides() -> None:
    regions = [(10.0, 12.0), (20.0, 22.0)]
    held = plan(regions, overrides=[Override(12.0, 20.0, "hold")])
    assert len(held.spans) == 1
    assert gain(held.points, 16.0) == -10.0
    freed = plan([(10.0, 30.0)], overrides=[Override(15.0, 16.0, "free")])
    assert gain(freed.points, 15.0) == 0.0  # up all through the free span, ramps outside it
    assert gain(freed.points, 15.5) == 0.0
    assert gain(freed.points, 16.0) == 0.0
    assert gain(freed.points, 13.8) == -10.0  # the duck ends a recovery before the free span
    assert gain(freed.points, 16.25) == -10.0  # and starts again a pre-roll after it
    deep = plan([(10.0, 20.0)], overrides=[Override(14.0, 16.0, "depth", depth_db=-20.0)])
    assert gain(deep.points, 12.0) == -10.0
    assert gain(deep.points, 15.0) == -20.0
    assert gain(deep.points, 18.0) == -10.0
    assert [s.depth_db for s in deep.spans] == [-10.0, -20.0, -10.0]


def test_protected_ranges_keep_the_music_up() -> None:
    env = plan([(10.0, 12.0)], protected=[(5.0, 9.9), (13.0, 20.0)])
    assert gain(env.points, 9.9) == 0.0  # the whole pre-roll comes after the range
    assert gain(env.points, 10.15) == -10.0
    assert gain(env.points, 11.8) == -10.0
    assert gain(env.points, 13.0) == 0.0  # the whole recovery ends where the range starts
    squeezed = plan([(10.0, 10.5)], protected=[(9.0, 9.9), (11.0, 20.0)])
    assert squeezed.points == []  # no room to duck between the two ranges
    inside = plan([(10.0, 20.0)], protected=[(14.0, 15.0)])
    assert [gain(inside.points, t) for t in (14.0, 14.5, 15.0)] == [0.0, 0.0, 0.0]


def test_the_ends_of_the_file() -> None:
    env = plan([(0.1, 2.0), (58.0, 60.0)], total=60.0)
    assert env.points[0] == (0.0, 0.0)  # a shorter fall: there is no room for the whole pre-roll
    assert env.points[1] == (0.1, -10.0)
    assert env.points[-1][0] <= 60.0
    at_zero = plan([(0.0, 1.0)])
    assert at_zero.points[0] == (0.0, -10.0)  # the music starts ducked: nothing before it to jump from
    assert plan([]).points == []


def test_helpers_and_parameters() -> None:
    assert merge([(5, 6), (1, 2), (2.5, 3), (4, 4)], 1.0) == [(1, 3), (5, 6)]
    assert subtract([(0, 10)], [(2, 3), (5, 12)]) == [(0, 2), (3, 5)]
    assert subtract([(0, 1)], [(5, 6)]) == [(0, 1)]
    for bad in (DuckingParams(attenuation_db=5), DuckingParams(hold=-1)):
        with pytest.raises(PreconditionFailedError):
            plan_spans([(1.0, 2.0)], bad)


spans = st.lists(st.tuples(st.floats(0, 300), st.floats(0.05, 20)).map(lambda p: (p[0], p[0] + p[1])), max_size=25)


@settings(max_examples=150, deadline=None)
@given(
    regions=spans,
    protected=st.lists(st.tuples(st.floats(0, 300), st.floats(0.2, 10)).map(lambda p: (p[0], p[0] + p[1])),
                       max_size=3),
    frees=st.lists(st.tuples(st.floats(0, 300), st.floats(0.2, 10)).map(lambda p: (p[0], p[0] + p[1])),
                   max_size=2),
    depth=st.floats(-30, -1),
)  # fmt: skip
def test_envelope_properties(
    regions: list[tuple[float, float]],
    protected: list[tuple[float, float]],
    frees: list[tuple[float, float]],
    depth: float,
) -> None:
    params = DuckingParams(attenuation_db=depth)
    env = plan(regions, params, overrides=[Override(a, b, "free") for a, b in frees], protected=protected)
    times = [t for t, _ in env.points]
    assert times == sorted(times)
    assert len(set(times)) == len(times)
    assert all(depth - 1e-9 <= g <= 0.0 for _, g in env.points)
    grid = np.arange(0.0, 340.0, 0.001)
    curve = env.gain_db(grid)
    # continuous: no step larger than the steepest ramp allows in 1 ms (no clicks); in the file's first
    # pre-roll a word may leave less room for the fall (see test_the_ends_of_the_file)
    steepest = abs(depth) / min(params.pre_roll, params.recovery)
    later = grid >= params.pre_roll
    assert np.max(np.abs(np.diff(curve[later]))) <= steepest * 0.001 + 1e-6
    for hole_start, hole_end in [*protected, *frees]:  # the music is up all through every hole
        inside = (grid >= hole_start) & (grid <= hole_end)
        assert np.all(curve[inside] == 0.0)
    holes = merge([*protected, *frees], 0.0)
    for start, end in regions:  # full depth in the middle of every word outside the holes
        middle = (start + end) / 2
        if all(not (a - params.recovery - params.pre_roll <= middle <= b + params.recovery + params.pre_roll)
               for a, b in holes):  # fmt: skip
            assert env.gain_db(np.array([middle]))[0] == pytest.approx(depth)
