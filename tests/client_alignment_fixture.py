"""Synthetic PE and native-profile fixtures for client-alignment tests."""

from __future__ import annotations

import json
import struct
from pathlib import Path


def build_pe(
    *,
    text_byte: int = 0x90,
    data_byte: int = 0x00,
    data_virtual_address: int = 0x2000,
) -> bytes:
    pe_offset = 0x80
    optional_size = 0xE0
    header_size = 0x200
    text_offset = 0x200
    data_offset = 0x400
    result = bytearray(0x600)
    result[:2] = b"MZ"
    struct.pack_into("<I", result, 0x3C, pe_offset)
    result[pe_offset : pe_offset + 4] = b"PE\0\0"
    struct.pack_into(
        "<HHIIIHH",
        result,
        pe_offset + 4,
        0x14C,
        2,
        0,
        0,
        0,
        optional_size,
        0x0102,
    )
    optional = pe_offset + 24
    struct.pack_into("<H", result, optional, 0x10B)
    struct.pack_into("<I", result, optional + 16, 0x1000)
    struct.pack_into("<I", result, optional + 28, 0x400000)
    struct.pack_into("<I", result, optional + 32, 0x1000)
    struct.pack_into("<I", result, optional + 36, 0x200)
    struct.pack_into(
        "<I",
        result,
        optional + 56,
        0x4000 if data_virtual_address == 0x3000 else 0x3000,
    )
    struct.pack_into("<I", result, optional + 60, header_size)

    section_table = optional + optional_size
    _write_section(
        result,
        section_table,
        name=b".text",
        virtual_size=0x100,
        virtual_address=0x1000,
        raw_size=0x200,
        raw_offset=text_offset,
        characteristics=0x60000020,
    )
    _write_section(
        result,
        section_table + 40,
        name=b".data",
        virtual_size=0x80,
        virtual_address=data_virtual_address,
        raw_size=0x200,
        raw_offset=data_offset,
        characteristics=0xC0000040,
    )
    result[text_offset:data_offset] = bytes([text_byte]) * 0x200
    result[data_offset:] = bytes([data_byte]) * 0x200
    return bytes(result)


def _write_section(
    target: bytearray,
    offset: int,
    *,
    name: bytes,
    virtual_size: int,
    virtual_address: int,
    raw_size: int,
    raw_offset: int,
    characteristics: int,
) -> None:
    target[offset : offset + 8] = name.ljust(8, b"\0")
    struct.pack_into(
        "<IIII",
        target,
        offset + 8,
        virtual_size,
        virtual_address,
        raw_size,
        raw_offset,
    )
    struct.pack_into("<I", target, offset + 36, characteristics)


def write_profile(directory: Path, executable_sha256: str, *, anchor_rva: int) -> None:
    payload = {
        "schema_version": 1,
        "profile_id": "fixture-native-layout",
        "executable_name": "sb.exe",
        "executable_sha256": executable_sha256,
        "pointer_size": 4,
        "root_pointer_rva": anchor_rva,
        "breakpoints": [
            {
                "role": "fixture",
                "rva": 0x1020,
                "signature_hex": "9090909090909090",
            }
        ],
    }
    (directory / "fixture.native-layout.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
