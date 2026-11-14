"""Write policy: what the MCP server may change, configured by the user.

- ``[writes] enabled = false`` (default): every project modification fails with ``WRITES_DISABLED``.
  Dry runs always work, and so does *navigation* (selecting a track, moving the cursor), which
  does not modify the project.
- ``allowed_tracks``: when not empty, only those track names may be modified (``NOT_ALLOWED``).
  Operations that can change any track (range edits on every track, Cubase commands acting on the
  window selection) are refused while it is set.
- ``save``: saving the project file needs its own switch (``SAVE_DISABLED``), on top of ``enabled``.

It also carries ``[analysis]`` (TW-1502): reading the samples of an audio file is off by default
(``ANALYSIS_DISABLED``) and limited in duration (``TOO_LONG``). It is independent of ``[writes]``: analysis
changes nothing in Cubase.
"""

from __future__ import annotations

from dataclasses import dataclass

from trackwright.config import AnalysisConfig, WritesConfig
from trackwright.errors import PolicyError, PreconditionFailedError


@dataclass(frozen=True, slots=True)
class WritePolicy:
    enabled: bool = False
    allowed_tracks: tuple[str, ...] = ()
    save: bool = False
    analysis: bool = False
    analysis_max_seconds: float = AnalysisConfig().max_seconds

    @classmethod
    def from_config(cls, config: WritesConfig, analysis: AnalysisConfig | None = None) -> WritePolicy:
        reading = analysis or AnalysisConfig()
        return cls(
            enabled=config.enabled,
            allowed_tracks=config.allowed_tracks,
            save=config.save,
            analysis=reading.enabled,
            analysis_max_seconds=reading.max_seconds,
        )

    def check_analysis(self, seconds: float | None = None) -> None:
        """Raise unless reading audio is allowed and a file of ``seconds`` is within the limit."""
        if not self.analysis:
            raise PolicyError(
                "audio analysis is disabled; set [analysis] enabled = true in the Trackwright configuration",
                code="ANALYSIS_DISABLED",
            )
        if seconds is not None and seconds > self.analysis_max_seconds:
            raise PreconditionFailedError(
                f"the file lasts {seconds:.0f} s, longer than [analysis] max_seconds "
                f"({self.analysis_max_seconds:.0f} s)",
                code="TOO_LONG",
                details={"seconds": seconds, "max_seconds": self.analysis_max_seconds},
            )

    def check_save(self) -> None:
        """Raise unless saving the project file is allowed."""
        self.check_project_write()
        if not self.save:
            raise PolicyError(
                "saving is disabled; set [writes] save = true in the Trackwright configuration "
                "(dry runs work without it)",
                code="SAVE_DISABLED",
            )

    def check_project_write(self) -> None:
        """Raise unless project modifications are enabled."""
        if not self.enabled:
            raise PolicyError(
                "writes are disabled; set [writes] enabled = true in the Trackwright configuration "
                "(dry runs work without it)",
                code="WRITES_DISABLED",
            )

    def check_track(self, track_name: str | None) -> None:
        """Raise unless writes are enabled and ``track_name`` may be modified."""
        self.check_project_write()
        if self.allowed_tracks and track_name not in self.allowed_tracks:
            raise PolicyError(
                f"track {track_name!r} is not in [writes] allowed_tracks",
                code="NOT_ALLOWED",
                details={"track": track_name, "allowed_tracks": list(self.allowed_tracks)},
            )

    def check_all_tracks(self, action: str) -> None:
        """Raise unless writes are enabled and ``action``, which can change any track, is allowed."""
        self.check_project_write()
        if self.allowed_tracks:
            raise PolicyError(
                f"{action} can change any track, so it is refused while [writes] allowed_tracks is set",
                code="NOT_ALLOWED",
                details={"allowed_tracks": list(self.allowed_tracks)},
            )

    def describe(self) -> dict[str, object]:
        return {
            "writes_enabled": self.enabled,
            "allowed_tracks": list(self.allowed_tracks),
            "save": self.save,
            "analysis_enabled": self.analysis,
        }
