"""Explicit source-protocol binding for the private server's own-player captures."""

import struct

from shadowbane_lab.client_observation.native_character_config import (
    ActiveCharacterError,
    NativeCharacterConfigReader,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey

from .build import SUPPORTED_IMAGES


class PrivateServerCharacterReader(NativeCharacterConfigReader):
    """Magicbane-derived GameObjectType.PlayerCharacter is wire type 52.

    Wonderbane's existing reader continues to require 53. This reader is used only
    by the explicit Private SB capture profile, never bot/action authorization.
    """

    def observe_local_key(self):
        if self.process.executable_sha256.lower() not in SUPPORTED_IMAGES:
            raise ActiveCharacterError("Private-server capture requires reviewed .14.")
        before = self.observe()
        raw = self._read(before.player_pointer + 0x18, 8)
        key = NativeObjectKey(*struct.unpack("<II", raw))
        if not key.object_type or key.object_uuid != 52:
            raise ActiveCharacterError("Private-server local object is not a type-52 player.")
        if self.observe() != before or self._read(before.player_pointer + 0x18, 8) != raw:
            raise ActiveCharacterError("Private-server player changed during identity read.")
        return key
