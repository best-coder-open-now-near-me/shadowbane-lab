"""Copied HUD scene collections; absence never establishes a server response.

The caller establishes exact-build HUD ownership and reverse-verifies this read
set. Native setup can discard records before either collection is populated.
"""
from __future__ import annotations

import math
import struct

from .native_furnishing_resources import _object_reference, _reference
from .native_vendor_dialog import NativeVendorDialogCaptureError
from .native_vendor_queue import _ReadSet

TRACKING_RVA = 0x116DDE8
FURNITURE_INFO_RVA = 0x117B364
MAX_SCENE_ENTRIES = 512


def _key(r: _ReadSet, address: int) -> dict[str, int]:
    object_id, object_type = struct.unpack("<II", r.read(address, 8))
    return {"object_id": object_id, "object_type": object_type}


def _scene_list(r: _ReadSet, hud: int) -> dict[str, object]:
    head = r.word(hud + 0x444)
    entries = []
    result = {"sentinel_address": head, "available": bool(head), "entries": entries}
    if not head:
        return result
    node, last = struct.unpack("<II", r.read(head, 8))
    previous = head
    seen, payloads = set(), set()
    while node != head:
        if node in seen or len(seen) >= MAX_SCENE_ENTRIES:
            raise NativeVendorDialogCaptureError("invalid furnishing scene list cycle or bound")
        seen.add(node)
        following, backward, payload = struct.unpack("<III", r.read(node, 12))
        if backward != previous or (payload and payload in payloads):
            raise NativeVendorDialogCaptureError("broken furnishing scene list ownership")
        payloads.add(payload)
        reference = _object_reference(r, payload)
        entry = {"node_address": node, "tracking_reference": reference}
        if reference and reference["class_rva"] == TRACKING_RVA:
            r.require(payload + 4, 2, "furnishing scene tracking kind")
            entry.update({
                "instance_key_raw": _key(r, payload + 0x90),
                "asset_key_raw": _key(r, payload + 0x60),
                "floor_index_raw": r.word(payload + 0x28),
                "object_reference": _reference(r, payload + 0x68),
            })
        entries.append(entry)
        previous, node = node, following
    if previous != last:
        raise NativeVendorDialogCaptureError("broken furnishing scene list tail")
    return result


def _furniture_map(r: _ReadSet, hud: int) -> dict[str, object]:
    head, count = struct.unpack("<II", r.read(hud + 0x664, 8))
    if count > MAX_SCENE_ENTRIES or (count and not head):
        raise NativeVendorDialogCaptureError("invalid furnishing scene map count or sentinel")
    records = []
    result = {
        "sentinel_address": head, "available": bool(head),
        "count_raw": count, "records": records,
    }
    if not head:
        return result
    root, first, last = struct.unpack("<III", r.read(head + 4, 12))
    # Native 0x5947e0 initializes parent/children and maintains sentinel extrema;
    # 0x111bd0 orders unsigned keys by type, then id. No native calls are made.
    pending = [(root, head, None, None)] if root else []
    edges: dict[int, tuple[int, int]] = {}
    payloads = set()
    while pending:
        node, parent, lower, upper = pending.pop()
        if node == head or node in edges or len(edges) >= count:
            raise NativeVendorDialogCaptureError("invalid furnishing scene map ownership or count")
        up, left, right = struct.unpack("<III", r.read(node + 4, 12))
        if up != parent:
            raise NativeVendorDialogCaptureError("broken furnishing scene map parent")
        edges[node] = left, right
        key = _key(r, node + 0x10)
        order = key["object_type"], key["object_id"]
        if (lower is not None and order <= lower) or (upper is not None and order >= upper):
            raise NativeVendorDialogCaptureError("invalid furnishing scene map key order")
        reference = _reference(r, node + 0x18)
        record = {"node_address": node, "instance_key_raw": key, "info_reference": reference}
        if reference:
            pointer = reference["address"]
            if pointer in payloads:
                raise NativeVendorDialogCaptureError("duplicate furnishing scene map record")
            payloads.add(pointer)
            if reference["class_rva"] == FURNITURE_INFO_RVA:
                if _key(r, pointer + 0x10) != key:
                    raise NativeVendorDialogCaptureError("furnishing scene map record key mismatch")
                x, y, z, rotation = struct.unpack("<4f", r.read(pointer + 0x20, 16))
                if not all(math.isfinite(value) for value in (x, y, z, rotation)):
                    raise NativeVendorDialogCaptureError("nonfinite furnishing scene record pose")
                record.update({
                    "asset_key_raw": _key(r, pointer + 8),
                    "position_raw": [x, y, z], "rotation_raw": rotation,
                    "floor_index_raw": r.word(pointer + 0x30),
                })
        records.append(record)
        if right:
            pending.append((right, node, order, upper))
        if left:
            pending.append((left, node, lower, order))
    if len(edges) != count:
        raise NativeVendorDialogCaptureError("furnishing scene map count mismatch")
    for direction, expected in ((0, first), (1, last)):
        endpoint = root
        while endpoint and edges[endpoint][direction]:
            endpoint = edges[endpoint][direction]
        if (endpoint or head) != expected:
            raise NativeVendorDialogCaptureError("furnishing scene map endpoint mismatch")
    return result


def read_scene_collections(r: _ReadSet, hud: int, manager: int) -> dict[str, object]:
    """Independently copy the tracking list and furniture map under one read set.

    Collections can differ during client setup. Do not infer server omissions,
    placement acceptance, render readiness or native lifetime from either one.
    Unknown payload classes remain references, without interpreting their fields.
    """
    scene = _scene_list(r, hud)
    furniture = _furniture_map(r, hud)
    selected = r.word(hud + 0x508)
    members = {
        entry["tracking_reference"]["address"] for entry in scene["entries"]
        if entry["tracking_reference"]
    }
    return {
        "scope": "owned_hud_scene_collection_evidence",
        "manager_building_keys_raw": {
            "offset_f0": _key(r, manager + 0xF0),
            "offset_f8": _key(r, manager + 0xF8),
        },
        "tracking_list": scene, "furniture_map": furniture,
        "scene_selection_address_raw": selected,
        "scene_selection_in_tracking_list": selected in members if scene["available"] else None,
        "placement_confirmed": False, "server_records_complete": False,
        "render_lifetime_owned": False, "command_admitted": False,
        "native_calls_made": False,
    }
