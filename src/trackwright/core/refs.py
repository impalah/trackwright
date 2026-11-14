"""Track selectors and opaque object references.

Runtime object ids are only valid inside one script session and are **reused** for different
objects after a reload (verified: id 550 went from Compressor to Input Filter). They are therefore
never exposed alone: tools return an opaque, informative ``ref`` that embeds the session and a
fingerprint of the object. No tool accepts a ``ref`` as input (C-25): tracks are designated with
``uid:`` selectors, and writes are protected by the session pinned for each tool (TW-1402).
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Literal

REF_PREFIX = "tw1."
SELECTED = "selected"


@dataclass(frozen=True, slots=True)
class TrackSelector:
    """How a tool input designates a track.

    Accepted forms: ``"selected"``; ``"uid:<UID>"`` (stable across Cubase restarts); ``"name:<exact name>"``;
    or any other text, taken as an exact track name.
    """

    kind: Literal["selected", "uid", "name"]
    value: str = ""

    @classmethod
    def parse(cls, text: str | None) -> TrackSelector:
        raw = (text or SELECTED).strip()
        if not raw or raw == SELECTED:
            return cls("selected")
        if raw.startswith("uid:") and raw[4:].strip():
            return cls("uid", raw[4:].strip())
        if raw.startswith("name:") and raw[5:]:
            return cls("name", raw[5:])
        return cls("name", raw)

    def __str__(self) -> str:
        return SELECTED if self.kind == "selected" else f"{self.kind}:{self.value}"


@dataclass(frozen=True, slots=True)
class ObjectRef:
    """Opaque handle on a Cubase object: session + runtime id + fingerprint."""

    session: str
    object_id: int
    type_name: str
    unique_name: str

    def encode(self) -> str:
        payload = {"s": self.session, "i": self.object_id, "t": self.type_name, "u": self.unique_name}
        raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode()
        return REF_PREFIX + base64.urlsafe_b64encode(raw).decode().rstrip("=")
