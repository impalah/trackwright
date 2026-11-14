"""Write and navigation tools (E06) against the simulator."""

from __future__ import annotations

import pytest

from trackwright.core.service import CubaseService
from trackwright.core.writing import bars_tuple, format_bars
from trackwright.errors import (
    NotFoundError,
    PolicyError,
    PreconditionFailedError,
    RequestTimeoutError,
)
from trackwright.fake import FakeCubase

STUDIO_EQ = "946051208E29496E804F64A825C8A047"
WRITE_OPS = {"da.param.set", "da.param.setDisplay", "pm.set", "sel.step", "transport.setTime", "transport.setTempo"}


def write_calls(fake: FakeCubase) -> list[str]:
    return [op for op, _ in fake.calls if op in WRITE_OPS or op == "cmd.run"]


# ---------------------------------------------------------------- helpers
@pytest.mark.parametrize(
    ("text", "expected"),
    [("3. 1. 1.  0", (3, 1, 1, 0)), ("3.1.1.0", (3, 1, 1, 0)), (" 12. 4. 2. 119 ", (12, 4, 2, 119)), ("3.1", None)],
)
def test_bars_tuple(text: str, expected: tuple[int, int, int, int] | None) -> None:
    assert bars_tuple(text) == expected


def test_format_bars_matches_cubase() -> None:
    assert format_bars((1, 1, 1, 0)) == "1. 1. 1.  0"
    assert format_bars((3, 2, 4, 120)) == "3. 2. 4.120"


# ---------------------------------------------------------------- set_parameter
def test_set_parameter_dry_run_writes_nothing(service: CubaseService, fake: FakeCubase) -> None:
    out = service.set_parameter("POC-TEST", "channel", 1025, 0.5)
    assert out.dry_run is True
    assert out.changes[0].before.display == "0.79"
    assert out.changes[0].requested == 0.5
    assert out.verified is None
    assert write_calls(fake) == []


def test_set_parameter_apply_and_verify(service: CubaseService, fake: FakeCubase) -> None:
    out = service.set_parameter("POC-TEST", "channel", 1025, 0.5, dry_run=False)
    assert out.verified is True
    assert out.changes[0].after is not None
    assert out.changes[0].after.process == 0.5
    assert fake.channel_by_title("POC-TEST").params[1025].value == 0.5


def test_set_parameter_plain_units(service: CubaseService) -> None:
    service.insert_plugin("POC-TEST", 1, STUDIO_EQ, dry_run=False)
    out = service.set_parameter("POC-TEST", "insert:1", 4207, 3.0, unit="plain", dry_run=False)
    assert out.changes[0].requested == pytest.approx(0.5625)
    assert out.verified is True


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"value": 1.5}, "OUT_OF_RANGE"),
        ({"value": 30.0, "unit": "plain"}, "OUT_OF_RANGE"),
        ({"value": 0.5, "unit": "decibels"}, "BAD_REQUEST"),
        ({"value": 0.5, "expect_title": "Pan"}, "PRECONDITION_FAILED"),
    ],
)
def test_set_parameter_rejections(service: CubaseService, kwargs: dict[str, object], code: str) -> None:
    with pytest.raises(PreconditionFailedError) as exc:
        service.set_parameter("POC-TEST", "channel", 1025, dry_run=False, **kwargs)  # type: ignore[arg-type]
    assert exc.value.code == code


def test_set_parameter_locked(service: CubaseService, fake: FakeCubase) -> None:
    original = fake._describe_param
    fake._describe_param = lambda obj, tag: {**original(obj, tag), "editLock": True}  # type: ignore[method-assign]
    with pytest.raises(PreconditionFailedError) as exc:
        service.set_parameter("POC-TEST", "channel", 1025, 0.5)
    assert exc.value.code == "PARAM_LOCKED"


def test_set_parameter_policy(readonly: CubaseService, fake: FakeCubase) -> None:
    assert readonly.set_parameter("POC-TEST", "channel", 1025, 0.5).dry_run is True
    with pytest.raises(PolicyError) as exc:
        readonly.set_parameter("POC-TEST", "channel", 1025, 0.5, dry_run=False)
    assert exc.value.code == "WRITES_DISABLED"
    assert write_calls(fake) == []


def test_set_parameter_allowed_tracks(fake: FakeCubase) -> None:
    from trackwright.core.policy import WritePolicy

    service = CubaseService(fake, WritePolicy(enabled=True, allowed_tracks=("POC-TEST",)))
    service.set_parameter("POC-TEST", "channel", 1027, 1, dry_run=False)
    with pytest.raises(PolicyError) as exc:
        service.set_parameter("POC-INSTR", "channel", 1027, 1, dry_run=False)
    assert exc.value.code == "NOT_ALLOWED"


def test_set_parameter_timeout_reads_back_and_does_not_retry(service: CubaseService, fake: FakeCubase) -> None:
    fake.fail_next["da.param.set"] = RequestTimeoutError("late", outcome_unknown=True)
    with pytest.raises(RequestTimeoutError) as exc:
        service.set_parameter("POC-TEST", "channel", 1025, 0.5, dry_run=False)
    assert exc.value.details["read_back"]["title"] == "Volumen"
    assert write_calls(fake) == ["da.param.set"]


def test_set_parameter_timeout_read_back_failure(service: CubaseService, fake: FakeCubase) -> None:
    fake.fail_next["da.param.set"] = RequestTimeoutError("late", outcome_unknown=True)
    original = service.read_parameter
    calls = {"n": 0}

    def flaky(object_id: int, tag: int) -> dict[str, object]:
        calls["n"] += 1
        if calls["n"] > 1:
            raise NotFoundError("gone")
        return original(object_id, tag)

    service.read_parameter = flaky  # type: ignore[method-assign]
    with pytest.raises(RequestTimeoutError) as exc:
        service.set_parameter("POC-TEST", "channel", 1025, 0.5, dry_run=False)
    assert "gone" in exc.value.details["read_back_error"]


def test_set_parameter_unverified(service: CubaseService, fake: FakeCubase) -> None:
    original = fake._op_da_param_set
    fake._op_da_param_set = lambda p: {**original(p), "after": {"process": 0.1, "display": "x"}}  # type: ignore[method-assign]
    out = service.set_parameter("POC-TEST", "channel", 1025, 0.5, dry_run=False)
    assert out.verified is False
    assert out.note is not None


# ---------------------------------------------------------------- track mix
def test_set_track_mix_on_unselected_track(service: CubaseService, fake: FakeCubase) -> None:
    out = service.set_track_mix("POC-INSTR", volume=0.75, mute=True, solo=True, record_arm=True, dry_run=False)
    assert out.verified is True
    assert [c.tag for c in out.changes] == [1025, 1027, 1028, 4002]
    instr = fake.channel_by_title("POC-INSTR")
    assert instr.params[1027].value == 1
    assert fake.selected != instr.id
    restored = service.set_track_mix("POC-INSTR", volume=0.7890865802764893, mute=False, solo=False, dry_run=False)
    assert restored.verified is True


def test_set_track_mix_dry_run_and_errors(service: CubaseService, fake: FakeCubase) -> None:
    assert service.set_track_mix("POC-INSTR", mute=True).dry_run is True
    assert write_calls(fake) == []
    with pytest.raises(PreconditionFailedError, match="at least one"):
        service.set_track_mix("POC-INSTR")
    with pytest.raises(PreconditionFailedError) as exc:
        service.set_track_mix("POC-INSTR", volume=2)
    assert exc.value.code == "OUT_OF_RANGE"


# ---------------------------------------------------------------- rename
def test_rename_track(service: CubaseService, fake: FakeCubase) -> None:
    uid = fake.channel_by_title("POC-INSTR").uid
    assert service.rename_track("POC-INSTR", "Keys").dry_run is True
    out = service.rename_track("POC-INSTR", "Keys", dry_run=False)
    assert out.verified is True
    assert uid in (out.note or "")
    assert service.list_inserts(f"uid:{uid}").track.name == "Keys"


def test_rename_track_rejections(service: CubaseService) -> None:
    with pytest.raises(PreconditionFailedError) as conflict:
        service.rename_track("POC-INSTR", "POC-TEST")
    assert conflict.value.code == "NAME_CONFLICT"
    with pytest.raises(PreconditionFailedError):
        service.rename_track("POC-INSTR", "   ")


# ---------------------------------------------------------------- plugins
def test_insert_plugin(service: CubaseService, fake: FakeCubase) -> None:
    plan = service.insert_plugin("POC-TEST", 1, STUDIO_EQ)
    assert plan.dry_run is True
    assert plan.plugin_name == "StudioEQ"
    assert write_calls(fake) == []
    out = service.insert_plugin("POC-TEST", 1, STUDIO_EQ, dry_run=False)
    assert out.inserted is True
    assert out.verified is True
    assert out.plugin_ref is not None
    with pytest.raises(PreconditionFailedError) as occupied:
        service.insert_plugin("POC-TEST", 1, STUDIO_EQ)
    assert occupied.value.code == "SLOT_OCCUPIED"


def test_insert_unknown_plugin(service: CubaseService) -> None:
    with pytest.raises(NotFoundError) as exc:
        service.insert_plugin("POC-TEST", 1, "NOPE")
    assert exc.value.code == "PLUGIN_NOT_FOUND"


def test_insert_plugin_timeout(service: CubaseService, fake: FakeCubase) -> None:
    fake.fail_next["pm.set"] = RequestTimeoutError("late", outcome_unknown=True)
    with pytest.raises(RequestTimeoutError) as exc:
        service.insert_plugin("POC-TEST", 1, STUDIO_EQ, dry_run=False)
    assert exc.value.details["read_back"]["type"] == "Slot"


# ---------------------------------------------------------------- selection
def test_select_track_by_selector_and_step(service: CubaseService) -> None:
    out = service.select_track("POC-INSTR")
    assert (out.selected_before, out.selected_after, out.verified) == ("POC-TEST", "POC-INSTR", True)
    step = service.select_track(step="next")
    assert step.selected_after == "POC-TEST"


def test_select_track_is_navigation(readonly: CubaseService) -> None:
    assert readonly.select_track("POC-INSTR").verified is True


def test_select_track_arguments(service: CubaseService, fake: FakeCubase) -> None:
    with pytest.raises(PreconditionFailedError):
        service.select_track()
    with pytest.raises(PreconditionFailedError):
        service.select_track("POC-TEST", "next")
    with pytest.raises(PreconditionFailedError):
        service.select_track(step="up")
    fake.selected = -1
    assert service.select_track(step="next").selected_before is None


# ---------------------------------------------------------------- position and tempo
def test_set_position_bars(service: CubaseService, fake: FakeCubase) -> None:
    out = service.set_position("cursor", "3.1.1.0")
    assert out.requested == "3. 1. 1.  0"
    assert out.verified is True
    assert out.after is not None
    assert fake.transport["locator"] == "3. 1. 1.  0"
    assert service.set_position("cycle_right", "4. 1. 1. 0").verified is True


def test_set_position_seconds(service: CubaseService, fake: FakeCubase) -> None:
    out = service.set_position("cursor", "0:00:02.000", unit="seconds")
    assert out.verified is True
    assert out.note == "cursor at 0:00:02.000 (read back in seconds)"
    assert fake.transport["locator"] == "2. 1. 1.  0"
    assert service.set_position("cursor", "1:30", unit="seconds").requested == "0:01:30.000"


def test_set_locators_in_seconds_go_through_the_cursor(service: CubaseService, fake: FakeCubase) -> None:
    service.set_position("cursor", "5", unit="seconds")
    left = service.set_position("cycle_left", "2", unit="seconds")
    right = service.set_position("cycle_right", "0:00:30", unit="seconds")
    assert (left.verified, right.verified) == (True, True)
    assert (fake.transport["cycleLeft"], fake.transport["cycleRight"]) == ("2. 1. 1.  0", "16. 1. 1.  0")
    assert fake.transport["locator"] == "3. 3. 1.  0"  # the cursor is back at 5 s
    assert fake.fired.count("transport.set_left_locator") == 1


def test_set_position_dry_run_and_errors(service: CubaseService, fake: FakeCubase) -> None:
    assert service.set_position("cursor", "2.1.1.0", dry_run=True).after is None
    assert fake.transport["locator"] == "1. 1. 1.  0"
    for args, kwargs in [
        (("cursor", "bar two"), {}),
        (("cursor", "2s"), {"unit": "seconds"}),
        (("cursor", "2.1.1.0"), {"unit": "beats"}),
        (("punch_in", "2.1.1.0"), {}),
    ]:
        with pytest.raises(PreconditionFailedError):
            service.set_position(*args, **kwargs)  # type: ignore[arg-type]


def test_set_position_not_reached(service: CubaseService, fake: FakeCubase) -> None:
    fake._op_transport_setTime = lambda p: {}  # type: ignore[method-assign]
    assert service.set_position("cursor", "5.1.1.0").verified is False


def test_set_tempo(service: CubaseService, fake: FakeCubase) -> None:
    assert service.set_tempo(100).dry_run is True
    assert fake.tempo == 120
    out = service.set_tempo(100, dry_run=False)
    assert out.verified is True
    assert fake.tempo == 100
    with pytest.raises(PreconditionFailedError):
        service.set_tempo(500)


def test_set_tempo_policy(readonly: CubaseService) -> None:
    with pytest.raises(PolicyError):
        readonly.set_tempo(100, dry_run=False)


def test_wait_until_polls(fake: FakeCubase) -> None:
    from trackwright.core.policy import WritePolicy

    sleeps: list[float] = []
    service = CubaseService(fake, WritePolicy(), sleep=sleeps.append, settle_timeout=0.05)
    values = iter([{"v": 0}, {"v": 0}, {"v": 1}])
    assert service.wait_until(lambda: next(values), lambda d: d["v"] == 1) == {"v": 1}
    assert sleeps == [0.1, 0.1]


def test_step_that_does_not_move_is_not_verified(service: CubaseService, fake: FakeCubase) -> None:
    """TW-1403 (C-14): at the last track 'next' does not move the selection."""
    fake._op_sel_step = lambda _p: {}  # type: ignore[method-assign]
    out = service.select_track(step="next")
    assert out.selected_before == out.selected_after
    assert out.verified is False
