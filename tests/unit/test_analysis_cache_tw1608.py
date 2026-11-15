"""TW-1608: analyses tied to an audio version (file identity, project range) and cached by hash."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from trackwright.analysis import cache as cache_module
from trackwright.analysis.cache import AnalysisCache, cache_key, load_cached
from trackwright.core import analyzing
from trackwright.core.models import LoudnessOut
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import NotFoundError
from trackwright.fake import FakeCubase
from trackwright.workspace import Workspace

RATE = 48000


class Launcher:
    def __init__(self, folders: list[str]) -> None:
        self.folders = folders

    def project_folders(self) -> list[str]:
        return self.folders


def write_speechlike(path: Path, *, level: float = 0.3) -> None:
    """2 s tone, 3 s silence, 2 s tone: one silence of 3 s."""
    t = np.arange(2 * RATE) / RATE
    tone = level * np.sin(2 * np.pi * 440 * t)
    signal = np.concatenate([tone, np.zeros(3 * RATE), tone])
    sf.write(path, np.column_stack([signal, signal]), RATE, subtype="FLOAT")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    folder = tmp_path / "E0001"
    (folder / "Mixdown").mkdir(parents=True)
    Workspace(folder).create()
    return folder


@pytest.fixture
def export(project: Path) -> Path:
    path = project / "Mixdown" / "voice.wav"
    write_speechlike(path)
    return path


def make(fake: FakeCubase, project: Path | None, *, workspace: bool = True) -> CubaseService:
    return CubaseService(
        fake,
        WritePolicy(analysis=True, workspace=workspace),
        launcher=Launcher([str(project)] if project else []),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------- the cache module
def test_keys() -> None:
    sha = "a" * 64
    key = cache_key("silences", sha, {"min_seconds": 2.0, "start": 0.0})
    assert key.startswith("silences-")
    assert key == cache_key("silences", sha, {"start": 0.0, "min_seconds": 2.0})  # order does not matter
    assert key != cache_key("silences", sha, {"min_seconds": 2.5, "start": 0.0})
    assert key != cache_key("speech", sha, {"min_seconds": 2.0, "start": 0.0})
    assert key != cache_key("silences", "b" * 64, {"min_seconds": 2.0, "start": 0.0})


def test_hashes_are_remembered_by_size_and_mtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "analysis"
    folder.mkdir()
    audio = tmp_path / "a.wav"
    write_speechlike(audio)
    cache = AnalysisCache(folder, writable=True)
    first = cache.identify(audio)
    assert first.sha256 == hashlib.sha256(audio.read_bytes()).hexdigest()
    assert json.loads((folder / "hashes.json").read_text())[str(audio)]["sha256"] == first.sha256

    def no_hashing(_path: Path) -> str:
        raise AssertionError("hashed again")

    monkeypatch.setattr(cache_module, "_sha256", no_hashing)
    assert cache.identify(audio) == first
    monkeypatch.undo()
    stat = audio.stat()
    os.utime(audio, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))  # touched: hashed again
    assert cache.identify(audio).modified_ns == stat.st_mtime_ns + 1_000_000_000


def test_read_only_and_broken_entries(tmp_path: Path) -> None:
    folder = tmp_path / "analysis"
    folder.mkdir()
    audio = tmp_path / "a.wav"
    write_speechlike(audio)
    read_only = AnalysisCache(folder, writable=False)
    read_only.identify(audio)
    assert read_only.put("k", {"x": 1}) is None
    assert list(folder.iterdir()) == []
    (folder / "hashes.json").write_text("[1, 2]")
    assert read_only.identify(audio).size == audio.stat().st_size
    for name, text in (("bad", "{"), ("old", '{"version": 0, "result": {}}'), ("flat", '{"version": 1, "result": 3}')):
        (folder / f"{name}.json").write_text(text)
        assert read_only.get(name) is None
    (folder / "wrong.json").write_text('{"version": 1, "result": {"file": "x"}}')
    assert load_cached(read_only, "wrong", LoudnessOut) is None  # no longer validates: computed again
    assert AnalysisCache(None, writable=True).get("x") is None
    assert AnalysisCache(tmp_path / "missing", writable=True).writable is False


# ---------------------------------------------------------------- through the tools
def test_silences_are_cached_and_paged(
    fake: FakeCubase, project: Path, export: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    svc = make(fake, project)
    first = svc.analyze_audio(str(export), start="10", min_seconds=1.0)
    assert (first.cache, first.total) == ("stored", 1)
    assert first.source is not None
    assert first.source.sha256 == hashlib.sha256(export.read_bytes()).hexdigest()
    assert (first.source.start, first.source.end, first.source.end_seconds) == ("0:00:10.000", "0:00:17.000", 17.0)
    assert first.source.project_saved_after is None  # no .cpr in the folder
    cached = list((project / "Trackwright" / "analysis").glob("silences-*.json"))
    assert len(cached) == 1

    def not_again(_path: Path) -> object:
        raise AssertionError("measured again")

    monkeypatch.setattr(analyzing, "measure", not_again)
    again = svc.analyze_audio(str(export), start="10", min_seconds=1.0, offset=1)
    assert (again.cache, again.total, again.silences) == ("hit", 1, [])
    assert again.source == first.source
    monkeypatch.undo()
    other = svc.analyze_audio(str(export), start="10", min_seconds=0.5)
    assert other.cache == "stored"
    write_speechlike(export, level=0.2)  # a new export: new bytes, new hash
    assert svc.analyze_audio(str(export), start="10", min_seconds=1.0).cache == "stored"


def test_loudness_and_speech_are_cached(fake: FakeCubase, project: Path, export: Path) -> None:
    svc = make(fake, project)
    assert svc.measure_loudness(str(export)).cache == "stored"
    loud = svc.measure_loudness(str(export))
    assert loud.cache == "hit"
    assert loud.integrated_lufs is not None
    voice = export.with_name("noisy.wav")
    rng = np.random.default_rng(1)
    t = np.arange(2 * RATE) / RATE
    tone = 0.3 * np.sin(2 * np.pi * 440 * t)
    signal = np.concatenate([tone, np.zeros(3 * RATE), tone]) + 0.001 * rng.standard_normal(7 * RATE)
    sf.write(voice, signal, RATE, subtype="FLOAT")
    assert svc.detect_speech(str(voice), start="5").cache == "stored"
    speech = svc.detect_speech(str(voice), start="5", limit=1)
    assert (speech.cache, speech.total, len(speech.regions)) == ("hit", 2, 1)
    assert speech.regions[0].start_seconds == pytest.approx(5.0, abs=0.05)


def test_no_cache_without_permission_or_project(fake: FakeCubase, project: Path, export: Path) -> None:
    out = make(fake, project, workspace=False).analyze_audio(str(export))
    assert out.cache == "off"
    assert out.source is not None
    assert list((project / "Trackwright" / "analysis").iterdir()) == []
    assert make(fake, None).measure_loudness(str(export)).cache == "off"
    with pytest.raises(NotFoundError):
        make(fake, project).measure_loudness(str(project / "missing.wav"))


def test_a_project_saved_after_the_export(fake: FakeCubase, project: Path, export: Path) -> None:
    svc = make(fake, project)
    cpr = project / "E0001.cpr"
    cpr.write_bytes(b"")
    mtime = export.stat().st_mtime
    os.utime(cpr, (mtime - 60, mtime - 60))
    out = svc.analyze_audio(str(export))
    assert out.source is not None
    assert out.source.project_saved_after is False
    os.utime(cpr, (mtime + 60, mtime + 60))
    hit = svc.analyze_audio(str(export))
    assert hit.cache == "hit"
    assert hit.source is not None
    assert hit.source.project_saved_after is True  # checked again on every call, never cached


def test_a_file_of_another_project_is_not_cached_here(fake: FakeCubase, project: Path, tmp_path: Path) -> None:
    elsewhere = tmp_path / "E0002" / "Mixdown"
    elsewhere.mkdir(parents=True)
    other = elsewhere / "voice.wav"
    write_speechlike(other)
    (project / "E0001.cpr").write_bytes(b"")
    out = make(fake, project).analyze_audio(str(other))
    assert out.cache == "off"
    assert out.source is not None
    assert out.source.project_saved_after is None
    assert list((project / "Trackwright" / "analysis").iterdir()) == []
