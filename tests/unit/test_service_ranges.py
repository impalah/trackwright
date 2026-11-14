"""TW-1211: range editing in seconds against the simulator, which models the behaviour seen in Cubase."""

from __future__ import annotations

import pytest

from trackwright.core.policy import WritePolicy
from trackwright.core.project import format_seconds, parse_seconds
from trackwright.core.ranges import compare_edges, expected_edge
from trackwright.core.service import CubaseService
from trackwright.errors import PolicyError, PreconditionFailedError
from trackwright.fake import FakeCubase

ORIGINAL = [0.0, 2.0, 2.4, 6.0, 6.8, 18.0, 22.0, 139.976]


def test_parse_and_format_seconds() -> None:
    assert parse_seconds("2") == 2
    assert parse_seconds("2.5") == 2.5
    assert parse_seconds("1:30") == 90
    assert parse_seconds("0:01:30.250") == 90.25
    assert parse_seconds("dos") is None
    assert format_seconds(90.25) == "0:01:30.250"
    assert format_seconds(3725.5) == "1:02:05.500"


@pytest.mark.parametrize(
    ("action", "edge", "expected"),
    [
        ("delete", 1.0, 1.0), ("delete", 10.0, None), ("delete", 40.0, 40.0),
        ("delete_time", 40.0, 12.0), ("cut_time", 2.0, 2.0),
        ("insert_silence", 1.0, 1.0), ("insert_silence", 2.0, 30.0),
        ("crop", 1.0, None), ("crop", 10.0, 10.0),
    ],
)  # fmt: skip
def test_expected_edge(action: str, edge: float, expected: float | None) -> None:
    assert expected_edge(action, 2.0, 30.0, edge) == expected


def test_compare_edges_respects_truncated_probes() -> None:
    assert compare_edges("delete", 2, 30, ([1.0, 40.0], True), ([1.0, 2.0, 30.0, 40.0], True)) == []
    problems = compare_edges("delete", 2, 30, ([1.0, 40.0], True), ([1.0, 10.0], True))
    assert problems == ["unexpected edge at 0:00:10.000", "missing edge at 0:00:40.000"]
    # a truncated walk only compares up to where both reached
    assert compare_edges("delete_time", 2, 30, ([40.0, 50.0], False), ([12.0], False)) == []


def edges(fake: FakeCubase) -> list[float]:
    return fake.edges(fake.channel_by_title("POC-TEST").id)


def test_dry_run_plans(service: CubaseService, fake: FakeCubase) -> None:
    out = service.edit_range("2", "30", "delete_time", verify_track="POC-TEST")
    assert (out.dry_run, out.start, out.end, out.length_seconds) == (True, "0:00:02.000", "0:00:30.000", 28.0)
    assert "every track" in out.scope
    assert edges(fake) == ORIGINAL
    assert fake.fired == []


@pytest.mark.parametrize(
    ("action", "after"),
    [
        ("delete", [2.0, 30.0, 139.976]),
        ("delete_time", [2.0, 111.976]),
        ("cut_time", [2.0, 111.976]),
        ("insert_silence", [2.0, 30.0, 30.4, 34.0, 34.8, 46.0, 50.0, 167.976]),
        ("crop", [2.0, 2.4, 6.0, 6.8, 18.0, 22.0, 30.0]),
    ],
)
def test_actions_are_applied_and_verified(service: CubaseService, fake: FakeCubase, action: str,
                                          after: list[float]) -> None:  # fmt: skip
    fake.transport["cycleLeft"], fake.transport["cycleRight"] = "5. 1. 1.  0", "6. 1. 1.  0"
    fake.transport["locator"] = "3. 1. 1.  0"
    fake.selected = fake.channel_by_title("POC-INSTR").id
    out = service.edit_range("0:00:02", "30", action, verify_track="POC-TEST", dry_run=False)  # type: ignore[arg-type]
    assert out.applied is True
    assert out.verified is True, out.mismatches
    assert [e for e in edges(fake) if e > 1.0] == after
    assert out.locators == ["2. 1. 1.  0", "16. 1. 1.  0"]
    # the user's state is restored: locators, cursor, selected track, object tool
    assert (fake.transport["cycleLeft"], fake.transport["cycleRight"]) == ("5. 1. 1.  0", "6. 1. 1.  0")
    assert fake.transport["locator"] == "3. 1. 1.  0"
    assert fake.selected == fake.channel_by_title("POC-INSTR").id
    assert fake.tool == "select"
    # the instrument track was edited too (every track in the range)
    assert fake.track_events[fake.channel_by_title("POC-INSTR").id] != [(0.0, 2.0), (2.0, 4.0), (4.0, 6.0), (6.0, 8.0)]
    fake.call("cmd.run", {"key": "edit.undo"})
    assert edges(fake) == ORIGINAL


def test_bars_unit(service: CubaseService, fake: FakeCubase) -> None:
    out = service.edit_range("2. 1. 1. 0", "16. 1. 1. 0", "delete", unit="bars", verify_track="POC-TEST",
                             dry_run=False)  # fmt: skip
    assert (out.start, out.end, out.verified) == ("0:00:02.000", "0:00:30.000", True)


def test_without_verify_track(service: CubaseService, fake: FakeCubase) -> None:
    out = service.edit_range("2", "30", "delete", dry_run=False)
    assert (out.applied, out.verified) == (True, None)
    assert any("not verified" in n for n in out.notes)


def test_mismatch_is_reported(service: CubaseService, fake: FakeCubase) -> None:
    original = fake._apply_edit

    def nothing_happens(key: str) -> bool:
        return True if key == "edit.delete" else original(key)

    fake._apply_edit = nothing_happens  # type: ignore[method-assign]
    out = service.edit_range("2", "30", "delete", verify_track="POC-TEST", dry_run=False)
    assert out.verified is False
    assert "unexpected edge at 0:00:02.400" in out.mismatches


def test_no_range_selection(service: CubaseService, fake: FakeCubase) -> None:
    original = fake._apply_edit
    fake._apply_edit = lambda key: True if key == "edit.select_in_loop" else original(key)  # type: ignore[method-assign]
    with pytest.raises(PreconditionFailedError) as exc:
        service.edit_range("2", "30", "delete", dry_run=False)
    assert exc.value.code == "NO_RANGE_SELECTION"
    assert fake.tool == "select"
    assert edges(fake) == ORIGINAL


def test_dialog_is_noticed(service: CubaseService, fake: FakeCubase) -> None:
    original = fake._apply_edit

    def with_dialog(key: str) -> bool:
        done = original(key)
        if key == "edit.delete":
            fake.pending_dialog = "process.silence"
        return done

    fake._apply_edit = with_dialog  # type: ignore[method-assign]
    out = service.edit_range("2", "30", "delete", dry_run=False)
    assert any("dialog" in n for n in out.notes)


@pytest.mark.parametrize(
    ("args", "code"),
    [
        (("30", "2", "delete"), "BAD_TIME"),
        (("dos", "30", "delete"), "BAD_TIME"),
        (("2", "30", "explode"), "BAD_REQUEST"),
    ],
)
def test_validation(service: CubaseService, args: tuple[str, str, str], code: str) -> None:
    with pytest.raises(PreconditionFailedError) as exc:
        service.edit_range(*args)  # type: ignore[arg-type]
    assert exc.value.code == code


def test_bad_units(service: CubaseService) -> None:
    with pytest.raises(PreconditionFailedError):
        service.edit_range("2", "30", "delete", unit="beats")
    with pytest.raises(PreconditionFailedError):
        service.edit_range("dos", "3", "delete", unit="bars")


def test_policy_and_running_transport(fake: FakeCubase) -> None:
    readonly = CubaseService(fake, WritePolicy(), sleep=lambda _s: None, settle_timeout=0.0)
    with pytest.raises(PolicyError):
        readonly.edit_range("2", "30", "delete", dry_run=False)
    service = CubaseService(fake, WritePolicy(enabled=True), sleep=lambda _s: None, settle_timeout=0.0)
    fake.studio_param("transport", "start").value = 1
    with pytest.raises(PreconditionFailedError) as exc:
        service.edit_range("2", "30", "delete", dry_run=False)
    assert exc.value.code == "TRANSPORT_RUNNING"


def test_probe_truncates(service: CubaseService, fake: FakeCubase, monkeypatch: pytest.MonkeyPatch) -> None:
    from trackwright.core import ranges

    monkeypatch.setattr(ranges, "MAX_EDGES", 3)
    out = service.edit_range("2", "30", "delete_time", verify_track="POC-TEST", dry_run=False)
    assert out.verified is True, out.mismatches
    assert len(out.edges_before) == 3


# ---------------------------------------------------------------- one track (TW-1212)
def test_single_track_delete(service: CubaseService, fake: FakeCubase) -> None:
    instr = fake.channel_by_title("POC-INSTR").id
    instr_before = list(fake.track_events[instr])
    fake.transport["locator"] = "3. 1. 1.  0"
    fake.selected = instr
    plan = service.edit_range("2", "30", "delete", track="POC-TEST")
    assert (plan.dry_run, plan.track, plan.scope) == (True, "POC-TEST", "only the track POC-TEST")
    out = service.edit_range("2", "30", "delete", track="POC-TEST", dry_run=False)
    assert out.verified is True, out.mismatches
    assert edges(fake) == [0.0, 2.0, 30.0, 139.976]
    assert fake.track_events[instr] == instr_before  # the other track is untouched
    assert out.undo_steps == 2 + 4  # two splits; four deletions (the hidden 2.0-2.4 piece needs a second round)
    assert any("Undo steps" in n for n in out.notes)
    assert (fake.transport["locator"], fake.selected, fake.tool) == ("3. 1. 1.  0", instr, "select")
    for _ in range(out.undo_steps):
        fake.call("cmd.run", {"key": "edit.undo"})
    assert edges(fake) == ORIGINAL


def test_single_track_only_deletes(service: CubaseService) -> None:
    with pytest.raises(PreconditionFailedError) as exc:
        service.edit_range("2", "30", "delete_time", track="POC-TEST")
    assert "out of sync" in str(exc.value)


def test_single_track_stops_when_a_split_fails(service: CubaseService, fake: FakeCubase) -> None:
    fake._split_selected = lambda at: None  # type: ignore[method-assign]
    with pytest.raises(PreconditionFailedError) as exc:
        service.edit_range("3", "30", "delete", track="POC-TEST", dry_run=False)
    assert exc.value.code == "SPLIT_FAILED"
    assert edges(fake) == ORIGINAL  # nothing was deleted


def test_single_track_range_without_events(service: CubaseService, fake: FakeCubase) -> None:
    out = service.edit_range("200", "210", "delete", track="POC-TEST", dry_run=False)
    assert (out.applied, out.verified, out.undo_steps) == (True, True, 0)


def test_range_mode_reports_one_undo_step(service: CubaseService) -> None:
    assert service.edit_range("2", "30", "delete", dry_run=False).undo_steps == 1


def test_single_track_without_auto_select(service: CubaseService, fake: FakeCubase) -> None:
    fake.auto_select_under_cursor = False
    out = service.edit_range("2", "30", "delete", track="POC-TEST", dry_run=False)
    assert out.verified is True, out.mismatches
    assert edges(fake) == [0.0, 2.0, 30.0, 139.976]


def test_bad_end_in_bars_puts_the_cursor_back(service: CubaseService, fake: FakeCubase) -> None:
    """TW-1403 (C-12): converting the start moves the cursor; a bad end must not leave it there."""
    before = fake.transport["locator"]
    with pytest.raises(PreconditionFailedError) as exc:
        service.edit_range("5. 1. 1. 0", "nonsense", "delete", unit="bars")
    assert exc.value.code == "BAD_TIME"
    assert fake.transport["locator"] == before


def test_export_converts_the_range_once(service: CubaseService, fake: FakeCubase) -> None:
    """TW-1403 (C-27): the apply step reuses the seconds computed for the plan."""
    service.export_mix("start", start="2. 1. 1. 0", end="4. 1. 1. 0", unit="bars", dry_run=False)
    bars_moves = [p for op, p in fake.calls if op == "transport.setTime" and p.get("display") == "primary"]
    assert len(bars_moves) == 2  # start and end, once each
