import struct

import pytest
from test_active_character_config import CharacterMemory, write_profile

from shadowbane_lab.client_observation.native_character_config import (
    REVIEWED_CHARACTER_CONFIG_LAYOUTS,
    ActiveCharacterError,
    NativeCharacterConfigReader,
)
from shadowbane_lab.client_observation.native_character_session import NativeCharacterSession


def setup_session(tmp_path):
    memory = CharacterMemory(tmp_path)
    memory.executable_sha256 = REVIEWED_CHARACTER_CONFIG_LAYOUTS[-1].executable_sha256
    memory.put(memory.player + 0x18, struct.pack("<II", 1001, 53))
    return memory, NativeCharacterSession(NativeCharacterConfigReader(memory))


def test_native_identity_does_not_require_or_pin_saved_settings(tmp_path):
    memory, session = setup_session(tmp_path)
    session.require_current()  # No saved character file exists.
    settings = write_profile(memory)
    settings.write_bytes(b"changed hotbar mappings")
    session.require_current()
    assert "config_sha256" not in session.binding.as_dict()
    session.close()
    assert memory.closed


@pytest.mark.parametrize("change", ["key", "name", "server", "closed"])
def test_character_change_permanently_revokes_binding(tmp_path, change):
    memory, session = setup_session(tmp_path)
    if change == "key":
        memory.put(memory.player + 0x18, struct.pack("<II", 1002, 53))
    elif change == "name":
        memory.set_identity("replacement", "Wonderbane")
    elif change == "server":
        memory.set_identity("testercle", "OtherServer")
    else:
        session.close()
    with pytest.raises(ActiveCharacterError):
        session.require_current()
    memory.set_identity("testercle", "Wonderbane")
    memory.put(memory.player + 0x18, struct.pack("<II", 1001, 53))
    with pytest.raises(ActiveCharacterError, match="revoked"):
        session.require_current()
