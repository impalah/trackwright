"""TW-1611: the final QC of an episode file: checks against the delivery profiles, warnings, report."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf

from trackwright.analysis.qc import bitrate_kbps, codec_of, level_changes, loudest_moment, section_levels
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import PolicyError, PreconditionFailedError
from trackwright.fake import FakeCubase
from trackwright.workspace import Workspace

RATE = 48000
SOURCE = {"url": "https://example.org/spec", "retrieved": date(2026, 11, 15)}
LOOSE: dict[str, Any] = {  # a host that accepts this test file
    "title": "Loose host",
    "loudness_lufs": -20.0,
    "loudness_tolerance_lu": 3.0,
    "true_peak_dbtp": -1.0,
    "codecs": ["wav"],
    "channels": ["stereo"],
    "sample_rates": [48000],
    "max_file_mb": 100.0,
    "sources": [{**SOURCE, "covers": ["loudness_lufs", "loudness_tolerance_lu", "true_peak_dbtp", "codecs",
                                      "channels", "sample_rates", "max_file_mb"]}],
}  # fmt: skip


class Launcher:
    def __init__(self, folders: list[str]) -> None:
        self.folders = folders

    def project_folders(self) -> list[str]:
        return self.folders


def tone(seconds: float, level: float, freq: float = 997.0) -> np.ndarray:
    t = np.arange(round(seconds * RATE)) / RATE
    return level * np.sin(2 * np.pi * freq * t)


def episode(path: Path, parts: list[np.ndarray]) -> Path:
    signal = np.concatenate(parts)
    sf.write(path, np.column_stack([signal, signal]), RATE, subtype="FLOAT")
    return path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    folder = tmp_path / "E0001"
    (folder / "Mixdown").mkdir(parents=True)
    Workspace(folder).create()
    return folder


@pytest.fixture
def svc(fake: FakeCubase, project: Path, tmp_path: Path) -> CubaseService:
    service = CubaseService(
        fake,
        WritePolicy(analysis=True, workspace=True),
        launcher=Launcher([str(project)]),  # type: ignore[arg-type]
        shows_dir=tmp_path / "shows",
    )
    service.profile("write_show", show="demo", data={"delivery": {"profiles": {"loose": LOOSE}}}, dry_run=False)
    service.profile("write_episode", data={"show": "demo", "delivery": {"targets": ["loose"]}}, dry_run=False)
    return service


# ---------------------------------------------------------------- the pure helpers
def test_level_changes_between_sections() -> None:
    steps = 600  # 60 s of short-term values every 100 ms
    series = np.full(steps, -20.0)
    series[300:] = -30.0  # 10 LU quieter from about 30 s
    series[100:110] = -80.0  # a pause: does not count
    changes = level_changes(series, -22.0, jump_lu=6.0)
    assert [(c.at, c.before_lufs, c.after_lufs) for c in changes] == [(30.0, -20.0, -30.0)]
    assert changes[0].change_lu == -10.0
    assert level_changes(series, -22.0, jump_lu=12.0) == []
    paused = np.full(200, -20.0)
    paused[100:] = -np.inf  # the second section is mostly digital silence: no level, no change
    assert section_levels(paused, -20.0)[1] is None
    assert level_changes(paused, -20.0) == []
    assert section_levels(np.zeros(0), -20.0) == []
    assert section_levels(series, None) == []


def test_loudest_codec_and_bitrate() -> None:
    series = np.array([-30.0, -10.0, -np.inf, -20.0])
    assert loudest_moment(series) == pytest.approx(0.1 + 1.5)
    assert loudest_moment(np.full(3, -np.inf)) is None
    assert loudest_moment(np.zeros(0)) is None
    assert [codec_of(Path(f"a{s}")) for s in (".WAV", ".mp3", ".m4a", ".xyz")] == ["wav", "mp3", "aac", None]
    assert bitrate_kbps(1_600_000, 100.0, "mp3") == 128.0
    assert bitrate_kbps(1_600_000, 100.0, "wav") is None
    assert bitrate_kbps(1_600_000, 0.0, "mp3") is None


# ---------------------------------------------------------------- the tool
def test_a_file_that_passes(svc: CubaseService, project: Path) -> None:
    path = episode(project / "Mixdown" / "ok.wav", [tone(20, 0.1)])
    out = svc.final_qc(str(path), start="10", expected_seconds=20.0)
    assert (out.verdict, out.failed, out.targets, out.codec) == ("pass", 0, ["loose"], "wav")
    checks = {i.id: i for i in out.items if i.kind == "check"}
    assert checks["loudness"].status == "pass"
    assert checks["loudness"].source == "https://example.org/spec"
    assert checks["duration"].status == "pass"
    assert {i.id for i in out.items if i.kind == "manual"} == {"excluded_tracks", "metadata", "content"}
    assert out.moments[0].at == "0:00:10.000"  # project time
    assert out.source is not None
    assert out.source.start_seconds == 10.0
    assert out.report == []


def test_failures_and_warnings(svc: CubaseService, project: Path) -> None:
    loud, soft = tone(12, 0.9), tone(12, 0.09)  # 20 dB apart
    path = episode(project / "Mixdown" / "bad.wav", [np.zeros(4 * RATE), loud, np.zeros(5 * RATE), soft])
    out = svc.final_qc(str(path), expected_seconds=30.0, targets=["apple", "loose"], long_pause_seconds=3.0)
    assert out.verdict == "fail"
    by = {(i.target, i.id): i for i in out.items}
    assert by[(None, "duration")].status == "fail"
    assert by[("apple", "sample_rate")].status == "pass"
    assert by[("apple", "loudness")].status == "fail"
    assert by[("loose", "codec")].status == "pass"
    assert by[("apple", "codec")].status == "fail"  # WAV is not an RSS codec
    warnings = {i.id for i in out.items if i.kind == "warning"}
    assert {"edge_silence", "long_pauses", "level_changes"} <= warnings
    assert any(m.why.startswith("level change") for m in out.moments)
    assert any(m.why.startswith("pause of") for m in out.moments)


def test_unpublished_values_are_info(svc: CubaseService, project: Path) -> None:
    path = episode(project / "Mixdown" / "s.wav", [tone(10, 0.5)])
    out = svc.final_qc(str(path), targets=["spotify"])
    loudness = next(i for i in out.items if i.id == "loudness")
    assert (loudness.status, loudness.expected) == ("info", "not published by the platform")
    clipped = episode(project / "Mixdown" / "c.wav", [tone(10, 1.0)])
    assert any(i.id == "full_scale" for i in svc.final_qc(str(clipped), targets=[]).items)


def test_the_report(svc: CubaseService, project: Path) -> None:
    path = episode(project / "Mixdown" / "r.wav", [tone(10, 0.1)])
    out = svc.final_qc(str(path), report=True)
    json_path, md_path = (Path(p) for p in out.report)
    assert json_path.parent == project / "Trackwright" / "reports"
    assert json.loads(json_path.read_text())["verdict"] == "pass"
    text = md_path.read_text()
    assert text.startswith("# Final QC: r.wav")
    assert "## Checks" in text
    assert "[-20 ± 3 LUFS](https://example.org/spec)" in text
    assert "## Listen at" in text


def test_refusals(fake: FakeCubase, svc: CubaseService, project: Path, tmp_path: Path) -> None:
    path = episode(project / "Mixdown" / "x.wav", [tone(5, 0.1)])
    for kwargs, code in (
        ({"targets": ["nowhere"]}, "BAD_REQUEST"),
        ({"start": "soon"}, "BAD_TIME"),
        ({"jump_lu": 0}, "BAD_REQUEST"),
    ):
        with pytest.raises(PreconditionFailedError) as exc:
            svc.final_qc(str(path), **kwargs)
        assert exc.value.code == code
    with pytest.raises(PreconditionFailedError):
        svc.final_qc("relative.wav")
    closed = CubaseService(fake, WritePolicy(analysis=True), launcher=Launcher([str(project)]))  # type: ignore[arg-type]
    with pytest.raises(PolicyError) as disabled:
        closed.final_qc(str(path), targets=[], report=True)
    assert disabled.value.code == "WORKSPACE_DISABLED"
    bare = tmp_path / "bare"
    bare.mkdir()
    other = CubaseService(fake, WritePolicy(analysis=True, workspace=True), launcher=Launcher([str(bare)]))  # type: ignore[arg-type]
    with pytest.raises(PreconditionFailedError) as missing:
        other.final_qc(str(path), targets=[], report=True)
    assert missing.value.code == "NO_WORKSPACE"
    nowhere = CubaseService(fake, WritePolicy(analysis=True, workspace=True), launcher=Launcher([]))  # type: ignore[arg-type]
    with pytest.raises(PreconditionFailedError) as unknown:
        nowhere.final_qc(str(path), targets=[], report=True)
    assert unknown.value.code == "NO_PROJECT_FOLDER"
    out = nowhere.final_qc(str(path), targets=[])
    assert out.notes[0].startswith("no delivery targets")
