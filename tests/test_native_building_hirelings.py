import pytest

from shadowbane_lab.client_observation.native_building_hirelings import (
    read_native_building_hirelings,
)
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from tests.test_native_vendor_queue import CONTROL, ENTRY, HUD, LIST, MANAGER, ROOT
from tests.test_native_vendor_roster import SECOND_ENTRY, building_roster_fixture


def test_building_roster_needs_no_selected_hireling_or_guard_window():
    memory = building_roster_fixture()
    memory.put(ENTRY + 0x14, "<I", 37)
    memory.put(ENTRY + 0x28, "<I", 4)
    result = read_native_building_hirelings(memory)
    assert result["building_roster_verified"]
    assert result["hireling_slots"] == 2
    assert result["hirelings"][0]["rank"] == 4
    assert result["hirelings"][0]["qualified_guard_type"]
    assert not result["hirelings"][1]["qualified_guard_type"]
    assert not any(result[key] for key in (
        "command_admitted", "management_permission_verified", "town_coverage_verified",
        "server_acceptance_verified",
    ))
    for offset in (0x50, 0x78, 0x384, 0x274, 0x2AC):
        assert (MANAGER + offset, 4) not in memory.reads


def test_complete_vacancy_list_and_unknown_types_are_distinct():
    memory = building_roster_fixture()
    memory.put(SECOND_ENTRY + 0x14, "<I", 99)
    result = read_native_building_hirelings(memory)
    assert result["hirelings"][1]["hireling"]["object_type"] == 99
    assert not result["hirelings"][1]["qualified_guard_type"]
    for entry in (ENTRY, SECOND_ENTRY):
        memory.put(entry + 0x10, "<II", 0, 0)
        memory.put(entry + 0x6C, "<I", 0)
    memory.put(MANAGER + 0x37C, "<I", 0)
    result = read_native_building_hirelings(memory)
    assert result["building_roster_verified"]
    assert result["hirelings"] == []
    assert result["vacant_hireling_slots"] == 2


@pytest.mark.parametrize("address,value", [
    (ROOT + 0x64, 0), (MANAGER + 0xD8, 1), (MANAGER + 0x48, 0),
    (MANAGER + 0xD0, 3), (MANAGER + 0xF8, 999), (MANAGER + 0x380, 3),
    (MANAGER + 0x380, 0), (MANAGER + 0x380, 129), (MANAGER + 0x37C, 0),
    (MANAGER + 0x37C, 3), (CONTROL + 0x3BC, HUD + 4), (CONTROL + 0x458, LIST + 4),
    (HUD + 0x104, MANAGER + 4), (0x190100 + 8, HUD + 4),
    (SECOND_ENTRY + 0x10, 101), (SECOND_ENTRY + 0x14, 0),
    (SECOND_ENTRY + 0x6C, 512), (SECOND_ENTRY + 8, 8),
    (CONTROL + 0x44C, SECOND_ENTRY),
])
def test_partial_stale_detached_and_duplicate_rows_are_rejected(address, value):
    memory = building_roster_fixture()
    memory.put(address, "<I", value)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_building_hirelings(memory)


@pytest.mark.parametrize("address,size", [
    (MANAGER + 0x380, 4), (MANAGER + 0x37C, 4), (MANAGER + 0xF0, 8),
    (ENTRY + 0x28, 4), (ENTRY + 0x6C, 4), (0x170000, 8), (0x310000, 12),
])
def test_complete_observation_is_rechecked(address, size):
    memory = building_roster_fixture()
    memory.change = (address, size, bytes([255]) * size)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_building_hirelings(memory)


def test_unreviewed_executable_cannot_read_memory():
    memory = building_roster_fixture()
    memory.executable_sha256 = "0" * 64
    with pytest.raises(NativeVendorDialogCompatibilityError):
        read_native_building_hirelings(memory)
    assert not memory.reads


def test_zero_capacity_with_no_rows_is_unverified_not_empty_success():
    memory = building_roster_fixture()
    memory.put(MANAGER + 0x380, "<I", 0)
    memory.put(MANAGER + 0x37C, "<I", 0)
    memory.put(LIST + 0x408, "<III", 0, 0, 0)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_building_hirelings(memory)
