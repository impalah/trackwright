"""Automation tools (TW-1207) against the simulator, which records touched controls while W is on and playing."""

from __future__ import annotations

import pytest

from trackwright.core import automation
from trackwright.core.automation import from_beats, interpolate, to_beats
from trackwright.core.models import AutomationPoint
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import NotFoundError, PolicyError, PreconditionFailedError, TrackwrightError
from trackwright.fake import FakeCubase

STUDIO_EQ = "946051208E29496E804F64A825C8A047"


def pts(*pairs: tuple[str, float]) -> list[AutomationPoint]:
    return [AutomationPoint(position=p, value=v) for p, v in pairs]


# ---------------------------------------------------------------- helpers
def test_beats_conversion_roundtrip() -> None:
    assert to_beats((1, 1, 1, 0)) == 0
    assert to_beats((3, 2, 1, 0)) == 9
    assert to_beats((1, 1, 3, 0)) == 0.5
    assert from_beats(9.5) == (3, 2, 3, 0)
    assert from_beats(-1) == (1, 1, 1, 0)


def test_interpolate() -> None:
    curve = [(4.0, 0.8), (8.0, 0.4)]
    assert interpolate(curve, 0) == 0.8
    assert interpolate(curve, 6) == pytest.approx(0.6)
    assert interpolate(curve, 20) == 0.4


# ---------------------------------------------------------------- list targets
def test_list_targets_selects_the_track(service: CubaseService, fake: FakeCubase) -> None:
    out = service.list_automation_targets("POC-INSTR")
    assert out.track == "POC-INSTR"
    assert fake.selected == fake.channel_by_title("POC-INSTR").id
    by_key = {t.parameter: t for t in out.targets}
    assert by_key["volume"].title == "POC-INSTR / Volumen"
    assert by_key["volume"].available is True
    assert by_key["qc1"].available is False
    assert by_key["insert1.p1"].available is False  # empty slot


def test_list_targets_with_a_plugin(service: CubaseService) -> None:
    service.insert_plugin("POC-TEST", 1, STUDIO_EQ, dry_run=False)
    targets = {t.parameter: t for t in service.list_automation_targets("POC-TEST").targets}
    assert targets["insert1.p1"].title == "StudioEQ / Param 1"
    assert targets["insert1.p1"].available is True


def test_old_script_without_controls(service: CubaseService, fake: FakeCubase) -> None:
    fake.automation_controls = False
    with pytest.raises(TrackwrightError) as exc:
        service.list_automation_targets("POC-TEST")
    assert exc.value.code == "UNSUPPORTED"


# ---------------------------------------------------------------- record
def test_dry_run_plans_without_playing(service: CubaseService, fake: FakeCubase) -> None:
    out = service.record_automation("POC-TEST", "volume", pts(("3.1.1.0", 0.8), ("5.1.1.0", 0.4)))
    assert out.dry_run is True
    assert out.start == "2. 1. 1.  0"
    assert out.title == "POC-TEST / Volumen"
    assert out.written == []
    assert fake.playing is False
    assert "transport.start" not in fake.fired


def test_record_and_verify_volume_ramp(service: CubaseService, fake: FakeCubase) -> None:
    out = service.record_automation("POC-TEST", "volume", pts(("2.1.1.0", 0.79), ("4.1.1.0", 0.4)), dry_run=False)
    assert out.verified is True, out.mismatches
    assert len(out.written) >= 8
    assert out.written[0].value == pytest.approx(0.79)
    assert out.written[-1].value == pytest.approx(0.4)
    recorded = fake.automation[(fake.channel_by_title("POC-TEST").id, "volume")]
    assert recorded[0][1] == pytest.approx(0.79)
    assert recorded[-1][1] == pytest.approx(0.4)
    # state restored: transport stopped, W/R as before, touch released
    audio = fake.channel_by_title("POC-TEST")
    assert fake.playing is False
    assert (audio.params[4013].value, audio.params[4014].value) == (0, 0)
    assert fake.auto_touched == set()
    assert fake.fired.count("transport.start") == 2  # record + verify
    assert fake.fired.count("transport.stop") == 2


def test_record_without_verify(service: CubaseService, fake: FakeCubase) -> None:
    out = service.record_automation("POC-TEST", "pan", pts(("2.1.1.0", 0.5), ("3.1.1.0", 0.1)),
                                    dry_run=False, verify=False)  # fmt: skip
    assert out.verified is None
    assert fake.fired.count("transport.start") == 1


def test_single_point_is_held(service: CubaseService) -> None:
    out = service.record_automation("POC-TEST", "pan", pts(("2.1.1.0", 0.3)), dry_run=False)
    assert out.verified is True
    assert all(w.value == pytest.approx(0.3) for w in out.written)


def test_previous_flags_are_restored(service: CubaseService, fake: FakeCubase) -> None:
    audio = fake.channel_by_title("POC-TEST")
    audio.params[4014].value = 1  # the user had read automation on
    service.record_automation("POC-TEST", "volume", pts(("2.1.1.0", 0.7), ("3.1.1.0", 0.6)), dry_run=False)
    assert audio.params[4014].value == 1
    assert audio.params[4013].value == 0


def test_verify_reports_mismatches(service: CubaseService, fake: FakeCubase) -> None:
    original = fake._op_auto_control

    def lossy(p: dict[str, object]) -> dict[str, object]:
        out = original(p)
        fake.automation.clear()  # Cubase did not keep anything
        return out

    fake._op_auto_control = lossy  # type: ignore[method-assign]
    out = service.record_automation("POC-TEST", "pan", pts(("2.1.1.0", 0.9), ("3.1.1.0", 0.1)), dry_run=False)
    assert out.verified is False
    assert out.mismatches
    assert any("read-back" in n for n in out.notes)


@pytest.mark.parametrize(
    ("points", "code"),
    [
        ([], "BAD_REQUEST"),
        ([("3.1.1.0", 0.5), ("2.1.1.0", 0.4)], "BAD_TIME"),
        ([("tres", 0.5)], "BAD_TIME"),
    ],
)
def test_point_validation(service: CubaseService, points: list[tuple[str, float]], code: str) -> None:
    with pytest.raises(PreconditionFailedError) as exc:
        service.record_automation("POC-TEST", "volume", pts(*points))
    assert exc.value.code == code


def test_too_many_points(service: CubaseService) -> None:
    many = pts(*((f"{i}.1.1.0", 0.5) for i in range(1, 70)))
    with pytest.raises(PreconditionFailedError):
        service.record_automation("POC-TEST", "volume", many)


def test_unknown_and_unbound_parameters(service: CubaseService) -> None:
    with pytest.raises(NotFoundError) as unknown:
        service.record_automation("POC-TEST", "tempo", pts(("2.1.1.0", 0.5)))
    assert unknown.value.code == "PARAM_NOT_FOUND"
    with pytest.raises(PreconditionFailedError) as unbound:
        service.record_automation("POC-TEST", "qc1", pts(("2.1.1.0", 0.5)))
    assert unbound.value.code == "NOT_AUTOMATABLE"


def test_policy_and_running_transport(fake: FakeCubase) -> None:
    readonly = CubaseService(fake, WritePolicy(), sleep=lambda _s: None, settle_timeout=0.0)
    assert readonly.record_automation("POC-TEST", "volume", pts(("2.1.1.0", 0.5))).dry_run is True
    with pytest.raises(PolicyError):
        readonly.record_automation("POC-TEST", "volume", pts(("2.1.1.0", 0.5)), dry_run=False)
    service = CubaseService(fake, WritePolicy(enabled=True), sleep=lambda _s: None, settle_timeout=0.0)
    fake.playing = True
    with pytest.raises(PreconditionFailedError) as exc:
        service.record_automation("POC-TEST", "volume", pts(("2.1.1.0", 0.5)), dry_run=False)
    assert exc.value.code == "TRANSPORT_RUNNING"


def test_transport_that_never_starts(service: CubaseService, fake: FakeCubase, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(automation, "STALL_SECONDS", 0.0)
    original = fake._apply_transport
    fake._apply_transport = lambda key: None if key == "transport.start" else original(key)  # type: ignore[method-assign]
    with pytest.raises(TrackwrightError) as exc:
        service.record_automation("POC-TEST", "volume", pts(("2.1.1.0", 0.5)), dry_run=False)
    assert exc.value.code == "NOT_RECORDED"
    audio = fake.channel_by_title("POC-TEST")
    assert audio.params[4013].value == 0  # restored even on failure
    assert fake.fired[-1] == "transport.stop"


def test_cursor_unavailable(service: CubaseService, fake: FakeCubase) -> None:
    fake.transport["locator"] = "garbage"
    with pytest.raises(TrackwrightError) as exc:
        service.record_automation("POC-TEST", "volume", pts(("2.1.1.0", 0.5)), dry_run=False)
    assert exc.value.code == "UNAVAILABLE"


def test_no_selected_channel_in_fake(fake: FakeCubase) -> None:
    fake.selected = -1
    assert fake.call("auto.list")["controls"] == []
    with pytest.raises(Exception, match="no selected channel"):
        fake.call("auto.control", {"key": "volume"})
    with pytest.raises(Exception, match="unknown"):
        fake.selected = fake.channels[-1]
        fake.call("auto.control", {"key": "nope"})
    with pytest.raises(Exception, match=r"\[0,1\]"):
        fake.call("auto.control", {"key": "pan", "value": 3})
