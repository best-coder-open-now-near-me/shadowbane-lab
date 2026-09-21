"""Observe the server-populated city cache without requesting or changing data.

The cache is not a complete guild directory, and its lifetime is not a login epoch.
Guild and nation roles were cross-checked against a selected saved Heraldry crest.
"""
from __future__ import annotations

import struct

from .native_crest_lists import REVIEWED_CREST_EXECUTABLES, _key
from .native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from .native_vendor_queue import VendorQueueMemory, _ReadSet
from .native_vendor_roster import _text

_MAX_CITIES = 2048


def read_native_city_registry(memory: VendorQueueMemory) -> dict[str, object]:
    """Read the exact-build cache populated by ArcCityDataMessage.

    Validate every tree edge, count, extremum, identity and record owner before
    returning anything. An empty cache does not establish an empty game world.
    No memory scan, native function call or network request is performed.
    """
    if (
        memory.executable_name.casefold() != "sb.exe" or memory.pointer_size != 4
        or memory.executable_sha256 not in REVIEWED_CREST_EXECUTABLES
    ):
        raise NativeVendorDialogCompatibilityError("unsupported city-registry executable")
    r, base = _ReadSet(memory), memory.base_address
    root = r.word(base + 0x16A7BFC)
    r.require(root, base + 0x1174884, "game window type")
    r.require(root + 0x64, 2, "in-world state")
    cache = base + 0x16ABBF0
    head, count = struct.unpack("<II", r.read(cache, 8))
    if count > _MAX_CITIES:
        raise NativeVendorDialogCaptureError("city registry exceeds size bound")
    tree_root, first, last = struct.unpack("<III", r.read(head + 4, 12))
    pending = [(tree_root, head)] if tree_root else []
    edges: dict[int, tuple[int, int]] = {}
    records, identities, record_addresses = [], set(), set()
    while pending:
        node, parent = pending.pop()
        if node == head or node in edges or len(edges) >= count:
            raise NativeVendorDialogCaptureError("invalid city registry ownership or count")
        up, left, right = struct.unpack("<III", r.read(node + 4, 12))
        if up != parent:
            raise NativeVendorDialogCaptureError("broken city registry parent link")
        edges[node] = left, right
        key = _key(r, node + 0x10)
        identity = key["object_id"], key["object_type"]
        if not identity[0] or identity in identities:
            raise NativeVendorDialogCaptureError("invalid or duplicate city identity")
        identities.add(identity)
        data = r.word(node + 0x18)
        if data in record_addresses:
            raise NativeVendorDialogCaptureError("duplicate city record ownership")
        record_addresses.add(data)
        r.require(data + 0x118, base + 0x117A704, "city data virtual base")
        r.require(data + 0x190, base + 0x117A6CC, "city data type")
        if _key(r, data) != key:
            raise NativeVendorDialogCaptureError("city registry key does not match record")
        records.append({
            "record_address": data,
            "city_key": key,
            "city_name": _text(r, data + 0x28),
            "nation": {"key": _key(r, data + 8), "name": _text(r, data + 0x10)},
            "guild": {"key": _key(r, data + 0x88), "name": _text(r, data + 0x90)},
        })
        for child in (right, left):
            if child:
                pending.append((child, node))
    if len(records) != count:
        raise NativeVendorDialogCaptureError("city registry count mismatch")
    for direction, expected in ((0, first), (1, last)):
        endpoint = tree_root
        while endpoint and edges[endpoint][direction]:
            endpoint = edges[endpoint][direction]
        if (endpoint or head) != expected:
            raise NativeVendorDialogCaptureError("city registry endpoint mismatch")
    r.verify()
    return {
        "cities": records,
        "cache_count": count,
        "cache_freshness_verified": False,
        "complete_guild_directory_verified": False,
        "command_admitted": False,
    }
