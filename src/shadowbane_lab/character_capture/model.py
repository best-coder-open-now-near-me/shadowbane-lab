"""Typed records emitted by the read-only WonderBane character collector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _hex_address(value: int) -> str:
    return f"0x{value:08x}" if value <= 0xFFFFFFFF else f"0x{value:016x}"


@dataclass(frozen=True, slots=True)
class ModuleInfo:
    name: str
    base_address: int
    size: int
    path: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "base_address": _hex_address(self.base_address),
            "size": self.size,
            "path": self.path,
        }


@dataclass(frozen=True, slots=True)
class ProcessInfo:
    process_id: int
    executable_name: str
    executable_path: str
    executable_sha256: str | None
    pointer_size: int

    def as_dict(self) -> dict[str, object]:
        return {
            "process_id": self.process_id,
            "executable_name": self.executable_name,
            "executable_path": self.executable_path,
            "executable_sha256": self.executable_sha256,
            "pointer_size": self.pointer_size,
        }


@dataclass(frozen=True, slots=True)
class MemoryRegion:
    base_address: int
    size: int
    state: int
    protection: int
    region_type: int
    readable: bool

    @property
    def end_address(self) -> int:
        return self.base_address + self.size

    def as_dict(self) -> dict[str, object]:
        return {
            "base_address": _hex_address(self.base_address),
            "size": self.size,
            "state": self.state,
            "protection": self.protection,
            "region_type": self.region_type,
            "readable": self.readable,
        }


@dataclass(frozen=True, slots=True)
class ScanMatch:
    address: int
    encoding: str
    region_base_address: int
    region_size: int
    preview_hex: str
    preview_text: str

    def as_dict(self) -> dict[str, object]:
        return {
            "address": _hex_address(self.address),
            "encoding": self.encoding,
            "region_base_address": _hex_address(self.region_base_address),
            "region_size": self.region_size,
            "preview_hex": self.preview_hex,
            "preview_text": self.preview_text,
        }


@dataclass(frozen=True, slots=True)
class CharacterCapture:
    schema_version: int
    layout_id: str
    captured_at_utc: str
    source: dict[str, Any]
    character: dict[str, Any]
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "layout_id": self.layout_id,
            "captured_at_utc": self.captured_at_utc,
            "source": self.source,
            "character": self.character,
            "warnings": list(self.warnings),
        }
