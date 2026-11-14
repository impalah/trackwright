"""TW-1401: every write path honours [writes] enabled, save and allowed_tracks (quality review C-01…C-10)."""

from __future__ import annotations

import pytest

from trackwright.commands import COMMANDS
from trackwright.core.commanding import DEDICATED_TOOLS, NAVIGATION_COMMANDS
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.core.writing import PROTECTED_CHANNEL_TAGS
from trackwright.errors import PolicyError, PreconditionFailedError
from trackwright.fake import FakeCubase
from trackwright.ops import WRITE_OPS


def make(fake: FakeCubase, **policy: object) -> CubaseService:
    return CubaseService(fake, WritePolicy(**policy), sleep=lambda _s: None, settle_timeout=0.0)  # type: ignore[arg-type]


def code_of(exc: pytest.ExceptionInfo[BaseException]) -> str:
    return str(getattr(exc.value, "code", ""))


# ---------------------------------------------------------------- run_command (C-01)
@pytest.mark.parametrize("key", sorted(DEDICATED_TOOLS))
@pytest.mark.parametrize("dry_run", [True, False])
def test_run_command_refuses_keys_with_a_dedicated_tool(fake: FakeCubase, key: str, dry_run: bool) -> None:
    service = make(fake, enabled=True, save=True)
    with pytest.raises(PreconditionFailedError) as exc:
        service.run_command(key, dry_run=dry_run)
    assert code_of(exc) == "USE_DEDICATED_TOOL"
    assert exc.value.details["tool"] == DEDICATED_TOOLS[key]  # type: ignore[attr-defined]
    assert fake.fired == []


def test_file_save_cannot_bypass_the_save_switch(fake: FakeCubase) -> None:
    service = make(fake, enabled=True, save=False)
    with pytest.raises(PreconditionFailedError):
        service.run_command("file.save", dry_run=False)
    assert fake.fired == []


def test_run_command_is_refused_while_allowed_tracks_is_set(fake: FakeCubase) -> None:
    service = make(fake, enabled=True, allowed_tracks=("POC-TEST",))
    with pytest.raises(PolicyError) as exc:
        service.run_command("marker.insert", dry_run=False)
    assert code_of(exc) == "NOT_ALLOWED"
    assert fake.fired == []
    navigation = sorted(NAVIGATION_COMMANDS)[0]
    assert service.run_command(navigation, dry_run=False, force=True).status == "fired"


def test_run_command_needs_writes_enabled(fake: FakeCubase) -> None:
    with pytest.raises(PolicyError) as exc:
        make(fake).run_command("marker.insert", dry_run=False)
    assert code_of(exc) == "WRITES_DISABLED"


def test_confirm_class_status_is_still_described(fake: FakeCubase) -> None:
    status, instructions = make(fake)._status_for(COMMANDS["project.remove_selected_tracks"])
    assert status == "fired"
    assert "confirm" in (instructions or "")


# ---------------------------------------------------------------- range edits (C-02, C-09)
def test_single_track_range_edit_honours_allowed_tracks(fake: FakeCubase) -> None:
    service = make(fake, enabled=True, allowed_tracks=("POC-TEST",))
    with pytest.raises(PolicyError) as exc:
        service.edit_range("2", "30", "delete", track="POC-INSTR", dry_run=False)
    assert code_of(exc) == "NOT_ALLOWED"
    assert exc.value.details["track"] == "POC-INSTR"  # type: ignore[attr-defined]
    assert fake.fired == []


def test_single_track_range_edit_on_an_allowed_track(fake: FakeCubase) -> None:
    service = make(fake, enabled=True, allowed_tracks=("POC-TEST",))
    assert service.edit_range("2", "30", "delete", track="POC-TEST", dry_run=False).applied is True


@pytest.mark.parametrize("call", ["edit_range", "split_at_locators"])
def test_edits_on_every_track_are_refused_with_allowed_tracks(fake: FakeCubase, call: str) -> None:
    service = make(fake, enabled=True, allowed_tracks=("POC-TEST",))
    with pytest.raises(PolicyError) as exc:
        if call == "edit_range":
            service.edit_range("2", "30", "delete_time", dry_run=False)
        else:
            service.split_at_locators("2.1.1.0", "4.1.1.0", dry_run=False)
    assert code_of(exc) == "NOT_ALLOWED"
    assert fake.fired == []


def test_split_at_locators_needs_writes_enabled(fake: FakeCubase) -> None:
    with pytest.raises(PolicyError) as exc:
        make(fake).split_at_locators("2.1.1.0", "4.1.1.0", dry_run=False)
    assert code_of(exc) == "WRITES_DISABLED"


def test_range_edit_on_every_track_clears_the_selection_first(fake: FakeCubase) -> None:
    make(fake, enabled=True).edit_range("2", "30", "delete", verify_track="POC-TEST", dry_run=False)
    assert fake.fired.index("edit.select_none") < fake.fired.index("tool.range")


# ---------------------------------------------------------------- set_parameter on the channel (C-03)
@pytest.mark.parametrize("tag", sorted(PROTECTED_CHANNEL_TAGS))
@pytest.mark.parametrize("dry_run", [True, False])
def test_protected_channel_parameters_are_refused(fake: FakeCubase, tag: int, dry_run: bool) -> None:
    with pytest.raises(PreconditionFailedError) as exc:
        make(fake, enabled=True).set_parameter("POC-TEST", "channel", tag, 0.0, dry_run=dry_run)
    assert code_of(exc) == "READ_ONLY_PARAM"
    assert [op for op, _ in fake.calls if op in WRITE_OPS] == []


# ---------------------------------------------------------------- locators (C-08)
@pytest.mark.parametrize("which", ["cycle_left", "cycle_right"])
def test_locators_need_writes_enabled(fake: FakeCubase, which: str) -> None:
    with pytest.raises(PolicyError) as exc:
        make(fake).set_position(which, "3.1.1.0")
    assert code_of(exc) == "WRITES_DISABLED"


def test_the_cursor_is_navigation(fake: FakeCubase) -> None:
    assert make(fake).set_position("cursor", "3.1.1.0").verified is True


# ---------------------------------------------------------------- removal when Cubase cannot (C-10)
def test_remove_selected_tracks_refuses_when_cubase_cannot(fake: FakeCubase) -> None:
    fake.can_perform_false.add("project.remove_selected_tracks")
    with pytest.raises(PreconditionFailedError) as exc:
        make(fake, enabled=True).remove_selected_tracks("POC-TEST", dry_run=False)
    assert code_of(exc) == "CANNOT_PERFORM"
    assert fake.fired == []
