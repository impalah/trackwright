"""Read-only tools (epic E05). None of them modifies the project."""

from __future__ import annotations

from trackwright.core.base import MIXER, JsonObject, ServiceBase
from trackwright.core.models import (
    ChangeEvent,
    ChangesOut,
    InsertsOut,
    ParameterInfo,
    ParameterOut,
    ParametersOut,
    PluginCatalogOut,
    PluginEntry,
    PluginInSlot,
    Section,
    SelectedChannelOut,
    SlotInfo,
    StatusOut,
    TimePosition,
    TrackListOut,
    TransportOut,
)
from trackwright.core.refs import TrackSelector
from trackwright.errors import NotFoundError, TrackwrightError

MAX_FILTER_SCAN = 500
MAX_EVENT_LOOKUPS = 20


class ReadingMixin(ServiceBase):
    def status(self) -> StatusOut:
        hello = self.call("hello")
        caps = self.call("capabilities")
        capabilities: JsonObject = caps.get("capabilities") or {}
        host: JsonObject = caps.get("host") or hello.get("host") or {}
        return StatusOut(
            connected=True,
            simulated=bool(self.host.simulated or capabilities.get("simulated")),
            session=self.host.session_id or hello.get("sessionId"),
            script_version=hello.get("scriptVersion"),
            host_app=host.get("appName"),
            host_version=host.get("appVersion"),
            insert_slots=host.get("insertSlots"),
            mixer_access=bool(
                capabilities.get("mixerDirectAccessActive", capabilities.get("mixerDirectAccessCreated"))
            ),
            transport_access=bool(capabilities.get("transportTimeDisplay")),
            commands_bound=capabilities.get("commandsBound"),
            writes_enabled=self.policy.enabled,
            allowed_tracks=list(self.policy.allowed_tracks),
        )

    def list_tracks(self, offset: int = 0, limit: int = 32) -> TrackListOut:
        channels = self.channels()
        page = channels[offset : offset + limit]
        return TrackListOut(total=len(channels), tracks=[self.track_info(c) for c in page])

    def get_selected_channel(self) -> SelectedChannelOut:
        base = self.call("da.base")
        if int(base.get("base", -1)) < 0:
            return SelectedChannelOut(track=None, sections=[])
        track = self.resolve_track(TrackSelector("selected"))
        sections = [
            Section(kind=str(c.get("type")), title=str(c.get("title")), ref=self.ref_for(c))
            for c in self.children(int(track["id"]))
        ]
        return SelectedChannelOut(track=self.track_info(track), sections=sections)

    def list_inserts(self, track: str) -> InsertsOut:
        item = self.resolve_track(TrackSelector.parse(track))
        slots: list[SlotInfo] = []
        for index, slot in enumerate(self.children(int(self.section(item, "Inserts")["id"])), start=1):
            plugin = None
            if slot.get("children"):
                child = self.children(int(slot["id"]))[0]
                plugin = PluginInSlot(
                    name=str(child.get("title")),
                    plugin_uid=self.plugin_uid(str(child.get("uniqueName"))),
                    ref=self.ref_for(child),
                )
            slots.append(SlotInfo(index=index, empty=plugin is None, ref=self.ref_for(slot), plugin=plugin))
        return InsertsOut(track=self.track_info(item), slots=slots)

    def list_available_plugins(
        self, track: str, slot: int = 1, filter_text: str | None = None, offset: int = 0, limit: int = 20
    ) -> PluginCatalogOut:
        slot_obj = self.insert_slot(self.resolve_track(TrackSelector.parse(track)), slot)
        collections = self.call("pm.collections", {"slot": slot_obj["id"], **MIXER})
        index = int(collections.get("activeIndex", -1))
        if int(collections.get("total", 0)) == 0 or index < 0:
            raise NotFoundError("this slot offers no plugin collection", code="NO_COLLECTION")
        entries = self.call(
            "pm.entries",
            {
                "slot": slot_obj["id"],
                "collection": index,
                "offset": offset,
                "limit": min(limit, 40),
                "filter": filter_text or "",
                **MIXER,
            },
        )
        items = [
            PluginEntry(
                name=str(e["name"]),
                vendor=str(e["vendor"]),
                version=str(e["version"]),
                uid=str(e["uid"]),
                sub_categories=str(e["subCategories"]),
            )
            for e in entries.get("items", [])
        ]
        return PluginCatalogOut(
            collection=entries.get("collectionName"),
            total=int(entries.get("total", 0)),
            matched=int(entries.get("matched", 0)),
            offset=offset,
            items=items,
        )

    def list_parameters(
        self, track: str, target: str, offset: int = 0, limit: int = 25, filter_text: str | None = None
    ) -> ParametersOut:
        obj = self.resolve_target(self.resolve_track(TrackSelector.parse(track)), target)
        needle = (filter_text or "").lower()
        items: list[ParameterInfo] = []
        position, scanned, total = offset, 0, None
        while True:
            page = self.call("da.params", {"id": obj["id"], "offset": position, "limit": 25, **MIXER})
            total = int(page.get("total", 0))
            batch = page.get("items", [])
            scanned += len(batch)
            position += len(batch)
            items.extend(self.parameter_info(p) for p in batch if needle in str(p.get("title", "")).lower())
            if not needle or not batch or position >= total or len(items) >= limit or scanned >= MAX_FILTER_SCAN:
                break
        truncated = bool(needle) and position < total and len(items) < limit
        return ParametersOut(
            target=target,
            target_ref=self.ref_for(obj),
            target_name=str(obj.get("title", "")),
            total=total,
            offset=offset,
            scanned=scanned,
            items=items[:limit],
            truncated=truncated,
        )

    def get_parameter(self, track: str, target: str, tag: int) -> ParameterOut:
        obj = self.resolve_target(self.resolve_track(TrackSelector.parse(track)), target)
        raw = self.read_parameter(int(obj["id"]), tag)
        return ParameterOut(
            target=target,
            target_ref=self.ref_for(obj),
            target_name=str(obj.get("title", "")),
            parameter=self.parameter_info(raw),
        )

    def get_transport(self) -> TransportOut:
        data = self.call("transport.get")
        primary: JsonObject = data.get("primary") or {}
        if not data.get("available") or not primary.get("locator"):
            raise TrackwrightError(
                "transport values have not arrived yet; move the cursor once in Cubase and retry", code="UNAVAILABLE"
            )

        def position(key: str) -> TimePosition | None:
            raw = primary.get(key)
            return TimePosition(time=str(raw["time"]), format=raw.get("format")) if isinstance(raw, dict) else None

        cursor = position("locator")
        assert cursor is not None
        return TransportOut(
            cursor=cursor,
            cycle_left=position("cycleLeft"),
            cycle_right=position("cycleRight"),
            tempo_bpm=data.get("tempoBPM"),
        )

    def poll_changes(self) -> ChangesOut:
        data = self.call("events")
        events: list[ChangeEvent] = []
        described: dict[int, JsonObject | None] = {}
        for raw in data.get("events", []):
            oid = int(raw.get("id", -1))
            if oid not in described and len(described) < MAX_EVENT_LOOKUPS:
                try:
                    described[oid] = self.call("da.object", {"id": oid, **MIXER})
                except TrackwrightError:
                    described[oid] = None
            obj = described.get(oid)
            tag = int(raw.get("t", -1))
            events.append(
                ChangeEvent(
                    kind=str(raw.get("k")),
                    tag=tag if tag >= 0 else None,
                    ref=self.ref_for(obj) if obj else None,
                    title=obj.get("title") if obj else None,
                    still_valid=obj is not None,
                )
            )
        dropped = int(data.get("dropped", 0))
        advice = (
            "events were dropped: re-list tracks and objects"
            if dropped
            else "a 'removed' event is a hint to re-validate, not proof of removal (it also fires on selection changes)"
        )
        return ChangesOut(events=events, dropped=dropped, advice=advice)
