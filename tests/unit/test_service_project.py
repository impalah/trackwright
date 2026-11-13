"""TW-1209: project properties from the simulated Transport / Metronome objects, and the time signature
used by the automation tools."""

from __future__ import annotations

import pytest

from trackwright.config import CubaseConfig
from trackwright.core.automation import from_beats, to_beats
from trackwright.core.models import AutomationPoint
from trackwright.core.project import parse_signature
from trackwright.core.service import CubaseService
from trackwright.errors import NotFoundError
from trackwright.fake import FakeCubase, FakeLauncher
from trackwright.launcher import CubaseLauncher


def test_parse_signature() -> None:
    assert parse_signature("3/4") is not None
    assert parse_signature(" 6 / 8 ").model_dump() == {"text": " 6 / 8 ", "numerator": 6, "denominator": 8}  # type: ignore[union-attr]
    assert parse_signature("libre").model_dump() == {"text": "libre", "numerator": None, "denominator": None}  # type: ignore[union-attr]
    assert parse_signature("") is None
    assert parse_signature(None) is None


def test_get_project_defaults(service: CubaseService) -> None:
    out = service.get_project()
    assert out.signature is not None and (out.signature.numerator, out.signature.denominator) == (4, 4)
    assert out.tempo_bpm == 120.0
    assert out.transport == "stopped"
    assert (out.cycle.active, out.metronome.active, out.precount) == (False, False, False)
    assert out.metronome.click_level == "127"
    assert out.time_formats == ["Compases+Tiempos", "Segundos"]
    assert out.modes["record_button"] == "Punch in/out"
    assert out.project_folders is None  # the fixture service has no launcher
    assert set(out.unavailable) == {"sample_rate", "bit_depth", "project_length", "project_name"}


def test_get_project_reflects_cubase(fake: FakeCubase) -> None:
    service = CubaseService(fake, __import__("trackwright.core.policy", fromlist=["WritePolicy"]).WritePolicy(),
                            launcher=FakeLauncher(fake))  # fmt: skip
    fake.studio_param("transport", "signature").text = "3/4"
    fake.studio_param("transport", "cycle").value = 1
    fake.studio_param("transport", "metronomeOn").value = 1
    fake.studio_param("transport", "start").value = 1
    fake.studio_param("transport", "stop").value = 0
    out = service.get_project()
    assert out.signature is not None and out.signature.text == "3/4"
    assert (out.cycle.active, out.metronome.active, out.transport) == (True, True, "playing")
    assert out.project_folders == ["/Projects/Demo"]
    fake.studio_param("transport", "record").value = 1
    assert service.get_project(include_folders=False).transport == "recording"
    fake.studio_param("transport", "record").value = 0
    fake.studio_param("transport", "start").value = 0
    assert service.get_project().transport == "unknown"


def test_device_root_found_by_scanning(service: CubaseService, fake: FakeCubase) -> None:
    root = fake.objects.pop(1)
    root.id = 7
    fake.objects[7] = root
    assert service.get_project().signature is not None
    del fake.objects[7]
    with pytest.raises(NotFoundError):
        service.get_project()
    assert service.current_signature() is None


def test_missing_transport(service: CubaseService, fake: FakeCubase) -> None:
    fake.studio["root"].children = [c for c in fake.studio["root"].children if c != fake.studio["transport"].id]
    with pytest.raises(NotFoundError):
        service.get_project()
    assert service.current_signature() is None


def test_signature_param_with_another_title(service: CubaseService, fake: FakeCubase) -> None:
    fake.studio["transport"].params[4027].title = "other"
    assert service.current_signature() is None


# ---------------------------------------------------------------- automation follows the signature
@pytest.mark.parametrize(
    ("meter", "position", "quarters"),
    [
        ((4, 4), (3, 2, 1, 0), 9.0),
        ((3, 4), (3, 2, 1, 0), 7.0),
        ((6, 8), (2, 3, 1, 0), 4.0),
        ((3, 4), (1, 1, 2, 60), 0.375),
    ],
)
def test_beats_with_signatures(meter: tuple[int, int], position: tuple[int, int, int, int], quarters: float) -> None:
    assert to_beats(position, meter) == pytest.approx(quarters)
    assert from_beats(quarters, meter) == position


def test_record_automation_in_three_four(service: CubaseService, fake: FakeCubase) -> None:
    fake.studio_param("transport", "signature").text = "3/4"
    points = [AutomationPoint(position="3. 1. 1. 0", value=0.8), AutomationPoint(position="4. 1. 1. 0", value=0.4)]
    plan = service.record_automation("POC-TEST", "volume", points)
    assert plan.start == "2. 1. 1.  0"  # one 3/4 bar of pre-roll
    assert any("3/4" in note for note in plan.notes)
    done = service.record_automation("POC-TEST", "volume", points, dry_run=False)
    assert done.verified is True, done.mismatches
    recorded = fake.automation[(fake.channel_by_title("POC-TEST").id, "volume")]
    assert recorded[0] == (pytest.approx(6.0), pytest.approx(0.8))  # bar 3 in 3/4 = 6 quarter notes


def test_unknown_signature_assumes_common_time(service: CubaseService, fake: FakeCubase) -> None:
    fake.studio["transport"].params[4027].title = "other"
    plan = service.record_automation("POC-TEST", "volume", [AutomationPoint(position="3. 1. 1. 0", value=0.5)])
    assert any("assume 4/4" in note for note in plan.notes)


# ---------------------------------------------------------------- project folders (lsof)
def test_project_folders_from_open_audio_files() -> None:
    outputs = {
        ("/usr/bin/pgrep", "-x", "Cubase 15"): "123\n",
        ("/usr/sbin/lsof", "-p", "123", "-Fn"): "p123\nn/Library/Audio/Plug-Ins/x.vst3\nn/Vol/Songs/A/Audio/take1.wav\n"
        "n/Vol/Songs/A/Audio/take2.wav\nn/Vol/Songs/B/Audio/x.wav\nf12\n",
    }
    launcher = CubaseLauncher(CubaseConfig(), run=lambda _a: 0, output=lambda argv: outputs[tuple(argv)])
    assert launcher.project_folders() == ["/Vol/Songs/A", "/Vol/Songs/B"]
    assert CubaseLauncher(CubaseConfig(), output=lambda _a: "").project_folders() == []
