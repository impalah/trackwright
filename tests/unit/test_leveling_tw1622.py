"""TW-1622: dialogue leveling: between people, between segments, never inside one; bounded; rendered."""

from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from trackwright.analysis.leveling import (
    BINS_PER_SECOND,
    Gain,
    LevelingParams,
    curve_db,
    gain_curve,
    gain_points,
    k_power_bins,
    lufs,
    plan_leveling,
    span_power,
)
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import NotFoundError, PreconditionFailedError
from trackwright.fake import FakeCubase
from trackwright.workspace import Workspace

RATE = 48000


def speech(seconds: float, parts: list[tuple[float, float, float]]) -> np.ndarray:
    """Noise floor plus 'speech' (a 300 Hz tone with a syllable rhythm) at given amplitudes."""
    t = np.arange(round(seconds * RATE)) / RATE
    x = 0.0003 * np.random.default_rng(1).standard_normal(len(t))
    for a, b, amp in parts:
        inside = (t >= a) & (t < b)
        x[inside] += amp * np.sin(2 * np.pi * 300 * t[inside]) * (0.75 + 0.25 * np.sin(2 * np.pi * 4 * t[inside]))
    return x


def write(path: Path, x: np.ndarray) -> Path:
    sf.write(path, np.column_stack([x, x]), RATE, subtype="FLOAT")
    return path


def test_power_bins_and_spans(tmp_path: Path) -> None:
    tone = write(tmp_path / "t.wav", speech(4.0, [(1.0, 3.0, 0.5)]))
    bins = k_power_bins(tone)
    assert len(bins) == 4 * BINS_PER_SECOND
    total, count = span_power(bins, BINS_PER_SECOND, 10.0, [(11.0, 13.0)])  # the file starts at 10 s
    assert count == 200
    level = lufs(total / count)
    assert level is not None
    assert -12 < level < -4  # a 0.5 tone on both channels
    assert lufs(0.0) is None
    assert span_power(bins, BINS_PER_SECOND, 0.0, [(10.0, 12.0)]) == (0.0, 0)


def test_gain_points_ramp_in_the_pauses() -> None:
    gains = [Gain(1.0, 4.0, 2.0), Gain(5.0, 8.0, -1.0), Gain(8.0, 9.0, -1.0)]
    points = gain_points(gains, 0.2)
    assert points[0] == (1.0, 2.0)
    assert (4.4, 2.0) in points  # the ramp in the middle of the 4..5 pause
    assert (4.6, -1.0) in points
    xs, ys = gain_curve(gains, 0.2)
    at = curve_db(xs, ys, np.array([0.0, 2.0, 4.5, 6.0, 20.0]))
    assert list(np.round(at, 3)) == [2.0, 2.0, 0.5, -1.0, -1.0]  # held before the first and after the last
    assert list(curve_db(np.zeros(0), np.zeros(0), np.array([1.0]))) == [0.0]
    assert all(b[0] > a[0] for a, b in itertools.pairwise(points))  # touching spans stay ordered


def bins_of(x: np.ndarray, tmp_path: Path, name: str) -> np.ndarray:
    return k_power_bins(write(tmp_path / name, x))


def test_between_people_between_segments_never_inside(tmp_path: Path) -> None:
    host = bins_of(speech(40.0, [(1.0, 9.0, 0.3), (20.0, 30.0, 0.3)]), tmp_path, "host.wav")
    # the guest: 9.5 dB quieter; the second answer another 6 dB quieter, with a whisper inside the first
    guest = bins_of(speech(40.0, [(1.0, 4.0, 0.1), (4.0, 5.0, 0.02), (5.0, 9.0, 0.1), (20.0, 30.0, 0.05)]),
                    tmp_path, "guest.wav")  # fmt: skip
    regions_host = [(1.0, 9.0), (20.0, 30.0)]
    regions_guest = [(1.0, 4.0), (4.0, 5.0), (5.0, 9.0), (20.0, 30.0)]
    voices = [("host", host, BINS_PER_SECOND, 0.0, regions_host), ("guest", guest, BINS_PER_SECOND, 0.0, regions_guest)]
    target, (h, g) = plan_leveling(voices, LevelingParams())
    assert h.loudness_lufs is not None
    assert g.loudness_lufs is not None
    assert target == pytest.approx((h.loudness_lufs + g.loudness_lufs) / 2, abs=0.01)  # the median of two
    assert h.voice_gain_db < 0 < g.voice_gain_db
    assert h.voice_gain_db == pytest.approx(-g.voice_gain_db, abs=0.02)
    assert [s.segment_gain_db for s in h.segments] == [0.0, 0.0]
    first, second = g.segments
    assert (first.start, first.end) == (1.0, 9.0)  # the whisper (4..5) is inside the segment: one gain
    assert second.deviation_db is not None
    assert second.deviation_db < -2
    assert second.segment_gain_db == pytest.approx(-(second.deviation_db + 2.0), abs=0.01)  # the excess only
    assert all(abs(s.gain_db) <= 6.0 for s in g.segments)
    bounded = [s for s in g.segments if "bounded" in s.reason]
    assert bounded  # +4.75 voice gain plus the second segment's own correction goes over 6 dB
    assert bounded[0].gain_db == 6.0


def test_short_segments_and_a_given_target(tmp_path: Path) -> None:
    voice = bins_of(speech(20.0, [(1.0, 9.0, 0.3), (12.0, 13.0, 0.02)]), tmp_path, "v.wav")
    target, (v,) = plan_leveling([("v", voice, BINS_PER_SECOND, 0.0, [(1.0, 9.0), (12.0, 13.0)])],
                                 LevelingParams(target_lufs=-20.0, max_gain_db=12.0))  # fmt: skip
    assert target == -20.0
    laugh = v.segments[1]
    assert laugh.deviation_db is not None
    assert laugh.deviation_db < -10
    assert laugh.segment_gain_db == 0.0  # short: only the voice's gain
    assert laugh.reason.startswith("short")
    assert laugh.gain_db == v.voice_gain_db
    silent = np.zeros(100)
    _, (none,) = plan_leveling([("x", silent, BINS_PER_SECOND, 0.0, [])], LevelingParams())
    assert (none.loudness_lufs, none.voice_gain_db, none.segments) == (None, 0.0, [])
    _, (empty,) = plan_leveling([("x", silent, BINS_PER_SECOND, 0.0, [(0.2, 0.9)])], LevelingParams())
    assert empty.segments[0].reason == "not measurable"


class Launcher:
    def __init__(self, folders: list[str]) -> None:
        self.folders = folders

    def project_folders(self) -> list[str]:
        return self.folders


@pytest.fixture
def project(tmp_path: Path) -> Path:
    folder = tmp_path / "E0001"
    (folder / "Mixdown").mkdir(parents=True)
    Workspace(folder).create()
    return folder


def make(fake: FakeCubase, project: Path) -> CubaseService:
    policy = WritePolicy(enabled=True, analysis=True, workspace=True)
    return CubaseService(fake, policy, launcher=Launcher([str(project)]))  # type: ignore[arg-type]


def test_the_tool_and_the_render(fake: FakeCubase, project: Path) -> None:
    host = write(project / "Mixdown" / "host.wav", speech(40.0, [(2.0, 10.0, 0.3), (20.0, 30.0, 0.3)]))
    guest = write(project / "Mixdown" / "guest.wav", speech(40.0, [(2.0, 10.0, 0.1), (20.0, 30.0, 0.05)]))
    svc = make(fake, project)
    plan = svc.leveling_plan([{"file": str(host), "name": "Host"}, {"file": str(guest), "start": 0.0}])
    h, g = plan.voices
    assert (h.name, g.name) == ("Host", "guest")
    assert g.corrected == 2  # its level is halfway between its two answers: both stray ~3 dB
    assert g.compare
    assert g.level["gains"][0][2] == g.segments[0].gain_db
    assert g.gain_range_db[0] <= g.gain_range_db[1]
    assert any("starting values" in n for n in plan.notes)
    paged = svc.leveling_plan([{"file": str(guest)}], offset=1, limit=1)
    assert len(paged.voices[0].segments) == 1
    assert any("one voice" in n for n in paged.notes)
    done = svc.render(file=str(guest), process="level", level=g.level, name="guest-level", dry_run=False)
    assert done.render is not None
    out, _ = sf.read(done.render.file, always_2d=True)
    src, _ = sf.read(str(guest), always_2d=True)
    for a, b, db in g.level["gains"]:
        mid = round((a + b) / 2 * RATE)
        assert out[mid, 0] == pytest.approx(src[mid, 0] * 10 ** (db / 20), abs=1e-6)
    assert done.render.parameters["ramp"] == 0.2


def test_refusals(fake: FakeCubase, project: Path) -> None:
    svc = make(fake, project)
    with pytest.raises(PreconditionFailedError):
        svc.leveling_plan([])
    with pytest.raises(PreconditionFailedError):
        svc.leveling_plan([{"file": "x", "loud": 1}])
    with pytest.raises(NotFoundError):
        svc.leveling_plan([{"file": str(project / "none.wav")}])
    quiet = write(project / "Mixdown" / "quiet.wav", np.zeros(RATE * 2))
    silent = svc.leveling_plan([{"file": str(quiet)}])
    assert any("no speech" in n for n in silent.notes)
    bads: list[dict[str, object]] = [
        {"gains": []},
        {"gains": [[2.0, 1.0, 0.0]]},
        {"gains": [[0.0, 1.0, 30.0]]},
        {"x": 1},
    ]
    for bad in bads:
        with pytest.raises(PreconditionFailedError):
            svc.render(file=str(quiet), process="level", level=bad)
