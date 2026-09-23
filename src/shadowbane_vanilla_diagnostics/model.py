"""Strict data contracts shared by the vanilla diagnostic collector."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PACKAGE_ID = "shadowbane-vanilla-diagnostics"
PACKAGE_SCHEMA_VERSION = 1
CAPTURE_SCHEMA_VERSION = 1
DEFAULT_OUTPUT_ROOT = Path(r"\\VBOXSVR\codexdiag\vanilla-diagnostics")
REVIEWED_VANILLA_EXECUTABLE_SHA256 = frozenset(
    {
        "e358237c458ddfe2fc7a86e478f165a8fd067655ab1a8ada5731f790c6995d96",
        "55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc",
    }
)


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    process_id: int
    process_creation_filetime_utc: int
    executable_path: str

    def __post_init__(self) -> None:
        if isinstance(self.process_id, bool) or self.process_id <= 0:
            raise ValueError("process_id must be positive")
        if (
            isinstance(self.process_creation_filetime_utc, bool)
            or self.process_creation_filetime_utc <= 0
        ):
            raise ValueError("process_creation_filetime_utc must be positive")
        if not self.executable_path or "\0" in self.executable_path:
            raise ValueError("executable_path must be non-empty text")

    @property
    def exact_key(self) -> tuple[int, int]:
        return self.process_id, self.process_creation_filetime_utc

    def as_dict(self) -> dict[str, object]:
        return {
            "process_id": self.process_id,
            "process_creation_filetime_utc": self.process_creation_filetime_utc,
            "executable_path": self.executable_path,
            "executable_name": Path(self.executable_path).name,
        }


@dataclass(frozen=True, slots=True)
class ProcessSample:
    identity: ProcessIdentity
    metrics: dict[str, int | float]


__all__ = [
    "CAPTURE_SCHEMA_VERSION",
    "DEFAULT_OUTPUT_ROOT",
    "PACKAGE_ID",
    "PACKAGE_SCHEMA_VERSION",
    "ProcessIdentity",
    "ProcessSample",
    "REVIEWED_VANILLA_EXECUTABLE_SHA256",
]
