import pytest

from shadowbane_lab.client_observation.native_nearby_vendor_roster import (
    read_native_nearby_hirelings,
    read_native_nearby_vendor_roster,
)
from shadowbane_lab.client_observation.native_vendor_dialog import NativeVendorDialogCaptureError
from tests.test_native_nearby_vendor_roster import (
    BLOCK,
    HIRELING,
    VNODE,
    VNODE2,
    nearby_fixture,
)


def test_mixed_guard_vendor_and_unknown_candidates_do_not_grant_eligibility():
    memory = nearby_fixture()
    memory.put(VNODE + 0x14, "<I", 37)
    result = read_native_nearby_hirelings(memory)
    assert result["buildings"][1]["hirelings"][0]["hireling"]["object_type"] == 37
    assert result["buildings"][0]["hirelings"][0]["hireling"]["object_type"] == 42
    assert not result["town_membership_verified"] and not result["roster_complete"]
    assert not result["command_admitted"]
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_nearby_vendor_roster(memory)
    memory.put(VNODE + 0x14, "<I", 99)
    assert read_native_nearby_hirelings(memory)["buildings"][1]["hirelings"][0][
        "hireling"
    ]["object_type"] == 99


@pytest.mark.parametrize("address,value", [
    (VNODE + 0x14, 0), (VNODE2 + 0x10, 401), (VNODE2 + 0x18, HIRELING),
    (VNODE + 4, 0), (VNODE + 8, VNODE), (BLOCK + 0x3C, 257),
])
def test_generic_types_do_not_relax_identity_or_owned_tree_checks(address, value):
    memory = nearby_fixture()
    memory.put(address, "<I", value)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_nearby_hirelings(memory)


def test_mixed_candidates_are_consistency_rechecked():
    memory = nearby_fixture()
    memory.put(VNODE + 0x14, "<I", 37)
    memory.change = (VNODE + 4, 24, bytes(24))
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_nearby_hirelings(memory)
