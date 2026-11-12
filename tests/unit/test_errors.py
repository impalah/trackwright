from __future__ import annotations

import pytest

from trackwright import errors


def test_to_dict_and_str() -> None:
    exc = errors.PreconditionFailedError("slot is occupied", details={"slot": 1})
    assert exc.to_dict() == {"code": "PRECONDITION_FAILED", "message": "slot is occupied", "details": {"slot": 1}}
    assert str(exc) == "PRECONDITION_FAILED: slot is occupied"


def test_to_dict_omits_empty_details() -> None:
    assert errors.NotFoundError("no such track").to_dict() == {"code": "NOT_FOUND", "message": "no such track"}


def test_custom_code_overrides_default() -> None:
    assert errors.PolicyError("writes are disabled", code="WRITES_DISABLED").code == "WRITES_DISABLED"


@pytest.mark.parametrize(("unknown", "outcome"), [(True, "unknown"), (False, "not_executed_or_lost")])
def test_timeout_outcome(unknown: bool, outcome: str) -> None:
    exc = errors.RequestTimeoutError("late", outcome_unknown=unknown, details={"op": "da.param.set"})
    assert exc.outcome_unknown is unknown
    assert exc.details == {"outcome": outcome, "op": "da.param.set"}
    assert exc.code == "TIMEOUT"


def test_host_error_maps_stale_session() -> None:
    exc = errors.host_error("STALE_SESSION", "expected session x")
    assert isinstance(exc, errors.StaleSessionError)
    assert exc.code == "STALE_SESSION"


def test_host_error_keeps_script_code() -> None:
    exc = errors.host_error("INVALID_OBJECT", "object 588 is not valid", {"rid": "1-a"})
    assert type(exc) is errors.HostError
    assert exc.code == "INVALID_OBJECT"
    assert exc.details == {"rid": "1-a"}
