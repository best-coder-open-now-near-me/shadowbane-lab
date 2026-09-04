"""Read the local-player identity used by the client's SCREEN_GAME paths.

New fields require their own build review, not the older native-layout family.
See docs/active-character-profile.md for the offline mapping evidence.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .native_health import ReadOnlyProcessMemory


class ActiveCharacterError(RuntimeError):
    """No trustworthy active-character configuration can be established."""


@dataclass(frozen=True, slots=True)
class CharacterConfigLayout:
    executable_sha256: str
    player_pointer_rva: int
    character_config_enabled_rva: int
    character_vtable_rva: int
    name_offset: int
    server_offset: int


# Load/save routines at RVAs 0x795DA0 and 0x7963E0 in this exact executable.
REVIEWED_CHARACTER_CONFIG_LAYOUTS = (
    CharacterConfigLayout(
        executable_sha256="55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc",
        player_pointer_rva=0x16A2D98,
        character_config_enabled_rva=0x16A7C60,
        character_vtable_rva=0x114165C,
        name_offset=0xC48,
        server_offset=0xC90,
    ),
)


@dataclass(frozen=True, slots=True)
class ActiveCharacterIdentity:
    player_pointer: int
    character_name: str
    server_name: str

    @property
    def config_filename(self) -> str:
        # Core::String formats each UTF-16 code unit as four hexadecimal digits.
        encoded = self.character_name.encode("utf-16-be").hex().upper()
        return f"SCREEN_GAME_{encoded}_{self.server_name}.cfg"


class NativeCharacterConfigReader:
    """Bounded reads through an already-open, read-only process handle."""

    def __init__(self, process: ReadOnlyProcessMemory) -> None:
        self.process = process
        layout = next(
            (
                item
                for item in REVIEWED_CHARACTER_CONFIG_LAYOUTS
                if item.executable_sha256 == process.executable_sha256.lower()
            ),
            None,
        )
        if process.executable_name.casefold() != "sb.exe" or process.pointer_size != 4:
            raise ActiveCharacterError("active-character selection requires reviewed 32-bit sb.exe")
        if layout is None:
            raise ActiveCharacterError(
                "active-character mapping is not reviewed for client SHA-256 "
                f"{process.executable_sha256}; review its config-selection layout before use"
            )
        creation = getattr(process, "process_creation_filetime_utc", None)
        if isinstance(creation, bool) or not isinstance(creation, int) or creation <= 0:
            raise ActiveCharacterError("active-character selection requires process creation time")
        self.layout = layout
        self.process_creation_filetime_utc = creation

    def observe(self) -> ActiveCharacterIdentity:
        first = self._snapshot()
        if self._snapshot() != first:
            raise ActiveCharacterError("active character changed during profile selection; retry")
        return first

    def _snapshot(self) -> ActiveCharacterIdentity:
        base = self.process.base_address
        layout = self.layout
        flag_address = base + layout.character_config_enabled_rva
        if self._read(flag_address, 1) != b"\x01":
            raise ActiveCharacterError(
                "character-specific configuration is not active; log in first"
            )
        pointer_address = base + layout.player_pointer_rva
        pointer = struct.unpack("<I", self._read(pointer_address, 4))[0]
        self._range(pointer, layout.server_offset + 16, alignment=4)
        if self._read(pointer, 4) != struct.pack("<I", base + layout.character_vtable_rva):
            raise ActiveCharacterError("local player is not a reviewed ArcCharacter instance")
        name = self._string(pointer + layout.name_offset)
        server = self._string(pointer + layout.server_offset)
        for value in (name, server):
            if (
                not value
                or value != value.strip()
                or any(ord(char) < 32 or ord(char) == 127 or char in '<>:"/\\|?*' for char in value)
                or value.endswith(".")
            ):
                raise ActiveCharacterError("character/server contains an invalid filename value")
        if (
            self._read(pointer_address, 4) != struct.pack("<I", pointer)
            or self._read(flag_address, 1) != b"\x01"
        ):
            raise ActiveCharacterError("active character changed during profile selection; retry")
        identity = ActiveCharacterIdentity(pointer, name, server)
        if len(identity.config_filename.encode("utf-8")) >= 290:
            raise ActiveCharacterError("character configuration filename exceeds client bounds")
        return identity

    def _string(self, address: int) -> str:
        header = self._read(address, 16)
        begin, end, capacity = struct.unpack_from("<III", header, 4)
        if end <= begin or end - begin > 128 or (end - begin) % 2 or capacity < end + 2:
            raise ActiveCharacterError("active character Core::String bounds are invalid")
        self._range(begin, end - begin + 2, alignment=2)
        if capacity > 0x7FFEFFFF:
            raise ActiveCharacterError("active character Core::String capacity is invalid")
        raw = self._read(begin, end - begin + 2)
        if raw[-2:] != b"\x00\x00" or self._read(address, 16) != header:
            raise ActiveCharacterError("active character string changed or is not terminated")
        try:
            return raw[:-2].decode("utf-16-le")
        except UnicodeError as exc:
            raise ActiveCharacterError("active character string is not valid UTF-16") from exc

    @staticmethod
    def _range(address: int, size: int, *, alignment: int = 1) -> None:
        if address < 0x10000 or address + size > 0x7FFEFFFF or address % alignment:
            raise ActiveCharacterError("active character pointer is outside the bounded user range")

    def _read(self, address: int, size: int) -> bytes:
        self._range(address, size)
        chunks = []
        for offset in range(0, size, 64):
            length = min(64, size - offset)
            try:
                chunk = self.process.read(address + offset, length)
            except Exception as exc:
                raise ActiveCharacterError("could not read the bound active character") from exc
            if len(chunk) != length:
                raise ActiveCharacterError("partial active character read")
            chunks.append(chunk)
        return b"".join(chunks)
