"""TW-1205: stepping plugin presets (simulated editor, focus and preset state)."""

from __future__ import annotations

import pytest

from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import PolicyError, PreconditionFailedError
from trackwright.fake import FakeCubase

STUDIO_EQ = "946051208E29496E804F64A825C8A047"


@pytest.fixture
def with_plugin(service: CubaseService) -> CubaseService:
    service.insert_plugin("POC-TEST", 1, STUDIO_EQ, dry_run=False)
    return service


def slot_edit(fake: FakeCubase) -> float:
    inserts = next(fake.objects[c] for c in fake.channel_by_title("POC-TEST").children
                   if fake.objects[c].type == "Inserts")  # fmt: skip
    return fake.objects[inserts.children[0]].params[4101].value


def test_plan(with_plugin: CubaseService, fake: FakeCubase) -> None:
    out = with_plugin.plugin_preset("POC-TEST", 1, "next")
    assert (out.status, out.plugin, out.changed) == ("planned", "StudioEQ", {})
    assert "preset.next" not in fake.fired


def test_next_and_previous(with_plugin: CubaseService, fake: FakeCubase) -> None:
    out = with_plugin.plugin_preset("POC-TEST", 1, "next", dry_run=False)
    assert (out.status, out.verified) == ("done", True)
    assert out.changed
    assert slot_edit(fake) == 0  # the editor is closed again
    back = with_plugin.plugin_preset("POC-TEST", 1, "previous", dry_run=False)
    assert back.verified is True
    assert {k: v.split(" -> ")[1] for k, v in back.changed.items()} == {
        k: v.split(" -> ")[0] for k, v in out.changed.items()
    }


def test_needs_focus_then_works(with_plugin: CubaseService, fake: FakeCubase) -> None:
    fake.editor_focused = False
    first = with_plugin.plugin_preset("POC-TEST", 1, "next", dry_run=False)
    assert (first.status, first.verified) == ("awaiting_user", False)
    assert first.instructions and "Click once" in first.instructions
    assert slot_edit(fake) == 1  # left open for the click
    fake.editor_focused = True  # the user clicks
    second = with_plugin.plugin_preset("POC-TEST", 1, "next", dry_run=False)
    assert (second.status, second.verified) == ("done", True)
    assert slot_edit(fake) == 1  # it was open before this call, so it stays open


def test_without_a_preset(with_plugin: CubaseService, fake: FakeCubase) -> None:
    fake.preset_loaded = False
    assert with_plugin.plugin_preset("POC-TEST", 1, "previous", dry_run=False).status == "awaiting_user"


def test_errors(with_plugin: CubaseService, fake: FakeCubase) -> None:
    with pytest.raises(PreconditionFailedError):
        with_plugin.plugin_preset("POC-TEST", 1, "sideways")  # type: ignore[arg-type]
    with pytest.raises(PreconditionFailedError) as empty:
        with_plugin.plugin_preset("POC-TEST", 2, "next")
    assert empty.value.code == "EMPTY_SLOT"
    readonly = CubaseService(fake, WritePolicy(), sleep=lambda _s: None, settle_timeout=0.0)
    with pytest.raises(PolicyError):
        readonly.plugin_preset("POC-TEST", 1, "next", dry_run=False)
