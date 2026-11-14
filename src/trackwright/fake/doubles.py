"""Test doubles for the launcher and the export inspector."""

from __future__ import annotations

from trackwright.fake.reads import FakeCubase


class FakeLauncher:
    """Opens the simulated Cubase: ``launch`` brings the script online after ``answers_after`` polls."""

    app = "Cubase 15 (simulated)"
    launch_timeout = 5.0

    def __init__(self, cubase: FakeCubase, *, running: bool = True, answers_after: int = 1) -> None:
        self.cubase = cubase
        self.running = running
        self.answers_after = answers_after
        self.launched: list[object] = []

    def is_running(self) -> bool:
        return self.running

    def project_folders(self) -> list[str]:
        return ["/Projects/Demo"] if self.running else []

    def launch(self, project: object = None) -> None:
        self.launched.append(project)
        self.running = True
        if self.answers_after >= 0:
            self.cubase.online = True


class FakeExports:
    """Export folder for the simulator: ``files`` are returned by ``find`` (no disk access)."""

    def __init__(self) -> None:
        from trackwright.exports import ExportedFile  # noqa: PLC0415

        self.files: list[ExportedFile] = []
        self._file = ExportedFile
        self.searched: list[tuple[object, float]] = []
        self.durations: dict[str, float] = {}

    def add(self, path: str, duration: float | None, *, modified: float = 2e9, size: int = 1000) -> None:
        self.files.append(self._file(path, size, modified, duration))

    def duration(self, path: object) -> float | None:
        return self.durations.get(str(path))

    def find(self, folder: object, since: float, suffixes: frozenset[str] | None = None) -> list[object]:
        self.searched.append((folder, since))
        return sorted(
            (f for f in self.files
             if f.modified >= since - 1.0 and (suffixes is None or any(f.path.lower().endswith(x) for x in suffixes))),
            key=lambda f: f.modified,  # type: ignore[attr-defined]
            reverse=True,
        )  # fmt: skip
