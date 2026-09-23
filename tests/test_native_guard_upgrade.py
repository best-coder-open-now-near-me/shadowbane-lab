import io
import json
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

import pytest

from shadowbane_lab.client_observation.native_guard_upgrade import read_native_guard_upgrade
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from shadowbane_lab.client_observation.native_vendor_roster import read_native_vendor_roster
from tests.test_native_vendor_queue import CONTROL, ENTRY, HUD, MANAGER, ROOT
from tests.test_native_vendor_roster import SECOND_ENTRY, building_roster_fixture, text

GUARD_HUD, BUTTON, COST, SLIDER = 0x410000, 0x420000, 0x430000, 0x440000


def fixture():
    m = building_roster_fixture()
    for address, value in ((MANAGER + 0x78, GUARD_HUD), (MANAGER + 0x50, 1),
                           (MANAGER + 0x384, ENTRY), (GUARD_HUD, 0x156A058),
                           (GUARD_HUD + 0x104, MANAGER), (MANAGER + 0x274, 122100),
                           (MANAGER + 0x2AC, 256)):
        m.put(address, "<I", value)
    m.put(0x190000, "<II", 0x190100, 0x190200)
    m.put(0x190100, "<III", 0x190200, 0x190000, HUD)
    m.put(0x190200, "<III", 0x190000, 0x190100, GUARD_HUD)
    for entry in (ENTRY, SECOND_ENTRY):
        m.put(entry + 0x14, "<I", 37)
        m.put(entry + 0x28, "<I", 1)
    m.put(GUARD_HUD + 0x54, "<III", 0x450000, 0x45000C, 0x45000C)
    m.put(0x450000, "<III", BUTTON, COST, SLIDER)
    for ptr, name, buf in ((BUTTON, "BTNUPGRADE", 0x460000),
                           (COST, "BTNUPGRADECOST", 0x470000),
                           (SLIDER, "SLIDEUPGRADE", 0x480000)):
        m.put(ptr, "<I", 0x1569EC0)
        m.put(ptr + 0x3BC, "<I", GUARD_HUD)
        text(m, ptr + 0x164, buf, name)
    m.put(SLIDER + 0x304, "<I", 256)
    return m


def test_complete_guard_rows_and_cost_do_not_grant_upgrade_authority():
    m = fixture()
    out = read_native_guard_upgrade(m)
    assert len(out["hirelings"]) == 2
    assert out["selected_guard"] == {"object_id": 101, "object_type": 37}
    assert out["upgrade_cost_gold"] == 122100
    assert out["displayed_building_funds_gold"] == 0
    assert out["can_upgrade"] and not out["upgrade_in_progress"]
    assert not out["controls"]["SLIDEUPGRADE"]["visible"]
    assert not any(out[k] for k in ("command_admitted", "management_permission_verified",
                                    "town_coverage_verified", "server_acceptance_verified"))
    # Guard support must not quietly admit type 37 to crafting operations.
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_vendor_roster(m, window="building")


@pytest.mark.parametrize("address,value", [
    (ROOT + 0x64, 0), (MANAGER + 0xD8, 1), (MANAGER + 0x50, 0),
    (MANAGER + 0x48, 0), (MANAGER + 0xD0, 3), (MANAGER + 0xF8, 999),
    (MANAGER + 0x380, 3), (MANAGER + 0x37C, 1), (ENTRY + 0x14, 42),
    (CONTROL + 0x3BC, GUARD_HUD), (GUARD_HUD + 0x104, MANAGER + 4),
    (0x190200 + 8, GUARD_HUD + 4), (BUTTON + 0x3BC, HUD),
    (BUTTON, 0), (BUTTON + 0x1A8, 2), (BUTTON + 0x304, 512),
    (MANAGER + 0x2AC, 2), (MANAGER + 0x2AC, 512),
    (SECOND_ENTRY + 0x10, 101), (SECOND_ENTRY + 0x6C, 512),
    (MANAGER + 0x68, GUARD_HUD), (MANAGER + 0x384, SECOND_ENTRY + 4),
])
def test_wrong_identity_window_ownership_counts_and_flags_rejected(address, value):
    m = fixture()
    m.put(address, "<I", value)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_guard_upgrade(m)


@pytest.mark.parametrize("address,size", [(MANAGER + 0x274, 4), (MANAGER + 0x2AC, 4),
                                          (BUTTON + 0x1A8, 4), (ENTRY + 0x28, 4),
                                          (MANAGER + 0x384, 4)])
def test_cost_flags_controls_rank_and_selection_rechecked(address, size):
    m = fixture()
    m.change = (address, size, bytes([255]) * size)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_guard_upgrade(m)


def test_vacancies_and_unknown_types_remain_distinct():
    m = fixture()
    m.put(SECOND_ENTRY + 0x14, "<I", 99)
    out = read_native_guard_upgrade(m)
    assert not out["hirelings"][1]["qualified_guard_type"]
    m.put(SECOND_ENTRY + 0x10, "<II", 0, 0)
    m.put(SECOND_ENTRY + 0x6C, "<I", 0)
    m.put(MANAGER + 0x37C, "<I", 1)
    assert read_native_guard_upgrade(m)["vacant_hireling_slots"] == 1


def test_upgrade_state_controls_and_duplicate_names():
    m = fixture()
    m.put(MANAGER + 0x2AC, "<I", 257)
    m.put(BUTTON + 0x1A8, "<I", 1)
    out = read_native_guard_upgrade(m)
    assert out["upgrade_in_progress"]
    assert not out["controls"]["BTNUPGRADE"]["enabled"]
    text(m, COST + 0x164, 0x470000, "BTNUPGRADE")
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_guard_upgrade(m)


def test_unsupported_build_rejected_before_memory_access():
    m = fixture()
    m.executable_sha256 = "0" * 64
    with pytest.raises(NativeVendorDialogCompatibilityError):
        read_native_guard_upgrade(m)
    assert not m.reads


@pytest.mark.parametrize("fail", [False, True])
def test_cli_closes_handle_and_reports_errors(fail):
    from shadowbane_lab.cli import main
    from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory
    m = fixture()
    m.close = Mock()
    if fail:
        m.put(MANAGER + 0x50, "<I", 0)
    out = io.StringIO()
    with patch.object(WindowsReadOnlyProcessMemory, "open_for_process", return_value=m), \
            redirect_stdout(out):
        status = main(["client", "observe-native-guard-upgrade", "--process-id", "988", "--json"])
    m.close.assert_called_once_with()
    assert json.loads(out.getvalue())["ok"] is (not fail)
    assert (status == 0) is (not fail)
