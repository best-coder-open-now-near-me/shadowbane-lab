"""Bind a saved character config to one process lifetime and login identity."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from shadowbane_lab.client_observation.native_character_config import (
    ActiveCharacterError,
    ActiveCharacterIdentity,
    NativeCharacterConfigReader,
)
from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory

_MAX_CONFIG_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class CharacterConfigBinding:
    process_id: int
    process_creation_filetime_utc: int
    executable_path: Path
    executable_sha256: str
    identity: ActiveCharacterIdentity
    config_path: Path
    config_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "selection_source": "native-local-player-character-and-server",
            "process_id": self.process_id,
            "process_creation_filetime_utc": self.process_creation_filetime_utc,
            "executable_path": str(self.executable_path),
            "executable_sha256": self.executable_sha256,
            "character_name": self.identity.character_name,
            "server_name": self.identity.server_name,
            "config_path": str(self.config_path),
            "config_sha256": self.config_sha256,
        }


class CharacterConfigSession:
    """A failed/relogged binding stays revoked until a fresh operation initializes."""

    def __init__(
        self,
        reader: NativeCharacterConfigReader,
        *,
        explicit_path: Path | None = None,
    ) -> None:
        self.reader = reader
        self._revoked = False
        process = reader.process
        executable = process.executable_path.resolve(strict=True)
        config_root = executable.parent / "Config"
        if config_root.resolve(strict=True) != config_root:
            raise ActiveCharacterError("client Config directory redirects outside the client root")
        identity = reader.observe()
        expected = config_root / identity.config_filename
        # No directory scan, first-file fallback, mtime guess, or alternate client root.
        if explicit_path is not None and explicit_path.resolve(strict=True) != expected:
            raise ActiveCharacterError(
                f"explicit profile does not match active {identity.character_name} "
                f"on {identity.server_name}: expected {expected}"
            )
        self.binding = CharacterConfigBinding(
            process_id=process.pid,
            process_creation_filetime_utc=reader.process_creation_filetime_utc,
            executable_path=executable,
            executable_sha256=process.executable_sha256,
            identity=identity,
            config_path=expected,
            config_sha256=self._digest(expected),
        )
        self.require_current()

    @staticmethod
    def _digest(path: Path) -> str:
        try:
            if path.resolve(strict=True) != path or not path.is_file():
                raise ActiveCharacterError("active profile must be a regular client-local file")
            with path.open("rb") as handle:
                data = handle.read(_MAX_CONFIG_BYTES + 1)
            if not data or len(data) > _MAX_CONFIG_BYTES:
                raise ActiveCharacterError("active character profile is empty or exceeds 4 MiB")
            return hashlib.sha256(data).hexdigest()
        except OSError as exc:
            raise ActiveCharacterError(f"active character profile is unavailable: {path}") from exc

    def require_current(self) -> None:
        if self._revoked:
            raise ActiveCharacterError("character profile binding was revoked; initialize again")
        try:
            if self.reader.observe() != self.binding.identity:
                raise ActiveCharacterError("active character changed; initialize again")
            if self._digest(self.binding.config_path) != self.binding.config_sha256:
                raise ActiveCharacterError("saved character profile changed; initialize again")
        except Exception:
            self._revoked = True
            raise

    def close(self) -> None:
        self._revoked = True
        self.reader.process.close()

    def __enter__(self) -> CharacterConfigSession:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def open_active_character_config(
    *,
    process_id: int | None = None,
    explicit_path: Path | None = None,
) -> CharacterConfigSession:
    process = (
        WindowsReadOnlyProcessMemory.open_unique("sb.exe")
        if process_id is None
        else WindowsReadOnlyProcessMemory.open_for_process("sb.exe", process_id)
    )
    try:
        return CharacterConfigSession(
            NativeCharacterConfigReader(process), explicit_path=explicit_path
        )
    except Exception:
        process.close()
        raise
