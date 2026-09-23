"""Read the active city-command window's cached nearby building/hireling roster.

The cache is populated by ArcCityAssetMessage mode 15, following ordinary mode
14 discovery. It is not a complete town roster, a fresh server receipt or a
command authorization. No native calls or writes are performed.
"""
from __future__ import annotations

import struct

from .native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from .native_vendor_queue import VendorQueueMemory, _ReadSet
from .native_vendor_roster import _text
from .reviewed_vendor_builds import REVIEWED_VENDOR_EXECUTABLES


def _tree(r: _ReadSet, address: int, limit: int, budget: list[int]):
    """Copy the client's null-child STL tree, validating all ownership links."""
    header, count = struct.unpack("<II", r.read(address, 8))
    if count > limit or count > budget[0]:
        raise NativeVendorDialogCaptureError("nearby roster exceeds collection limit")
    budget[0] -= count
    root, first, last = struct.unpack("<III", r.read(header + 4, 12))
    if not count:
        if root or first != header or last != header:
            raise NativeVendorDialogCaptureError("invalid empty nearby roster tree")
        return ()
    if not root or root == header:
        raise NativeVendorDialogCaptureError("missing nearby roster tree root")
    pending = [(root, header)]
    nodes = {}
    keys = set()
    payloads = set()
    while pending:
        node, owner = pending.pop()
        if node == header or node in nodes or len(nodes) >= count:
            raise NativeVendorDialogCaptureError("nearby roster tree cycle or count mismatch")
        parent, left, right, object_id, object_type, payload = struct.unpack(
            "<6I", r.read(node + 4, 24)
        )
        key = (object_id, object_type)
        if parent != owner or not object_id or key in keys or not payload or payload in payloads:
            raise NativeVendorDialogCaptureError("invalid nearby roster tree ownership or identity")
        nodes[node] = (left, right, key, payload)
        keys.add(key)
        payloads.add(payload)
        if right:
            pending.append((right, node))
        if left:
            pending.append((left, node))
    if len(nodes) != count:
        raise NativeVendorDialogCaptureError("incomplete nearby roster tree")
    smallest, largest = root, root
    while nodes[smallest][0]:
        smallest = nodes[smallest][0]
    while nodes[largest][1]:
        largest = nodes[largest][1]
    if first != smallest or last != largest:
        raise NativeVendorDialogCaptureError("invalid nearby roster tree extrema")
    return tuple((key, payload) for _, _, key, payload in nodes.values())


def read_native_nearby_vendor_roster(memory: VendorQueueMemory) -> dict[str, object]:
    """Observe a strict crafting-only cache; never infer town coverage."""
    return _read_nearby_roster(memory, vendors_only=True)


def read_native_nearby_hirelings(memory: VendorQueueMemory) -> dict[str, object]:
    """Retain all typed hireling candidates; eligibility needs the owned building roster."""
    return _read_nearby_roster(memory, vendors_only=False)


def _read_nearby_roster(memory: VendorQueueMemory, *, vendors_only: bool) -> dict[str, object]:
    row_name = "vendor" if vendors_only else "hireling"
    rows_name = "vendors" if vendors_only else "hirelings"
    if (
        memory.executable_name.casefold() != "sb.exe"
        or memory.executable_sha256 not in REVIEWED_VENDOR_EXECUTABLES or memory.pointer_size != 4
    ):
        raise NativeVendorDialogCompatibilityError("unsupported nearby roster executable")
    r = _ReadSet(memory)
    base = memory.base_address
    window = r.word(base + 0x16A7BFC)
    r.require(window, base + 0x1174884, "game window type")
    r.require(window + 0x64, 2, "in-world state")
    manager = r.word(window + 0xD4)
    r.require(manager, base + 0x1171BCC, "city command manager type")
    if r.word(manager + 0x44) not in (1, 2):
        raise NativeVendorDialogCaptureError("city command window is not initialized")
    hud = r.word(manager + 0x4C)
    r.require(hud, base + 0x1166234, "city command HUD type")
    r.require(hud + 0x104, manager, "city command HUD owner")
    if hud not in r.hud_stack(window):
        raise NativeVendorDialogCaptureError("city command window is not active")
    if r.read(hud + 0x568, 4)[2]:
        raise NativeVendorDialogCaptureError("nearby roster response is pending")
    budget = [4096]
    buildings = []
    vendor_keys = set()
    vendor_blocks = set()
    for key, block in _tree(r, manager + 0x74, 512, budget):
        if key[1] != 8:
            raise NativeVendorDialogCaptureError(
                "nearby roster contains an unsupported building key"
            )
        r.require(block, base + 0x117A7A8, "city info block type")
        if r.read(block + 0x20, 8) != struct.pack("<II", *key):
            raise NativeVendorDialogCaptureError("nearby building key mismatch")
        vendors = []
        for vendor_key, hireling in _tree(r, block + 0x38, 256, budget):
            if (not vendor_key[1] or vendors_only and vendor_key[1] != 42
                    or vendor_key in vendor_keys
                    or hireling in vendor_blocks):
                raise NativeVendorDialogCaptureError("invalid or repeated nearby hireling identity")
            vendor_keys.add(vendor_key)
            vendor_blocks.add(hireling)
            r.require(hireling, base + 0x117A7BC, "hireling info block type")
            vendors.append({
                row_name: {"object_id": vendor_key[0], "object_type": vendor_key[1]},
                "display_name": _text(r, hireling + 4),
            })
        buildings.append({
            "building": {"object_id": key[0], "object_type": key[1]},
            "display_name": _text(r, block + 8),
            rows_name: sorted(
                vendors, key=lambda row: (row[row_name]["object_id"], row[row_name]["object_type"])
            ),
        })
    if not buildings:
        raise NativeVendorDialogCaptureError(
            "nearby roster is empty; server response is unverified"
        )
    r.verify()
    return {
        "schema_version": 1,
        "scope": "active_city_command_cached_nearby_buildings",
        "process_id": memory.pid,
        "process_creation_filetime_utc": memory.process_creation_filetime_utc,
        "buildings": sorted(buildings, key=lambda row: row["building"]["object_id"]),
        "town_membership_verified": False,
        "roster_complete": False,
        "server_response_verified": False,
        "management_permission_verified": False,
        "command_admitted": False,
    }
