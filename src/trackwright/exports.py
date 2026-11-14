"""Find the audio files Cubase exported (TW-1204). Only metadata is read: name, size, time and duration.

The duration comes from macOS ``afinfo`` ("estimated duration: 27.991125 sec"), which reads the file header.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

AUDIO_SUFFIXES = frozenset({".wav", ".mp3", ".aif", ".aiff", ".flac", ".ogg", ".m4a", ".wv"})
PROJECT_SUFFIXES = frozenset({".cpr"})
DURATION = re.compile(r"estimated duration:\s*([0-9.]+)\s*sec")
Output = Callable[[Sequence[str]], str]


def _afinfo(argv: Sequence[str]) -> str:
    try:
        result = subprocess.run(list(argv), capture_output=True, check=False, text=True, timeout=15)  # noqa: S603
    except subprocess.TimeoutExpired:  # I-09: an unknown duration, not a crash
        return ""
    return result.stdout


@dataclass(frozen=True)
class ExportedFile:
    path: str
    size_bytes: int
    modified: float
    duration_seconds: float | None


class ExportInspector:
    def __init__(self, *, output: Output = _afinfo) -> None:
        self._output = output

    def duration(self, path: Path) -> float | None:
        match = DURATION.search(self._output(["/usr/bin/afinfo", str(path.resolve())]))  # I-13: never an option
        return float(match.group(1)) if match else None

    def find(self, folder: Path, since: float, suffixes: frozenset[str] = AUDIO_SUFFIXES) -> list[ExportedFile]:
        """Files with ``suffixes`` directly in ``folder`` modified at or after ``since`` (epoch seconds), newest
        first. Audio files also get their duration; nothing else is read."""
        if not folder.is_dir():
            return []
        found = []
        for entry in folder.iterdir():
            if entry.suffix.lower() not in suffixes or not entry.is_file():
                continue
            info = entry.stat()
            if info.st_mtime >= since - 1.0:
                duration = self.duration(entry) if entry.suffix.lower() in AUDIO_SUFFIXES else None
                found.append(ExportedFile(str(entry), info.st_size, info.st_mtime, duration))
        return sorted(found, key=lambda f: f.modified, reverse=True)
