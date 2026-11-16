"""Music beds (TW-1617): tempo and beats, repeated sections, loop candidates, the ending, and a bed of a given
length that keeps the ending. Pure numpy and scipy; no time stretch, ever.

1. **Onsets and tempo.** Spectral flux of the magnitude spectrogram (frames of 1024 samples, hop 512) is the
   onset strength; its autocorrelation, weighed by a prior around 120 BPM (a tempo and its half correlate
   alike), gives the beat period between 60 and 180 BPM; a beat grid is fitted to the onset peaks.
   ``tempo_confidence`` says how clear the periodicity was (ambient material has none, and then loop lengths
   are free instead of whole bars).
2. **Features.** Log energy in 24 bands (timbre) and energy in the 12 pitch classes (chroma, 55 Hz-5 kHz) per
   frame, each vector normalised.
3. **Loop candidates** (all before the ending). For each repetition lag (whole bars when there is a beat, up
   to 40 s), the agreement of the music with itself that much later is the lower of the timbre and harmony
   similarities, frame by frame; the seam goes where it is best within 1 s on each side, the loop is ranked by
   the agreement over a bar on each side of that point (a jump between two equal chords that drops the rest of
   a progression agrees within 1 s, not over a bar), and the loop's end is
   then lined up with its start by correlation (envelopes within 80 ms, waveforms within 3 ms). The score is
   that agreement: a piece that evolves (a march that builds up) scores lower, and its seams need a listen.
4. **Crossfade.** Half a beat (0.1 s without a beat), equal-power.
5. **Ending.** The tail is where the level falls for good below the music's typical level minus 10 dB; the
   ending starts at the beginning of the last bar (or the last two seconds) before that fall.
6. **Bed.** The music to the end of the loop, back to its start as many times as fit, and on the last pass on
   to the end of the file (or, if asked, a jump to a given ending): the nearest length to the target without
   going over, never stretched.

Checked by ear on a real bed (TW-1617): with the first version (features per beat, a grid off the beat, a jump
to the ending) the seams were clearly heard; with this one, "hardly noticeable, more than acceptable".
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt
from scipy import signal

FRAME = 1024
HOP = 512
BANDS = 24
MIN_BPM, MAX_BPM = 60.0, 180.0
ONSET_DELAY = FRAME - HOP  # samples: a frame's flux rises when the onset enters its window
ZERO_SEARCH = 0.005  # seconds around a cut point to look for a zero crossing
CONFIDENT_TEMPO = 0.3
PRIOR_BPM = 120.0
MAX_LOOP_SECONDS = 40.0
SEAM_WINDOW = 1.0  # seconds on each side of a seam where the two passes must agree, without a beat
Audio = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Tempo:
    bpm: float | None
    confidence: float
    """0..1: how clear the periodicity of the onsets is (below 0.3 there is no usable beat)."""
    beats: list[float] = field(default_factory=list)
    """Beat times in seconds (empty without a usable beat)."""


@dataclass(frozen=True, slots=True)
class Loop:
    start: float
    end: float
    score: float
    """0..1: how invisible the jump from ``end`` back to ``start`` is."""
    crossfade: float
    """Suggested crossfade at the seam, seconds (0: none needed)."""
    bars: int | None = None

    @property
    def seconds(self) -> float:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class Ending:
    start: float
    """Where the ending (the last phrase before the fall) starts."""
    tail: float
    """Where the level starts falling for good."""
    end: float
    """The last sample with sound (above -60 dBFS)."""


@dataclass(frozen=True, slots=True)
class MusicAnalysis:
    seconds: float
    tempo: Tempo
    loops: list[Loop]
    ending: Ending | None


def mono(data: Audio) -> Audio:
    return data.mean(axis=1) if data.ndim == 2 else data


def spectrogram(x: Audio) -> Audio:
    """Magnitude spectrogram, frames in rows."""
    if len(x) < FRAME:
        return np.zeros((0, FRAME // 2 + 1))
    windows = np.lib.stride_tricks.sliding_window_view(x, FRAME)[::HOP] * np.hanning(FRAME)
    return np.asarray(np.abs(np.fft.rfft(windows, axis=1)), dtype=np.float64)


def onset_strength(spec: Audio) -> Audio:
    """Positive spectral flux of the log spectrogram, per frame."""
    if len(spec) < 2:
        return np.zeros(len(spec))
    log = np.log1p(100 * spec)
    flux = np.maximum(np.diff(log, axis=0), 0).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    return np.asarray(flux - np.convolve(flux, np.ones(16) / 16, mode="same"), dtype=np.float64).clip(min=0)


def estimate_tempo(x: Audio, rate: int) -> Tempo:
    spec = spectrogram(x)
    onset = onset_strength(spec)
    fps = rate / HOP
    if len(onset) < fps * 4 or not np.any(onset):
        return Tempo(None, 0.0)
    centred = onset - onset.mean()
    corr = signal.correlate(centred, centred, mode="full", method="fft")[len(centred) - 1 :]
    corr /= corr[0] if corr[0] > 0 else 1.0
    lags = np.arange(len(corr))
    usable = (lags >= fps * 60 / MAX_BPM) & (lags <= fps * 60 / MIN_BPM)
    if not usable.any():
        return Tempo(None, 0.0)
    # A tempo and its half or double correlate alike; weigh by a prior around 120 BPM (one octave wide), as
    # most music sits there. A strong half-time accent still wins (TW-1617: a march at 129 BPM correlates 0.69
    # at 64 and 0.32 at 129); its bars are then twice as long, which keeps loop lengths in whole bars.
    candidates = lags[usable]
    prior = np.exp(-0.5 * np.log2((60 * fps / candidates) / PRIOR_BPM) ** 2)
    best = int(candidates[np.argmax(corr[usable] * prior)])
    confidence = float(max(0.0, corr[best]))
    # refine the period with a parabola through the peak
    if 0 < best < len(corr) - 1:
        a, b, c = corr[best - 1], corr[best], corr[best + 1]
        shift = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
        period = (best + shift) / fps
    else:
        period = best / fps
    bpm = 60.0 / period
    if confidence < CONFIDENT_TEMPO:
        return Tempo(round(bpm, 2), round(confidence, 3))
    # phase: the offset whose comb collects the most onset strength
    step = period * fps
    phases = np.arange(0, step, 0.5)
    sums = [onset[np.arange(p, len(onset), step).astype(int)].sum() for p in phases]
    first = phases[int(np.argmax(sums))]
    # then the grid is fitted to the onset peaks near each beat (a straight line: period and phase together)
    frames = np.arange(first, len(onset), step)
    reach = max(1, int(step / 4))
    peaks = []
    for index, frame in enumerate(frames):
        lo, hi = max(0, int(frame) - reach), min(len(onset), int(frame) + reach + 1)
        window = onset[lo:hi]
        if window.size and window.max() > 0:
            peaks.append((index, lo + int(np.argmax(window))))
    if len(peaks) >= 4:
        idx, pos = np.array(peaks, dtype=np.float64).T
        slope, intercept = np.polyfit(idx, pos, 1)
        step, first = float(slope), float(intercept)
    period = step / fps
    bpm = 60.0 / period
    start = first / fps + ONSET_DELAY / rate
    beats = list(np.arange(start % period, len(x) / rate, period))
    return Tempo(round(bpm, 2), round(confidence, 3), [round(float(b), 4) for b in beats])


def band_features(spec: Audio, rate: int) -> Audio:
    """Log energy in BANDS log-spaced bands per frame."""
    freqs = np.fft.rfftfreq(FRAME, 1 / rate)
    edges = np.geomspace(40.0, min(16000.0, rate / 2), BANDS + 1)
    power = spec**2
    bands = np.stack(
        [power[:, (freqs >= lo) & (freqs < hi)].sum(axis=1) for lo, hi in itertools.pairwise(edges)],
        axis=1,
    )
    return np.asarray(np.log10(bands + 1e-10), dtype=np.float64)


def chroma_features(spec: Audio, rate: int) -> Audio:
    """Energy per pitch class (C, C#, ... B) per frame, from the spectrum between 55 Hz and 5 kHz."""
    freqs = np.fft.rfftfreq(FRAME, 1 / rate)
    usable = (freqs >= 55.0) & (freqs <= 5000.0)
    classes = np.round(12 * np.log2(freqs[usable] / 440.0)).astype(int) % 12
    power = spec[:, usable] ** 2
    out = np.zeros((len(spec), 12))
    for pitch in range(12):
        out[:, pitch] = power[:, classes == pitch].sum(axis=1)
    return np.asarray(np.sqrt(out), dtype=np.float64)


def nearest_zero(x: Audio, rate: int, at: float) -> float:
    """``at`` moved to the nearest zero crossing within ZERO_SEARCH seconds (or kept)."""
    centre = round(at * rate)
    reach = round(ZERO_SEARCH * rate)
    lo, hi = max(1, centre - reach), min(len(x) - 1, centre + reach)
    if hi <= lo:
        return at
    seg = x[lo - 1 : hi]
    crossings = np.flatnonzero(np.signbit(seg[:-1]) != np.signbit(seg[1:])) + lo
    if len(crossings) == 0:
        return at
    return float(crossings[np.argmin(np.abs(crossings - centre))] / rate)


def refine_end(x: Audio, rate: int, start: float, end: float) -> float:
    """``end`` moved so the audio after it lines up with the audio after ``start``: first the envelopes
    (within 80 ms, the rhythm), then the waveforms (within 3 ms, the phase)."""
    envelope = np.abs(signal.hilbert(x))
    envelope = signal.sosfiltfilt(signal.butter(2, 40, fs=rate, output="sos"), envelope)

    def best(curve: Audio, at: float, reach: float, length: float) -> float:
        ref = curve[round(start * rate) : round((start + length) * rate)]
        lo = max(0, round((at - reach) * rate))
        seg = curve[lo : round((at + reach + length) * rate)]
        if len(ref) < 2 or len(seg) <= len(ref):
            return at
        corr = signal.correlate(seg - seg.mean(), ref - ref.mean(), mode="valid", method="fft")
        return float((lo + int(np.argmax(corr))) / rate)

    coarse = best(envelope, end, 0.08, 2.0)
    return round(best(x, coarse, 0.003, 0.5), 5)


def find_loops(
    x: Audio,
    rate: int,
    tempo: Tempo,
    *,
    before: float | None = None,
    min_seconds: float = 4.0,
    top: int = 5,
) -> list[Loop]:
    """The best loop candidates before ``before``: for each repetition lag (whole bars when there is a beat),
    the point where the two passes agree best within SEAM_WINDOW, and the end lined up with the start.

    Agreement is the lower of the timbre and the harmony similarities, frame by frame, averaged over the
    window: a seam is only as good as the worse of the two."""
    spec = spectrogram(x)
    if len(spec) == 0:
        return []
    fps = rate / HOP
    timbre = _normalised(band_features(spec, rate))
    harmony = _normalised(chroma_features(spec, rate))
    usable = len(spec) if before is None else min(len(spec), int(before * fps))
    bar = 4 * 60 / tempo.bpm if tempo.beats and tempo.bpm else None
    # The seam goes where the passes agree best within 1 s (the seams the user approved by ear, TW-1617); the
    # loop is ranked by the agreement over a bar on each side of that point, which catches a jump between two
    # equal chords that would drop the rest of a progression (it scored 1.0 within 1 s).
    near = max(1, round(SEAM_WINDOW * fps))
    half = max(near, round((bar or SEAM_WINDOW) * fps))
    if bar:
        lags = [round(k * bar * fps) for k in range(1, int(MAX_LOOP_SECONDS / bar) + 1) if k * bar >= min_seconds]
    else:
        lags = list(range(round(min_seconds * fps), round(MAX_LOOP_SECONDS * fps), max(1, round(fps / 4))))
    found: list[tuple[float, int, int]] = []
    for lag in lags:
        count = usable - lag
        if count <= 2 * half:
            continue
        agree = np.minimum(
            np.sum(timbre[:count] * timbre[lag : lag + count], axis=1),
            np.sum(harmony[:count] * harmony[lag : lag + count], axis=1),
        )
        local = np.convolve(agree, np.ones(2 * near) / (2 * near), mode="same")
        wide = np.convolve(agree, np.ones(2 * half) / (2 * half), mode="same")
        point = half + int(np.argmax(local[half:-half]))
        found.append((float(wide[point]), lag, point))
    found.sort(key=lambda f: (-round(f[0], 2), f[1]))  # the best seams first; on a tie, the shortest loop
    beat = 60 / tempo.bpm if tempo.beats and tempo.bpm else None
    fade = round(beat / 2, 3) if beat else 0.1
    loops: list[Loop] = []
    for score, lag, point in found:
        start = point / fps
        end = refine_end(x, rate, start, start + lag / fps)
        if all(abs(start - o.start) > 1.0 or abs(end - o.end) > 1.0 for o in loops):
            loops.append(Loop(round(start, 5), end, round(max(0.0, score), 3), fade,
                              round((lag / fps) / bar) if bar else None))  # fmt: skip
        if len(loops) == top:
            break
    return loops


def _normalised(features: Audio) -> Audio:
    centred = features - features.mean(axis=1, keepdims=True)
    norms = np.linalg.norm(centred, axis=1, keepdims=True)
    return np.asarray(centred / np.where(norms > 0, norms, 1.0), dtype=np.float64)


def find_ending(x: Audio, rate: int, tempo: Tempo) -> Ending | None:
    """The last phrase and the tail where the level falls for good."""
    window = round(0.1 * rate)
    count = len(x) // window
    if count < 10:
        return None
    rms = np.sqrt(np.mean(x[: count * window].reshape(count, window) ** 2, axis=1))
    level = 20 * np.log10(np.maximum(rms, 1e-12))
    audible = level > -60
    if not audible.any():
        return None
    last = int(np.flatnonzero(audible)[-1])
    typical = float(np.median(level[audible]))
    loud = np.flatnonzero(level[: last + 1] >= typical - 10)
    if len(loud) == 0:
        return None
    tail = (int(loud[-1]) + 1) * 0.1
    bar = 4 * 60 / tempo.bpm if tempo.beats and tempo.bpm else 2.0
    starts = [b for b in tempo.beats[::4] if b <= tail - bar] if tempo.beats else []
    start = starts[-1] if starts else max(0.0, tail - bar)
    return Ending(round(start, 3), round(tail, 3), round((last + 1) * 0.1, 3))


def analyze(data: Audio, rate: int, *, top: int = 5) -> MusicAnalysis:
    x = mono(np.asarray(data, dtype=np.float64))
    tempo = estimate_tempo(x, rate)
    ending = find_ending(x, rate, tempo)
    loops = find_loops(x, rate, tempo, before=ending.start if ending else None, top=top)
    return MusicAnalysis(len(x) / rate, tempo, loops, ending)


@dataclass(frozen=True, slots=True)
class BedPlan:
    pieces: list[tuple[float, float]]
    """Source spans in order: the intro, the repeats of the loop, the ending."""
    seconds: float
    repeats: int
    crossfade: float


def plan_bed(
    loop: Loop,
    total: float,
    target: float,
    *,
    ending_start: float | None = None,
    crossfade: float | None = None,
) -> BedPlan:
    """A bed the nearest to ``target`` seconds without going over (never stretched).

    By default the music plays to the end of the loop, goes back to its start as many times as fit, and on the
    last pass carries on to the end of the file: the only artificial seams are the loop's own (TW-1617: the
    user found that clearly better than jumping to a separate ending). With ``ending_start`` the last pass
    jumps there instead. Each seam overlaps its two pieces by the crossfade."""
    if ending_start is not None and ending_start < loop.end:
        raise ValueError("the ending starts inside the loop: choose an earlier loop or a later ending")
    fade = loop.crossfade if crossfade is None else crossfade

    def build(repeats: int) -> list[tuple[float, float]]:
        if ending_start is None:
            if repeats == 0:
                return [(0.0, total)]
            return [(0.0, loop.end), *([(loop.start, loop.end)] * (repeats - 1)), (loop.start, total)]
        intro = [(0.0, loop.start)] if loop.start > 0 else []
        return [*intro, *([(loop.start, loop.end)] * repeats), (ending_start, total)]

    def length(pieces: list[tuple[float, float]]) -> float:
        return sum(b - a for a, b in pieces) - fade * (len(pieces) - 1)

    repeats = 0
    while length(build(repeats + 1)) <= target + 1e-9:
        repeats += 1
    pieces = build(repeats)
    return BedPlan(pieces=pieces, seconds=round(length(pieces), 3), repeats=repeats, crossfade=fade)


def render_bed(data: Audio, rate: int, plan: BedPlan) -> Audio:
    """The pieces joined with equal-power crossfades of ``plan.crossfade`` at every seam."""
    audio = np.asarray(data, dtype=np.float64)
    if audio.ndim == 1:
        audio = audio[:, None]
    fade = round(plan.crossfade * rate)
    out = np.zeros((0, audio.shape[1]))
    for start, end in plan.pieces:
        piece = audio[round(start * rate) : round(end * rate)]
        if len(out) == 0 or fade == 0 or len(piece) < fade or len(out) < fade:
            out = np.concatenate([out, piece])
            continue
        t = np.linspace(0, np.pi / 2, fade)[:, None]
        overlap = out[-fade:] * np.cos(t) + piece[:fade] * np.sin(t)
        out = np.concatenate([out[:-fade], overlap, piece[fade:]])
    return out
