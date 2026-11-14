"""Time formats of Cubase's displays (C-22): bars ("3. 1. 1.  0") and seconds ("0:01:30.250").

Pure functions, shared by every mixin; no Cubase access.
"""

from __future__ import annotations

import re

SECONDS_TOLERANCE = 0.0015
CLOCK = re.compile(r"^\s*(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d+)?)\s*$")


def parse_seconds(text: str) -> float | None:
    """'2', '2.5', '1:30', '0:01:30.250' → seconds; ``None`` when it is not a time."""
    match = CLOCK.match(text)
    if match is None:
        return None
    first, second, seconds = match.groups()
    hours, minutes = (first, second) if second is not None else (None, first)
    return int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(seconds)


def format_seconds(seconds: float) -> str:
    """Seconds → 'h:mm:ss.mmm', the format of Cubase's seconds display."""
    millis = round(max(seconds, 0.0) * 1000)
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    return f"{hours}:{minutes:02d}:{rest // 1000:02d}.{rest % 1000:03d}"


BARS_RE = re.compile(r"^\s*(\d+)\s*\.\s*(\d+)\s*\.\s*(\d+)\s*\.\s*(\d+)\s*$")


def bars_tuple(text: str) -> tuple[int, int, int, int] | None:
    match = BARS_RE.match(text)
    if not match:
        return None
    bar, beat, sixteenth, ticks = (int(g) for g in match.groups())
    return bar, beat, sixteenth, ticks


def format_bars(position: tuple[int, int, int, int]) -> str:
    """Cubase's own rendering, e.g. ``"3. 1. 1.  0"`` (ticks right-aligned on three characters)."""
    bar, beat, sixteenth, ticks = position
    return f"{bar}. {beat}. {sixteenth}.{ticks:>3}"
