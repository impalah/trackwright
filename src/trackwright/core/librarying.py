"""The licensed audio library tool (TW-1620): search the user's sounds and check their sidecars.

Read-only; the folders come from ``[library] folders``. Only sidecars and file headers are read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from trackwright.core.base import ServiceBase
from trackwright.core.models import LibraryItemOut, LibraryOut
from trackwright.errors import PreconditionFailedError
from trackwright.library import Item, scan, search

MAX_ITEMS = 200


def item_out(item: Item) -> LibraryItemOut:
    s = item.sidecar
    return LibraryItemOut(
        file=str(item.path), title=s.title, kind=s.kind,
        seconds=round(item.seconds, 3) if item.seconds is not None else None, license=s.license,
        license_url=s.license_url, source=s.source, attribution=s.attribution, allowed_uses=s.allowed_uses,
        restrictions=s.restrictions, tags=s.tags,
    )  # fmt: skip


class LibraryMixin(ServiceBase):
    def library(
        self,
        action: Literal["search", "check"] = "search",
        *,
        query: str = "",
        kind: str | None = None,
        use: str | None = None,
        min_seconds: float | None = None,
        max_seconds: float | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> LibraryOut:
        if action not in ("search", "check"):
            raise PreconditionFailedError("action must be 'search' or 'check'", code="BAD_REQUEST")
        folders = [Path(f).expanduser() for f in self._library_folders]
        if not folders:
            raise PreconditionFailedError(
                'no library folders: add [library] folders = ["…"] to the Trackwright configuration',
                code="NO_LIBRARY",
            )
        items, problems = scan(folders)
        out = LibraryOut(action=action, folders=[str(f) for f in folders], total=len(items),
                         missing_folders=[str(p) for p in problems.missing_folders])  # fmt: skip
        if action == "check":
            out.no_sidecar = [str(p) for p in problems.no_sidecar]
            out.invalid = {str(k): v for k, v in problems.invalid.items()}
            out.orphan_sidecars = [str(p) for p in problems.orphan_sidecars]
            left_out = len(problems.no_sidecar) + len(problems.invalid)
            if left_out:
                out.notes.append(f"{left_out} sounds are not offered until their sidecar names a licence "
                                 "(`trackwright library template <file>` prints one to fill in)")  # fmt: skip
            return out
        found = search(items, query, kind=kind, use=use, min_seconds=min_seconds, max_seconds=max_seconds)
        out.total = len(found)
        limit = max(1, min(limit, MAX_ITEMS))
        out.items = [item_out(i) for i in found[offset : offset + limit]]
        if not items:
            out.notes.append("the library has no licensed sounds yet: run action 'check' to see why")
        return out
