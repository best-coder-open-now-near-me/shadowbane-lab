"""Dependency-free Portable Executable inspection for offline build alignment."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

from shadowbane_lab.client_alignment.model import PeImage, PeSection

_PE32_MAGIC = 0x10B
_PE32_PLUS_MAGIC = 0x20B
_MIN_DOS_HEADER_SIZE = 0x40
_COFF_HEADER_SIZE = 20
_SECTION_HEADER_SIZE = 40


class PeInspectionError(ValueError):
    """Raised when an input is not a bounded, structurally valid PE image."""


def _unpack_from(format_string: str, data: bytes, offset: int, label: str) -> tuple[int, ...]:
    size = struct.calcsize(format_string)
    if offset < 0 or offset + size > len(data):
        raise PeInspectionError(f"{label} extends beyond the file")
    return struct.unpack_from(format_string, data, offset)


def _decode_section_name(raw: bytes, index: int) -> str:
    value = raw.split(b"\0", 1)[0]
    try:
        decoded = value.decode("ascii")
    except UnicodeDecodeError as exc:
        raise PeInspectionError(f"section {index} has a non-ASCII name") from exc
    return decoded or f"<section-{index}>"


def inspect_pe(path: str | Path) -> PeImage:
    """Parse stable PE metadata and section fingerprints from *path*."""

    executable_path = Path(path)
    try:
        data = executable_path.read_bytes()
    except OSError as exc:
        raise PeInspectionError(f"could not read executable: {executable_path}") from exc
    return inspect_pe_bytes(data, path=str(executable_path))


def inspect_pe_bytes(data: bytes, *, path: str = "<memory>") -> PeImage:
    """Parse PE metadata from bytes; primarily useful for deterministic fixtures."""

    if len(data) < _MIN_DOS_HEADER_SIZE:
        raise PeInspectionError("file is too short for a DOS header")
    if data[:2] != b"MZ":
        raise PeInspectionError("file does not start with an MZ header")

    (pe_offset,) = _unpack_from("<I", data, 0x3C, "PE header pointer")
    if pe_offset < _MIN_DOS_HEADER_SIZE:
        raise PeInspectionError("PE header pointer overlaps the DOS header")
    if pe_offset + 4 + _COFF_HEADER_SIZE > len(data):
        raise PeInspectionError("PE header extends beyond the file")
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise PeInspectionError("PE signature is missing")

    coff_offset = pe_offset + 4
    (
        machine,
        number_of_sections,
        _timestamp,
        _symbol_table,
        _number_of_symbols,
        optional_header_size,
        characteristics,
    ) = _unpack_from("<HHIIIHH", data, coff_offset, "COFF header")
    if number_of_sections <= 0 or number_of_sections > 96:
        raise PeInspectionError("PE section count is outside the supported bounds")

    optional_offset = coff_offset + _COFF_HEADER_SIZE
    optional_end = optional_offset + optional_header_size
    if optional_header_size < 64 or optional_end > len(data):
        raise PeInspectionError("optional header is truncated")

    (magic,) = _unpack_from("<H", data, optional_offset, "optional-header magic")
    if magic == _PE32_MAGIC:
        pointer_size = 4
        (image_base,) = _unpack_from("<I", data, optional_offset + 28, "PE32 image base")
    elif magic == _PE32_PLUS_MAGIC:
        pointer_size = 8
        (image_base,) = _unpack_from("<Q", data, optional_offset + 24, "PE32+ image base")
    else:
        raise PeInspectionError(f"unsupported optional-header magic: 0x{magic:04x}")

    (entry_point_rva,) = _unpack_from("<I", data, optional_offset + 16, "entry point")
    (section_alignment,) = _unpack_from(
        "<I", data, optional_offset + 32, "section alignment"
    )
    (file_alignment,) = _unpack_from("<I", data, optional_offset + 36, "file alignment")
    (size_of_image,) = _unpack_from("<I", data, optional_offset + 56, "image size")
    (size_of_headers,) = _unpack_from("<I", data, optional_offset + 60, "header size")
    if section_alignment <= 0 or file_alignment <= 0:
        raise PeInspectionError("PE alignments must be positive")
    if size_of_headers <= 0 or size_of_headers > len(data):
        raise PeInspectionError("declared PE header size is outside the file")

    section_table_offset = optional_end
    section_table_end = section_table_offset + number_of_sections * _SECTION_HEADER_SIZE
    if section_table_end > len(data):
        raise PeInspectionError("section table is truncated")

    sections: list[PeSection] = []
    occupied_raw_ranges: list[tuple[int, int]] = []
    for index in range(number_of_sections):
        offset = section_table_offset + index * _SECTION_HEADER_SIZE
        name = _decode_section_name(data[offset : offset + 8], index)
        (
            virtual_size,
            virtual_address,
            raw_size,
            raw_offset,
        ) = _unpack_from("<IIII", data, offset + 8, f"section {index} dimensions")
        (section_characteristics,) = _unpack_from(
            "<I", data, offset + 36, f"section {index} characteristics"
        )
        if raw_size:
            raw_end = raw_offset + raw_size
            if raw_offset < size_of_headers or raw_end > len(data):
                raise PeInspectionError(f"section {name} raw range is outside the file")
            occupied_raw_ranges.append((raw_offset, raw_end))
            section_bytes = data[raw_offset:raw_end]
        else:
            section_bytes = b""
        sections.append(
            PeSection(
                index=index,
                name=name,
                virtual_address=virtual_address,
                virtual_size=virtual_size,
                raw_offset=raw_offset,
                raw_size=raw_size,
                characteristics=section_characteristics,
                sha256=hashlib.sha256(section_bytes).hexdigest(),
            )
        )

    for previous, current in zip(
        sorted(occupied_raw_ranges), sorted(occupied_raw_ranges)[1:], strict=False
    ):
        if previous[1] > current[0]:
            raise PeInspectionError("PE sections have overlapping raw ranges")

    return PeImage(
        path=path,
        sha256=hashlib.sha256(data).hexdigest(),
        length=len(data),
        machine=machine,
        pointer_size=pointer_size,
        image_base=image_base,
        entry_point_rva=entry_point_rva,
        section_alignment=section_alignment,
        file_alignment=file_alignment,
        size_of_image=size_of_image,
        size_of_headers=size_of_headers,
        characteristics=characteristics,
        optional_header_magic=magic,
        sections=tuple(sections),
    )


def pe_header_layout_key(image: PeImage) -> tuple[object, ...]:
    """Return the exact reviewed metadata defining the PE's structural layout."""

    return (
        image.machine,
        image.pointer_size,
        image.image_base,
        image.entry_point_rva,
        image.section_alignment,
        image.file_alignment,
        image.size_of_image,
        image.size_of_headers,
        image.characteristics,
        image.optional_header_magic,
        tuple(
            (
                section.index,
                section.name,
                section.virtual_address,
                section.virtual_size,
                section.raw_offset,
                section.raw_size,
                section.characteristics,
            )
            for section in image.sections
        ),
    )


def section_layout_key(image: PeImage) -> tuple[object, ...]:
    """Return only the section layout, independent of entry point and image flags."""

    return tuple(
        (
            section.index,
            section.name,
            section.virtual_address,
            section.virtual_size,
            section.raw_offset,
            section.raw_size,
            section.characteristics,
        )
        for section in image.sections
    )


__all__ = [
    "PeInspectionError",
    "inspect_pe",
    "inspect_pe_bytes",
    "pe_header_layout_key",
    "section_layout_key",
]
