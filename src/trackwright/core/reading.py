"""Read-only tools (epic E05). None of them modifies the project."""

from __future__ import annotations

from trackwright.core.base import MIXER, JsonObject, ServiceBase, operation
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
    @operation
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

    @operation
    def list_tracks(self, offset: int = 0, limit: int = 32) -> TrackListOut:
        channels = self.channels()
        page = channels[offset : offset + limit]
        return TrackListOut(total=len(channels), tracks=[self.track_info(c) for c in page])

    @operation
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

    @operation
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

    @operation
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

    @operation
    def list_parameters(
        self, track: str, target: str, offset: int = 0, limit: int = 25, filter_text: str | None = None
    ) -> ParametersOut:
        obj = self.resolve_target(self.resolve_track(TrackSelector.parse(track)), target)
        needle = (filter_text or "").lower()
        items: list[ParameterInfo] = []
        next_offset, scanned, total = offset, 0, 0
        while len(items) < limit and scanned < MAX_FILTER_SCAN:
            page_size = 25 if needle else min(25, limit - len(items))
            page = self.call("da.params", {"id": obj["id"], "offset": next_offset, "limit": page_size, **MIXER})
            total = int(page.get("total", 0))
            batch = page.get("items", [])
            if not batch:
                break
            for raw in batch:
                # Consume parameter by parameter so that no match is skipped when the limit is reached.
                next_offset = int(raw.get("index", next_offset)) + 1
                scanned += 1
                if needle in str(raw.get("title", "")).lower():
                    items.append(self.parameter_info(raw))
                    if len(items) >= limit:
                        break
            if next_offset >= total:
                break
        return ParametersOut(
            target=target,
            target_ref=self.ref_for(obj),
            target_name=str(obj.get("title", "")),
            total=total,
            offset=offset,
            scanned=scanned,
            items=items,
            next_offset=next_offset,
            truncated=next_offset < total,
        )

    @operation
    def get_parameter(self, track: str, target: str, tag: int) -> ParameterOut:
        obj = self.resolve_target(self.resolve_track(TrackSelector.parse(track)), target)
        raw = self.read_parameter(int(obj["id"]), tag)
        return ParameterOut(
            target=target,
            target_ref=self.ref_for(obj),
            target_name=str(obj.get("title", "")),
            parameter=self.parameter_info(raw),
        )

    @operation
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

    @operation
    def poll_changes(self) -> ChangesOut:
        data = self.call("events")
        events: list[ChangeEvent] = []
        described: dict[int, JsonObject | None] = {}
        unchecked = 0
        for raw in data.get("events", []):
            oid = int(raw.get("id", -1))
            if oid not in described and len(described) < MAX_EVENT_LOOKUPS:
                try:
                    described[oid] = self.call("da.object", {"id": oid, **MIXER})
                except TrackwrightError:
                    described[oid] = None
            checked = oid in described
            obj = described.get(oid)
            unchecked += not checked
            tag = int(raw.get("t", -1))
            events.append(
                ChangeEvent(
                    kind=str(raw.get("k")),
                    tag=tag if tag >= 0 else None,
                    ref=self.ref_for(obj) if obj else None,
                    title=obj.get("title") if obj else None,
                    still_valid=(obj is not None) if checked else None,
                )
            )
        dropped = int(data.get("dropped", 0))
        advice = (
            "events were dropped: re-list tracks and objects"
            if dropped
            else "a 'removed' event is a hint to re-validate, not proof of removal (it also fires on selection changes)"
        )
        return ChangesOut(events=events, dropped=dropped, unchecked=unchecked, advice=advice)
