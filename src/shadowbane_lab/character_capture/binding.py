"""Explicit source-protocol binding for the private server's own-player captures."""

import struct
from dataclasses import replace

from shadowbane_lab.client_observation.native_character_config import (
    REVIEWED_CHARACTER_CONFIG_LAYOUTS,
    ActiveCharacterError,
    NativeCharacterConfigReader,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey

from .build import ORIGINAL_14, SUPPORTED_IMAGES


class CaptureCharacterReader(NativeCharacterConfigReader):
    """Original .14 identity review belongs to read-only capture, not bot admission."""
    reviewed_layouts = REVIEWED_CHARACTER_CONFIG_LAYOUTS + (
        replace(REVIEWED_CHARACTER_CONFIG_LAYOUTS[-1], executable_sha256=ORIGINAL_14),
    )


class PrivateServerCharacterReader(CaptureCharacterReader):
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
