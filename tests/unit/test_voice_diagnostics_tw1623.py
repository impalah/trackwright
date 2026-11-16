"""TW-1623: voice diagnostics: each fault found in its own case and not in a clean voice."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from scipy import signal

from trackwright.analysis.speech import SpeechCriteria, detect_speech
from trackwright.analysis.voice import HUM_FRAME, Finding, VoiceDiagnosis, diagnose, noise_finding, reverb_finding
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import NotFoundError
from trackwright.fake import FakeCubase

RATE = 48000
SECONDS = 40.0


def synthetic_voice(rng: np.random.Generator) -> tuple[np.ndarray, list[tuple[float, float]]]:
    """Phrases of a harmonic voice (f0 100-140 Hz, syllable rhythm, 10 ms onsets) between pauses."""
    t = np.arange(int(SECONDS * RATE)) / RATE
    x = np.zeros_like(t)
    regions = []
    s = 1.0
    while s < SECONDS - 3:
        d = rng.uniform(2, 5)
        m = (t >= s) & (t < s + d)
        f0 = 120 + 20 * np.sin(2 * np.pi * 0.5 * t[m])
        phase = 2 * np.pi * np.cumsum(f0) / RATE
        envelope = (0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 3 * t[m]))) * np.minimum(
            1, np.minimum(t[m] - s, s + d - t[m]) / 0.01
        )
        x[m] += 0.15 * envelope * sum(np.sin(k * phase) / k for k in range(1, 25))
        regions.append((s, s + d))
        s += d + rng.uniform(1.2, 2.0)
    return x, regions


@pytest.fixture(scope="module")
def cases(tmp_path_factory: pytest.TempPathFactory) -> dict[str, VoiceDiagnosis]:
    folder = tmp_path_factory.mktemp("voices")
    rng = np.random.default_rng(0)
    base, regions = synthetic_voice(rng)
    t = np.arange(len(base)) / RATE
    floor = 0.0005 * rng.standard_normal(len(t))
    signals = {"clean": base + floor, "noisy": base + 0.01 * rng.standard_normal(len(t))}
    signals["hum"] = base + floor + sum(0.003 / k * np.sin(2 * np.pi * 50 * k * t) for k in range(1, 5))
    plosives = base + floor
    clicks = base + floor
    sibilance = base + floor
    band = signal.sosfilt(signal.butter(4, [5500 / 24000, 9000 / 24000], "bandpass", output="sos"),
                          rng.standard_normal(len(t)))  # fmt: skip
    for a, b in regions:
        i, n = int((a + 0.3) * RATE), int(0.04 * RATE)
        plosives[i : i + n] += 0.6 * np.sin(2 * np.pi * 45 * np.arange(n) / RATE) * np.hanning(n)
        for _ in range(3):
            j = int((a + rng.uniform(0, b - a)) * RATE)
            clicks[j] += 0.3
            clicks[j + 1] -= 0.25
        for _ in range(4):
            j, n = int((a + rng.uniform(0, b - a - 0.15)) * RATE), int(0.12 * RATE)
            sibilance[j : j + n] += 0.5 * band[j : j + n] * np.hanning(n)
    signals |= {"plosives": plosives, "clicks": clicks, "sibilance": sibilance}
    ir_t = np.arange(int(1.2 * RATE)) / RATE
    ir = rng.standard_normal(len(ir_t)) * np.exp(-6.9 * ir_t / 0.9)  # T60 0.9 s
    ir[0] = 1.0
    ir /= np.sqrt((ir**2).sum()) * 0.6
    signals["reverb"] = signal.fftconvolve(base, ir)[: len(base)] + floor
    found = {}
    for name, x in signals.items():
        path = folder / f"{name}.wav"
        sf.write(path, np.column_stack([x, x]), RATE, subtype="FLOAT")
        speech = detect_speech(path, SpeechCriteria())
        found[name] = diagnose(path, [(r.start, r.end) for r in speech.regions], speech.noise_floor_db,
                               speech.speech_level_db)  # fmt: skip
    return found


def finding(d: VoiceDiagnosis, problem: str) -> Finding:
    return next(f for f in d.findings if f.problem == problem)


FAULTS = {"hum": "hum", "noisy": "noise", "plosives": "plosives", "clicks": "clicks", "sibilance": "sibilance",
          "reverb": "reverb"}  # fmt: skip


@pytest.mark.parametrize("case", list(FAULTS))
def test_each_fault_is_found_in_its_case_only(cases: dict[str, VoiceDiagnosis], case: str) -> None:
    problem = FAULTS[case]
    assert finding(cases[case], problem).detected, case
    assert not finding(cases["clean"], problem).detected, problem
    for other, d in cases.items():
        if other not in (case, "clean") and FAULTS.get(other) != problem and problem != "noise":
            assert not finding(d, problem).detected, (problem, other)


def test_the_measures(cases: dict[str, VoiceDiagnosis]) -> None:
    hum = finding(cases["hum"], "hum")
    assert (hum.measures["mains_hz"], hum.measures["measured_on"]) == (50, "pauses")
    assert all(hum.measures[f"h{k}_db"] > 10 for k in range(1, 5))  # type: ignore[operator]  # four injected
    for k in range(1, 5):  # TW-1624: each harmonic's own level, 0.003/k of amplitude: RMS 20 log10(0.003/k/sqrt 2)
        assert hum.measures[f"h{k}_dbfs"] == pytest.approx(20 * np.log10(0.003 / k / np.sqrt(2)), abs=0.5)
    sibilant = finding(cases["sibilance"], "sibilance").measures
    assert 4700 <= sibilant["band_low_hz"] <= 6000  # type: ignore[operator]  # the injected noise: 5.5-9 kHz
    assert 8000 <= sibilant["band_high_hz"] <= 10600  # type: ignore[operator]
    assert finding(cases["clean"], "noise").measures["snr_db"] > 45  # type: ignore[operator]
    assert finding(cases["noisy"], "noise").measures["snr_db"] < 35  # type: ignore[operator]
    assert finding(cases["reverb"], "reverb").measures["t60_s"] == pytest.approx(0.9, abs=0.3)
    assert finding(cases["clean"], "reverb").measures["t60_s"] < 0.2  # type: ignore[operator]
    clicks = finding(cases["clicks"], "clicks")
    assert clicks.times
    assert clicks.measures["per_minute"] > 20  # type: ignore[operator]
    spectrum = finding(cases["clean"], "spectrum")
    bands = ("rumble", "low", "body", "presence", "sibilance", "air")
    assert set(spectrum.measures) == {f"{b}_db" for b in bands} | {f"{b}_dbfs" for b in bands}
    # TW-1624: absolute levels, and the esses' peaks louder where noise bursts were added
    assert spectrum.measures["body_dbfs"] < 0  # type: ignore[operator]
    peaks = [finding(cases[c], "sibilance").measures["peak_dbfs"] for c in ("clean", "sibilance")]
    assert peaks[1] > peaks[0] + 6  # type: ignore[operator]
    assert finding(cases["sibilance"], "spectrum").detected  # its 4-10 kHz band outweighs the presence band


def test_edge_cases(tmp_path: Path) -> None:
    silent = tmp_path / "silent.wav"
    sf.write(silent, np.zeros((RATE * 2, 2)), RATE)
    d = diagnose(silent, [], None, None)
    assert not any(f.detected for f in d.findings)
    assert finding(d, "noise").note.startswith("no speech")
    assert finding(d, "reverb").confidence == 0.0
    assert noise_finding(-90.0, -20.0, np.zeros(HUM_FRAME // 2 + 1), RATE, 0).confidence == 0.5
    assert not reverb_finding(np.full(10, 1e-6), [(0.0, 0.02)], 1e-12).detected  # too short to see a fall
    rumble = tmp_path / "rumble.wav"
    t = np.arange(RATE * 6) / RATE
    x = 0.3 * np.sin(2 * np.pi * 40 * t) + 0.05 * np.sin(2 * np.pi * 300 * t)
    sf.write(rumble, np.column_stack([x, x]), RATE)
    rough = diagnose(rumble, [(0.5, 5.5)], -60.0, -15.0)
    assert finding(rough, "spectrum").detected  # much energy under 80 Hz


class Launcher:
    def __init__(self, folders: list[str]) -> None:
        self.folders = folders

    def project_folders(self) -> list[str]:
        return self.folders


def test_the_tool(fake: FakeCubase, tmp_path: Path) -> None:
    rng = np.random.default_rng(3)
    x, _ = synthetic_voice(rng)
    x += 0.0005 * rng.standard_normal(len(x))  # a noise floor: the detector leaves digital silence out
    path = tmp_path / "voice.wav"
    sf.write(path, np.column_stack([x, x]), RATE, subtype="FLOAT")
    svc = CubaseService(fake, WritePolicy(analysis=True), launcher=Launcher([]))  # type: ignore[arg-type]
    out = svc.voice_diagnostics(str(path), start=100.0)
    assert [f.problem for f in out.findings] == ["spectrum", "hum", "noise", "plosives", "clicks", "sibilance",
                                                 "reverb"]  # fmt: skip
    assert out.speech_seconds > 20
    assert any("listen to the times" in n for n in out.notes)
    silent = tmp_path / "silent.wav"
    sf.write(silent, np.zeros((RATE, 2)), RATE)
    assert any("no speech" in n for n in svc.voice_diagnostics(str(silent)).notes)
    with pytest.raises(NotFoundError):
        svc.voice_diagnostics(str(tmp_path / "none.wav"))
