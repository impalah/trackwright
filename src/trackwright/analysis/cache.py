"""Analyses tied to an audio version (TW-1608): the file's identity and a cache of results.

Every analysis says which file it measured: its path, size, modification time and SHA-256, and the project
range it covers. Results are cached in ``Trackwright/analysis/`` under a key made of the analysis kind, the
file's SHA-256 and the parameters, so the same question about the same audio is answered without reading it
again, and a re-export (new bytes) is never confused with the old one.

Hashing a long episode takes about as long as analyzing it, so ``hashes.json`` remembers the hash of each
file by path, size and modification time (nanoseconds); a file that changed in any of them is hashed again.
Writing needs the caller's permission (``writable``); a read-only cache still answers from what is there.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from trackwright.jsontypes import JsonObject
from trackwright.workspace import atomic_write

HASHES = "hashes.json"
CACHE_VERSION = 1


@dataclass(frozen=True, slots=True)
class FileIdentity:
    path: str
    size: int
    modified_ns: int
    sha256: str

    @property
    def modified(self) -> float:
        return self.modified_ns / 1e9


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_key(kind: str, sha256: str, parameters: JsonObject) -> str:
    canonical = json.dumps({"v": CACHE_VERSION, "kind": kind, "sha": sha256, "p": parameters}, sort_keys=True)
    return f"{kind}-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:20]}"


class AnalysisCache:
    """``Trackwright/analysis/``: one JSON file per result, plus the remembered hashes."""

    def __init__(self, folder: Path | None, *, writable: bool) -> None:
        self.folder = folder if folder is not None and folder.is_dir() else None
        self.writable = writable and self.folder is not None

    def _hashes(self) -> dict[str, Any]:
        if self.folder is None:
            return {}
        try:
            data = json.loads((self.folder / HASHES).read_text(encoding="utf-8"))
        except OSError, ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def identify(self, path: Path) -> FileIdentity:
        """The file's identity; its SHA-256 from ``hashes.json`` when size and mtime have not changed."""
        stat = path.stat()
        known = self._hashes()
        entry = known.get(str(path))
        if isinstance(entry, dict) and entry.get("size") == stat.st_size and entry.get("mtime_ns") == stat.st_mtime_ns:
            sha = entry.get("sha256")
            if isinstance(sha, str) and len(sha) == 64:
                return FileIdentity(str(path), stat.st_size, stat.st_mtime_ns, sha)
        sha = _sha256(path)
        if self.writable and self.folder is not None:
            known[str(path)] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": sha}
            atomic_write(self.folder / HASHES, (json.dumps(known, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        return FileIdentity(str(path), stat.st_size, stat.st_mtime_ns, sha)

    def get(self, key: str) -> JsonObject | None:
        if self.folder is None:
            return None
        try:
            data = json.loads((self.folder / f"{key}.json").read_text(encoding="utf-8"))
        except OSError, ValueError:
            return None
        if (
            not isinstance(data, dict)
            or data.get("version") != CACHE_VERSION
            or not isinstance(data.get("result"), dict)
        ):
            return None
        result: JsonObject = data["result"]
        return result

    def put(self, key: str, result: JsonObject) -> Path | None:
        if not self.writable or self.folder is None:
            return None
        path = self.folder / f"{key}.json"
        payload = {"version": CACHE_VERSION, "result": result}
        atomic_write(path, (json.dumps(payload, indent=1) + "\n").encode("utf-8"))
        return path


def load_cached[T](cache: AnalysisCache, key: str, model: type[T]) -> T | None:
    """A cached result validated as ``model``; a result that no longer validates is ignored."""
    raw = cache.get(key)
    if raw is None:
        return None
    try:
        return model.model_validate(raw)  # type: ignore[attr-defined, no-any-return]
    except ValidationError:
        return None
