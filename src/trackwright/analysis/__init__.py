"""Audio analysis (TW-1503): window levels, noise floor and silences of an audio file.

Cubase's MIDI Remote API cannot read track contents, so silences and noise are measured on a file the user
exported (TW-1501: an export between the locators is aligned with the project to the sample). This package
knows nothing about Cubase: times are seconds from the start of the file.

- :func:`probe` reads only the header (format, rate, channels, duration), so limits are checked first.
- :func:`measure` reads the samples in blocks and keeps one RMS level per window: memory grows with the
  number of windows (50 per second), not with the file.
- :func:`noise_floor` and :func:`find_silences` work on those levels and are pure.
"""

from trackwright.analysis.detect import Silence, SilenceCriteria, find_silences, noise_floor, sound_levels
from trackwright.analysis.reader import AudioInfo, Levels, measure, probe

__all__ = [
    "AudioInfo",
    "Levels",
    "Silence",
    "SilenceCriteria",
    "find_silences",
    "measure",
    "noise_floor",
    "probe",
    "sound_levels",
]
