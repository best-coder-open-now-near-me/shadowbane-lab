"""Read-only access to Shadowbane ``.cache`` resource archives."""

from __future__ import annotations

import mmap
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

_HEADER = struct.Struct("<IIII")
_DIRECTORY_ENTRY = struct.Struct("<IIIII")


class CacheArchiveFormatError(ValueError):
    """Raised when a Shadowbane cache archive violates its binary contract."""


@dataclass(frozen=True, slots=True)
class CacheArchiveHeader:
    resource_count: int
    data_offset: int
    file_size: int
    marker: int


@dataclass(frozen=True, slots=True)
class CacheResourceEntry:
    index: int
    group_id: int
    resource_id: int
    data_offset: int
    uncompressed_size: int
    stored_size: int

    @property
    def is_compressed(self) -> bool:
        return self.uncompressed_size != self.stored_size


class CacheArchive:
    """Memory-mapped, bounds-checked reader for one Shadowbane cache archive."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._stream = self.path.open("rb")
        try:
            self._view = mmap.mmap(self._stream.fileno(), 0, access=mmap.ACCESS_READ)
            self.header, self.entries = self._parse_directory()
        except Exception:
            view = getattr(self, "_view", None)
            if view is not None:
                view.close()
            self._stream.close()
            raise

    def __enter__(self) -> CacheArchive:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        view = getattr(self, "_view", None)
        if view is not None:
            view.close()
            self._view = None
        if not self._stream.closed:
            self._stream.close()

    def read_resource(self, entry: CacheResourceEntry) -> bytes:
        self._require_open()
        if not 0 <= entry.index < len(self.entries) or self.entries[entry.index] != entry:
            raise ValueError("cache resource entry does not belong to this archive")
        end = entry.data_offset + entry.stored_size
        stored = self._view[entry.data_offset : end]
        if not entry.is_compressed:
            return bytes(stored)
        try:
            payload = zlib.decompress(stored)
        except zlib.error as exc:
            raise CacheArchiveFormatError(
                f"resource {entry.index} has invalid deflate data"
            ) from exc
        if len(payload) != entry.uncompressed_size:
            raise CacheArchiveFormatError(
                f"resource {entry.index} inflated to {len(payload)} bytes; "
                f"expected {entry.uncompressed_size}"
            )
        return payload

    def entries_for_id(self, resource_id: int) -> tuple[CacheResourceEntry, ...]:
        return tuple(entry for entry in self.entries if entry.resource_id == resource_id)

    def _require_open(self) -> None:
        if getattr(self, "_view", None) is None:
            raise ValueError("cache archive is closed")

    def _parse_directory(self) -> tuple[CacheArchiveHeader, tuple[CacheResourceEntry, ...]]:
        actual_size = len(self._view)
        if actual_size < _HEADER.size:
            raise CacheArchiveFormatError("cache archive is smaller than its 16-byte header")
        header = CacheArchiveHeader(*_HEADER.unpack_from(self._view, 0))
        minimum_data_offset = _HEADER.size + header.resource_count * _DIRECTORY_ENTRY.size
        if header.data_offset < minimum_data_offset:
            raise CacheArchiveFormatError(
                f"cache data offset {header.data_offset} overlaps the directory ending at "
                f"{minimum_data_offset}"
            )
        if header.file_size != actual_size:
            raise CacheArchiveFormatError(
                f"cache header size is {header.file_size}; actual size is {actual_size}"
            )
        if header.data_offset > actual_size:
            raise CacheArchiveFormatError("cache directory extends past end of file")

        entries = []
        for index in range(header.resource_count):
            offset = _HEADER.size + index * _DIRECTORY_ENTRY.size
            group_id, resource_id, data_offset, raw_size, stored_size = (
                _DIRECTORY_ENTRY.unpack_from(self._view, offset)
            )
            data_end = data_offset + stored_size
            if data_offset < header.data_offset or data_end > actual_size:
                raise CacheArchiveFormatError(
                    f"resource {index} data range [{data_offset}, {data_end}) is out of bounds"
                )
            entries.append(
                CacheResourceEntry(
                    index=index,
                    group_id=group_id,
                    resource_id=resource_id,
                    data_offset=data_offset,
                    uncompressed_size=raw_size,
                    stored_size=stored_size,
                )
            )
        return header, tuple(entries)
