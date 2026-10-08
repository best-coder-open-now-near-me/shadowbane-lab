import struct

import pytest
from test_native_character_session import setup_session

from shadowbane_lab.character_capture.binding import PrivateServerCharacterReader
from shadowbane_lab.client_observation.native_character_config import (
    ActiveCharacterError,
    NativeCharacterConfigReader,
)
from shadowbane_lab.client_observation.native_character_session import NativeCharacterSession


def test_private_type_is_explicit_and_does_not_weaken_wonderbane(tmp_path):
    memory, _ = setup_session(tmp_path)
    memory.put(memory.player + 0x18, struct.pack("<II", 1001, 52))
    with pytest.raises(ActiveCharacterError):
        NativeCharacterSession(NativeCharacterConfigReader(memory))
    session = NativeCharacterSession(PrivateServerCharacterReader(memory))
    assert session.binding.object_key.object_uuid == 52
    memory.put(memory.player + 0x18, struct.pack("<II", 1002, 52))
    with pytest.raises(ActiveCharacterError):
        session.require_current()
