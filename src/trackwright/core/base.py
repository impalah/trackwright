"""Shared machinery of the Cubase service: session, references, track and target resolution."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

from trackwright.core.models import ParameterInfo, TrackInfo, Value
from trackwright.core.policy import WritePolicy
from trackwright.core.refs import ObjectRef, TrackSelector
from trackwright.errors import HostError, NotFoundError, PreconditionFailedError, TrackwrightError
from trackwright.hostport import HostPort

JsonObject = dict[str, Any]
MIXER: JsonObject = {"scope": "mixer"}
CHANNEL_TAGS = (1024, 4000, 1025, 1027, 1028, 4101, 4102)
TAG_NAME, TAG_SELECTED, TAG_VOLUME, TAG_MUTE, TAG_SOLO, TAG_RECORD, TAG_INPUT, TAG_OUTPUT = (
    1024,
    4000,
    1025,
    1027,
    1028,
    4002,
    4101,
    4102,
)
_SLOT_SUFFIX = re.compile(r"-\d+$")


class ServiceBase:
    """Base of :class:`trackwright.core.service.CubaseService`; tool groups are mixins on top of it."""

    def __init__(
        self,
        host: HostPort,
        policy: WritePolicy,
        *,
        sleep: Callable[[float], None] = time.sleep,
        settle_timeout: float = 1.0,
    ) -> None:
        self.host = host
        self.policy = policy
        self._sleep = sleep
        self._settle_timeout = settle_timeout

    # ------------------------------------------------------------------ host access
    def call(self, op: str, params: JsonObject | None = None) -> JsonObject:
        return self.host.call(op, params)

    def session(self) -> str:
        if self.host.session_id is None:
            self.call("hello")
        session = self.host.session_id
        if session is None:
            raise TrackwrightError("the Cubase script did not report a session", code="NO_SESSION")
        return session

    def wait_until(self, read: Callable[[], JsonObject], done: Callable[[JsonObject], bool]) -> JsonObject:
        """Re-read until ``done`` or the settle timeout (values that arrive through callbacks lag a little)."""
        deadline = time.monotonic() + self._settle_timeout
        value = read()
        while not done(value) and time.monotonic() < deadline:
            self._sleep(0.1)
            value = read()
        return value

    # ------------------------------------------------------------------ references
    def ref_for(self, described: JsonObject) -> str:
        return ObjectRef(
            self.session(), int(described["id"]), str(described["type"]), str(described["uniqueName"])
        ).encode()

    def resolve_ref(self, text: str) -> JsonObject:
        """Validate an opaque reference and return the object it designates, freshly described."""
        ref = ObjectRef.decode(text)
        ref.check_session(self.session())
        described = self.call("da.object", {"id": ref.object_id, **MIXER})
        ref.check_fingerprint(described)
        return described

    # ------------------------------------------------------------------ tracks
    def channels(self) -> list[JsonObject]:
        """Every mixer channel, deduplicated by id (the mixer's last child is a duplicate)."""
        items: list[JsonObject] = []
        offset = 0
        while True:
            page = self.call("da.channels", {"offset": offset, "limit": 32, "tags": list(CHANNEL_TAGS), **MIXER})
            items.extend(page.get("items", []))
            indexes = [i["index"] for i in page.get("items", [])] + [d["index"] for d in page.get("duplicates", [])]
            if not indexes:
                break
            offset = max(indexes) + 1
            if offset >= int(page.get("total", 0)):
                break
        unique: dict[int, JsonObject] = {}
        for item in items:
            unique.setdefault(int(item["id"]), item)
        return list(unique.values())

    def track_info(self, item: JsonObject) -> TrackInfo:
        values: JsonObject = item.get("values") or {}

        def value(tag: int) -> JsonObject | None:
            v = values.get(str(tag))
            return v if isinstance(v, dict) else None

        def flag(tag: int) -> bool | None:
            v = value(tag)
            return None if v is None else float(v.get("process") or 0) >= 0.5

        def text(tag: int) -> str | None:
            v = value(tag)
            return None if v is None else str(v.get("display"))

        volume = value(TAG_VOLUME)
        return TrackInfo(
            track=f"uid:{item['uid']}",
            uid=str(item["uid"]),
            name=text(TAG_NAME) or str(item.get("title", "")),
            type=str(item.get("type", "")),
            ref=self.ref_for(item),
            mixer_index=item.get("mixerIndex"),
            selected=bool(flag(TAG_SELECTED)),
            volume=Value(process=volume.get("process"), display=volume.get("display")) if volume else None,
            mute=flag(TAG_MUTE),
            solo=flag(TAG_SOLO),
            input=text(TAG_INPUT),
            output=text(TAG_OUTPUT),
        )

    def resolve_track(self, selector: TrackSelector) -> JsonObject:
        """Return the mixer item of the designated track (with ``values``)."""
        channels = self.channels()
        if selector.kind == "selected":
            base = int(self.call("da.base").get("base", -1))
            if base < 0:
                raise NotFoundError(
                    "no track with a mixer channel is selected (marker and folder tracks have none)",
                    code="NO_SELECTION",
                )
            matches = [c for c in channels if c["id"] == base]
        elif selector.kind == "uid":
            matches = [c for c in channels if c.get("uid") == selector.value]
        else:
            matches = [c for c in channels if self.track_info(c).name == selector.value]
        if not matches:
            raise NotFoundError(
                f"track {selector} not found",
                code="TRACK_NOT_FOUND",
                details={"available": [self.track_info(c).name for c in channels]},
            )
        if len(matches) > 1:
            raise PreconditionFailedError(
                f"{len(matches)} tracks are called {selector.value!r}; use the uid selector",
                code="TRACK_AMBIGUOUS",
                details={"candidates": [f"uid:{m['uid']}" for m in matches]},
            )
        return matches[0]

    # ------------------------------------------------------------------ targets inside a track
    def children(self, object_id: int) -> list[JsonObject]:
        items: list[JsonObject] = []
        while True:
            page = self.call("da.children", {"id": object_id, "offset": len(items), "limit": 50, **MIXER})
            items.extend(page.get("items", []))
            if not page.get("items") or len(items) >= int(page.get("total", 0)):
                return items

    def section(self, track: JsonObject, kind: str) -> JsonObject:
        for child in self.children(int(track["id"])):
            if child.get("type") == kind:
                return child
        raise NotFoundError(f"the track has no {kind} section", details={"track": track.get("title")})

    def insert_slot(self, track: JsonObject, slot: int) -> JsonObject:
        slots = self.children(int(self.section(track, "Inserts")["id"]))
        if not 1 <= slot <= len(slots):
            raise NotFoundError(f"insert slot {slot} does not exist (1..{len(slots)})", code="SLOT_NOT_FOUND")
        return slots[slot - 1]

    def resolve_target(self, track: JsonObject, target: str) -> JsonObject:
        """``channel`` | ``insert:N`` (the plugin in slot N) | ``strip:eq``."""
        spec = target.strip().lower()
        if spec == "channel":
            return track
        if spec.startswith("insert:") and spec[7:].isdigit():
            slot = self.insert_slot(track, int(spec[7:]))
            if not slot.get("children"):
                raise PreconditionFailedError(f"insert slot {spec[7:]} is empty", code="EMPTY_SLOT")
            return self.children(int(slot["id"]))[0]
        if spec == "strip:eq":
            for strip_slot in self.children(int(self.section(track, "Strips")["id"])):
                for child in self.children(int(strip_slot["id"])) if strip_slot.get("children") else []:
                    if child.get("type") == "EQ":
                        return child
            raise NotFoundError("the channel strip has no EQ module", code="EQ_NOT_FOUND")
        raise NotFoundError(f"unknown target {target!r}: use 'channel', 'insert:N' or 'strip:eq'", code="BAD_TARGET")

    # ------------------------------------------------------------------ parameters
    @staticmethod
    def parameter_info(raw: JsonObject) -> ParameterInfo:
        return ParameterInfo(
            tag=int(raw["tag"]),
            title=str(raw.get("title", "")),
            process=raw.get("process"),
            display=raw.get("display"),
            units=raw.get("units"),
            plain=raw.get("plain"),
            value_type=raw.get("valueType"),
            automatable=raw.get("automatable"),
            edit_locked=raw.get("editLock"),
        )

    def read_parameter(self, object_id: int, tag: int) -> JsonObject:
        raw = self.call("da.param.get", {"id": object_id, "tag": tag, **MIXER})
        if not raw.get("title") and raw.get("process") == -1:
            raise NotFoundError(f"parameter {tag} does not exist on this object", code="PARAM_NOT_FOUND")
        return raw

    @staticmethod
    def plugin_uid(unique_name: str) -> str:
        """The plugin's type UID: its unique name without the ``-N`` instance suffix."""
        return _SLOT_SUFFIX.sub("", unique_name)

    @staticmethod
    def is_host_code(exc: TrackwrightError, code: str) -> bool:
        return isinstance(exc, HostError) and exc.code == code
