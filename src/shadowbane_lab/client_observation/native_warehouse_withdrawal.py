"""Read an owned warehouse withdrawal quote and its current resource reserve."""

from __future__ import annotations

import re
import struct

from .native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from .native_vendor_queue import VendorQueueMemory, _ReadSet
from .native_vendor_roster import _text
from .reviewed_vendor_builds import REVIEWED_VENDOR_EXECUTABLES


def _reserves(r: _ReadSet, address: int) -> dict[int, int]:
    # The reviewed std::map node has parent/left/right at +4/+8/+c and
    # the resource ID/minimum pair at +10/+14. Null children use zero.
    header, count = struct.unpack("<II", r.read(address, 8))
    if count > 1024:
        raise NativeVendorDialogCaptureError("warehouse reserve count exceeds bound")
    root, first, last = struct.unpack("<III", r.read(header + 4, 12))
    if not count:
        if root or first != header or last != header:
            raise NativeVendorDialogCaptureError("invalid empty warehouse reserve map")
        return {}
    pending = [(root, header)]
    nodes, result = {}, {}
    while pending:
        node, owner = pending.pop()
        if not node or node == header or node in nodes or len(nodes) >= count:
            raise NativeVendorDialogCaptureError("invalid warehouse reserve ownership")
        parent, left, right, resource, minimum = struct.unpack("<5I", r.read(node + 4, 20))
        if parent != owner or not resource or resource in result or minimum > 0x7FFFFFFF:
            raise NativeVendorDialogCaptureError("invalid warehouse reserve entry")
        nodes[node] = left, right
        result[resource] = minimum
        if right:
            pending.append((right, node))
        if left:
            pending.append((left, node))
    if len(nodes) != count:
        raise NativeVendorDialogCaptureError("incomplete warehouse reserve map")
    low = high = root
    while nodes[low][0]:
        low = nodes[low][0]
    while nodes[high][1]:
        high = nodes[high][1]
    if first != low or last != high:
        raise NativeVendorDialogCaptureError("invalid warehouse reserve extrema")
    return result


def read_native_warehouse_withdrawal(memory: VendorQueueMemory) -> dict[str, object]:
    if (
        memory.executable_name.casefold() != "sb.exe"
        or memory.pointer_size != 4
        or memory.executable_sha256 not in REVIEWED_VENDOR_EXECUTABLES
    ):
        raise NativeVendorDialogCompatibilityError("unsupported warehouse executable")
    r = _ReadSet(memory)
    base = memory.base_address
    root = r.word(base + 0x16A7BFC)
    r.require(root, base + 0x1174884, "game window type")
    r.require(root + 0x64, 2, "in-world state")
    active = r.hud_stack(root)
    warehouses = [hud for hud in active if r.word(hud) == base + 0x1170308]
    if len(warehouses) != 1:
        raise NativeVendorDialogCaptureError("exactly one active warehouse is required")
    warehouse = warehouses[0]
    quote = r.word(warehouse + 0x10C)
    if quote == warehouse or quote not in active:
        raise NativeVendorDialogCaptureError("warehouse withdrawal quote is not active")
    r.require(quote, base + 0x1168044, "warehouse amount HUD type")
    r.require(quote + 0x108, warehouse, "warehouse quote owner")
    # GetReference (0x1125d0) used by withdrawal reads object +18/+1c.
    owner = r.word(warehouse + 0x378)
    r.require(owner, base + 0x114165C, "warehouse source object type")
    source = struct.unpack("<II", r.read(owner + 0x18, 8))
    if not source[0] or source[1] != 42:
        raise NativeVendorDialogCaptureError("invalid warehouse source hireling")
    resource = r.word(quote + 0x388)
    if not resource:
        raise NativeVendorDialogCaptureError("warehouse quote has no resource identity")
    lists, rows, entries = set(), {}, set()
    for child in r.vector(warehouse + 0x54, 512):
        r.require(child + 0x3BC, warehouse, "warehouse control owner")
        name = _text(r, child + 0x164)
        if name != "WAREHOUSE_INV":
            continue
        if name in lists:
            raise NativeVendorDialogCaptureError("duplicate warehouse inventory")
        lists.add(name)
        r.require(child, base + 0x116ACF0, "warehouse inventory type")
        for control in r.vector(child + 0x408, 1024):
            r.require(control, base + 0x116AEBC, "warehouse resource control type")
            r.require(control + 0x3BC, warehouse, "warehouse resource HUD owner")
            r.require(control + 0x458, child, "warehouse resource list owner")
            entry = r.word(control + 0x44C)
            r.require(entry, base + 0x116F258, "warehouse resource entry type")
            identity = r.word(entry + 0x20)
            amount = r.word(entry + 0x48)
            if not identity or identity in rows or entry in entries or amount > 0x7FFFFFFF:
                raise NativeVendorDialogCaptureError(
                    "invalid warehouse resource identity or amount"
                )
            entries.add(entry)
            rows[identity] = {
                "resource_id": identity,
                "display_name": _text(r, entry + 0x30),
                "amount": amount,
            }
    if lists != {"WAREHOUSE_INV"} or resource not in rows:
        raise NativeVendorDialogCaptureError("quoted resource is missing from the warehouse")
    controls = {}
    for control in r.vector(quote + 0x54, 32):
        r.require(control + 0x3BC, quote, "withdrawal control owner")
        name = _text(r, control + 0x164)
        if name not in ("ACCEPT", "CANCEL", "SLIDEHELPER"):
            continue
        if name in controls:
            raise NativeVendorDialogCaptureError("duplicate withdrawal control")
        r.require(control, base + 0x1169EC0, "withdrawal control type")
        r.require(control + 0x1A8, 0, "withdrawal control enabled")
        if r.read(control + 0x304, 4)[1]:
            raise NativeVendorDialogCaptureError("withdrawal control hidden")
        if name != "SLIDEHELPER":
            r.require(
                control + 0x1D0,
                0x1009 if name == "ACCEPT" else 0x100B,
                "warehouse withdrawal direction",
            )
            r.require(control + 0x1D4, 0, "warehouse withdrawal parameter")
            r.require(control + 0x1D8, 0, "warehouse withdrawal parameter")
        controls[name] = control
    if len(controls) != 3:
        raise NativeVendorDialogCaptureError("missing warehouse withdrawal controls")
    entered = _text(r, controls["SLIDEHELPER"] + 0xA4)
    if not re.fullmatch(r"[0-9]{1,10}", entered):
        raise NativeVendorDialogCaptureError("invalid withdrawal amount text")
    amount, limit = int(entered), r.word(quote + 0x3C0)
    reserve = _reserves(r, warehouse + 0x3E8).get(resource, 0)
    available = max(0, rows[resource]["amount"] - reserve)
    if not 0 < amount <= limit <= 0x7FFFFFFF or limit != available:
        raise NativeVendorDialogCaptureError("withdrawal exceeds funds or quote is stale")
    result = {
        "schema_version": 1,
        "scope": "active_warehouse_withdrawal_quote",
        "process_id": memory.pid,
        "process_creation_filetime_utc": memory.process_creation_filetime_utc,
        "source_hireling": {"object_id": source[0], "object_type": source[1]},
        "resource": rows[resource],
        "minimum_balance": reserve,
        "available_amount": available,
        "entered_amount": amount,
        "current_purse_verified": False,
        "server_acceptance_verified": False,
        "command_admitted": False,
    }
    r.verify()
    return result
