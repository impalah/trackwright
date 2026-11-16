"""Voice diagnostics (TW-1623): what a voice recording suffers from, each finding with a confidence.

Pure analyses of one voice track's export, read once in blocks (an hour of voice never sits in memory), with
the speech regions from :mod:`trackwright.analysis.speech` (file seconds). Nothing is treated here: the
findings say what was measured, how sure the measure is, and where to listen.

- **spectrum:** the long-term average spectrum of the speech, in six bands, relative to the whole;
- **hum:** peaks at 50 or 60 Hz and their harmonics in the pauses, against the spectrum around each;
- **noise:** the signal-to-noise ratio (typical speech level against the floor of the pauses) and its colour;
- **plosives:** bursts below 80 Hz that dominate a 10 ms window inside speech (a voice's fundamental is above
  80 Hz, a "p" or "b" hitting the microphone is not);
- **clicks:** short transients above 3 kHz standing far above their surroundings, near speech;
- **sibilance:** windows where the 5-10 kHz band is as loud as typical speech;
- **reverb:** how fast the level falls after a phrase ends (followed by a pause), as a T60 estimate.

The thresholds are starting values, chosen on synthetic signals and checked on a real episode (TW-1623);
they are not standards. The confidence says how much the data supports each finding.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
import soundfile as sf
from scipy import signal

Array = npt.NDArray[np.float64]
Span = tuple[float, float]
Severity = Literal["none", "mild", "moderate", "strong"]

BIN = 0.01  # seconds: every envelope is kept in 10 ms bins
LTAS_FRAME = 4096
HUM_FRAME = 32768  # 1.46 Hz at 48 kHz (50 and 60 Hz apart); 0.68 s, so pauses of 1 s count
BLOCK_SECONDS = 30.0
EPS = 1e-20
BANDS: tuple[tuple[str, float, float], ...] = (
    ("rumble", 20, 80),
    ("low", 80, 250),
    ("body", 250, 1000),
    ("presence", 1000, 4000),
    ("sibilance", 4000, 10000),
    ("air", 10000, 20000),
)
MAX_TIMES = 20
CLICK_AUDIBLE_DB = -30.0  # a click's peak no more than 30 dB under the typical speech level
CLICK_CREST = 30.0  # over its surroundings (+-40 ms); TW-1623: x10 caught a presenter's ordinary speech
CLICK_OWN_CREST = 12.0  # within its 10 ms: a click is 1-2 ms, a consonant fills the window


@dataclass(slots=True)
class Finding:
    problem: str
    detected: bool
    severity: Severity
    confidence: float
    """0..1: how much the data supports the finding (not how bad it is)."""
    measures: dict[str, float | str | None] = field(default_factory=dict)
    times: list[float] = field(default_factory=list)
    """Where to listen (file seconds), the strongest first."""
    note: str = ""


@dataclass(slots=True)
class VoiceDiagnosis:
    seconds: float
    rate: int
    speech_seconds: float
    findings: list[Finding]


def _db(power: float) -> float:
    return float(10 * np.log10(max(power, EPS)))


class _Frames:
    """Cuts a stream of chunks into frames of ``size`` samples, keeping each frame's index."""

    def __init__(self, size: int) -> None:
        self.size = size
        self.pending = np.zeros(0)
        self.index = 0

    def feed(self, chunk: Array) -> Iterator[tuple[int, Array]]:
        data = np.concatenate([self.pending, chunk])
        whole = len(data) // self.size
        for i in range(whole):
            yield self.index + i, data[i * self.size : (i + 1) * self.size]
        self.index += whole
        self.pending = data[whole * self.size :]

    def bins(self, chunk: Array) -> Array:
        """The frames of ``chunk`` as rows (no per-frame Python loop: used for the 10 ms envelopes)."""
        data = np.concatenate([self.pending, chunk])
        whole = len(data) // self.size
        self.index += whole
        self.pending = data[whole * self.size :]
        return data[: whole * self.size].reshape(whole, self.size)


class _Band:
    """A band-pass (or high/low-pass) filter that keeps its state between blocks."""

    def __init__(self, rate: int, low: float | None, high: float | None) -> None:
        nyquist = rate / 2
        if low is not None and high is not None:
            self.sos = signal.butter(4, [low / nyquist, min(high, 0.99 * nyquist) / nyquist], "bandpass", output="sos")
        elif low is not None:
            self.sos = signal.butter(4, low / nyquist, "highpass", output="sos")
        else:
            assert high is not None
            self.sos = signal.butter(4, high / nyquist, "lowpass", output="sos")
        self.zi = np.zeros((self.sos.shape[0], 2))

    def __call__(self, x: Array) -> Array:
        y, self.zi = signal.sosfilt(self.sos, x, zi=self.zi)
        return np.asarray(y, dtype=np.float64)


def _mask(regions: Sequence[Span], count: int, step: float, pad: float = 0.0) -> npt.NDArray[np.bool_]:
    """True for every step (of ``step`` seconds) inside a region widened by ``pad``."""
    mask = np.zeros(count, dtype=bool)
    for a, b in regions:
        mask[max(0, int((a - pad) / step)) : min(count, int(np.ceil((b + pad) / step)))] = True
    return mask


@dataclass(slots=True)
class _Envelopes:
    total: list[Array] = field(default_factory=list)
    lf: list[Array] = field(default_factory=list)
    mid: list[Array] = field(default_factory=list)
    sib: list[Array] = field(default_factory=list)
    hp_peak: list[Array] = field(default_factory=list)
    hp_rms: list[Array] = field(default_factory=list)


def _read(path: Path, regions: Sequence[Span]) -> tuple[dict[str, Array], Array, Array, int, int, float]:
    """One pass over the file: the 10 ms envelopes, the speech spectrum and the pause spectrum."""
    info = sf.info(str(path))
    rate = info.samplerate
    bin_size = round(rate * BIN)
    bands = {
        "lf": _Band(rate, 20, 80),
        "mid": _Band(rate, 1000, 4000),
        "sib": _Band(rate, 5000, 10000),
        "hp": _Band(rate, 3000, None),
    }
    cutters = {name: _Frames(bin_size) for name in ("total", "lf", "mid", "sib", "hp")}
    env = _Envelopes()
    ltas, hum = _Frames(LTAS_FRAME), _Frames(HUM_FRAME)
    speech_power, pause_power, all_power = np.zeros(LTAS_FRAME // 2 + 1), np.zeros(HUM_FRAME // 2 + 1), None
    speech_frames = pause_frames = 0
    speech_spans = [(a, b) for a, b in regions]
    window_l, window_h = np.hanning(LTAS_FRAME), np.hanning(HUM_FRAME)
    frames_total = info.frames
    ltas_mask = _mask(speech_spans, frames_total // LTAS_FRAME + 1, LTAS_FRAME / rate)
    hum_mask = _mask(speech_spans, frames_total // HUM_FRAME + 1, HUM_FRAME / rate, pad=0.15)
    all_power = np.zeros(HUM_FRAME // 2 + 1)
    for chunk in sf.blocks(str(path), blocksize=round(rate * BLOCK_SECONDS), dtype="float64", always_2d=True):
        x = np.asarray(chunk.mean(axis=1), dtype=np.float64)
        rows = cutters["total"].bins(x)
        env.total.append((rows * rows).mean(axis=1))
        for name, key in (("lf", "lf"), ("mid", "mid"), ("sib", "sib")):
            filtered = cutters[name].bins(bands[name](x))
            getattr(env, key).append((filtered * filtered).mean(axis=1))
        hp = cutters["hp"].bins(bands["hp"](x))
        env.hp_peak.append(np.abs(hp).max(axis=1) if len(hp) else np.zeros(0))
        env.hp_rms.append(np.sqrt((hp * hp).mean(axis=1)) if len(hp) else np.zeros(0))
        for i, frame in ltas.feed(x):
            if i < len(ltas_mask) and ltas_mask[i]:
                speech_power += np.abs(np.fft.rfft(frame * window_l)) ** 2
                speech_frames += 1
        for i, frame in hum.feed(x):
            power = np.abs(np.fft.rfft(frame * window_h)) ** 2
            all_power += power
            if i < len(hum_mask) and not hum_mask[i]:
                pause_power += power
                pause_frames += 1
    envelopes = {k: (np.concatenate(v) if v else np.zeros(0)) for k, v in vars_of(env).items()}
    hum_spectrum = pause_power / pause_frames if pause_frames else all_power / max(1, hum.index)
    speech_spectrum = speech_power / max(1, speech_frames)
    return envelopes, speech_spectrum, hum_spectrum, rate, pause_frames, frames_total / rate


def vars_of(env: _Envelopes) -> dict[str, list[Array]]:
    return {
        "total": env.total,
        "lf": env.lf,
        "mid": env.mid,
        "sib": env.sib,
        "hp_peak": env.hp_peak,
        "hp_rms": env.hp_rms,
    }


def _events(flags: npt.NDArray[np.bool_], strength: Array) -> list[tuple[float, float]]:
    """Runs of True bins as (start seconds, strongest value), merged when 2 bins apart or less."""
    idx = np.flatnonzero(flags)
    if len(idx) == 0:
        return []
    events: list[tuple[float, float]] = []
    start, best = idx[0], strength[idx[0]]
    last = idx[0]
    for i in idx[1:]:
        if i - last > 2:
            events.append((round(float(start * BIN), 2), float(best)))
            start, best = i, strength[i]
        best = max(best, strength[i])
        last = i
    events.append((round(float(start * BIN), 2), float(best)))
    return events


def _times(events: list[tuple[float, float]]) -> list[float]:
    return [t for t, _ in sorted(events, key=lambda e: -e[1])[:MAX_TIMES]]


def _rate_severity(per_minute: float, mild: float, moderate: float, strong: float) -> Severity:
    if per_minute >= strong:
        return "strong"
    if per_minute >= moderate:
        return "moderate"
    return "mild" if per_minute >= mild else "none"


def spectrum_finding(spectrum: Array, rate: int, frames: int) -> Finding:
    freqs = np.fft.rfftfreq(LTAS_FRAME, 1 / rate)
    total = float(spectrum[(freqs >= 20) & (freqs <= 20000)].sum())
    measures: dict[str, float | str | None] = {}
    for name, low, high in BANDS:
        band = float(spectrum[(freqs >= low) & (freqs < min(high, rate / 2))].sum())
        measures[f"{name}_db"] = round(_db(band) - _db(total), 1) if total > 0 else None
    notes = []
    rumble = measures["rumble_db"]
    if isinstance(rumble, float) and rumble > -20:
        notes.append("much energy under 80 Hz (rumble, handling, proximity)")
    sib, presence = measures["sibilance_db"], measures["presence_db"]
    if isinstance(sib, float) and isinstance(presence, float) and sib > presence:
        notes.append("the 4-10 kHz band outweighs the presence band (bright or sibilant)")
    return Finding(
        "spectrum",
        detected=bool(notes),
        severity="mild" if notes else "none",
        confidence=round(min(1.0, frames / 500), 2),
        measures=measures,
        note="; ".join(notes) or "the long-term speech spectrum, by band, relative to the whole",
    )


def hum_finding(spectrum: Array, rate: int, pause_frames: int) -> Finding:
    freqs = np.fft.rfftfreq(HUM_FRAME, 1 / rate)
    db = 10 * np.log10(np.maximum(spectrum, EPS))
    best: tuple[int, list[float]] = (50, [0.0] * 6)
    for base in (50, 60):
        prominences = []
        for k in range(1, 7):
            f = base * k
            peak = db[(freqs >= f - 1.5) & (freqs <= f + 1.5)]
            flank = db[((freqs >= f - 15) & (freqs <= f - 5)) | ((freqs >= f + 5) & (freqs <= f + 15))]
            prominences.append(float(peak.max() - np.median(flank)) if len(peak) and len(flank) else 0.0)
        if sum(p for p in prominences if p > 0) > sum(p for p in best[1] if p > 0):
            best = (base, prominences)
    base, prominences = best
    strong = [p for p in prominences if p >= 10]
    top = max(prominences) if prominences else 0.0
    # over the voice its harmonics make peaks too: then only the mains fundamental, under any voice, counts
    in_pauses = len(strong) >= 2 or prominences[0] >= 15
    detected = in_pauses if pause_frames else prominences[0] >= 10 and len(strong) >= 2
    severity: Severity = "none"
    if detected:
        severity = "strong" if top >= 25 else "moderate" if top >= 15 else "mild"
    source = 1.0 if pause_frames >= 10 else 0.6 if pause_frames else 0.3  # pauses show hum without the voice
    return Finding(
        "hum",
        detected,
        severity,
        round(min(1.0, len(strong) / 4 + 0.25) * source if detected else source * 0.8, 2),
        measures={
            "mains_hz": base if detected else None,
            "prominence_db": round(top, 1),
            "harmonics": len(strong),
            "measured_on": "pauses" if pause_frames else "everything",
        },
        note=f"peaks at {base} Hz and its harmonics above the spectrum around them"
        if detected
        else "no mains peaks above the spectrum around them",
    )


def noise_finding(
    floor_db: float | None, speech_db: float | None, spectrum: Array, rate: int, pause_frames: int
) -> Finding:
    if floor_db is None or speech_db is None:
        return Finding("noise", False, "none", 0.0, note="no speech or no pauses to measure")
    snr = round(speech_db - floor_db, 1)
    severity: Severity = "strong" if snr < 25 else "moderate" if snr < 35 else "mild" if snr < 45 else "none"
    freqs = np.fft.rfftfreq(HUM_FRAME, 1 / rate)
    total = float(spectrum[(freqs >= 20) & (freqs <= 20000)].sum())
    low = float(spectrum[(freqs >= 20) & (freqs < 200)].sum())
    high = float(spectrum[(freqs >= 4000) & (freqs <= 20000)].sum())
    colour = "rumble" if total and low / total > 0.5 else "hiss" if total and high / total > 0.5 else "broadband"
    return Finding(
        "noise",
        severity != "none",
        severity,
        1.0 if pause_frames >= 10 else 0.5,
        measures={"snr_db": snr, "floor_db": round(floor_db, 1), "colour": colour},
        note=f"speech {snr} dB above the floor of the pauses; the floor is mostly {colour}",
    )


def plosive_finding(env: dict[str, Array], speech: npt.NDArray[np.bool_], minutes: float) -> Finding:
    lf, total = env["lf"], env["total"]
    n = min(len(lf), len(total), len(speech))
    lf, total, speech = lf[:n], total[:n], speech[:n]
    if not speech.any():
        return Finding("plosives", False, "none", 0.0, note="no speech")
    reference = float(np.median(total[speech]))
    flags = speech & (lf > 0.5 * total) & (lf > 0.3 * reference)
    events = _events(flags, 10 * np.log10(np.maximum(lf, EPS) / max(reference, EPS)))
    per_minute = len(events) / max(minutes, 1e-9)
    severity = _rate_severity(per_minute, 0.1, 0.5, 2.0)
    return Finding(
        "plosives",
        severity != "none",
        severity,
        0.7 if events else 0.8,
        measures={"count": len(events), "per_minute": round(per_minute, 2)},
        times=_times(events),
        note="bursts under 80 Hz that dominate the voice for an instant (a 'p' or 'b' on the microphone)",
    )


def click_finding(
    env: dict[str, Array], near: npt.NDArray[np.bool_], speech: npt.NDArray[np.bool_], minutes: float, floor: float
) -> Finding:
    peak, rms = env["hp_peak"], env["hp_rms"]
    total = env["total"][: len(speech)]
    reference = float(np.median(total[speech[: len(total)]])) if speech[: len(total)].any() else floor
    n = min(len(peak), len(near))
    peak, rms, near = peak[:n], rms[:n], near[:n]
    if n == 0:
        return Finding("clicks", False, "none", 0.0, note="nothing to measure")
    local = np.asarray(signal.medfilt(rms, 9), dtype=np.float64)  # the surroundings: +-40 ms
    crest = peak / np.maximum(local, EPS)
    own = peak / np.maximum(rms, EPS)
    audible = np.sqrt(max(reference, EPS)) * 10 ** (CLICK_AUDIBLE_DB / 20)  # TW-1623: spikes in digital silence
    flags = (
        near & (crest > CLICK_CREST) & (own > CLICK_OWN_CREST) & (peak > max(audible, 10 * np.sqrt(max(floor, EPS))))
    )
    events = _events(flags, 20 * np.log10(np.maximum(crest, EPS)))
    per_minute = len(events) / max(minutes, 1e-9)
    severity = _rate_severity(per_minute, 2.0, 5.0, 10.0)
    return Finding(
        "clicks",
        severity != "none",
        severity,
        0.4,
        measures={"count": len(events), "per_minute": round(per_minute, 2)},
        times=_times(events),
        note="short transients above 3 kHz far above their surroundings, near speech (mouth "
        "clicks; also keyboard or chair noises); candidates to listen to: a strong voice's own "
        "consonants can look alike",
    )


def sibilance_finding(env: dict[str, Array], speech: npt.NDArray[np.bool_], minutes: float) -> Finding:
    sib, total = env["sib"], env["total"]
    n = min(len(sib), len(total), len(speech))
    sib, total, speech = sib[:n], total[:n], speech[:n]
    if not speech.any():
        return Finding("sibilance", False, "none", 0.0, note="no speech")
    reference = float(np.median(total[speech]))
    flags = speech & (sib > reference)
    events = _events(flags, 10 * np.log10(np.maximum(sib, EPS) / max(reference, EPS)))
    per_minute = len(events) / max(minutes, 1e-9)
    severity = _rate_severity(per_minute, 0.5, 2.0, 6.0)
    return Finding(
        "sibilance",
        severity != "none",
        severity,
        0.6,
        measures={"count": len(events), "per_minute": round(per_minute, 2)},
        times=_times(events),
        note="windows where 5-10 kHz is as loud as typical speech (harsh 's' and 'sh')",
    )


def reverb_finding(total: Array, regions: Sequence[Span], floor: float) -> Finding:
    """How fast the level falls after each phrase, as a T60 estimate: from the phrase's last loud moment (10 dB
    under its typical level: the detector counts a reverb tail as speech, so its end is not the phrase's), the
    time between falling 5 dB and falling 25 dB (or to 5 dB over the floor), scaled to 60 dB, before the next
    phrase. A fall faster than a bin counts as one bin: a dry voice."""
    level = 10 * np.log10(np.maximum(total, EPS))
    floor_db = _db(floor)
    estimates: list[float] = []
    nexts = [a for a, _ in regions[1:]] + [np.inf] if regions else []
    for (start, end), following in zip(regions, nexts, strict=True):
        first, last = int(start / BIN), min(len(level), int(end / BIN))
        phrase = level[first:last]
        if len(phrase) < 20:
            continue
        loud = np.flatnonzero(phrase >= np.median(phrase) - 10)
        top = first + int(loud[-1])  # the last loud moment of the phrase
        stop = min(len(level), top + 100, int(following / BIN) if np.isfinite(following) else len(level))
        tail = level[top:stop]
        start_db = level[top]
        drop = min(25.0, start_db - floor_db - 5)
        if drop < 15 or len(tail) < 30:  # too little range above the floor, or no pause to fall into
            continue
        below5 = np.flatnonzero(tail <= start_db - 5)
        below = np.flatnonzero(tail <= start_db - drop)
        if not len(below):
            continue
        t5 = below5[0] if len(below5) else 0
        seconds = max(1, below[0] - t5) * BIN
        estimates.append(60 * seconds / (drop - 5))
    if not estimates:
        return Finding("reverb", False, "none", 0.0, note="no phrase end with enough range above the floor")
    t60 = float(np.median(estimates))
    spread = float(np.subtract(*np.percentile(estimates, [75, 25])))
    severity: Severity = "strong" if t60 > 0.8 else "moderate" if t60 > 0.5 else "mild" if t60 > 0.35 else "none"
    confidence = min(1.0, len(estimates) / 20) * (0.9 if spread <= 0.5 * t60 else 0.5)
    return Finding(
        "reverb",
        severity != "none",
        severity,
        round(confidence, 2),
        measures={"t60_s": round(t60, 2), "phrase_ends": len(estimates), "spread_s": round(spread, 2)},
        note="how fast the voice dies after a phrase (the voice's own fall counts too: an estimate)",
    )


def _quietest(total: Array) -> float:
    """The level of the quietest 5 % of the file, digital silence left out: a reverb tail fills the pauses, so
    their floor would hide the very fall being measured."""
    audible = total[total > 1e-12]
    return float(np.percentile(audible, 5)) if len(audible) else EPS


def diagnose(path: Path, regions: Sequence[Span], floor_db: float | None, speech_db: float | None) -> VoiceDiagnosis:
    """Every finding for the voice export at ``path`` with its speech ``regions`` (file seconds) and the
    speech detector's noise floor and speech level (dB)."""
    env, speech_spectrum, hum_spectrum, rate, pause_frames, seconds = _read(path, regions)
    n = len(env["total"])
    speech = _mask(regions, n, BIN)
    near = _mask(regions, n, BIN, pad=0.5)
    minutes = max(seconds / 60, 1e-9)
    pauses = env["total"][~near] if (~near).any() else env["total"]
    floor = float(np.percentile(pauses, 10)) if len(pauses) else EPS
    speech_seconds = round(sum(b - a for a, b in regions), 2)
    findings = [
        spectrum_finding(speech_spectrum, rate, int(speech.sum() * BIN * rate / LTAS_FRAME)),
        hum_finding(hum_spectrum, rate, pause_frames),
        noise_finding(floor_db, speech_db, hum_spectrum, rate, pause_frames),
        plosive_finding(env, speech, minutes),
        click_finding(env, near, speech, minutes, floor),
        sibilance_finding(env, speech, minutes),
        reverb_finding(env["total"], sorted(regions), _quietest(env["total"])),
    ]
    return VoiceDiagnosis(round(seconds, 3), rate, speech_seconds, findings)
