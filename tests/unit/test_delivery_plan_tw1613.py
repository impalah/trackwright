"""TW-1613: the delivery plan (fader gain, predicted true peak, a post-fader limiter when needed)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from trackwright.analysis.delivery import FADER_MAX_DB, plan_delivery
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import PreconditionFailedError
from trackwright.fake import FakeCubase

RATE = 48000


def apple(**kwargs: float) -> dict[str, float | None]:
    base: dict[str, float | None] = {"target_lufs": -16.0, "tolerance_lu": 1.0, "ceiling_dbtp": -1.0}
    base.update(kwargs)
    return base


# ---------------------------------------------------------------- the plan, against TW-1612's measurements
def test_lowering_needs_no_limiter() -> None:
    """R0 -> R1/R2 of TW-1612: -10.75 LUFS, -0.77 dBTP; the MP3 measured -16.04 LUFS and -5.24 dBTP."""
    plan = plan_delivery(measured_lufs=-10.75, measured_true_peak=-0.77, fader_now_db=0.0, codec="mp3", **apple())
    assert (plan.gain_db, plan.fader_db, plan.reachable, plan.limiter) == (-5.25, -5.25, True, False)
    assert plan.predicted_lufs == -16.0
    assert plan.predicted_true_peak == pytest.approx(-5.2, abs=0.01)  # measured: -5.24
    assert plan.threshold_db is None


def test_raising_past_the_ceiling_needs_a_limiter() -> None:
    """The brainstorm's example: a quiet master, -21 LUFS, with peaks at -3 dBTP."""
    plan = plan_delivery(measured_lufs=-21.0, measured_true_peak=-3.0, fader_now_db=0.0, codec="mp3", **apple())
    assert (plan.gain_db, plan.limiter) == (5.0, True)
    assert plan.predicted_true_peak == pytest.approx(2.82)
    assert plan.threshold_db == -2.1  # -1 - 0.24 - 0.82, rounded down
    assert plan.peak_reduction_db == pytest.approx(4.1)
    assert any("second round" in w for w in plan.warnings)
    wav = plan_delivery(measured_lufs=-21.0, measured_true_peak=-3.0, fader_now_db=0.0, codec="wav", **apple())
    assert wav.threshold_db == -1.3  # no encoding rise


def test_heavy_limiting_and_the_fader_range() -> None:
    heavy = plan_delivery(measured_lufs=-24.0, measured_true_peak=0.0, fader_now_db=0.0, codec="mp3", **apple())
    assert any("a lot for a limiter" in w for w in heavy.warnings)
    far = plan_delivery(measured_lufs=-30.0, measured_true_peak=-20.0, fader_now_db=0.0, codec="wav", **apple())
    assert (far.reachable, far.fader_db) == (False, round(FADER_MAX_DB, 2))
    assert far.predicted_lufs == pytest.approx(-30.0 + FADER_MAX_DB, abs=0.01)
    assert any("goes up to" in w for w in far.warnings)
    already = plan_delivery(measured_lufs=-18.0, measured_true_peak=-6.0, fader_now_db=-2.0, codec="wav", **apple())
    assert (already.gain_db, already.fader_db) == (2.0, 0.0)  # from the current fader


def test_unpublished_values_and_unmeasured_codecs() -> None:
    spotify = plan_delivery(measured_lufs=-20.0, measured_true_peak=-1.0, fader_now_db=0.0, codec="mp3",
                            target_lufs=None, tolerance_lu=None, ceiling_dbtp=None)  # fmt: skip
    assert (spotify.gain_db, spotify.limiter) == (0.0, False)
    assert any("no loudness target" in w for w in spotify.warnings)
    assert any("no true-peak ceiling" in w for w in spotify.warnings)
    aac = plan_delivery(measured_lufs=-16.0, measured_true_peak=-1.5, fader_now_db=0.0, codec="aac", **apple())
    assert any("was not measured" in w for w in aac.warnings)
    assert aac.limiter is True  # -1.5 + 0.82 > -1


# ---------------------------------------------------------------- the tool
@pytest.fixture
def master(tmp_path: Path) -> Path:
    t = np.arange(20 * RATE) / RATE
    tone = 0.05 * np.sin(2 * np.pi * 997 * t)  # about -29 LUFS, peaks -26 dBFS
    path = tmp_path / "master.wav"
    sf.write(path, np.column_stack([tone, tone]), RATE, subtype="FLOAT")
    return path


def make(fake: FakeCubase) -> CubaseService:
    # the simulator maps continuous parameters linearly onto -24..+24: 0.5 is a fader at 0 dB
    fake.channel_by_title("Stereo Out").params[1025].value = 0.5
    return CubaseService(fake, WritePolicy(analysis=True), sleep=lambda _s: None, settle_timeout=0.0)


def test_the_tool_reads_the_fader_and_the_slots(fake: FakeCubase, master: Path) -> None:
    out = make(fake).delivery_plan(str(master), "apple")
    assert (out.target, out.codec, out.stereo_out, out.fader_now_db) == ("apple", "aac", "Stereo Out", 0.0)
    assert out.reachable is False  # about 13 dB up: beyond the fader
    assert out.source == "https://podcasters.apple.com/support/893-audio-requirements"
    assert out.limiter_slot == 7  # the first free post-fader slot
    assert any("not measured" in w for w in out.warnings)
    mp3 = make(fake).delivery_plan(str(master), "apple", codec="mp3")
    assert mp3.codec == "mp3"
    assert not any("not measured" in w for w in mp3.warnings)


def test_refusals(fake: FakeCubase, master: Path, tmp_path: Path) -> None:
    with pytest.raises(PreconditionFailedError) as unknown:
        make(fake).delivery_plan(str(master), "nowhere")
    assert unknown.value.code == "BAD_REQUEST"
    silent = tmp_path / "silent.wav"
    sf.write(silent, np.zeros((RATE * 5, 2)), RATE)
    with pytest.raises(PreconditionFailedError) as quiet:
        make(fake).delivery_plan(str(silent), "apple")
    assert quiet.value.code == "BAD_AUDIO"


LIMITER = "94DEB7BF378041EE9E2FEDA24E19EF60"
COMPRESSOR = "5B38F28281144FFE80285FF7CCF20483"


def test_limiters_already_on_stereo_out(fake: FakeCubase, master: Path) -> None:
    svc = CubaseService(fake, WritePolicy(enabled=True, analysis=True), sleep=lambda _s: None, settle_timeout=0.0)
    make(fake)
    svc.insert_plugin("Stereo Out", 1, LIMITER, dry_run=False)
    out = svc.delivery_plan(str(master), "apple")
    assert any("slot 1 is before the fader" in n for n in out.notes)
    svc.insert_plugin("Stereo Out", 8, LIMITER, dry_run=False)
    reuse = svc.delivery_plan(str(master), "apple")
    assert (reuse.limiter_slot, reuse.limiter_in_slot) == (8, "Brickwall Limiter")  # reused, not doubled
    loud = master.with_name("loud.wav")
    t = np.arange(20 * RATE) / RATE
    tone = 0.9 * np.sin(2 * np.pi * 997 * t)
    sf.write(loud, np.column_stack([tone, tone]), RATE, subtype="FLOAT")
    svc.insert_plugin("Stereo Out", 7, COMPRESSOR, dry_run=False)
    full = CubaseService(fake, WritePolicy(analysis=True), sleep=lambda _s: None, settle_timeout=0.0)
    blocked = full.delivery_plan(str(loud), "apple", codec="mp3")
    assert blocked.limiter_slot == 8  # the limiter in 8 is still there


def test_no_post_fader_slot_left(master: Path) -> None:
    fake = FakeCubase()
    svc = CubaseService(fake, WritePolicy(enabled=True, analysis=True), sleep=lambda _s: None, settle_timeout=0.0)
    make(fake)
    svc.insert_plugin("Stereo Out", 7, COMPRESSOR, dry_run=False)
    svc.insert_plugin("Stereo Out", 8, COMPRESSOR, dry_run=False)
    spiky = master.with_name("spiky.wav")
    t = np.arange(20 * RATE) / RATE
    signal = 0.05 * np.sin(2 * np.pi * 997 * t)
    signal[:: 2 * RATE] = 0.9  # quiet speech, sharp peaks: the gain pushes them past the ceiling
    sf.write(spiky, np.column_stack([signal, signal]), RATE, subtype="FLOAT")
    out = svc.delivery_plan(str(spiky), "apple", codec="mp3")
    assert out.limiter is True
    assert out.limiter_slot is None
    assert any("slots 7 and 8 are taken" in w for w in out.warnings)
