"""TW-1202: saving the project (simulated folder; the fake records the command)."""

from __future__ import annotations

import time

import pytest

from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import PolicyError
from trackwright.fake import FakeCubase, FakeExports, FakeLauncher


@pytest.fixture
def exports() -> FakeExports:
    files = FakeExports()
    files.add("/Projects/Demo/Demo.cpr", None, modified=1000.0, size=200)
    files.add("/Projects/Demo/Audio/take.wav", 3.0, modified=1000.0)
    return files


def saver(fake: FakeCubase, exports: FakeExports, *, save: bool = True, launcher: bool = True) -> CubaseService:
    return CubaseService(fake, WritePolicy(enabled=True, save=save), sleep=lambda _s: None, settle_timeout=0.0,
                         launcher=FakeLauncher(fake) if launcher else None, exports=exports)  # type: ignore[arg-type]  # fmt: skip


def test_plan_lists_project_files(fake: FakeCubase, exports: FakeExports) -> None:
    out = saver(fake, exports).save_project()
    assert (out.status, out.folder) == ("planned", "/Projects/Demo")
    assert [f.name for f in out.files_before] == ["Demo.cpr"]
    assert "file.save" not in fake.fired


def test_save_is_verified_by_the_file_date(fake: FakeCubase, exports: FakeExports) -> None:
    original = fake._apply_command

    def write(key: str) -> None:
        if key == "file.save":
            exports.add("/Projects/Demo/Demo.cpr", None, modified=time.time() + 0.5, size=210)
        original(key)

    fake._apply_command = write  # type: ignore[method-assign]
    out = saver(fake, exports).save_project(dry_run=False)
    assert (out.status, out.verified) == ("saved", True)
    assert out.saved is not None and (out.saved.name, out.saved.size_bytes) == ("Demo.cpr", 210)


def test_new_version_needs_a_new_file(fake: FakeCubase, exports: FakeExports, monkeypatch: pytest.MonkeyPatch) -> None:
    from trackwright.core import saving

    monkeypatch.setattr(saving, "SAVE_WAIT_SECONDS", 0.0)
    original = fake._apply_command

    def rewrite_old_only(key: str) -> None:  # an old file touched is not a new version
        exports.add("/Projects/Demo/Demo.cpr", None, modified=time.time() + 0.5)
        original(key)

    fake._apply_command = rewrite_old_only  # type: ignore[method-assign]
    out = saver(fake, exports).save_project("new_version", dry_run=False)
    assert (out.status, out.verified) == ("awaiting_user", False)
    assert out.instructions and "dialog" in out.instructions

    def new_version(key: str) -> None:
        exports.add("/Projects/Demo/Demo-01.cpr", None, modified=time.time() + 0.5)
        original(key)

    fake._apply_command = new_version  # type: ignore[method-assign]
    assert saver(fake, exports).save_project("new_version", dry_run=False).saved.name == "Demo-01.cpr"  # type: ignore[union-attr]


def test_unknown_folder(fake: FakeCubase, exports: FakeExports) -> None:
    out = saver(fake, exports, launcher=False).save_project(dry_run=False)
    assert (out.status, out.verified) == ("saved", None)
    assert any("cannot be verified" in n for n in out.notes)


def test_policy(fake: FakeCubase, exports: FakeExports) -> None:
    with pytest.raises(PolicyError) as exc:
        saver(fake, exports, save=False).save_project(dry_run=False)
    assert exc.value.code == "SAVE_DISABLED"
    no_writes = CubaseService(fake, WritePolicy(save=True), exports=exports)  # type: ignore[arg-type]
    with pytest.raises(PolicyError) as writes:
        no_writes.save_project(dry_run=False)
    assert writes.value.code == "WRITES_DISABLED"
    assert "file.save" not in fake.fired
