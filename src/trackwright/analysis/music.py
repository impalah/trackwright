"""Music beds (TW-1617): tempo and beats, repeated sections, loop candidates, the ending, and a bed of a given
length that keeps the ending. Pure numpy and scipy; no time stretch, ever.

1. **Onsets and tempo.** Spectral flux of the magnitude spectrogram (frames of 1024 samples, hop 512) is the
   onset strength; its autocorrelation gives the beat period between 60 and 180 BPM; the beat phase is the one
   whose comb of beats collects the most onset strength. Beats are then evenly spaced at that period (a bed
   rarely changes tempo); ``tempo_confidence`` says how clear the periodicity was (ambient material has none,
   and then loops fall back to whole seconds instead of beats).
2. **Features.** Log energy in 24 bands (timbre) and energy in the 12 pitch classes (chroma, 55 Hz-5 kHz) per
   frame, averaged per beat (or per half second without a beat), each vector normalised.
3. **Loop candidates** (all before the ending). A loop ``[a, b)`` is good when the music just after ``b``
   would continue like the music just after ``a`` (the jump back is musically invisible): its seam score
   compares the beats after ``b`` with those after ``a``, and those before ``b`` with those before ``a``, in
   timbre (the bands) and in harmony (chroma: energy per pitch class); the lower of the two counts, so a jump
   between two chords that sound alike in timbre is still caught. Lengths are whole bars (4 beats) when
   there is a beat. The cut points move to the nearest zero
   crossing (of the channels' sum) within 5 ms, so a seam needs at most a short crossfade.
4. **Crossfade.** A suggestion from the level jump at the seam: none for a seam that matches, longer when the
   two sides differ (10 ms to one beat).
5. **Ending.** The tail is where the level falls for good below the music's typical level minus 10 dB; the
   ending starts at the beginning of the last bar (or the last two seconds) before that fall.
6. **Bed.** ``intro [0, a)`` + n x ``[a, b)`` + ``ending [e, end]`` with equal-power crossfades at the seams;
   n is chosen so the length is the nearest to the target without going over (the difference is reported).
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
    best = int(lags[usable][np.argmax(corr[usable])])
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


def unit_features(features: Audio, times: Audio, grid: list[float]) -> Audio:
    """Mean features between consecutive grid points, each row normalised (zero mean, unit length)."""
    rows = []
    for a, b in itertools.pairwise(grid):
        inside = (times >= a) & (times < b)
        rows.append(features[inside].mean(axis=0) if inside.any() else np.zeros(features.shape[1]))
    out = np.asarray(rows, dtype=np.float64)
    out -= out.mean(axis=1, keepdims=True)
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    return np.asarray(out / np.where(norms > 0, norms, 1.0), dtype=np.float64)


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


def _level_db(x: Audio, rate: int, at: float, width: float = 0.05) -> float:
    a, b = max(0, round((at - width) * rate)), min(len(x), round((at + width) * rate))
    seg = x[a:b]
    rms = float(np.sqrt(np.mean(seg**2))) if len(seg) else 0.0
    return 20 * np.log10(rms) if rms > 0 else -240.0


def find_loops(
    x: Audio,
    rate: int,
    tempo: Tempo,
    *,
    before: float | None = None,
    min_seconds: float = 4.0,
    context: int = 4,
    top: int = 5,
) -> list[Loop]:
    """The best loop candidates, each a whole number of bars (or seconds without a beat)."""
    spec = spectrogram(x)
    if len(spec) == 0:
        return []
    times = (np.arange(len(spec)) * HOP + FRAME / 2) / rate
    beat = tempo.beats or None
    grid = list(beat) if beat else list(np.arange(0.0, len(x) / rate, 0.5))
    if before is not None:
        grid = [g for g in grid if g <= before]
    if len(grid) < 2:
        return []
    timbre = unit_features(band_features(spec, rate), times, grid)
    harmony = unit_features(chroma_features(spec, rate), times, grid)
    unit = 4 if beat else 2  # a bar of beats, or a second of half-seconds
    candidates: list[Loop] = []
    n = len(timbre)

    def similar(feats: Audio, i: int, j: int) -> float:
        after = float(np.mean(np.sum(feats[j : j + context] * feats[i : i + context], axis=1)))
        before = float(np.mean(np.sum(feats[j - context : j] * feats[i - context : i], axis=1)))
        return (after + before) / 2

    per_second = tempo.bpm / 60 if beat and tempo.bpm else 2.0
    shortest = unit * max(1, int(np.ceil(min_seconds * per_second / unit)))  # whole bars (or seconds) only
    for i in range(context, n - context):
        for j in range(i + shortest, n - context, unit):
            score = min(similar(timbre, i, j), similar(harmony, i, j))
            if score > 0.5:
                start, end = nearest_zero(x, rate, grid[i]), nearest_zero(x, rate, grid[j])
                jump = abs(_level_db(x, rate, end) - _level_db(x, rate, start))
                period = 60 / tempo.bpm if beat and tempo.bpm else 0.5
                crossfade = 0.0 if score > 0.95 and jump < 1 else round(min(period, 0.01 + jump * 0.02), 3)
                candidates.append(Loop(round(start, 4), round(end, 4), round(score, 3), float(crossfade),
                                       (j - i) // 4 if beat else None))  # fmt: skip
    # the best seams first; among equally good ones the shortest, which fits a target length more finely
    candidates.sort(key=lambda c: (-round(c.score, 2), c.seconds))
    chosen: list[Loop] = []
    for c in candidates:  # keep distinct ones
        if all(abs(c.start - o.start) > 1.0 or abs(c.end - o.end) > 1.0 for o in chosen):
            chosen.append(c)
        if len(chosen) == top:
            break
    return chosen


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


def plan_bed(loop: Loop, ending: Ending, total: float, target: float, *, crossfade: float | None = None) -> BedPlan:
    """Intro + n loops + ending, the nearest to ``target`` seconds without going over (never stretched).

    Each seam between two pieces overlaps them by the crossfade, so the length is the sum of the pieces
    minus one crossfade per seam."""
    if ending.start < loop.end:
        raise ValueError("the ending starts inside the loop: choose an earlier loop or a later ending")
    fade = loop.crossfade if crossfade is None else crossfade

    def build(repeats: int) -> list[tuple[float, float]]:
        intro = [(0.0, loop.start)] if loop.start > 0 else []
        return [*intro, *([(loop.start, loop.end)] * repeats), (ending.start, total)]

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
