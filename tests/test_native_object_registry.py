"""Exact membership and bounded coherent capture of the native ArcWorld registry."""

import json
import struct
from dataclasses import replace
from importlib.resources import files
from unittest.mock import Mock

import pytest
from test_native_character_population import FakeScanningProcess, _profile

from shadowbane_lab.client_observation.native_population import (
    NativeCharacterPopulationProfileLoadError,
    load_native_character_population_profile_text,
)
from shadowbane_lab.client_observation.native_registry import (
    NativeObjectRegistryReader,
    NativeObjectRegistryReadError,
    NativeObjectRegistrySnapshotChanged,
)


def fixture(**changes):
    process = FakeScanningProcess(_profile())
    profile = replace(process.profile.registry_profile, **changes)
    now = [0.0]
    reader = NativeObjectRegistryReader(profile, process, clock=lambda: now[0])
    return process, reader, now


def test_capture_has_only_registry_members_and_no_heap_scan():
    process, reader, _ = fixture()
    snapshot = reader.capture()
    assert [entry.address for entry in snapshot.objects] == [
        process.player,
        process.crab,
        process.trainer,
    ]
    assert process.find_calls == 0
    reader.verify(snapshot)


@pytest.mark.parametrize(
    "field,value",
    [("executable_sha256", "b" * 64), ("pointer_size", 8), ("executable_name", "other.exe")],
)
def test_registry_does_not_inherit_unreviewed_family_admission(field, value):
    process, _, _ = fixture()
    setattr(process, field, value)
    with pytest.raises(NativeObjectRegistryReadError, match="exact qualified"):
        NativeObjectRegistryReader(process.profile.registry_profile, process)


@pytest.mark.parametrize("which", ["world", "registry", "buckets", "object"])
@pytest.mark.parametrize("value", [0, 4, 0xFFFF, 0xFFFFFFFF])
def test_invalid_pointers_reject_before_offset_arithmetic(which, value):
    process, reader, _ = fixture()
    address = {
        "world": process.base_address + 0x108,
        "registry": process.world + 0x94,
        "buckets": process.registry + 4,
        "object": process.buckets + 4,
    }[which]
    if which == "object" and value in (0, 0xFFFFFFFF):
        return  # Native empty and tombstone values, tested separately.
    payload = bytearray(process.memory.get(address, b""))
    if payload:
        struct.pack_into("<I", payload, 0, value)
        process.memory[address] = bytes(payload)
    else:
        block = bytearray(process.memory[process.buckets])
        struct.pack_into("<I", block, 4, value)
        process.memory[process.buckets] = bytes(block)
    with pytest.raises(NativeObjectRegistryReadError):
        reader.capture()


def test_empty_and_tombstone_buckets_are_not_objects():
    process, reader, _ = fixture()
    process.set_registry(process.player, 0, 0xFFFFFFFF)
    assert [o.address for o in reader.capture().objects] == [process.player]


@pytest.mark.parametrize("change", ["pointer", "key", "capacity", "count"])
def test_duplicate_and_oversized_membership_is_never_partial(change):
    process, reader, _ = fixture()
    if change == "pointer":
        process.set_registry(process.player, process.crab, process.crab)
    if change == "key":
        block = bytearray(process.memory[process.trainer])
        struct.pack_into("<II", block, 0x10, 2001, 37)
        process.memory[process.trainer] = bytes(block)
    if change == "capacity":
        process.memory[process.registry + 4] = struct.pack("<II", process.buckets, 17)
    if change == "count":
        reader = NativeObjectRegistryReader(replace(reader.profile, maximum_objects=2), process)
    with pytest.raises(NativeObjectRegistryReadError):
        reader.capture()


@pytest.mark.parametrize(
    "part", ["world", "registry", "buckets", "exponent", "member", "key", "vtable"]
)
def test_final_verification_covers_every_membership_structure(part):
    process, reader, _ = fixture()
    snapshot = reader.capture()
    if part == "world":
        process.memory[process.base_address + 0x108] = struct.pack("<I", process.world + 4)
    elif part == "registry":
        process.memory[process.world + 0x94] = struct.pack("<I", process.registry + 4)
    elif part in ("buckets", "exponent"):
        process.memory[process.registry + 4] = struct.pack(
            "<II", process.buckets + (4 if part == "buckets" else 0), 3 if part == "exponent" else 2
        )
    elif part == "member":
        process.set_registry(process.player, process.trainer)
    else:
        block = bytearray(process.memory[process.crab])
        struct.pack_into("<I", block, 0 if part == "vtable" else 0x10, 999)
        process.memory[process.crab] = bytes(block)
    with pytest.raises(NativeObjectRegistrySnapshotChanged, match="changed"):
        reader.verify(snapshot)


def test_shared_deadline_includes_time_spent_reading_population_fields():
    _, reader, now = fixture()
    snapshot = reader.capture()
    now[0] = 0.201
    with pytest.raises(NativeObjectRegistryReadError, match="budget"):
        reader.verify(snapshot)
    with pytest.raises(NativeObjectRegistryReadError, match="budget"):
        reader.check_budget(snapshot)


@pytest.mark.parametrize("limit", [{"maximum_reads": 1}, {"maximum_bytes": 4}])
def test_read_and_byte_budget_exhaustion_cannot_return_partial_snapshot(limit):
    _, reader, _ = fixture(**limit)
    with pytest.raises(NativeObjectRegistryReadError, match="budget"):
        reader.capture()


def test_read_deadline_is_checked_after_backend_returns():
    process, reader, now = fixture()
    original = process.read

    def slow(address, size):
        result = original(address, size)
        now[0] = 1.0
        return result

    process.read = slow
    with pytest.raises(NativeObjectRegistryReadError, match="budget"):
        reader.capture()


def test_incomplete_read_has_no_snapshot():
    process, reader, _ = fixture()
    process.read = Mock(return_value=b"")
    with pytest.raises(NativeObjectRegistryReadError, match="partial"):
        reader.capture()


def test_bundled_nested_schema_is_exact_and_legacy_scan_profile_is_rejected():
    resource = files("shadowbane_lab.client_observation").joinpath(
        "data", "wonderbane-ef43784b.native-character-population.json"
    )
    raw = json.loads(resource.read_text())
    profile = load_native_character_population_profile_text(json.dumps(raw))
    assert profile.schema_version == 4 and profile.registry_profile.world_pointer_rva == 0x1389028
    assert set(profile.registry_profile.executable_sha256s) == {
        "3891fcab09dac06d858ac55911046448e75f3519e2f58e1d7c2ccc954aa410b7",
        "2dc0e19c3fcf43bc19508939fb9c63982bc370a868f810208394324a12cdc289",
        "e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8",
        "0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d",
        "381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5",
        "a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a",
        "e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e",
        "e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437",
        "1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c",
        "78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903",
    }
    raw["schema_version"] = 3
    with pytest.raises(NativeCharacterPopulationProfileLoadError):
        load_native_character_population_profile_text(json.dumps(raw))
    raw["schema_version"] = 4
    raw["registry_profile"]["unexpected"] = True
    with pytest.raises(NativeCharacterPopulationProfileLoadError):
        load_native_character_population_profile_text(json.dumps(raw))
