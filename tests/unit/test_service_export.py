"""TW-1204: exporting the mix with the user (simulated dialog and export folder)."""

from __future__ import annotations

from pathlib import Path

import pytest

from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import PolicyError, PreconditionFailedError, TrackwrightError
from trackwright.exports import ExportInspector
from trackwright.fake import FakeCubase, FakeExports, FakeLauncher


@pytest.fixture
def exports() -> FakeExports:
    return FakeExports()


@pytest.fixture
def exporter(fake: FakeCubase, exports: FakeExports) -> CubaseService:
    return CubaseService(fake, WritePolicy(enabled=True), sleep=lambda _s: None, settle_timeout=0.0,
                         launcher=FakeLauncher(fake), exports=exports)  # type: ignore[arg-type]  # fmt: skip


def test_plan_range_and_whole_project(exporter: CubaseService, fake: FakeCubase) -> None:
    plan = exporter.export_mix("start", start="2", end="30")
    assert (plan.status, plan.expected_seconds, plan.folder) == ("planned", 28.0, "/Projects/Demo/Mixdown")
    whole = exporter.export_mix("start")
    assert whole.expected_seconds is None
    assert fake.fired == []


def test_start_range_opens_the_dialog(exporter: CubaseService, fake: FakeCubase) -> None:
    out = exporter.export_mix("start", start="2", end="30", dry_run=False)
    assert out.status == "awaiting_user"
    assert out.since is not None and out.instructions
    assert (fake.transport["cycleLeft"], fake.transport["cycleRight"]) == ("2. 1. 1.  0", "16. 1. 1.  0")
    assert fake.pending_dialog == "file.export_audio_mixdown"
    assert fake.transport["locator"] == "1. 1. 1.  0"  # cursor back


def test_start_whole_project(exporter: CubaseService, fake: FakeCubase) -> None:
    out = exporter.export_mix("start", dry_run=False)
    assert (out.start, out.end, out.expected_seconds) == ("0:00:00.000", "0:02:19.976", 139.976)


def test_confirm(exporter: CubaseService, exports: FakeExports) -> None:
    exports.add("/Projects/Demo/Mixdown/Demo.mp3", 27.991, modified=1000.0)
    out = exporter.export_mix("confirm", since=999.0, expected_seconds=28.0)
    assert (out.status, out.verified) == ("done", True)
    assert out.files[0].path.endswith("Demo.mp3")
    wrong = exporter.export_mix("confirm", since=999.0, expected_seconds=60.0)
    assert (wrong.status, wrong.verified) == ("done", False)
    none = exporter.export_mix("confirm", since=5000.0, expected_seconds=28.0, folder="~/Elsewhere")
    assert none.status == "not_found"
    assert none.folder is not None and "Elsewhere" in none.folder
    no_duration = exporter.export_mix("confirm", since=999.0)
    assert no_duration.verified is None


def test_confirm_without_known_folder(fake: FakeCubase, exports: FakeExports) -> None:
    service = CubaseService(fake, WritePolicy(enabled=True), exports=exports)  # type: ignore[arg-type]
    out = service.export_mix("confirm", since=1.0)
    assert out.status == "not_found"
    assert out.instructions and "folder" in out.instructions
    with pytest.raises(PreconditionFailedError):
        service.export_mix("confirm")


def test_errors(exporter: CubaseService, fake: FakeCubase) -> None:
    with pytest.raises(PreconditionFailedError):
        exporter.export_mix("start", start="2")
    with pytest.raises(PreconditionFailedError):
        exporter.export_mix("start", start="30", end="2")
    fake.studio_param("transport", "start").value = 1
    with pytest.raises(PreconditionFailedError) as running:
        exporter.export_mix("start", start="2", end="30", dry_run=False)
    assert running.value.code == "TRANSPORT_RUNNING"
    fake.studio_param("transport", "start").value = 0
    fake.can_perform_false.add("file.export_audio_mixdown")
    with pytest.raises(TrackwrightError) as dialog:
        exporter.export_mix("start", start="2", end="30", dry_run=False)
    assert dialog.value.code == "CANNOT_PERFORM"


def test_policy(fake: FakeCubase, exports: FakeExports) -> None:
    service = CubaseService(fake, WritePolicy(), sleep=lambda _s: None, settle_timeout=0.0, exports=exports)  # type: ignore[arg-type]
    with pytest.raises(PolicyError):
        service.export_mix("start", start="2", end="30", dry_run=False)


# ---------------------------------------------------------------- inspector (metadata only)
def test_inspector_reads_only_new_audio_files(tmp_path: Path) -> None:
    old, new, text = tmp_path / "old.wav", tmp_path / "new.MP3", tmp_path / "notes.txt"
    for f in (old, new, text):
        f.write_bytes(b"x" * 10)
    import os

    os.utime(old, (100, 100))
    os.utime(new, (5000, 5000))
    os.utime(text, (5000, 5000))
    calls: list[list[str]] = []

    def afinfo(argv: object) -> str:
        calls.append(list(argv))  # type: ignore[call-overload]
        return "File type ID:   MPG3\nestimated duration: 27.991125 sec\n"

    found = ExportInspector(output=afinfo).find(tmp_path, since=4000)
    assert [(Path(f.path).name, f.size_bytes, f.duration_seconds) for f in found] == [("new.MP3", 10, 27.991125)]
    assert calls == [["/usr/bin/afinfo", str(new)]]
    assert ExportInspector(output=lambda _a: "garbage").duration(new) is None
    assert ExportInspector().find(tmp_path / "missing", 0) == []


def test_lossy_files_get_a_wider_tolerance(exporter: CubaseService, exports: FakeExports) -> None:
    exports.add("/Projects/Demo/Mixdown/Episode.mp3", 139.721, modified=1000.0)  # measured in Cubase
    exports.add("/Projects/Demo/Mixdown/Episode.wav", 139.721, modified=999.5)
    out = exporter.export_mix("confirm", since=999.0, expected_seconds=139.976)
    by_name = {Path(f.path).suffix: f for f in out.files}
    assert (by_name[".mp3"].duration_matches, by_name[".mp3"].difference_seconds) == (True, -0.255)
    assert by_name[".wav"].duration_matches is False
    assert out.verified is True  # the newest file
