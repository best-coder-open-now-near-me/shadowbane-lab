"""Exact native character lifetime, independent of saved hotbar/settings files."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .native_character_config import (
    ActiveCharacterError,
    ActiveCharacterIdentity,
    NativeCharacterConfigReader,
)
from .native_health import WindowsReadOnlyProcessMemory
from .native_object import NativeObjectKey


@dataclass(frozen=True, slots=True)
class NativeCharacterBinding:
    process_id: int
    process_creation_filetime_utc: int
    executable_path: Path
    executable_sha256: str
    identity: ActiveCharacterIdentity
    object_key: NativeObjectKey

    def as_dict(self) -> dict[str, object]:
        return {
            "identity_source": "native-local-player-character-and-server",
            "process_id": self.process_id,
            "process_creation_filetime_utc": self.process_creation_filetime_utc,
            "executable_path": str(self.executable_path),
            "executable_sha256": self.executable_sha256,
            "character_name": self.identity.character_name,
            "server_name": self.identity.server_name,
            "object_key": [self.object_key.object_type, self.object_key.object_uuid],
        }


class NativeCharacterSession:
    """One process handle and character; a lost binding never reauthorizes itself."""

    def __init__(self, reader: NativeCharacterConfigReader) -> None:
        self.reader = reader
        self._revoked = False
        process = reader.process
        identity = reader.observe()
        key = reader.observe_local_key()
        self.binding = NativeCharacterBinding(
            process.pid, reader.process_creation_filetime_utc, process.executable_path,
            process.executable_sha256, identity, key,
        )
        self.require_current()

    def require_current(self) -> None:
        if self._revoked:
            raise ActiveCharacterError("native character binding was revoked; initialize again")
        try:
            if (self.reader.observe() != self.binding.identity
                    or self.reader.observe_local_key() != self.binding.object_key
                    or self.reader.observe() != self.binding.identity):
                raise ActiveCharacterError("native character identity changed; initialize again")
        except Exception:
            self._revoked = True
            raise

    def close(self) -> None:
        self._revoked = True
        self.reader.process.close()

    def __enter__(self) -> NativeCharacterSession:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def open_native_character_session(*, process_id: int) -> NativeCharacterSession:
    process = WindowsReadOnlyProcessMemory.open_for_process("sb.exe", process_id)
    try:
        return NativeCharacterSession(NativeCharacterConfigReader(process))
    except Exception:
        process.close()
        raise
