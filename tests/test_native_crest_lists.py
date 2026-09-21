import pytest

from shadowbane_lab.client_observation.native_crest_lists import (
    REVIEWED_CREST_EXECUTABLES,
    read_native_crest_lists,
)
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from tests.test_native_vendor_queue import CONTROL, ENTRY, HUD, LIST, ROOT
from tests.test_native_vendor_queue import fixture as queue_fixture
from tests.test_native_vendor_roster import text


def fixture():
    m = queue_fixture()
    m.executable_sha256 = next(iter(REVIEWED_CREST_EXECUTABLES))
    for address, value in (
        (HUD, m.base_address + 0x1168CA8), (HUD + 0xDC, 55),
        (HUD + 0x3C8, LIST), (HUD + 0x3B8, ENTRY),
        (ENTRY, m.base_address + 0x11693EC), (ENTRY + 8, 0x1D),
    ):
        m.put(address, "<I", value)
    for offset, key in ((0x10, (2, 0)), (0x68, (11, 53)), (0x70, (12, 23)),
                        (0x78, (12, 23))):
        m.put(ENTRY + offset, "<II", *key)
    for offset, name, buffer in ((0x20, "Someone", 0x310000),
                                 (0x38, "A guild", 0x320000),
                                 (0x50, "A nation", 0x330000)):
        text(m, ENTRY + offset, buffer, name)
    return m


def test_distinct_identity_roles_survive_equal_guild_and_nation_keys():
    result = read_native_crest_lists(fixture())
    window = result["windows"][0]
    row = window["entries"][0]
    assert not window["visibility_verified"] and row["selected"]
    assert row["row_key_raw"] == {"object_id": 2, "object_type": 0}
    assert row["identities"]["guild"] == row["identities"]["nation"]
    assert row["display_labels_raw"] == ["Someone", "A guild", "A nation"]
    assert not any(result[k] for k in (
        "command_admitted", "server_acceptance_verified", "town_coverage_verified",
    ))


def test_unbound_kos_is_retained_without_claiming_visibility_or_active_building():
    m = fixture()
    m.put(HUD, "<I", m.base_address + 0x1168E94)
    m.put(HUD + 0xFC, "<I", 1)
    m.put(HUD + 0x3B8, "<I", 0)
    m.put(LIST + 0x408, "<III", 0, 0, 0)
    window = read_native_crest_lists(m)["windows"][0]
    assert not window["visibility_verified"] and window["entries"] == []
    assert window["hud_flag_fc_raw"] == 1
    assert window["context_key_raw"] == {"object_id": 0, "object_type": 0}


def test_options_window_does_not_parse_list_fields():
    m = fixture()
    m.put(HUD, "<I", m.base_address + 0x1168AD4)
    m.put(HUD + 0x3E8, "<8B", 0, 1, 0, 1, 0, 0, 0, 0)
    window = read_native_crest_lists(m)["windows"][0]
    assert window["options_raw"] == [0, 1, 0, 1, 0]
    assert (HUD + 0x3C8, 4) not in m.reads


def test_unrecognized_hud_does_not_read_arbitrary_crest_fields():
    m = fixture()
    m.put(HUD, "<I", m.base_address + 0x123456)
    assert read_native_crest_lists(m)["windows"] == []
    assert (HUD + 0x3C8, 4) not in m.reads


@pytest.mark.parametrize("address,value", [
    (ROOT + 0x64, 1), (LIST + 0x3BC, HUD + 4),
    (CONTROL + 0x3BC, HUD + 4), (CONTROL + 0x458, LIST + 4),
    (ENTRY, 0), (ENTRY + 8, 9), (HUD + 0x3B8, ENTRY + 4),
    (0x160000, LIST + 4),
])
def test_wrong_lifetime_layout_or_ownership_is_rejected(address, value):
    m = fixture()
    m.put(address, "<I", value)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_crest_lists(m)


@pytest.mark.parametrize("address,size", [
    (ENTRY + 0x70, 8), (LIST + 0x408, 12), (HUD + 0xFC, 4),
    (HUD + 0x3B8, 4), (0x320000, len("A guild".encode("utf-16-le"))),
])
def test_changing_list_identity_flag_or_name_rejects_whole_snapshot(address, size):
    m = fixture()
    m.change = address, size, bytes([255]) * size
    with pytest.raises(NativeVendorDialogCaptureError, match="changed"):
        read_native_crest_lists(m)


def test_unreviewed_older_vendor_build_is_rejected_before_memory_reads():
    m = queue_fixture()
    with pytest.raises(NativeVendorDialogCompatibilityError):
        read_native_crest_lists(m)
    assert not m.reads


def test_multiple_controls_cannot_alias_one_entry():
    m = fixture()
    other = 0x210000
    m.put(LIST + 0x408, "<III", 0x170000, 0x170008, 0x170010)
    m.put(0x170000, "<II", CONTROL, other)
    for offset, value in ((0, m.base_address + 0x116AEBC), (0x3BC, HUD),
                           (0x458, LIST), (0x44C, ENTRY)):
        m.put(other + offset, "<I", value)
    with pytest.raises(NativeVendorDialogCaptureError, match="duplicate"):
        read_native_crest_lists(m)


def test_nation_condemn_label_is_not_reported_as_a_character_name():
    m = fixture()
    m.put(HUD, "<I", m.base_address + 0x1168E94)
    m.put(HUD + 0xFC, "<I", 1)
    m.put(HUD + 0x3D0, "<II", 500, 8)
    m.put(ENTRY + 0x10, "<II", 12, 23)
    m.put(ENTRY + 0x68, "<II", 0, 0)
    m.put(ENTRY + 0x70, "<II", 0, 0)
    m.put(ENTRY + 0x84, "<4B", 0, 0, 1, 0)
    text(m, ENTRY + 0x20, 0x310000, "A nation")
    m.put(ENTRY + 0x38 + 4, "<III", 0, 0, 0)
    m.put(ENTRY + 0x50 + 4, "<III", 0, 0, 0)
    window = read_native_crest_lists(m)["windows"][0]
    row = window["entries"][0]
    assert window["context_key_raw"] == {"object_id": 500, "object_type": 8}
    assert row["identities"]["character"] == {"object_id": 0, "object_type": 0}
    assert row["identities"]["guild"] == {"object_id": 0, "object_type": 0}
    assert row["identities"]["nation"] == {"object_id": 12, "object_type": 23}
    assert row["display_labels_raw"] == ["A nation", "", ""]
    assert row["flags_raw"] == [0, 0, 1]
    assert "visible" not in window and not window["visibility_verified"]


@pytest.mark.parametrize("raw_flag", [0, 1, 2, 255])
def test_unqualified_hud_flag_never_becomes_a_visibility_claim(raw_flag):
    m = fixture()
    m.put(HUD + 0xFC, "<I", raw_flag)
    window = read_native_crest_lists(m)["windows"][0]
    assert window["hud_flag_fc_raw"] == raw_flag
    assert "visible" not in window and not window["visibility_verified"]
