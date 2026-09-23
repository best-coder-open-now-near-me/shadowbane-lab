import pytest

from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from shadowbane_lab.client_observation.native_warehouse_withdrawal import (
    read_native_warehouse_withdrawal,
)
from tests.test_native_guard_upgrade import BUTTON, COST, GUARD_HUD, SLIDER
from tests.test_native_structure_deposit import fixture as deposit_fixture
from tests.test_native_vendor_queue import CONTROL, ENTRY, HUD, LIST, ROOT
from tests.test_native_vendor_roster import text

OWNER, HEADER, RESERVE = 0x500000, 0x510000, 0x520000


def fixture():
    m = deposit_fixture()
    m.put(HUD, "<I", 0x1570308)
    m.put(HUD + 0x10C, "<I", GUARD_HUD)
    m.put(HUD + 0x378, "<I", OWNER)
    m.put(OWNER, "<I", 0x154165C)
    m.put(OWNER + 0x18, "<II", 321, 42)
    m.put(GUARD_HUD + 0x108, "<I", HUD)
    m.put(GUARD_HUD + 0x388, "<I", 123)
    m.put(GUARD_HUD + 0x3C0, "<I", 450)
    text(m, LIST + 0x164, 0x530000, "WAREHOUSE_INV")
    m.put(LIST + 0x408, "<III", 0x170000, 0x170004, 0x170004)
    m.put(ENTRY, "<I", 0x156F258)
    m.put(ENTRY + 0x20, "<I", 123)
    text(m, ENTRY + 0x30, 0x310000, "Gold")
    m.put(ENTRY + 0x48, "<I", 500)
    m.put(HUD + 0x3E8, "<II", HEADER, 1)
    m.put(HEADER + 4, "<III", RESERVE, RESERVE, RESERVE)
    m.put(RESERVE + 4, "<5I", HEADER, 0, 0, 123, 50)
    text(m, SLIDER + 0xA4, 0x490000, "100")
    for control, action in ((BUTTON, 0x1009), (COST, 0x100B)):
        m.put(control + 0x1D0, "<III", action, 0, 0)
    return m


def test_resource_reserve_and_real_input_are_independently_verified():
    m = fixture()
    result = read_native_warehouse_withdrawal(m)
    assert result["resource"] == {"resource_id": 123, "display_name": "Gold", "amount": 500}
    assert result["source_hireling"] == {"object_id": 321, "object_type": 42}
    assert result["minimum_balance"] == 50
    assert result["available_amount"] == 450
    assert result["entered_amount"] == 100
    assert not result["command_admitted"] and not result["server_acceptance_verified"]
    assert (GUARD_HUD + 0x3C4, 4) not in m.reads


@pytest.mark.parametrize(
    "address,value",
    [
        (ROOT + 0x64, 0),
        (HUD + 0x10C, 0),
        (GUARD_HUD + 0x108, HUD + 4),
        (GUARD_HUD + 0x388, 999),
        (OWNER, 0),
        (OWNER + 0x1C, 8),
        (BUTTON + 0x1D0, 0x458),
        (BUTTON + 0x1D4, 13),
        (BUTTON + 0x1A8, 1),
        (COST + 0x1D0, 0x1009),
        (SLIDER + 0x304, 256),
        (CONTROL + 0x458, 0),
        (ENTRY + 0x48, 499),
        (GUARD_HUD + 0x3C0, 451),
        (RESERVE + 4, 0),
        (RESERVE + 8, RESERVE),
        (RESERVE + 0x14, 51),
        (HEADER + 8, HEADER),
        (HUD + 0x3EC, 2),
        (RESERVE + 0x14, 0xFFFFFFFF),
    ],
)
def test_wrong_direction_source_reserve_or_stale_quote_rejected(address, value):
    m = fixture()
    m.put(address, "<I", value)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_warehouse_withdrawal(m)


@pytest.mark.parametrize("value", ["", "0", "-1", "451", "1,000", "1.5", " 100", "１００"])
def test_invalid_amount_rejected(value):
    m = fixture()
    text(m, SLIDER + 0xA4, 0x490000, value)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_warehouse_withdrawal(m)


@pytest.mark.parametrize(
    "address,size",
    [
        (OWNER + 0x18, 8),
        (ENTRY + 0x48, 4),
        (RESERVE + 4, 20),
        (GUARD_HUD + 0x3C0, 4),
        (BUTTON + 0x1D0, 4),
        (0x490000, 6),
    ],
)
def test_transfer_inputs_rechecked(address, size):
    m = fixture()
    m.change = (address, size, bytes(size))
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_warehouse_withdrawal(m)


def test_no_reserve_is_inferred_only_from_a_verified_empty_map():
    m = fixture()
    m.put(HUD + 0x3E8, "<II", HEADER, 0)
    m.put(HEADER + 4, "<III", 0, HEADER, HEADER)
    m.put(GUARD_HUD + 0x3C0, "<I", 500)
    assert read_native_warehouse_withdrawal(m)["minimum_balance"] == 0
    m.put(HEADER + 4, "<I", RESERVE)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_warehouse_withdrawal(m)


def test_duplicate_resource_and_unreviewed_executable_rejected():
    m = fixture()
    m.put(LIST + 0x408, "<III", 0x170000, 0x170008, 0x170008)
    m.put(0x170004, "<I", CONTROL)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_warehouse_withdrawal(m)
    m = fixture()
    m.executable_sha256 = "0" * 64
    with pytest.raises(NativeVendorDialogCompatibilityError):
        read_native_warehouse_withdrawal(m)
    assert not m.reads
