"""TW-1614: the ducking plan tool and the ducked render, on synthetic voice and music."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf

from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import NotFoundError, PreconditionFailedError
from trackwright.fake import FakeCubase
from trackwright.renders import load_provenance
from trackwright.workspace import Workspace

RATE = 48000
SPEECH = [(5.0, 9.0), (20.0, 24.0)]  # seconds of the voice export


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


@pytest.fixture
def voice(project: Path) -> Path:
    """30 s: quiet room noise, with speech-band tone bursts where SPEECH says."""
    rng = np.random.default_rng(7)
    signal = 0.001 * rng.standard_normal(30 * RATE)
    t = np.arange(30 * RATE) / RATE
    for start, end in SPEECH:
        inside = (t >= start) & (t < end)
        signal[inside] += 0.3 * np.sin(2 * np.pi * 300 * t[inside])
    path = project / "Mixdown" / "voices.wav"
    sf.write(path, np.column_stack([signal, signal]), RATE, subtype="FLOAT")
    return path


@pytest.fixture
def music(project: Path) -> Path:
    t = np.arange(30 * RATE) / RATE
    tone = 0.2 * np.sin(2 * np.pi * 220 * t)
    path = project / "Mixdown" / "music.wav"
    sf.write(path, np.column_stack([tone, tone]), RATE, subtype="FLOAT")
    return path


def make(fake: FakeCubase, project: Path) -> CubaseService:
    return CubaseService(fake, WritePolicy(enabled=True, analysis=True, workspace=True),
                         launcher=Launcher([str(project)]))  # type: ignore[arg-type]  # fmt: skip


def test_the_plan(fake: FakeCubase, project: Path, voice: Path) -> None:
    out = make(fake, project).ducking_plan({"voice_file": str(voice), "voice_start": 100.0}, music_start="100")
    assert (out.speech_regions, out.total) == (2, 2)
    first = out.spans[0]
    assert first.start_seconds == pytest.approx(105.0, abs=0.05)  # project time: voice_start + 5 s
    assert first.end_seconds == pytest.approx(109.0 + 0.15 + 0.8, abs=0.06)  # speech hangover + hold
    assert first.depth_db == -10.0
    assert out.parameters["attenuation_db"] == -10.0
    assert out.points == 8


def test_the_plan_keeps_protected_ranges_and_overrides(fake: FakeCubase, project: Path, voice: Path) -> None:
    svc = make(fake, project)
    svc.profile("write_episode", data={"protected": [{"start": 19.0, "end": 26.0}]}, dry_run=False)
    out = svc.ducking_plan({"voice_file": str(voice)})
    assert out.total == 1  # the second phrase is inside the protected range
    assert out.protected == [[19.0, 26.0]]
    held = svc.ducking_plan({"voice_file": str(voice), "use_protected": False,
                             "overrides": [{"start": 9.0, "end": 20.0, "mode": "hold"}]})  # fmt: skip
    assert held.total == 1
    assert held.spans[0].end_seconds > 24.0


def test_the_ducked_render(fake: FakeCubase, project: Path, voice: Path, music: Path) -> None:
    svc = make(fake, project)
    out = svc.render(file=str(music), process="duck", ducking={"voice_file": str(voice), "attenuation_db": -12.0},
                     name="music-ducked", skill="podcast-music-ducking", dry_run=False)  # fmt: skip
    assert out.render is not None
    render = Path(out.render.file)
    ducked, _ = sf.read(render, always_2d=True)
    original, _ = sf.read(music, always_2d=True)

    def ratio_db(t: float) -> float:
        i = round(t * RATE)
        window = slice(i - 240, i + 240)
        return float(20 * np.log10(np.sqrt(np.mean(ducked[window] ** 2)) / np.sqrt(np.mean(original[window] ** 2))))

    assert ratio_db(7.0) == pytest.approx(-12.0, abs=0.01)  # under the voice: exactly the attenuation
    assert ratio_db(22.0) == pytest.approx(-12.0, abs=0.01)
    assert ratio_db(15.0) == pytest.approx(0.0, abs=0.01)  # between the phrases: full level
    assert ratio_db(2.0) == pytest.approx(0.0, abs=0.01)
    # no clicks: the ducked music never jumps from one sample to the next more than the music itself does
    assert np.max(np.abs(np.diff(ducked[:, 0]))) <= np.max(np.abs(np.diff(original[:, 0]))) + 1e-6
    provenance = load_provenance(render)
    params: dict[str, Any] = provenance.parameters
    assert (provenance.process, params["attenuation_db"], params["speech_regions"]) == ("duck", -12.0, 2)
    assert len(params["voice_sha256"]) == 64
    assert params["ducked_spans"] == 2


def test_bad_specifications(fake: FakeCubase, project: Path, voice: Path, music: Path) -> None:
    svc = make(fake, project)
    cases: list[dict[str, Any] | None] = [
        None,
        {"voice_file": str(voice), "attenuation_db": 5},
        {"voice_file": str(voice), "tempo": 1},
        {"voice_file": str(voice), "overrides": [{"start": 5, "end": 4, "mode": "hold"}]},
        {"voice_file": str(voice), "overrides": [{"start": 1, "end": 4, "mode": "depth"}]},
        {"voice_file": "relative.wav"},
    ]
    for spec in cases:
        with pytest.raises(PreconditionFailedError):
            svc.ducking_plan(spec)  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        svc.ducking_plan({"voice_file": str(voice.with_name("nope.wav"))})
    with pytest.raises(PreconditionFailedError) as no_spec:
        svc.render(file=str(music), process="duck", dry_run=False)
    assert no_spec.value.code == "BAD_REQUEST"
    with pytest.raises(PreconditionFailedError) as bad_time:
        svc.ducking_plan({"voice_file": str(voice)}, music_start="soon")
    assert bad_time.value.code == "BAD_TIME"


def test_a_quiet_voice_export_is_noted(fake: FakeCubase, project: Path) -> None:
    flat = project / "Mixdown" / "flat.wav"
    rng = np.random.default_rng(3)
    sf.write(flat, 0.1 * rng.standard_normal((10 * RATE, 1)), RATE)
    out = make(fake, project).ducking_plan({"voice_file": str(flat)})
    assert any("little contrast" in n for n in out.notes)
