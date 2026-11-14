"""TW-1210: changing transport/metronome settings through the simulated Transport and Metronome objects."""

from __future__ import annotations

import pytest

from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import NotFoundError, PolicyError, PreconditionFailedError
from trackwright.fake import FakeCubase


def test_plan_does_not_write(service: CubaseService, fake: FakeCubase) -> None:
    out = service.set_project({"metronome": True, "click_level": 100})
    assert [(c.setting, c.before, c.requested) for c in out.changes] == [("metronome", False, True),
                                                                        ("click_level", 127, 100)]  # fmt: skip
    assert fake.studio_param("transport", "metronomeOn").value == 0


def test_apply_and_read_back(service: CubaseService, fake: FakeCubase) -> None:
    switches = ("cycle", "metronome", "precount", "punch_in", "punch_out", "pre_roll", "post_roll",
                "click_in_playback", "click_in_record")  # fmt: skip
    settings: dict[str, bool | int] = {**dict.fromkeys(switches, True), "click_level": 64}
    out = service.set_project(settings, dry_run=False)
    assert out.verified is True
    assert {c.setting: c.after for c in out.changes} == settings
    project = service.get_project()
    assert (project.cycle.active, project.metronome.active, project.precount) == (True, True, True)
    assert project.metronome.click_level == "64"


def test_not_verified_when_cubase_ignores_it(service: CubaseService, fake: FakeCubase) -> None:
    original = fake._op_da_param_set
    fake._op_da_param_set = lambda p: {} if p.get("tag") == 4022 else original(p)  # type: ignore[method-assign]
    out = service.set_project({"cycle": True, "metronome": True}, dry_run=False)
    assert out.verified is False
    assert [c.verified for c in out.changes] == [False, True]


@pytest.mark.parametrize(
    ("settings", "code"),
    [({}, "BAD_REQUEST"), ({"tempo": True}, "BAD_REQUEST"), ({"click_level": 200}, "OUT_OF_RANGE"),
     ({"click_level": True}, "OUT_OF_RANGE")],
)  # fmt: skip
def test_validation(service: CubaseService, settings: dict[str, bool | int], code: str) -> None:
    with pytest.raises(PreconditionFailedError) as exc:
        service.set_project(settings)
    assert exc.value.code == code


def test_missing_object(service: CubaseService, fake: FakeCubase) -> None:
    fake.studio["root"].children.remove(fake.studio["metronome"].id)
    with pytest.raises(NotFoundError):
        service.set_project({"click_level": 10})


def test_policy(fake: FakeCubase) -> None:
    readonly = CubaseService(fake, WritePolicy(), sleep=lambda _s: None, settle_timeout=0.0)
    with pytest.raises(PolicyError):
        readonly.set_project({"metronome": True}, dry_run=False)


def test_partial_failure_reports_what_was_applied(service: CubaseService, fake: FakeCubase) -> None:
    """TW-1403 (C-11): a timeout on the second setting reads it back and lists the first one as applied."""
    from trackwright.errors import RequestTimeoutError

    original = fake.call
    writes = 0

    def second_write_times_out(op: str, params: dict[str, object] | None = None, **kw: object) -> dict[str, object]:
        nonlocal writes
        if op == "da.param.set":
            writes += 1
            if writes == 2:
                raise RequestTimeoutError("no answer", outcome_unknown=True, details={"op": op})
        return original(op, params, **kw)  # type: ignore[arg-type]

    fake.call = second_write_times_out  # type: ignore[method-assign]
    with pytest.raises(RequestTimeoutError) as exc:
        service.set_project({"metronome": True, "cycle": True}, dry_run=False)
    assert [c["setting"] for c in exc.value.details["applied"]] == ["metronome"]
    assert exc.value.details["failed_setting"] == "cycle"
    assert "read_back" in exc.value.details
