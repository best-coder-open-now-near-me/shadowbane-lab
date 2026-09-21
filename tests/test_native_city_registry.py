import pytest

from shadowbane_lab.client_observation.native_city_registry import read_native_city_registry
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from tests.test_native_crest_lists import fixture as crest_fixture
from tests.test_native_vendor_roster import text

CACHE = 0x400000 + 0x16ABBF0
HEAD, NODE, OTHER = 0x400000, 0x400100, 0x400200
DATA, OTHER_DATA = 0x410000, 0x420000


def fixture():
    m = crest_fixture()
    m.put(CACHE, "<II", HEAD, 2)
    m.put(HEAD + 4, "<III", NODE, OTHER, NODE)
    m.put(NODE + 4, "<III", HEAD, OTHER, 0)
    m.put(OTHER + 4, "<III", NODE, 0, 0)
    for node, data, key, label, buffer in (
        (NODE, DATA, 100, "City A", 0x430000),
        (OTHER, OTHER_DATA, 50, "City B", 0x440000),
    ):
        m.put(node + 0x10, "<III", key, 15, data)
        m.put(data, "<II", key, 15)
        m.put(data + 0x118, "<I", m.base_address + 0x117A704)
        m.put(data + 0x190, "<I", m.base_address + 0x117A6CC)
        m.put(data + 8, "<II", 20, 23)
        m.put(data + 0x88, "<II", key + 1, 23)
        text(m, data + 0x10, buffer, "Shared crest")
        text(m, data + 0x28, buffer + 0x100, label)
        text(m, data + 0x90, buffer + 0x200, "Other crest")
    return m


def test_reads_shared_crest_keys_without_merging_cities_or_inventing_coverage():
    result = read_native_city_registry(fixture())
    assert result["cache_count"] == 2
    a, b = result["cities"]
    assert (a["city_name"], b["city_name"]) == ("City A", "City B")
    assert a["nation"] == b["nation"]
    assert a["guild"] != b["guild"]
    assert not any(result[k] for k in (
        "command_admitted", "cache_freshness_verified",
        "complete_guild_directory_verified",
    ))


def test_empty_cache_is_not_proof_of_no_guilds():
    m = fixture()
    m.put(CACHE + 4, "<I", 0)
    m.put(HEAD + 4, "<III", 0, HEAD, HEAD)
    result = read_native_city_registry(m)
    assert result["cities"] == []
    assert not result["complete_guild_directory_verified"]


@pytest.mark.parametrize("address,value", [
    (CACHE + 4, 2049), (CACHE + 4, 1), (CACHE + 4, 3),
    (HEAD + 4, 0), (HEAD + 8, NODE), (HEAD + 12, OTHER),
    (NODE + 4, 0), (OTHER + 4, HEAD),
    (NODE + 8, HEAD), (OTHER + 8, NODE), (NODE + 12, OTHER),
    (DATA + 0x118, 0), (DATA + 0x190, 0), (DATA, 777),
    (NODE + 0x10, 0), (OTHER + 0x10, 100), (OTHER + 0x18, DATA),
])
def test_broken_tree_identity_or_record_ownership_rejects_snapshot(address, value):
    m = fixture()
    m.put(address, "<I", value)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_city_registry(m)


@pytest.mark.parametrize("address,size", [
    (CACHE, 8), (HEAD + 4, 12), (NODE + 4, 12), (OTHER + 0x18, 4),
    (DATA + 0x88, 8), (DATA + 0x190, 4), (0x430100, 12),
])
def test_changed_cache_or_name_is_not_returned(address, size):
    m = fixture()
    m.change = address, size, bytes([255]) * size
    with pytest.raises(NativeVendorDialogCaptureError, match="changed"):
        read_native_city_registry(m)


def test_unsupported_client_is_rejected_before_reading():
    m = fixture()
    m.executable_sha256 = "0" * 64
    with pytest.raises(NativeVendorDialogCompatibilityError):
        read_native_city_registry(m)
    assert not m.reads


def test_equal_nation_and_guild_keys_keep_both_roles():
    m = fixture()
    m.put(DATA + 0x88, "<II", 20, 23)
    row = read_native_city_registry(m)["cities"][0]
    assert row["nation"]["key"] == row["guild"]["key"]
    assert row["nation"]["name"] != row["guild"]["name"]


def test_zero_crest_keys_are_retained_without_becoming_targets():
    m = fixture()
    m.put(DATA + 8, "<II", 0, 0)
    m.put(DATA + 0x88, "<II", 0, 0)
    result = read_native_city_registry(m)
    assert result["cities"][0]["nation"]["key"] == {"object_id": 0, "object_type": 0}
    assert not result["command_admitted"]
