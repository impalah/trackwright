"""TW-1203: importing audio with the user (simulated selector, which blocks Cubase while open)."""

from __future__ import annotations

from pathlib import Path

import pytest

from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import PolicyError, PreconditionFailedError, TrackwrightError
from trackwright.fake import FakeCubase, FakeExports, FakeLauncher


@pytest.fixture
def tone(tmp_path: Path) -> Path:
    path = tmp_path / "tono.wav"
    path.write_bytes(b"RIFF")
    return path


@pytest.fixture
def exports(tone: Path) -> FakeExports:
    files = FakeExports()
    files.durations[str(tone)] = 3.0
    return files


@pytest.fixture
def importer(fake: FakeCubase, exports: FakeExports) -> CubaseService:
    return CubaseService(fake, WritePolicy(enabled=True), sleep=lambda _s: None, settle_timeout=0.0,
                         launcher=FakeLauncher(fake), exports=exports)  # type: ignore[arg-type]  # fmt: skip


def edges(fake: FakeCubase) -> list[float]:
    return fake.edges(fake.channel_by_title("POC-TEST").id)


def test_plan(importer: CubaseService, fake: FakeCubase, tone: Path) -> None:
    out = importer.import_audio("start", "POC-TEST", "150", file=str(tone))
    assert (out.status, out.position, out.expected_seconds) == ("planned", "0:02:30.000", 3.0)
    assert "file.import_audio" not in fake.fired


def test_full_flow(importer: CubaseService, fake: FakeCubase, exports: FakeExports, tone: Path) -> None:
    fake.selected = fake.channel_by_title("POC-INSTR").id
    started = importer.import_audio("start", "POC-TEST", "150", file=str(tone), dry_run=False)
    assert started.status == "awaiting_user"
    assert started.instructions and str(tone) in started.instructions and "Cmd+Shift+G" in started.instructions
    assert fake.selected == fake.channel_by_title("POC-TEST").id
    # the selector is open: Cubase does not answer
    waiting = importer.import_audio("confirm", "POC-TEST", "150", file=str(tone), since=started.since)
    assert waiting.status == "awaiting_user"
    fake.finish_import(3.0)
    exports.add("/Projects/Demo/Audio/tono.wav", 3.0, modified=(started.since or 0) + 1)
    done = importer.import_audio("confirm", "POC-TEST", "150", file=str(tone), since=started.since)
    assert (done.status, done.verified) == ("done", True)
    assert done.edges_found == ["0:02:30.000", "0:02:33.000"]
    assert done.copied_to_project == ["tono.wav"]
    assert 150.0 in edges(fake) and 153.0 in edges(fake)


def test_cancelled_import(importer: CubaseService, fake: FakeCubase, tone: Path) -> None:
    started = importer.import_audio("start", "POC-TEST", "150", file=str(tone), dry_run=False)
    fake.finish_import(None)
    out = importer.import_audio("confirm", "POC-TEST", "150", file=str(tone), since=started.since)
    assert (out.status, out.verified) == ("not_found", False)


def test_without_file_only_the_start_is_checked(importer: CubaseService, fake: FakeCubase) -> None:
    started = importer.import_audio("start", "POC-TEST", "150", dry_run=False)
    assert started.instructions and "choose the audio file" in started.instructions
    fake.finish_import(5.0)
    out = importer.import_audio("confirm", "POC-TEST", "150", since=started.since)
    assert (out.status, out.edges_found) == ("done", ["0:02:30.000"])
    assert any("only the start" in n for n in out.notes)


def test_errors(importer: CubaseService, fake: FakeCubase, tmp_path: Path) -> None:
    with pytest.raises(PreconditionFailedError) as missing:
        importer.import_audio("start", "POC-TEST", "150", file=str(tmp_path / "nope.wav"))
    assert missing.value.code == "NOT_FOUND"
    with pytest.raises(PreconditionFailedError):
        importer.import_audio("confirm", "POC-TEST", "150")
    fake.studio_param("transport", "start").value = 1
    with pytest.raises(PreconditionFailedError) as running:
        importer.import_audio("start", "POC-TEST", "150", dry_run=False)
    assert running.value.code == "TRANSPORT_RUNNING"
    fake.studio_param("transport", "start").value = 0
    fake.can_perform_false.add("file.import_audio")
    with pytest.raises(TrackwrightError) as cannot:
        importer.import_audio("start", "POC-TEST", "150", dry_run=False)
    assert cannot.value.code == "CANNOT_PERFORM"


def test_policy(fake: FakeCubase, exports: FakeExports) -> None:
    service = CubaseService(fake, WritePolicy(), sleep=lambda _s: None, settle_timeout=0.0, exports=exports)  # type: ignore[arg-type]
    with pytest.raises(PolicyError):
        service.import_audio("start", "POC-TEST", "150", dry_run=False)
