"""Collection evidence is bounded and never admits placement or native calls."""
import pytest

from shadowbane_lab.client_observation import native_furnishing_scene as scene
from shadowbane_lab.client_observation.native_furnishing_preview import (
    read_native_furnishing_preview,
)
from shadowbane_lab.client_observation.native_vendor_dialog import NativeVendorDialogCaptureError
from tests.test_native_furnishing_preview import furnishing_fixture
from tests.test_native_vendor_queue import HUD, MANAGER

LIST_HEAD, LIST_NODE, TRACKING, OBJECT = 0x600000, 0x610000, 0x620000, 0x630000
MAP_HEAD, MAP_NODE, INFO, LEFT_NODE, LEFT_INFO = 0x640000, 0x650000, 0x660000, 0x670000, 0x680000


def scene_fixture(*, populated=True):
    m = furnishing_fixture(selected=False)
    m.put(HUD + 0x444, "<I", LIST_HEAD)
    m.put(LIST_HEAD, "<II", LIST_NODE if populated else LIST_HEAD,
          LIST_NODE if populated else LIST_HEAD)
    m.put(HUD + 0x664, "<II", MAP_HEAD, int(populated))
    m.put(MAP_HEAD + 4, "<III", MAP_NODE if populated else 0,
          MAP_NODE if populated else MAP_HEAD, MAP_NODE if populated else MAP_HEAD)
    if populated:
        m.put(LIST_NODE, "<III", LIST_HEAD, LIST_HEAD, TRACKING)
        m.put(TRACKING, "<II", m.base_address + scene.TRACKING_RVA, 2)
        m.put(TRACKING + 0x90, "<II", 42, 30)
        m.put(TRACKING + 0x60, "<II", 622657, 0)
        m.put(TRACKING + 0x68, "<I", OBJECT)
        m.put(OBJECT, "<I", m.base_address + 0x1143540)
        m.put(MAP_NODE + 4, "<III", MAP_HEAD, 0, 0)
        m.put(MAP_NODE + 0x10, "<III", 42, 30, INFO)
        m.put(INFO, "<I", m.base_address + scene.FURNITURE_INFO_RVA)
        m.put(INFO + 8, "<IIII", 622657, 0, 42, 30)
        m.put(INFO + 0x20, "<4f", 1., 2., 3., 0.5)
    return m


def capture(m):
    result = read_native_furnishing_preview(m, include_scene_collections=True)
    return result["scene_collections_raw"]


def test_retained_unselected_furniture_is_observed_without_admission():
    m = scene_fixture()
    result = capture(m)
    assert result["tracking_list"]["entries"][0]["object_reference"]["address"] == OBJECT
    record = result["furniture_map"]["records"][0]
    assert record["instance_key_raw"] == {"object_id": 42, "object_type": 30}
    assert record["position_raw"] == [1., 2., 3.]
    assert record["rotation_raw"] == 0.5
    assert result["scene_selection_in_tracking_list"] is False
    assert result["manager_building_keys_raw"]["offset_f0"] == {
        "object_id": 2229645, "object_type": 8,
    }
    for flag in ("placement_confirmed", "server_records_complete", "render_lifetime_owned",
                 "command_admitted", "native_calls_made"):
        assert result[flag] is False
    assert not any(OBJECT < at < OBJECT + 0x1000 for at, _ in m.reads)


def test_empty_and_unavailable_collections_are_distinct():
    empty = capture(scene_fixture(populated=False))
    missing = capture(furnishing_fixture())
    for name, items in (("tracking_list", "entries"), ("furniture_map", "records")):
        assert empty[name]["available"] is True
        assert missing[name]["available"] is False
        assert empty[name][items] == missing[name][items] == []
    assert empty["scene_selection_in_tracking_list"] is False
    assert missing["scene_selection_in_tracking_list"] is None
    assert not empty["server_records_complete"]


def test_default_observer_does_not_read_scene_collections():
    m = scene_fixture()
    assert "scene_collections_raw" not in read_native_furnishing_preview(m)
    assert not any(at in (HUD + 0x444, HUD + 0x664) for at, _ in m.reads)


@pytest.mark.parametrize("selection,member", [(0, False), (TRACKING, True), (INFO, False)])
def test_scene_selection_membership_is_independent_of_deed_selection(selection, member):
    m = scene_fixture()
    m.put(HUD + 0x508, "<I", selection)
    assert capture(m)["scene_selection_in_tracking_list"] is member


@pytest.mark.parametrize("address,field", [(TRACKING, "instance_key_raw"), (INFO, "position_raw")])
def test_unknown_payload_class_is_not_interpreted(address, field):
    m = scene_fixture()
    m.put(address, "<I", m.base_address + 0x1140010)
    result = capture(m)
    record = (result["tracking_list"]["entries"][0] if address == TRACKING
              else result["furniture_map"]["records"][0])
    assert field not in record
    assert not any(address < at < address + 0x1000 for at, _ in m.reads)


@pytest.mark.parametrize("slot", [LIST_NODE + 8, MAP_NODE + 0x18])
def test_null_payload_does_not_turn_nonempty_collection_into_empty(slot):
    m = scene_fixture()
    m.put(slot, "<I", 0)
    result = capture(m)
    assert len(result["tracking_list"]["entries"]) == 1
    assert len(result["furniture_map"]["records"]) == 1


@pytest.mark.parametrize("field,value", [
    (LIST_NODE, LIST_NODE), (LIST_NODE + 4, LIST_NODE), (LIST_HEAD + 4, LIST_HEAD),
    (TRACKING + 4, 3), (HUD + 0x668, 513), (HUD + 0x668, 0), (HUD + 0x668, 2),
    (HUD + 0x664, 0), (MAP_NODE + 4, MAP_NODE), (MAP_NODE + 8, MAP_NODE),
    (MAP_NODE + 8, MAP_HEAD), (MAP_HEAD + 8, MAP_HEAD), (MAP_HEAD + 0xC, MAP_HEAD),
    (INFO + 0x10, 43), (INFO + 0x20, 0x7F800000),
])
def test_malformed_collection_or_record_is_rejected(field, value):
    m = scene_fixture()
    m.put(field, "<I", value)
    with pytest.raises(NativeVendorDialogCaptureError):
        capture(m)


@pytest.mark.parametrize("at,size", [
    (HUD + 0x444, 4), (LIST_HEAD, 8), (LIST_NODE, 12), (TRACKING, 4),
    (TRACKING + 0x90, 8), (TRACKING + 0x68, 4), (HUD + 0x664, 8),
    (MAP_HEAD + 4, 12), (MAP_NODE + 4, 12), (MAP_NODE + 0x18, 4),
    (INFO + 0x20, 16), (MANAGER + 0xF0, 8), (HUD + 0x508, 4),
])
def test_changed_collection_or_hud_invalidates_entire_snapshot(at, size):
    m = scene_fixture()
    m.change = (at, size, b"\xff" * size)
    with pytest.raises(NativeVendorDialogCaptureError):
        capture(m)


def test_list_and_map_are_independent_client_collections():
    m = scene_fixture()
    m.put(LIST_HEAD, "<II", LIST_HEAD, LIST_HEAD)
    result = capture(m)
    assert result["tracking_list"]["entries"] == []
    assert len(result["furniture_map"]["records"]) == 1
    assert result["placement_confirmed"] is False


def two_node_fixture():
    m = scene_fixture()
    m.put(HUD + 0x668, "<I", 2)
    m.put(MAP_HEAD + 8, "<I", LEFT_NODE)
    m.put(MAP_NODE + 8, "<I", LEFT_NODE)
    m.put(LEFT_NODE + 4, "<III", MAP_NODE, 0, 0)
    # Native unsigned order is type first: a larger id with lower type is left.
    m.put(LEFT_NODE + 0x10, "<III", 0xFFFFFFFF, 29, LEFT_INFO)
    m.put(LEFT_INFO, "<I", m.base_address + scene.FURNITURE_INFO_RVA)
    m.put(LEFT_INFO + 0x10, "<II", 0xFFFFFFFF, 29)
    return m


def test_map_edges_extrema_and_native_unsigned_key_order():
    assert len(capture(two_node_fixture())["furniture_map"]["records"]) == 2


@pytest.mark.parametrize("field,value", [
    (LEFT_NODE + 0x14, 31), (LEFT_NODE + 4, MAP_HEAD),
    (MAP_NODE + 0xC, LEFT_NODE), (LEFT_NODE + 0x18, INFO),
])
def test_map_rejects_wrong_order_multiple_parents_and_shared_records(field, value):
    m = two_node_fixture()
    m.put(field, "<I", value)
    with pytest.raises(NativeVendorDialogCaptureError):
        capture(m)


def test_list_walk_has_independent_bound(monkeypatch):
    monkeypatch.setattr(scene, "MAX_SCENE_ENTRIES", 0)
    with pytest.raises(NativeVendorDialogCaptureError, match="list cycle or bound"):
        capture(scene_fixture())


@pytest.mark.parametrize("option", [None, 1, "true"])
def test_scene_option_is_validated_before_reading(option):
    m = scene_fixture()
    with pytest.raises(NativeVendorDialogCaptureError, match="scene collection option"):
        read_native_furnishing_preview(m, include_scene_collections=option)
    assert not m.reads
