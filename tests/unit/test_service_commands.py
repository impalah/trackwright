"""Command tools (E07) against the simulator."""

from __future__ import annotations

import re

import pytest

from trackwright.commands import COMMANDS
from trackwright.core.service import CubaseService
from trackwright.cubase import SCRIPT_PATH
from trackwright.errors import NotFoundError, PolicyError, PreconditionFailedError
from trackwright.fake import FakeCubase


def test_registry_matches_the_script() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    table = source.split("var COMMANDS = [")[1].split("\n]")[0]
    bound = {m[0]: (m[1], m[2]) for m in re.findall(r"\['([\w.]+)', '([^']+)', '([^']+)'\]", table)}
    assert bound == {k: (s.category, s.name) for k, s in COMMANDS.items()}


def test_every_command_has_a_known_class() -> None:
    assert {s.command_class for s in COMMANDS.values()} <= {"direct", "dialog", "confirm", "ui_selection", "unknown"}
    assert COMMANDS["addtrack.audio"].command_class == "dialog"
    assert COMMANDS["project.remove_selected_tracks"].command_class == "confirm"


# ---------------------------------------------------------------- run_command
def test_run_command_dry_run(service: CubaseService, fake: FakeCubase) -> None:
    out = service.run_command("zoom.in")
    assert (out.status, out.dry_run, out.can_perform) == ("planned", True, True)
    assert fake.fired == []


def test_run_command_classes(service: CubaseService, fake: FakeCubase) -> None:
    dialog = service.run_command("addtrack.audio", dry_run=False)
    assert dialog.status == "awaiting_user"
    assert dialog.instructions is not None
    assert fake.pending_dialog == "addtrack.audio"
    selection = service.run_command("edit.copy", dry_run=False)
    assert selection.command_class == "ui_selection"
    assert "selection" in (selection.instructions or "")
    direct = service.run_command("zoom.in", dry_run=False)
    assert (direct.status, direct.verified, direct.instructions) == ("fired", "not_observable", None)


def test_run_command_cannot_perform_and_force(service: CubaseService, fake: FakeCubase) -> None:
    with pytest.raises(PreconditionFailedError) as exc:
        service.run_command("edit.undo", dry_run=False)
    assert exc.value.code == "CANNOT_PERFORM"
    assert service.run_command("edit.undo", dry_run=False, force=True).status == "fired"
    assert fake.fired == ["edit.undo"]


def test_run_command_unknown(service: CubaseService) -> None:
    with pytest.raises(NotFoundError) as exc:
        service.run_command("format.disk")
    assert exc.value.code == "COMMAND_NOT_FOUND"


def test_run_command_policy(readonly: CubaseService, fake: FakeCubase) -> None:
    with pytest.raises(PolicyError):
        readonly.run_command("zoom.in", dry_run=False)
    assert readonly.run_command("project.select_track_prev", dry_run=False).status == "fired"
    assert fake.fired == ["project.select_track_prev"]


# ---------------------------------------------------------------- markers
def test_markers_flow(service: CubaseService, fake: FakeCubase) -> None:
    assert service.markers("add_marker_track").status == "planned"
    created = service.markers("add_marker_track", dry_run=False)
    assert created.verified == "not_observable"
    service.set_position("cursor", "2.1.1.0")
    assert service.markers("insert_at_cursor", dry_run=False).details["cursor"] == "2. 1. 1.  0"
    service.set_position("cursor", "3.1.1.0")
    back = service.markers("locate_prev", dry_run=False)
    assert back.details["cursor_after"] == "2. 1. 1.  0"
    assert back.verified is True
    service.markers("locate_next", dry_run=False)
    assert fake.markers == ["2. 1. 1.  0"]


def test_markers_errors(service: CubaseService, readonly: CubaseService, fake: FakeCubase) -> None:
    with pytest.raises(PreconditionFailedError):
        service.markers("delete_all")
    with pytest.raises(PolicyError):
        readonly.markers("insert_at_cursor", dry_run=False)
    fake.can_perform_false.add("marker.insert")
    with pytest.raises(PreconditionFailedError) as exc:
        service.markers("insert_at_cursor")
    assert exc.value.code == "CANNOT_PERFORM"


# ---------------------------------------------------------------- remove selected tracks
def test_remove_selected_track(service: CubaseService, fake: FakeCubase) -> None:
    plan = service.remove_selected_tracks("POC-TEST")
    assert plan.status == "planned"
    assert plan.details["track"] == "POC-TEST"
    out = service.remove_selected_tracks("POC-TEST", dry_run=False)
    assert (out.status, out.verified) == ("done", True)
    assert [t.name for t in service.list_tracks().tracks] == ["Stereo Out", "POC-INSTR"]


def test_remove_requires_matching_selection(service: CubaseService, fake: FakeCubase) -> None:
    with pytest.raises(PreconditionFailedError) as exc:
        service.remove_selected_tracks("POC-INSTR", dry_run=False)
    assert exc.value.code == "SELECTION_MISMATCH"
    assert fake.fired == []


def test_remove_track_with_events_waits_for_confirmation(service: CubaseService, fake: FakeCubase) -> None:
    fake.channel_by_title("POC-TEST").has_events = True
    out = service.remove_selected_tracks("POC-TEST", dry_run=False)
    assert out.status == "pending_confirmation"
    assert out.verified is False
    fake.confirm_pending_removal()
    assert len(service.list_tracks().tracks) == 2


def test_remove_respects_policy(fake: FakeCubase) -> None:
    from trackwright.core.policy import WritePolicy

    service = CubaseService(fake, WritePolicy(enabled=True, allowed_tracks=("Other",)))
    with pytest.raises(PolicyError):
        service.remove_selected_tracks("POC-TEST", dry_run=False)


# ---------------------------------------------------------------- split at locators
def test_split_at_locators(service: CubaseService, fake: FakeCubase) -> None:
    plan = service.split_at_locators("2.1.1.0", "4.1.1.0")
    assert plan.status == "planned"
    assert "every track" in str(plan.details["warning"])
    out = service.split_at_locators("2.1.1.0", "4.1.1.0", dry_run=False)
    assert out.status == "done"
    assert fake.transport["cycleLeft"] == "2. 1. 1.  0"
    assert fake.transport["cycleRight"] == "4. 1. 1.  0"
    assert fake.fired == ["edit.split_loop"]


def test_split_at_locators_validation(service: CubaseService, fake: FakeCubase) -> None:
    for left, right in [("x", "4.1.1.0"), ("4.1.1.0", "2.1.1.0")]:
        with pytest.raises(PreconditionFailedError):
            service.split_at_locators(left, right)
    fake._op_transport_setTime = lambda p: {}  # type: ignore[method-assign]
    with pytest.raises(PreconditionFailedError) as exc:
        service.split_at_locators("2.1.1.0", "4.1.1.0", dry_run=False)
    assert exc.value.code == "VERIFY_FAILED"
    assert fake.fired == []


def test_split_at_locators_cannot_perform(service: CubaseService, fake: FakeCubase) -> None:
    fake.can_perform_false.add("edit.split_loop")
    with pytest.raises(PreconditionFailedError) as exc:
        service.split_at_locators("2.1.1.0", "4.1.1.0", dry_run=False)
    assert exc.value.code == "CANNOT_PERFORM"


# ---------------------------------------------------------------- add a track with the user
def test_add_track_interactive_group(service: CubaseService, fake: FakeCubase) -> None:
    start = service.add_track_interactive("start", "group", "POC-GROUP")
    assert start.status == "awaiting_user"
    assert "POC-GROUP" in (start.instructions or "")
    assert service.add_track_interactive("confirm", "group", "POC-GROUP").status == "not_found"
    fake.complete_dialog("POC-GROUP")
    done = service.add_track_interactive("confirm", "group", "POC-GROUP")
    assert (done.status, done.verified) == ("done", True)
    assert str(done.details["track"]).startswith("uid:")


def test_add_track_interactive_folder_and_errors(
    service: CubaseService, readonly: CubaseService, fake: FakeCubase
) -> None:
    service.add_track_interactive("start", "folder", "Drums")
    fake.complete_dialog("Drums")
    assert service.add_track_interactive("confirm", "folder", "Drums").verified == "not_observable"
    with pytest.raises(PreconditionFailedError):
        service.add_track_interactive("start", "bus", "x")
    with pytest.raises(PreconditionFailedError):
        service.add_track_interactive("finish", "audio", "x")  # type: ignore[arg-type]
    with pytest.raises(PolicyError):
        readonly.add_track_interactive("start", "audio", "x")
    fake.can_perform_false.add("addtrack.audio")
    with pytest.raises(PreconditionFailedError):
        service.add_track_interactive("start", "audio", "x")


def test_locate_next_without_next_marker_goes_to_end_of_last_event(service: CubaseService, fake: FakeCubase) -> None:
    """Verified on Cubase 15: no next marker -> end of the last event (the audio of POC-TEST ended at bar 70)."""
    fake.last_event_end = "70. 4. 4. 97"
    service.set_position("cursor", "2.1.1.0")
    out = service.markers("locate_next", dry_run=False)
    assert out.details["cursor_after"] == "70. 4. 4. 97"


def test_locate_next_without_events_stays_put(service: CubaseService, fake: FakeCubase) -> None:
    fake.last_event_end = None
    service.set_position("cursor", "2.1.1.0")
    assert service.markers("locate_next", dry_run=False).details["cursor_after"] == "2. 1. 1.  0"


def test_locate_next_prefers_a_marker_before_the_end(service: CubaseService, fake: FakeCubase) -> None:
    fake.markers = ["5. 1. 1.  0"]
    fake.last_event_end = "70. 4. 4. 97"
    service.set_position("cursor", "2.1.1.0")
    assert service.markers("locate_next", dry_run=False).details["cursor_after"] == "5. 1. 1.  0"
