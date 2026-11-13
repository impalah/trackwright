"""Regression tests for the independent review findings (epic E10)."""

from __future__ import annotations

from typing import Any

import pytest

from trackwright.core.service import CubaseService
from trackwright.errors import PreconditionFailedError, RequestTimeoutError
from trackwright.fake import FakeCubase, Param

STUDIO_EQ = "946051208E29496E804F64A825C8A047"
JsonObject = dict[str, Any]


def test_tw1002_refuses_when_several_tracks_are_selected(service: CubaseService, fake: FakeCubase) -> None:
    fake.channel_by_title("POC-INSTR").params[4000].value = 1  # a second track selected in the GUI
    with pytest.raises(PreconditionFailedError) as exc:
        service.remove_selected_tracks("POC-TEST", dry_run=False)
    assert exc.value.code == "SELECTION_MISMATCH"
    assert exc.value.details["selected"] == ["POC-INSTR", "POC-TEST"]
    assert fake.fired == []


def test_tw1003_filter_never_skips_matches(service: CubaseService, fake: FakeCubase) -> None:
    for eq in (o for o in fake.objects.values() if o.type == "EQ"):
        eq.params = {
            4232 + i: Param(f"EQ {i} Gain" if i % 2 == 0 else f"EQ {i} Freq", "continuous", 0.5) for i in range(60)
        }
    seen: list[int] = []
    offset = 0
    while True:
        page = service.list_parameters("selected", "strip:eq", offset=offset, limit=2, filter_text="gain")
        seen += [p.tag for p in page.items]
        if not page.truncated:
            break
        assert page.next_offset > offset
        offset = page.next_offset
    assert seen == [4232 + i for i in range(0, 60, 2)]


def test_tw1003_unfiltered_paging(service: CubaseService) -> None:
    first = service.list_parameters("selected", "channel", limit=3)
    assert [p.tag for p in first.items] == [1024, 4000, 1025]
    assert (first.next_offset, first.truncated) == (3, True)
    rest = service.list_parameters("selected", "channel", offset=first.next_offset, limit=25)
    assert len(rest.items) == 7
    assert rest.truncated is False


def test_tw1004_insert_read_back_failure_keeps_the_write_timeout(service: CubaseService, fake: FakeCubase) -> None:
    fake.fail_next["pm.set"] = RequestTimeoutError("pm.set late", outcome_unknown=True)
    original = fake._op_da_object
    calls = {"n": 0}

    def slow_object(p: JsonObject) -> JsonObject:
        calls["n"] += 1
        if calls["n"] > 0 and any(op == "pm.set" for op, _ in fake.calls):
            raise RequestTimeoutError("da.object late", outcome_unknown=False)
        return original(p)

    fake._op_da_object = slow_object  # type: ignore[method-assign]
    with pytest.raises(RequestTimeoutError) as exc:
        service.insert_plugin("POC-TEST", 1, STUDIO_EQ, dry_run=False)
    assert exc.value.outcome_unknown is True
    assert "da.object late" in exc.value.details["read_back_error"]


def test_tw1006_partial_mix_changes_are_reported(service: CubaseService, fake: FakeCubase) -> None:
    original = fake._op_da_param_set

    def fail_on_mute(p: JsonObject) -> JsonObject:
        if p["tag"] == 1027:
            raise RequestTimeoutError("mute late", outcome_unknown=True)
        return original(p)

    fake._op_da_param_set = fail_on_mute  # type: ignore[method-assign]
    with pytest.raises(RequestTimeoutError) as exc:
        service.set_track_mix("POC-INSTR", volume=0.5, mute=True, dry_run=False)
    applied = exc.value.details["applied"]
    assert [c["tag"] for c in applied] == [1025]
    assert applied[0]["after"]["process"] == 0.5


def test_tw1007_start_refuses_existing_names(service: CubaseService, fake: FakeCubase) -> None:
    with pytest.raises(PreconditionFailedError) as exc:
        service.add_track_interactive("start", "audio", "POC-TEST")
    assert exc.value.code == "NAME_CONFLICT"
    assert fake.fired == []


def test_tw1008_unchecked_events_are_not_reported_invalid(service: CubaseService, fake: FakeCubase) -> None:
    for oid in list(fake.objects)[:25]:
        fake._event("changed", oid)
    out = service.poll_changes()
    assert out.unchecked == 5
    assert [e.still_valid for e in out.events[-5:]] == [None] * 5
    assert all(e.still_valid for e in out.events[:20])


def test_tw1009_expect_title_travels_with_the_write(service: CubaseService, fake: FakeCubase) -> None:
    service.set_parameter("POC-TEST", "channel", 1025, 0.5, expect_title="Volumen", dry_run=False)
    params = next(p for op, p in fake.calls if op == "da.param.set")
    assert params["expectTitle"] == "Volumen"


def test_tw1012_removal_that_lands_late_is_seen(fake: FakeCubase) -> None:
    from trackwright.core.policy import WritePolicy

    service = CubaseService(fake, WritePolicy(enabled=True), sleep=lambda _s: None, settle_timeout=1.0)
    audio = fake.channel_by_title("POC-TEST").id
    original_apply = fake._apply_command
    original_channels = fake._op_da_channels
    state = {"reads_after": 0}

    def delayed(key: str) -> None:
        if key != "project.remove_selected_tracks":
            original_apply(key)

    def channels(p: JsonObject) -> JsonObject:
        if fake.fired:
            state["reads_after"] += 1
            if state["reads_after"] == 2:  # the removal becomes visible on the second read
                fake.remove(audio)
        return original_channels(p)

    fake._apply_command = delayed  # type: ignore[method-assign]
    fake._op_da_channels = channels  # type: ignore[method-assign]
    out = service.remove_selected_tracks("POC-TEST", dry_run=False)
    assert out.status == "done"


def test_tw1013_split_reports_previous_locators(service: CubaseService, fake: FakeCubase) -> None:
    fake.transport["cycleLeft"] = "5. 1. 1.  0"
    fake.transport["cycleRight"] = "9. 1. 1.  0"
    out = service.split_at_locators("2.1.1.0", "4.1.1.0", dry_run=False)
    assert (out.details["previous_left"], out.details["previous_right"]) == ("5. 1. 1.  0", "9. 1. 1.  0")
