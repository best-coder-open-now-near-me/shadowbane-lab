import struct
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from test_active_character_config import CharacterMemory
from test_native_character_population import FakeScanningProcess, _profile

from shadowbane_lab.client_observation.native_character_config import (
    REVIEWED_CHARACTER_CONFIG_LAYOUTS,
    ActiveCharacterError,
    NativeCharacterConfigReader,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.client_observation.native_population import (
    NativeCharacterPopulationReader,
    NativeCharacterPopulationReadError,
)


def memory(tmp_path):
    m = CharacterMemory(tmp_path)
    m.layout = REVIEWED_CHARACTER_CONFIG_LAYOUTS[-1]
    m.executable_sha256 = m.layout.executable_sha256
    m.set_identity("Umbra", "Wonderbane")
    m.put(m.player + 0x18, struct.pack("<II", 7, 53))
    remote = 0x30000000
    m.put(remote, struct.pack("<I", m.base_address + m.layout.character_vtable_rva))
    m.put(remote + 0x18, struct.pack("<II", 42, 53))
    for offset, address, value in ((m.layout.name_offset, 0x40000000, "Other Player"),
                                   (m.layout.server_offset, 0x40001000, "Wonderbane")):
        raw = value.encode("utf-16-le")
        m.put(remote + offset, struct.pack("<IIII", 0, address,
                                          address + len(raw), address + len(raw) + 2))
        m.put(address, raw + b"\0\0")
    return m, remote


def test_remote_identity_never_reads_selection(tmp_path):
    m, remote = memory(tmp_path)
    reader = NativeCharacterConfigReader(m)
    result = reader.observe_player_at(remote, NativeObjectKey(42, 53))
    assert result.character_name == "Other Player" and result.server_name == "Wonderbane"
    assert not any(address == m.base_address + 0x16A2DA4 for address, _ in m.reads)
    assert not m.closed


@pytest.mark.parametrize("kind", ["key", "vtable", "name", "server", "self"])
def test_remote_changed_or_invalid_identity_refused(tmp_path, kind):
    m, remote = memory(tmp_path)
    reader = NativeCharacterConfigReader(m)
    if kind == "key":
        m.put(remote + 0x18, struct.pack("<II", 43, 53))
    if kind == "vtable":
        m.put(remote, b"\0" * 4)
    if kind == "server":
        m.put(0x40001000, "Otherworld".encode("utf-16-le"))
    if kind == "name":
        m.put(0x40000000, "\n".encode("utf-16-le"))
    if kind == "self":
        remote = m.player
    with pytest.raises(ActiveCharacterError):
        reader.observe_player_at(remote, NativeObjectKey(42, 53))


def test_remote_replacement_between_name_reads_refused(tmp_path):
    m, remote = memory(tmp_path)
    original = m.read
    def read(address, length):
        value = original(address, length)
        if address == 0x40000000:
            m.put(remote + 0x18, struct.pack("<II", 43, 53))
        return value
    m.read = read
    with pytest.raises(ActiveCharacterError, match="changed"):
        NativeCharacterConfigReader(m).observe_player_at(remote, NativeObjectKey(42, 53))


@pytest.mark.parametrize("mutation", [None, "membership", "key", "lifetime"])
def test_population_brackets_identity_with_real_registry(mutation):
    profile = _profile()
    process = FakeScanningProcess(profile)
    process.process_creation_filetime_utc = 123
    process._character(process.crab, object_key=(2001, 53), health=(75, 75),
                       position=(108, 5, -206))
    population = NativeCharacterPopulationReader(profile, process)
    character = next(c for c in population.observe().characters
                     if c.object_key == NativeObjectKey(2001, 53))
    reader = Mock(spec=NativeCharacterConfigReader)
    reader.process = process
    reader.process_creation_filetime_utc = 124 if mutation == "lifetime" else 123
    reader.observe_local_key.return_value = NativeObjectKey(1001, 53)
    def observe(*args):
        if mutation == "membership":
            process.set_registry(process.player, process.trainer)
        if mutation == "key":
            process._character(process.crab, object_key=(2009, 53), health=(75, 75),
                               position=(108, 5, -206))
        return NS(object_key=character.object_key, character_name="Other", server_name="Wonderbane")
    reader.observe_player_at.side_effect = observe
    if mutation is None:
        assert population.observe_player_identity(character.token, character.object_key,
                                                   reader).character_name == "Other"
    else:
        with pytest.raises((ValueError, NativeCharacterPopulationReadError)):
            population.observe_player_identity(character.token, character.object_key, reader)
    assert not process.closed
