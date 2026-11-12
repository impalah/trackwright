"""Read tools (E05) against the simulator."""

from __future__ import annotations

import pytest

from trackwright.core.policy import WritePolicy
from trackwright.core.refs import ObjectRef
from trackwright.core.service import CubaseService
from trackwright.errors import NotFoundError, PreconditionFailedError, StaleReferenceError, TrackwrightError
from trackwright.fake import FakeCubase

STUDIO_EQ = "946051208E29496E804F64A825C8A047"


def test_status(service: CubaseService) -> None:
    status = service.status()
    assert status.connected is True
    assert status.simulated is True
    assert status.script_version == "1.0.0"
    assert status.mixer_access is True
    assert status.commands_bound == 30
    assert status.writes_enabled is True


def test_status_reports_policy(readonly: CubaseService) -> None:
    assert readonly.status().writes_enabled is False


def test_list_tracks_deduplicates_and_describes(service: CubaseService, fake: FakeCubase) -> None:
    tracks = service.list_tracks()
    assert tracks.total == 3
    names = [t.name for t in tracks.tracks]
    assert names == ["Stereo Out", "POC-INSTR", "POC-TEST"]
    audio = tracks.tracks[2]
    assert audio.selected is True
    assert audio.mute is False
    assert audio.output == "Stereo Out"
    assert audio.input == "Stereo In"
    assert audio.volume is not None
    assert audio.volume.display == "0.79"
    assert audio.track == f"uid:{fake.channel_by_title('POC-TEST').uid}"
    assert service.list_tracks(offset=1, limit=1).tracks[0].name == "POC-INSTR"


def test_list_tracks_paginates_many_channels() -> None:
    fake = FakeCubase(tracks=tuple(("AudioChannel", f"T{i:02d}") for i in range(40)))
    service = CubaseService(fake, WritePolicy())
    assert service.list_tracks(limit=100).total == 41


def test_track_resolution(service: CubaseService, fake: FakeCubase) -> None:
    uid = fake.channel_by_title("POC-INSTR").uid
    assert service.list_inserts(f"uid:{uid}").track.name == "POC-INSTR"
    assert service.list_inserts("POC-INSTR").track.uid == uid
    assert service.list_inserts("name:POC-INSTR").track.uid == uid
    with pytest.raises(NotFoundError) as exc:
        service.list_inserts("Vocals")
    assert exc.value.code == "TRACK_NOT_FOUND"
    assert "POC-TEST" in exc.value.details["available"]


def test_ambiguous_track_name() -> None:
    service = CubaseService(FakeCubase(tracks=(("AudioChannel", "Gtr"), ("AudioChannel", "Gtr"))), WritePolicy())
    with pytest.raises(PreconditionFailedError) as exc:
        service.list_inserts("Gtr")
    assert exc.value.code == "TRACK_AMBIGUOUS"
    assert len(exc.value.details["candidates"]) == 2


def test_selected_track_without_mixer_channel(service: CubaseService, fake: FakeCubase) -> None:
    fake.selected = -1
    assert service.get_selected_channel().track is None
    with pytest.raises(NotFoundError) as exc:
        service.list_inserts("selected")
    assert exc.value.code == "NO_SELECTION"


def test_get_selected_channel_sections(service: CubaseService) -> None:
    out = service.get_selected_channel()
    assert out.track is not None
    assert out.track.name == "POC-TEST"
    assert [s.kind for s in out.sections] == ["Panner", "Inserts", "Strips", "Sends"]
    assert all(s.ref.startswith("tw1.") for s in out.sections)


def test_list_inserts_shows_loaded_plugin(service: CubaseService, fake: FakeCubase) -> None:
    slots = service.list_inserts("selected").slots
    assert len(slots) == 8
    assert all(s.empty for s in slots)
    service.insert_plugin("selected", 2, STUDIO_EQ, dry_run=False)
    slot = service.list_inserts("selected").slots[1]
    assert slot.empty is False
    assert slot.plugin is not None
    assert slot.plugin.name == "StudioEQ"
    assert slot.plugin.plugin_uid == STUDIO_EQ


def test_list_available_plugins(service: CubaseService) -> None:
    catalog = service.list_available_plugins("selected", 1, "dynamics")
    assert catalog.collection == "Por defecto"
    assert [p.name for p in catalog.items] == ["Compressor"]
    assert catalog.total == 2
    assert catalog.matched == 1
    with pytest.raises(NotFoundError) as exc:
        service.list_available_plugins("selected", 9)
    assert exc.value.code == "SLOT_NOT_FOUND"


def test_list_available_plugins_without_collection(service: CubaseService, fake: FakeCubase) -> None:
    original = fake._op_pm_collections
    fake._op_pm_collections = lambda p: {**original(p), "total": 0, "activeIndex": -1}  # type: ignore[method-assign]
    with pytest.raises(NotFoundError) as exc:
        service.list_available_plugins("selected", 1)
    assert exc.value.code == "NO_COLLECTION"


def test_list_parameters_channel_and_filter(service: CubaseService) -> None:
    out = service.list_parameters("selected", "channel")
    assert out.total == 8
    assert {p.tag for p in out.items} >= {1024, 1025, 1027}
    filtered = service.list_parameters("selected", "channel", filter_text="vol")
    assert [p.title for p in filtered.items] == ["Volumen"]
    assert filtered.truncated is False


def test_list_parameters_targets(service: CubaseService) -> None:
    eq = service.list_parameters("selected", "strip:eq")
    assert eq.target_name == "EQ"
    assert [p.tag for p in eq.items] == [4232]
    with pytest.raises(PreconditionFailedError) as empty:
        service.list_parameters("selected", "insert:1")
    assert empty.value.code == "EMPTY_SLOT"
    service.insert_plugin("selected", 1, STUDIO_EQ, dry_run=False)
    assert service.list_parameters("selected", "insert:1").target_name == "StudioEQ"
    with pytest.raises(NotFoundError) as bad:
        service.list_parameters("selected", "sends:1")
    assert bad.value.code == "BAD_TARGET"


def test_strip_without_eq(service: CubaseService, fake: FakeCubase) -> None:
    for obj in fake.objects.values():
        if obj.type == "EQ":
            obj.type = "Gate"
    with pytest.raises(NotFoundError) as exc:
        service.list_parameters("selected", "strip:eq")
    assert exc.value.code == "EQ_NOT_FOUND"


def test_missing_section(service: CubaseService, fake: FakeCubase) -> None:
    audio = fake.channel_by_title("POC-TEST")
    audio.children = [c for c in audio.children if fake.objects[c].type != "Inserts"]
    with pytest.raises(NotFoundError, match="no Inserts"):
        service.list_inserts("selected")


def test_get_parameter(service: CubaseService) -> None:
    out = service.get_parameter("selected", "channel", 1025)
    assert out.parameter.title == "Volumen"
    assert out.parameter.automatable is True
    with pytest.raises(NotFoundError) as exc:
        service.get_parameter("selected", "channel", 9999)
    assert exc.value.code == "PARAM_NOT_FOUND"


def test_get_transport(service: CubaseService, fake: FakeCubase) -> None:
    out = service.get_transport()
    assert out.cursor.time == "1. 1. 1.  0"
    assert out.cursor.format == "Compases+Tiempos"
    assert out.tempo_bpm == 120
    original = fake._op_transport_get
    fake._op_transport_get = lambda p: {**original(p), "primary": {}}  # type: ignore[method-assign]
    with pytest.raises(TrackwrightError) as exc:
        service.get_transport()
    assert exc.value.code == "UNAVAILABLE"


def test_poll_changes(service: CubaseService, fake: FakeCubase) -> None:
    instr = fake.channel_by_title("POC-INSTR").id
    service.set_track_mix("POC-TEST", mute=True, dry_run=False)
    fake.remove(instr)
    out = service.poll_changes()
    kinds = [(e.kind, e.still_valid) for e in out.events]
    assert ("param", True) in kinds
    assert ("mix.removed", False) in kinds
    assert out.dropped == 0
    assert "hint" in out.advice
    assert service.poll_changes().events == []


def test_poll_changes_with_drops(service: CubaseService, fake: FakeCubase) -> None:
    original = fake._op_events
    fake._op_events = lambda p: {**original(p), "dropped": 3}  # type: ignore[method-assign]
    assert "dropped" in service.poll_changes().advice


def test_refs_are_validated(service: CubaseService, fake: FakeCubase) -> None:
    ref = service.list_tracks().tracks[2].ref
    assert service.resolve_ref(ref)["title"] == "POC-TEST"
    fake.reload_script()
    with pytest.raises(StaleReferenceError):
        service.resolve_ref(ref)
    decoded = ObjectRef.decode(ref)
    same_session_wrong_object = ObjectRef(fake.session, decoded.object_id, decoded.type_name, decoded.unique_name)
    with pytest.raises(StaleReferenceError, match="different object"):
        service.resolve_ref(same_session_wrong_object.encode())


def test_session_is_negotiated_lazily() -> None:
    class Lazy(FakeCubase):
        started = False

        @property
        def session_id(self) -> str | None:
            return self.session if self.started else None

        def _op_hello(self, p: dict[str, object]) -> dict[str, object]:
            self.started = True
            return super()._op_hello(p)

    lazy = Lazy()
    service = CubaseService(lazy, WritePolicy())
    assert service.session() == lazy.session
    assert lazy.calls[0][0] == "hello"


def test_missing_session_is_an_error() -> None:
    class NoSession(FakeCubase):
        @property
        def session_id(self) -> str | None:
            return None

    with pytest.raises(TrackwrightError) as exc:
        CubaseService(NoSession(), WritePolicy()).session()
    assert exc.value.code == "NO_SESSION"
