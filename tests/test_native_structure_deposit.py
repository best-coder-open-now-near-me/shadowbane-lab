import pytest

from shadowbane_lab.client_observation.native_structure_deposit import read_native_structure_deposit
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from tests.test_native_guard_upgrade import BUTTON, COST, GUARD_HUD, SLIDER
from tests.test_native_guard_upgrade import fixture as guard_fixture
from tests.test_native_vendor_queue import HUD, MANAGER, ROOT
from tests.test_native_vendor_roster import text


def fixture():
    m = guard_fixture()
    m.put(MANAGER + 0xD0, "<I", 13)
    m.put(MANAGER + 0x74, "<I", GUARD_HUD)
    m.put(GUARD_HUD, "<I", 0x1568044)
    m.put(GUARD_HUD + 0x3C0, "<I", 122100)
    m.put(GUARD_HUD + 0x3C4, "<I", 0)
    for ptr, name, buffer in ((BUTTON, "ACCEPT", 0x460000),
                              (COST, "CANCEL", 0x470000),
                              (SLIDER, "SLIDEHELPER", 0x480000)):
        text(m, ptr + 0x164, buffer, name)
        m.put(ptr + 0x304, "<I", 0)
        for offset in (0x1D4, 0x1F8, 0x21C):
            m.put(ptr + offset, "<I", 13)
    text(m, SLIDER + 0xA4, 0x490000, "122100")
    return m


def test_typed_amount_is_read_instead_of_stale_cache_without_granting_authority():
    m = fixture()
    out = read_native_structure_deposit(m)
    assert out["entered_amount_gold"] == 122100
    assert out["purse_limit_at_prompt_open_gold"] == 122100
    assert out["building"] == {"object_id": 2229645, "object_type": 8}
    assert not any(out[k] for k in ("current_purse_verified", "server_acceptance_verified",
                                    "command_admitted"))
    assert (GUARD_HUD + 0x3C4, 4) not in m.reads


@pytest.mark.parametrize("address,value", [
    (ROOT + 0x64, 0), (MANAGER + 0xD8, 1), (MANAGER + 0xD0, 12),
    (MANAGER + 0x48, 0), (MANAGER + 0xF8, 999), (MANAGER + 0xF4, 42),
    (MANAGER + 0x74, HUD), (GUARD_HUD + 0x104, 0),
    (0x190200 + 8, GUARD_HUD + 4), (BUTTON + 0x3BC, HUD),
    (BUTTON + 0x1D4, 12), (COST + 0x21C, 12), (BUTTON + 0x1A8, 1),
    (SLIDER + 0x304, 256), (GUARD_HUD + 0x3C0, 122099),
])
def test_wrong_destination_mode_owner_control_or_bounds_rejected(address, value):
    m = fixture()
    m.put(address, "<I", value)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_structure_deposit(m)


@pytest.mark.parametrize("value", ["", "-1", "0", "122101", "12x", "12,210", "1.0",
                                    "2147483648", " 122100", "１２２１００"])
def test_invalid_numeric_text_cannot_become_a_deposit(value):
    m = fixture()
    text(m, SLIDER + 0xA4, 0x490000, value)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_structure_deposit(m)


@pytest.mark.parametrize("address,size", [(MANAGER + 0xF0, 8), (MANAGER + 0x1CC, 4),
                                          (GUARD_HUD + 0x3C0, 4), (0x490000, 12),
                                          (BUTTON + 0x1D4, 4)])
def test_quote_rechecked_after_read(address, size):
    m = fixture()
    m.change = (address, size, bytes([255]) * size)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_structure_deposit(m)


def test_wrong_executable_and_duplicate_input_rejected():
    m = fixture()
    m.executable_sha256 = "0" * 64
    with pytest.raises(NativeVendorDialogCompatibilityError):
        read_native_structure_deposit(m)
    assert not m.reads
    m = fixture()
    text(m, COST + 0x164, 0x470000, "SLIDEHELPER")
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_structure_deposit(m)
