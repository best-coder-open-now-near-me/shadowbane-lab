"""Observe building-to-hireling membership in the active management window.

This is a visible roster, not proof of town completeness or permission to craft.
Native identities are preserved separately from display labels and actor keys.
"""
from __future__ import annotations

import struct

from .native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from .native_vendor_queue import VendorQueueMemory, _ReadSet

_BUILD = "bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87"


def _text(r: _ReadSet, address: int) -> str:
    # ArcString's UTF-16 buffer follows its allocator field. The constructors
    # initialize these fields at manager+15c and hireling+30/+48.
    begin, end, capacity = struct.unpack("<III", r.read(address + 4, 12))
    if begin == end == capacity == 0:
        return ""
    if (
        not 0x10000 <= begin <= end <= capacity < 0x80000000
        or begin % 4 or end % 2 or capacity % 2 or end - begin > 1024
    ):
        raise NativeVendorDialogCaptureError("invalid roster text bounds")
    if begin == end:
        return ""
    try:
        value = r.read(begin, end - begin).decode("utf-16-le")
    except UnicodeDecodeError as exc:
        raise NativeVendorDialogCaptureError("invalid roster text encoding") from exc
    if any(ord(c) < 32 for c in value):
        raise NativeVendorDialogCaptureError("invalid roster display text")
    return value


def read_native_vendor_roster(memory: VendorQueueMemory) -> dict[str, object]:
    """Copy a consistent rooted building roster, without selecting a hireling."""
    if (
        memory.executable_name.casefold() != "sb.exe"
        or memory.executable_sha256 != _BUILD or memory.pointer_size != 4
    ):
        raise NativeVendorDialogCompatibilityError("unsupported building roster executable")
    r = _ReadSet(memory)
    base = memory.base_address
    window = r.word(base + 0x16A7BFC)
    r.require(window, base + 0x1174884, "game window type")
    r.require(window + 0x64, 2, "in-world state")
    manager = r.word(window + 0xA4)
    r.require(manager, base + 0x1171ADC, "city manager type")
    menu = r.word(manager + 0x78)
    r.require(menu, base + 0x116A058, "management menu type")
    r.require(menu + 0x104, manager, "management menu owner")
    r.require(manager + 0xD8, 0, "pending management transition")
    if menu not in r.hud_stack(window):
        raise NativeVendorDialogCaptureError("building menu is not active")
    building_id, building_type = struct.unpack("<II", r.read(manager + 0xF0, 8))
    if not building_id or building_type != 8:
        raise NativeVendorDialogCaptureError("invalid roster building identity")
    if r.read(manager + 0xF8, 8) != struct.pack("<II", building_id, building_type):
        raise NativeVendorDialogCaptureError("building selection is changing")
    building_name = _text(r, manager + 0x15C)
    owner_label = _text(r, manager + 0x174)
    rows: list[dict[str, object]] = []
    ids: set[int] = set()
    roster_list = None
    for child in r.vector(menu + 0x54, 512):
        r.require(child + 0x3BC, menu, "roster child owner")
        if r.word(child) != base + 0x116ACF0:
            continue
        for control in r.vector(child + 0x408, 128):
            r.require(control, base + 0x116AEBC, "roster control type")
            r.require(control + 0x3BC, menu, "roster control owner")
            r.require(control + 0x458, child, "roster control list")
            entry = r.word(control + 0x44C)
            if not entry or r.word(entry) != base + 0x1169518:
                continue
            if roster_list is not None and roster_list != child:
                raise NativeVendorDialogCaptureError("ambiguous hireling lists")
            roster_list = child
            vendor_id, vendor_type = struct.unpack("<II", r.read(entry + 0x10, 8))
            if not vendor_id or vendor_type != 42 or vendor_id in ids:
                raise NativeVendorDialogCaptureError("invalid or duplicate hireling identity")
            ids.add(vendor_id)
            rows.append({
                "vendor": {"object_id": vendor_id, "object_type": vendor_type},
                "display_name": _text(r, entry + 0x30),
                "service_label": _text(r, entry + 0x48),
            })
    if not rows:
        raise NativeVendorDialogCaptureError("no visible hireling roster; completeness unknown")
    # Detect changed strings, lists, ownership and identities during the copy.
    for (address, size), block in reversed(tuple(r.blocks.items())):
        if memory.read_block(address, size) != block:
            raise NativeVendorDialogCaptureError("building roster changed during observation")
    return {
        "schema_version": 1,
        "scope": "current_building_visible_hirelings",
        "process_id": memory.pid,
        "process_creation_filetime_utc": memory.process_creation_filetime_utc,
        "building": {"object_id": building_id, "object_type": building_type},
        "building_name": building_name,
        "owner_label": owner_label,
        "vendors": rows,
        "town_membership_verified": False,
        "roster_complete": False,
        "management_permission_verified": False,
        "command_admitted": False,
    }
