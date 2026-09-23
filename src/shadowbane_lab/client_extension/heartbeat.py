"""Strict evidence emitted by the no-op native extension initializer."""

from __future__ import annotations

import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path

EXTENSION_HEARTBEAT_SCHEMA_VERSION = 1
EXTENSION_ABI_VERSION = 1
_HEARTBEAT_NAME = re.compile(r"heartbeat-([1-9][0-9]*)-([1-9][0-9]*)\.json\Z")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
_MAX_HEARTBEAT_BYTES = 4096
_FIELDS = {
    "schema_version",
    "abi_version",
    "extension_version",
    "process_id",
    "process_creation_filetime_utc",
    "initialized_at_filetime_utc",
    "status",
}


class ExtensionHeartbeatError(ValueError):
    """Raised when extension heartbeat evidence is malformed or inconsistent."""


@dataclass(frozen=True, slots=True)
class ExtensionHeartbeat:
    extension_version: str
    process_id: int
    process_creation_filetime_utc: int
    initialized_at_filetime_utc: int
    schema_version: int = EXTENSION_HEARTBEAT_SCHEMA_VERSION
    abi_version: int = EXTENSION_ABI_VERSION
    status: str = "initialized"

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or self.schema_version != EXTENSION_HEARTBEAT_SCHEMA_VERSION
        ):
            raise ExtensionHeartbeatError("unsupported extension heartbeat schema version")
        if isinstance(self.abi_version, bool) or self.abi_version != EXTENSION_ABI_VERSION:
            raise ExtensionHeartbeatError("unsupported extension ABI version")
        if not isinstance(self.extension_version, str) or _VERSION.fullmatch(
            self.extension_version
        ) is None:
            raise ExtensionHeartbeatError("extension_version must use major.minor.patch")
        _positive_integer(self.process_id, "process_id", maximum=0xFFFFFFFF)
        _positive_integer(
            self.process_creation_filetime_utc,
            "process_creation_filetime_utc",
            maximum=0xFFFFFFFFFFFFFFFF,
        )
        _positive_integer(
            self.initialized_at_filetime_utc,
            "initialized_at_filetime_utc",
            maximum=0xFFFFFFFFFFFFFFFF,
        )
        if self.initialized_at_filetime_utc < self.process_creation_filetime_utc:
            raise ExtensionHeartbeatError("initialization time predates process creation")
        if self.status != "initialized":
            raise ExtensionHeartbeatError("extension heartbeat status is not initialized")

    @property
    def process_identity(self) -> tuple[int, int]:
        return self.process_id, self.process_creation_filetime_utc

    @property
    def expected_file_name(self) -> str:
        return (
            f"heartbeat-{self.process_id}-{self.process_creation_filetime_utc}.json"
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "abi_version": self.abi_version,
            "extension_version": self.extension_version,
            "process_id": self.process_id,
            "process_creation_filetime_utc": self.process_creation_filetime_utc,
            "initialized_at_filetime_utc": self.initialized_at_filetime_utc,
            "status": self.status,
        }


def load_extension_heartbeat(path: str | Path) -> ExtensionHeartbeat:
    heartbeat_path = Path(path)
    try:
        attributes = getattr(
            heartbeat_path.stat(follow_symlinks=False),
            "st_file_attributes",
            0,
        )
    except OSError as exc:
        raise ExtensionHeartbeatError("extension heartbeat is not a regular file") from exc
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if heartbeat_path.is_symlink() or attributes & reparse or not heartbeat_path.is_file():
        raise ExtensionHeartbeatError("extension heartbeat is not a regular file")
    match = _HEARTBEAT_NAME.fullmatch(heartbeat_path.name)
    if match is None:
        raise ExtensionHeartbeatError("extension heartbeat file name is not canonical")
    try:
        source = heartbeat_path.read_bytes()
    except OSError as exc:
        raise ExtensionHeartbeatError("could not read extension heartbeat") from exc
    if not source or len(source) > _MAX_HEARTBEAT_BYTES:
        raise ExtensionHeartbeatError("extension heartbeat size is outside supported bounds")
    try:
        payload = json.loads(
            source.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ExtensionHeartbeatError("extension heartbeat is not valid UTF-8 JSON") from exc
    heartbeat = parse_extension_heartbeat(payload)
    name_identity = int(match.group(1)), int(match.group(2))
    if heartbeat.process_identity != name_identity:
        raise ExtensionHeartbeatError("extension heartbeat identity differs from its file name")
    return heartbeat


def parse_extension_heartbeat(value: object) -> ExtensionHeartbeat:
    if not isinstance(value, dict):
        raise ExtensionHeartbeatError("extension heartbeat must be a JSON object")
    missing = _FIELDS - value.keys()
    unknown = value.keys() - _FIELDS
    if missing:
        raise ExtensionHeartbeatError(
            f"extension heartbeat is missing: {', '.join(sorted(missing))}"
        )
    if unknown:
        raise ExtensionHeartbeatError(
            f"extension heartbeat has unknown fields: {', '.join(sorted(unknown))}"
        )
    try:
        return ExtensionHeartbeat(
            schema_version=value["schema_version"],  # type: ignore[arg-type]
            abi_version=value["abi_version"],  # type: ignore[arg-type]
            extension_version=value["extension_version"],  # type: ignore[arg-type]
            process_id=value["process_id"],  # type: ignore[arg-type]
            process_creation_filetime_utc=value["process_creation_filetime_utc"],  # type: ignore[arg-type]
            initialized_at_filetime_utc=value["initialized_at_filetime_utc"],  # type: ignore[arg-type]
            status=value["status"],  # type: ignore[arg-type]
        )
    except TypeError as exc:
        raise ExtensionHeartbeatError(str(exc)) from exc


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ExtensionHeartbeatError(f"duplicate extension heartbeat field: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ExtensionHeartbeatError(f"forbidden extension heartbeat constant: {value}")


def _positive_integer(value: object, field_name: str, *, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
        raise ExtensionHeartbeatError(f"{field_name} must be a bounded positive integer")


__all__ = [
    "EXTENSION_ABI_VERSION",
    "EXTENSION_HEARTBEAT_SCHEMA_VERSION",
    "ExtensionHeartbeat",
    "ExtensionHeartbeatError",
    "load_extension_heartbeat",
    "parse_extension_heartbeat",
]
