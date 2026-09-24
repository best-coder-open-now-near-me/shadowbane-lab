"""Synthetic ownership and consistency tests; live visual qualification is separate."""

import pytest

from shadowbane_lab.client_observation.native_furnishing_preview import (
    REVIEWED_FURNISHING_EXECUTABLES,
    read_native_furnishing_preview,
)
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from tests.test_native_vendor_queue import CONTROL, ENTRY, HUD, LIST, MANAGER, ROOT, fixture
from tests.test_native_vendor_roster import text

LAYOUT, SOURCE, MODEL, STRUCTURE = 0x210000, 0x220000, 0x230000, 0x240000


def furnishing_fixture(*, selected=True):
    m = fixture()
    m.executable_sha256 = "7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f"
    for address, value in (
        (HUD, 0x1567C68), (MANAGER + 0xA8, HUD),
        (HUD + 0x524, LIST), (HUD + 0x648, LAYOUT),
        (HUD + 0x660, ENTRY if selected else 0), (ENTRY, 0x1569908),
        (ENTRY + 8, 0x25), (LAYOUT + 0x3BC, HUD),
        (ENTRY + 0x20, SOURCE), (ENTRY + 0x24, MODEL),
        (SOURCE, 0x1542468), (MODEL, 0x1542748),
        (HUD + 0x64C, STRUCTURE), (STRUCTURE, 0x154381C),
    ):
        m.put(address, "<I", value)
    m.put(ENTRY + 0x10, "<II", 5017277, 30)
    m.put(SOURCE + 0x7B8, "<II", 622657, 0)
    m.put(HUD + 0x54, "<III", 0x160000, 0x160008, 0x160010)
    m.put(0x160000, "<II", LIST, LAYOUT)
    m.put(HUD + 0x630, "<ii", 400, 400)
    m.put(HUD + 0x638, "<ff", 64, 54)
    m.put(HUD + 0x37C, "<f", 1)
    text(m, LAYOUT + 0x164, 0x310000, "BTNPROPLAYOUT")
    # Empty row names are observed live and must be preserved for diagnosis.
    return m


@pytest.mark.parametrize("digest", sorted(REVIEWED_FURNISHING_EXECUTABLES))
def test_copies_exact_build_owned_selection_without_claiming_preview_or_placement(digest):
    m = furnishing_fixture()
    m.executable_sha256 = digest
    result = read_native_furnishing_preview(m)
    assert result["rows"][0]["entry_key_raw"] == {"object_id": 5017277, "object_type": 30}
    assert result["rows"][0]["model_reference"]["address"] == MODEL
    assert result["rows"][0]["source_reference"]["address"] == SOURCE
    assert result["rows"][0]["control_name"] == ""
    assert result["rows"][0]["selected"] is True
    assert result["floor_index_raw"] == 0
    assert result["layout_raw"] == {"width": 400, "height": 400, "x": 64, "y": 54, "zoom": 1}
    for flag in ("preview_pose_verified", "render_lifetime_owned", "placement_confirmed",
                 "command_admitted"):
        assert result[flag] is False
    # Unknown native classes stay references: no inferred offsets or calls.
    assert result["rows"][0]["furnishing_key_raw"] == {"object_id": 622657, "object_type": 0}
    assert result["list_selected_control_address_raw"] == 0
    assert {a for a, _ in m.reads if SOURCE < a < SOURCE + 0x1000} == {SOURCE + 0x7B8}
    assert not any(MODEL < address < MODEL + 0x1000 for address, _ in m.reads)


def test_loading_and_unselected_states_remain_unavailable_not_guessed():
    m = furnishing_fixture(selected=False)
    for address in (HUD + 0x64C, HUD + 0x648, ENTRY + 0x20, ENTRY + 0x24):
        m.put(address, "<I", 0)
    result = read_native_furnishing_preview(m)
    assert result["selected_entry_address"] == 0
    assert result["structure_reference"] is None
    assert result["layout_control"] is None
    assert result["rows"][0]["model_reference"] is None
    assert result["rows"][0]["selected"] is False


@pytest.mark.parametrize("field,value", [
    (LIST + 0x404, CONTROL + 4), (ROOT + 0x64, 1), (HUD + 0x104, MANAGER + 4),
    (MANAGER + 0xA8, HUD + 4),
    (HUD + 0x660, ENTRY + 4), (HUD + 0x524, LIST + 4),
    (LIST + 0x3BC, HUD + 4), (CONTROL + 0x3BC, HUD + 4),
    (CONTROL + 0x458, LIST + 4), (ENTRY, 0x1569518), (ENTRY + 8, 9),
    (HUD + 0x648, LAYOUT + 4), (LAYOUT + 0x3BC, HUD + 4),
    (ENTRY + 0x24, 0xFFFFFFFF), (ENTRY + 0x20, SOURCE + 1),
    (MODEL, 0), (MODEL, 0x80000000),
])
def test_rejects_detached_or_unknown_ownership(field, value):
    m = furnishing_fixture()
    m.put(field, "<I", value)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_furnishing_preview(m)


@pytest.mark.parametrize("address,size", [
    (HUD + 0x660, 4), (MANAGER + 0xA8, 4), (0x170000, 4),
    (ENTRY + 0x24, 4), (MODEL, 4), (HUD + 0x628, 4), (HUD + 0x638, 8),
    (ROOT + 0x20, 4), (SOURCE + 0x7B8, 8), (LIST + 0x404, 4),
])
def test_rechecks_selection_geometry_lifetime_and_membership(address, size):
    m = furnishing_fixture()
    m.change = (address, size, bytes([255]) * size)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_furnishing_preview(m)


def test_rejects_ambiguous_huds_and_duplicate_rows():
    m = furnishing_fixture()
    m.put(0x190100, "<III", 0x190200, 0x190000, HUD)
    m.put(0x190200, "<III", 0x190000, 0x190100, HUD + 0x1000)
    m.put(0x190000 + 4, "<I", 0x190200)
    m.put(HUD + 0x1000, "<I", 0x1567C68)
    with pytest.raises(NativeVendorDialogCaptureError, match="one active"):
        read_native_furnishing_preview(m)
    m = furnishing_fixture()
    m.put(LIST + 0x408, "<III", 0x170000, 0x170008, 0x170010)
    m.put(0x170000, "<II", CONTROL, CONTROL)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_furnishing_preview(m)


@pytest.mark.parametrize("field,fmt,value", [
    (HUD + 0x37C, "<f", float("nan")), (HUD + 0x638, "<f", float("inf")),
    (HUD + 0x630, "<i", -1),
])
def test_rejects_invalid_layout_values(field, fmt, value):
    m = furnishing_fixture()
    m.put(field, fmt, value)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_furnishing_preview(m)


def test_rejects_wrong_build_before_memory_reads():
    m = furnishing_fixture()
    m.executable_sha256 = "0" * 64
    with pytest.raises(NativeVendorDialogCompatibilityError):
        read_native_furnishing_preview(m)
    assert not m.reads


def test_short_read_is_rejected():
    m = furnishing_fixture()
    read = m.read_block
    m.read_block = lambda address, size: b"" if address == ENTRY else read(address, size)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_furnishing_preview(m)



def test_unknown_source_type_remains_raw_reference_without_interpreting_deed_fields():
    m = furnishing_fixture()
    m.put(SOURCE, "<I", 0x1542748)
    result = read_native_furnishing_preview(m)
    assert result["rows"][0]["furnishing_key_raw"] is None
    assert (SOURCE + 0x7B8, 8) not in m.reads


def test_retains_distinct_list_and_hud_selection_for_input_diagnosis():
    m = furnishing_fixture(selected=False)
    m.put(LIST + 0x404, "<I", CONTROL)
    result = read_native_furnishing_preview(m)
    assert result["list_selected_control_address_raw"] == CONTROL
    assert result["selected_entry_address"] == 0
    assert not result["rows"][0]["selected"]


@pytest.mark.parametrize("enabled", [False, True])
def test_recorder_channel_is_opt_in_and_closes_read_only_handle(monkeypatch, tmp_path, enabled):
    from unittest.mock import Mock

    from shadowbane_lab.client_observation import workflow_capture

    memory = furnishing_fixture()
    memory.close = Mock()
    opener = Mock(return_value=memory)
    recorder = Mock(return_value={"reason": "deadline"})
    monkeypatch.setattr(workflow_capture.WindowsReadOnlyProcessMemory, "open_for_process", opener)
    monkeypatch.setattr(workflow_capture, "record_workflow", recorder)
    args = ["capture", "--process-id", "988", "--creation", "100",
            "--output", str(tmp_path / "capture.jsonl"),
            "--stop-file", str(tmp_path / "stop")]
    monkeypatch.setattr("sys.argv", args + (["--furnishings"] if enabled else []))
    assert workflow_capture.main() == 0
    readers = recorder.call_args.kwargs["readers"]
    assert ("furnishings" in readers) is enabled
    if enabled:
        assert readers["furnishings"] is read_native_furnishing_preview
    memory.close.assert_called_once()


ACTOR, COMPONENT, POSE, OTHER_BUILDING = 0x410000, 0x420000, 0x430000, 0x440000


def occupied_fixture():
    m = furnishing_fixture()
    for address, value in (
        (0x1AA2D98, ACTOR), (ACTOR, 0x154165C),
        (ACTOR + 0x4B0, COMPONENT), (COMPONENT, POSE),
        (POSE + 8, STRUCTURE), (STRUCTURE, 0x1577C0C),
    ):
        m.put(address, "<I", value)
    m.put(STRUCTURE + 0x18, "<II", 4761372, 8)
    return m


def test_actor_parent_identifies_building_and_hud_only_confirms_it():
    m = occupied_fixture()
    result = read_native_furnishing_preview(m)
    occupancy = result["occupancy_raw"]
    assert occupancy["occupied_building_key_raw"] == {"object_id": 4761372, "object_type": 8}
    assert occupancy["hud_matches_occupied_building"] is True
    assert not result["preview_pose_verified"]
    assert not result["command_admitted"]
    m.put(HUD + 0x64C, "<I", OTHER_BUILDING)
    m.put(OTHER_BUILDING, "<I", 0x1577C0C)
    # Even equal keys cannot substitute for the actual native parent object.
    m.put(OTHER_BUILDING + 0x18, "<II", 4761372, 8)
    result = read_native_furnishing_preview(m)
    assert (result["occupancy_raw"]["occupied_building_key_raw"]
            == occupancy["occupied_building_key_raw"])
    assert result["occupancy_raw"]["hud_matches_occupied_building"] is False


@pytest.mark.parametrize("address,value", [
    (0x1AA2D98, 0), (ACTOR, 0x1542748), (ACTOR + 0x4B0, 0),
    (COMPONENT, 0), (POSE + 8, 0), (STRUCTURE, 0x154381C),
])
def test_loading_exit_and_unreviewed_classes_do_not_infer_occupancy_from_hud(address, value):
    m = occupied_fixture()
    m.put(address, "<I", value)
    result = read_native_furnishing_preview(m)["occupancy_raw"]
    assert result["occupied_building_key_raw"] is None
    assert result["hud_matches_occupied_building"] is False
    if address in (0x1AA2D98, ACTOR):
        assert (ACTOR + 0x4B0, 4) not in m.reads
    if address == STRUCTURE:
        assert (STRUCTURE + 0x18, 8) not in m.reads


@pytest.mark.parametrize("address,size", [
    (0x1AA2D98, 4), (ACTOR, 4), (ACTOR + 0x4B0, 4), (COMPONENT, 4),
    (POSE + 8, 4), (STRUCTURE, 4), (STRUCTURE + 0x18, 8),
])
def test_occupancy_changes_invalidate_entire_hud_snapshot(address, size):
    m = occupied_fixture()
    m.change = (address, size, b"\xff" * size)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_furnishing_preview(m)


@pytest.mark.parametrize("key", [(0, 8), (4761372, 42)])
def test_reviewed_parent_requires_valid_structure_identity(key):
    m = occupied_fixture()
    m.put(STRUCTURE + 0x18, "<II", *key)
    with pytest.raises(NativeVendorDialogCaptureError, match="occupied building identity"):
        read_native_furnishing_preview(m)


def test_parent_change_reports_new_building_even_while_hud_is_stale():
    m = occupied_fixture()
    m.put(POSE + 8, "<I", OTHER_BUILDING)
    m.put(OTHER_BUILDING, "<I", 0x1577C0C)
    m.put(OTHER_BUILDING + 0x18, "<II", 123, 8)
    result = read_native_furnishing_preview(m)["occupancy_raw"]
    assert result["occupied_building_key_raw"] == {"object_id": 123, "object_type": 8}
    assert result["hud_matches_occupied_building"] is False
