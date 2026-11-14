"""Time and event helpers of the simulated project (bars, seconds, range edits)."""

from __future__ import annotations


def _bars_to_beats(time: str, meter: tuple[int, int]) -> float:
    bar, beat, sixteenth, ticks = (int(part) for part in time.replace(".", " ").split())
    beat_length = 4 / meter[1]
    return (bar - 1) * meter[0] * beat_length + (beat - 1) * beat_length + (sixteenth - 1) / 4 + ticks / 480


def _beats_to_bars(beats: float, meter: tuple[int, int]) -> str:
    beat_length = 4 / meter[1]
    bar, rest = divmod(beats, meter[0] * beat_length)
    beat, rest = divmod(rest, beat_length)
    sixteenth, rest = divmod(rest, 0.25)
    return f"{int(bar) + 1}. {int(beat) + 1}. {int(sixteenth) + 1}.{round(rest * 480):>3}"


def _bars(time: str) -> tuple[int, ...]:
    return tuple(int(part) for part in time.replace(".", " ").split())


def _parse_seconds(time: str) -> float:
    hours, minutes, seconds = time.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _format_seconds(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    return f"{hours}:{minutes:02d}:{rest // 1000:02d}.{rest % 1000:03d}"


def _edit_events(events: list[tuple[float, float]], key: str, start: float, end: float) -> list[tuple[float, float]]:
    """What each range command does to one track's events (verified in Cubase, TW-1211)."""
    gap = end - start
    out: list[tuple[float, float]] = []
    for a, b in events:
        if key == "edit.crop_range":
            if b > start and a < end:
                out.append((max(a, start), min(b, end)))
        elif key == "edit.insert_silence":
            if b <= start:
                out.append((a, b))
            elif a >= start:
                out.append((a + gap, b + gap))
            else:
                out += [(a, start), (start + gap, b + gap)]
        else:  # delete keeps a hole; delete_time / cut_time close it
            shift = gap if key != "edit.delete" else 0.0
            if a < start:
                out.append((a, min(b, start)))
            if b > end:
                out.append((max(a, end) - shift, b - shift))
    return out
