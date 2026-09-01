"""Explicit host-filesystem and guest-Windows runtime path domains."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Protocol


class RuntimePathDomainError(ValueError):
    """Raised when a path crosses runtime domains without an authorized mapping."""


@dataclass(frozen=True, slots=True)
class HostRuntimePath:
    """An absolute path in the filesystem visible to the current Python process."""

    path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise RuntimePathDomainError("host runtime path must be pathlib.Path")
        if not self.path.is_absolute():
            raise RuntimePathDomainError("host runtime path must be absolute")
        normalized = self.path.resolve(strict=False)
        object.__setattr__(self, "path", normalized)


@dataclass(frozen=True, slots=True)
class GuestWindowsPath:
    """An absolute guest-local Windows path carried by a manager manifest."""

    path: PureWindowsPath

    def __post_init__(self) -> None:
        if not isinstance(self.path, PureWindowsPath):
            raise RuntimePathDomainError("guest runtime path must be pathlib.PureWindowsPath")
        if not self.path.is_absolute():
            raise RuntimePathDomainError("guest runtime path must be absolute")
        if not self.path.drive or str(self.path).startswith(("\\\\", "//")):
            raise RuntimePathDomainError("guest runtime path must use a guest-local drive")
        if ".." in self.path.parts:
            raise RuntimePathDomainError("guest runtime path must not traverse parent directories")


class RuntimePathMapper(Protocol):
    """The sole authority for translating runtime paths between host and guest."""

    def host_to_guest(self, path: HostRuntimePath) -> GuestWindowsPath: ...

    def guest_to_host(self, path: GuestWindowsPath) -> HostRuntimePath: ...


@dataclass(frozen=True, slots=True)
class RootedRuntimePathMapper:
    """Bidirectional mapping between one host root and one guest Windows root."""

    host_root: HostRuntimePath
    guest_root: GuestWindowsPath

    def __post_init__(self) -> None:
        if not isinstance(self.host_root, HostRuntimePath):
            raise RuntimePathDomainError("host_root must be HostRuntimePath")
        if not isinstance(self.guest_root, GuestWindowsPath):
            raise RuntimePathDomainError("guest_root must be GuestWindowsPath")

    def host_to_guest(self, path: HostRuntimePath) -> GuestWindowsPath:
        if not isinstance(path, HostRuntimePath):
            raise RuntimePathDomainError("host_to_guest requires HostRuntimePath")
        try:
            relative = path.path.relative_to(self.host_root.path)
        except ValueError as exc:
            raise RuntimePathDomainError("host path is outside the mapped runtime root") from exc
        return GuestWindowsPath(self.guest_root.path.joinpath(*relative.parts))

    def guest_to_host(self, path: GuestWindowsPath) -> HostRuntimePath:
        if not isinstance(path, GuestWindowsPath):
            raise RuntimePathDomainError("guest_to_host requires GuestWindowsPath")
        guest_key = tuple(part.casefold() for part in self.guest_root.path.parts)
        path_parts = path.path.parts
        path_key = tuple(part.casefold() for part in path_parts)
        if path_key[: len(guest_key)] != guest_key:
            raise RuntimePathDomainError("guest path is outside the mapped runtime root")
        relative_parts = path_parts[len(guest_key) :]
        return HostRuntimePath(self.host_root.path.joinpath(*relative_parts))


def local_windows_runtime_mapper(host_root: Path) -> RootedRuntimePathMapper:
    """Create the identity mapping used when the manager runs inside the Windows guest."""

    host = HostRuntimePath(host_root)
    if os.name != "nt":
        raise RuntimePathDomainError(
            "a guest path mapper is required when runtime deployment runs outside Windows"
        )
    return RootedRuntimePathMapper(
        host_root=host,
        guest_root=GuestWindowsPath(PureWindowsPath(str(host.path))),
    )


__all__ = [
    "GuestWindowsPath",
    "HostRuntimePath",
    "RootedRuntimePathMapper",
    "RuntimePathDomainError",
    "RuntimePathMapper",
    "local_windows_runtime_mapper",
]
