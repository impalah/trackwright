"""Track selectors and opaque object references.

Runtime object ids are only valid inside one script session and are **reused** for different
objects after a reload (verified: id 550 went from Compressor to Input Filter). They are therefore
never exposed alone: tools return an opaque ``ref`` that embeds the session and a fingerprint of
the object, and validate both before every use.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Literal

from trackwright.errors import ProtocolError, StaleReferenceError

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

    @classmethod
    def decode(cls, text: str) -> ObjectRef:
        if not text.startswith(REF_PREFIX):
            raise ProtocolError("not a Trackwright object reference", details={"ref": text[:40]})
        body = text[len(REF_PREFIX) :]
        try:
            data: Any = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            return cls(str(data["s"]), int(data["i"]), str(data["t"]), str(data["u"]))
        except (ValueError, KeyError, TypeError) as exc:
            raise ProtocolError("malformed object reference", details={"ref": text[:40]}) from exc

    def check_session(self, current: str | None) -> None:
        if current is None or current != self.session:
            raise StaleReferenceError(
                "the reference belongs to a previous Cubase script session; list the objects again",
                details={"ref_session": self.session, "current_session": current},
            )

    def check_fingerprint(self, described: dict[str, Any]) -> None:
        if described.get("type") != self.type_name or described.get("uniqueName") != self.unique_name:
            raise StaleReferenceError(
                "the reference now points at a different object; list the objects again",
                details={
                    "expected": {"type": self.type_name, "uniqueName": self.unique_name},
                    "found": {"type": described.get("type"), "uniqueName": described.get("uniqueName")},
                },
            )
