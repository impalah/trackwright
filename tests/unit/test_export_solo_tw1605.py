"""TW-1605: exporting some tracks alone, with every solo restored afterwards whatever happens."""

from __future__ import annotations

import pytest

from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import PolicyError, TrackwrightError
from trackwright.fake import FakeCubase, FakeExports, FakeLauncher
from trackwright.jsontypes import JsonObject


def service(fake: FakeCubase, exports: FakeExports | None = None, **policy: object) -> CubaseService:
    return CubaseService(
        fake,
        WritePolicy(enabled=True, **policy),  # type: ignore[arg-type]
        sleep=lambda _s: None,
        settle_timeout=0.0,
        launcher=FakeLauncher(fake),
        exports=exports or FakeExports(),  # type: ignore[arg-type]
    )


def solos(svc: CubaseService) -> dict[str, bool | None]:
    return {t.name: t.solo for t in svc.list_tracks().tracks if t.type != "OutputChannel"}


def test_dry_run_plans_without_touching(fake: FakeCubase) -> None:
    svc = service(fake)
    plan = svc.export_mix("start", solo=["POC-TEST"], start="2", end="30")
    assert [(c.name, c.before, c.during) for c in plan.solo] == [("POC-TEST", False, True)]
    assert solos(svc) == {"POC-INSTR": False, "POC-TEST": False}


def test_solo_during_the_export_and_restored_on_confirm(fake: FakeCubase) -> None:
    exports = FakeExports()
    svc = service(fake, exports)
    svc.set_track_mix("POC-INSTR", solo=True, dry_run=False)  # the user had another track soloed
    out = svc.export_mix("start", solo=["POC-TEST"], start="2", end="30", dry_run=False)
    assert out.status == "awaiting_user"
    assert {(c.name, c.before, c.during) for c in out.solo} == {("POC-TEST", False, True), ("POC-INSTR", True, False)}
    assert solos(svc) == {"POC-INSTR": False, "POC-TEST": True}  # only the exported track sounds
    exports.add("/Projects/Demo/Mixdown/stem.wav", 28.0, modified=(out.since or 0) + 1)
    done = svc.export_mix("confirm", since=out.since, expected_seconds=28.0)
    assert done.status == "done"
    assert done.solo_restored is True
    assert all(c.restored for c in done.solo)
    assert solos(svc) == {"POC-INSTR": True, "POC-TEST": False}  # exactly as before
    again = svc.export_mix("confirm", since=out.since, expected_seconds=28.0)
    assert (again.solo, again.solo_restored) == ([], None)  # restored once only


def test_cancel_restores_without_looking_for_files(fake: FakeCubase) -> None:
    exports = FakeExports()
    svc = service(fake, exports)
    out = svc.export_mix("start", solo=["uid:" + svc.list_tracks().tracks[-1].uid], dry_run=False)
    cancelled = svc.export_mix("cancel", since=out.since)
    assert (cancelled.status, cancelled.solo_restored) == ("cancelled", True)
    assert exports.searched == []
    assert set(solos(svc).values()) == {False}


def test_not_found_still_restores(fake: FakeCubase) -> None:
    svc = service(fake)
    out = svc.export_mix("start", solo=["POC-TEST"], start="2", end="30", dry_run=False)
    missing = svc.export_mix("confirm", since=out.since, expected_seconds=28.0)
    assert missing.status == "not_found"
    assert missing.solo_restored is True
    assert solos(svc)["POC-TEST"] is False


def test_nothing_to_change(fake: FakeCubase) -> None:
    svc = service(fake)
    svc.set_track_mix("POC-TEST", solo=True, dry_run=False)
    out = svc.export_mix("start", solo=["POC-TEST"], start="2", end="30", dry_run=False)
    assert out.solo == []
    assert solos(svc)["POC-TEST"] is True


def test_a_failing_dialog_puts_every_solo_back(fake: FakeCubase) -> None:
    fake.can_perform_false.add("file.export_audio_mixdown")
    svc = service(fake)
    svc.set_track_mix("POC-INSTR", solo=True, dry_run=False)
    with pytest.raises(TrackwrightError) as exc:
        svc.export_mix("start", solo=["POC-TEST"], start="2", end="30", dry_run=False)
    assert exc.value.code == "CANNOT_PERFORM"
    assert solos(svc) == {"POC-INSTR": True, "POC-TEST": False}


def test_allowed_tracks_are_respected(fake: FakeCubase) -> None:
    svc = service(fake, allowed_tracks=("POC-TEST",))
    svc.set_track_mix("POC-TEST", solo=False, dry_run=False)
    with pytest.raises(PolicyError) as exc:
        svc.export_mix("start", solo=["POC-INSTR"], start="2", end="30", dry_run=False)
    assert exc.value.code == "NOT_ALLOWED"
    assert solos(svc) == {"POC-INSTR": False, "POC-TEST": False}


def test_a_restore_that_fails_is_reported(fake: FakeCubase) -> None:
    svc = service(fake)
    out = svc.export_mix("start", solo=["POC-TEST"], start="2", end="30", dry_run=False)

    def refuse(params: JsonObject) -> JsonObject:
        raise TrackwrightError("Cubase refused", code="HOST_ERROR")

    fake.override("da.param.set", refuse)
    cancelled = svc.export_mix("cancel", since=out.since)
    assert cancelled.solo_restored is False
    assert cancelled.solo[0].restored is False
    assert any("could not restore the solo of POC-TEST" in n for n in cancelled.notes)


def test_cancel_needs_since(fake: FakeCubase) -> None:
    with pytest.raises(TrackwrightError) as exc:
        service(fake).export_mix("cancel")
    assert exc.value.code == "BAD_REQUEST"


# ---------------------------------------------------------------- muted tracks (TW-1616)
def test_muted_tracks_are_left_out_of_the_solo(fake: FakeCubase) -> None:
    """Live, a muted track soloed for an export was heard in it: Cubase lets a solo override a mute."""
    from trackwright.errors import PreconditionFailedError

    svc = service(fake)
    svc.set_track_mix("POC-INSTR", mute=True, dry_run=False)
    plan = svc.export_mix("start", solo=["POC-TEST", "POC-INSTR"], start="2", end="30")
    assert [c.name for c in plan.solo] == ["POC-TEST"]
    assert any("left out of the solo because they are muted" in n and "POC-INSTR" in n for n in plan.notes)
    both = svc.export_mix("start", solo=["POC-TEST", "POC-INSTR"], include_muted=True, start="2", end="30")
    assert sorted(c.name for c in both.solo) == ["POC-INSTR", "POC-TEST"]
    with pytest.raises(PreconditionFailedError) as exc:
        svc.export_mix("start", solo=["POC-INSTR"], start="2", end="30")
    assert exc.value.code == "BAD_REQUEST"
