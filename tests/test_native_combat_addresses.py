"""Canonical object addresses remain distinct from opaque observation tokens."""
import struct

import pytest
from test_native_character_population import FakeScanningProcess, _profile

from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.client_observation.native_population import (
    NativeCharacterPopulationReader,
    NativeCharacterPopulationReadError,
)


def setup_reader():
    profile = _profile()
    process = FakeScanningProcess(profile)
    reader = NativeCharacterPopulationReader(profile, process)
    frame = reader.observe()
    target = next(c for c in frame.characters if c.object_key == NativeObjectKey(2001, 37))
    return process, reader, dict(local_key=frame.local_player_object_key,
                                target_token=target.token, target_key=target.object_key)


def test_resolves_exact_objects_without_reading_selection():
    process, reader, binding = setup_reader()
    del process.memory[process.base_address + process.profile.selected_pointer_rva]
    assert reader.resolve_combat_addresses(**binding) == (process.player, process.crab)
    assert process.find_calls == 0


@pytest.mark.parametrize("change", ["unknown_token", "wrong_key", "replaced", "actor", "closed"])
def test_rejects_stale_or_noncanonical_identity(change):
    process, reader, binding = setup_reader()
    if change == "unknown_token":
        binding["target_token"] = format(process.crab, "x")
    elif change == "wrong_key":
        binding["target_key"] = NativeObjectKey(2002, 37)
    elif change == "replaced":
        block = bytearray(process.memory[process.crab])
        struct.pack_into("<II", block, process.profile.object_type_offset, 9999, 37)
        process.memory[process.crab] = bytes(block)
    elif change == "actor":
        binding["local_key"] = NativeObjectKey(9999, 53)
    else:
        reader.close()
    with pytest.raises(NativeCharacterPopulationReadError):
        reader.resolve_combat_addresses(**binding)


def test_target_replaced_between_resolution_reads_is_rejected():
    process, reader, binding = setup_reader()
    process.block_reads.clear()
    process.identity_changes[process.crab] = (9999, 37)
    with pytest.raises(NativeCharacterPopulationReadError):
        reader.resolve_combat_addresses(**binding)
