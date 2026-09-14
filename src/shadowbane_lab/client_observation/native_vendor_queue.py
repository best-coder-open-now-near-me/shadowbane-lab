"""Read the current menu's production slots through native ownership links.

Exact x86 build only. This is a consistency-checked observation, not a command
lease or a login epoch: an external reader cannot prevent native object reuse.
"""
from __future__ import annotations

import math
import struct
from typing import Protocol

from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)

_QUEUE_BUILD = "bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87"
_WINDOW_RVA = 0x16A7BFC
_WINDOW_VTABLE = 0x1174884
_MANAGER_VTABLE = 0x1171ADC
_HUD_VTABLE = 0x116A058
_LIST_BOX_VTABLE = 0x116ACF0
_LIST_CONTROL_VTABLE = 0x116AEBC
_PRODUCTION_VTABLE = 0x1169560
_MAX_CONTROLS = 512
_MAX_LIST_ENTRIES = 128
_MAX_SLOTS = 16


class VendorQueueMemory(Protocol):
    base_address: int
    executable_name: str
    executable_sha256: str
    pointer_size: int
    pid: int
    process_creation_filetime_utc: int | None

    def read_block(self, address: int, size: int) -> bytes: ...


class _ReadSet:
    def __init__(self, memory: VendorQueueMemory):
        self.memory = memory
        self.blocks: dict[tuple[int, int], bytes] = {}

    def read(self, address: int, size: int) -> bytes:
        if (
            type(address) is not int or address % 4
            or not 0x10000 <= address < 0x80000000
            or not 0 < size <= 8192 or address + size > 0x80000000
        ):
            raise NativeVendorDialogCaptureError("invalid vendor queue read bounds")
        block = self.memory.read_block(address, size)
        if len(block) != size:
            raise NativeVendorDialogCaptureError("short vendor queue read")
        key = (address, size)
        if key in self.blocks and self.blocks[key] != block:
            raise NativeVendorDialogCaptureError("vendor queue changed during observation")
        self.blocks[key] = block
        return block

    def word(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]

    def require(self, address: int, value: int, label: str) -> None:
        if self.word(address) != value:
            raise NativeVendorDialogCaptureError(f"vendor queue {label} mismatch")

    def vector(self, address: int, limit: int) -> tuple[int, ...]:
        begin, end, capacity = struct.unpack("<III", self.read(address, 12))
        if begin == end == capacity == 0:
            return ()
        if (
            not 0x10000 <= begin <= end <= capacity < 0x80000000
            or begin % 4 or end % 4 or capacity % 4
            or end - begin > limit * 4
        ):
            raise NativeVendorDialogCaptureError("invalid vendor queue vector")
        values = (
            tuple(value for (value,) in struct.iter_unpack("<I", self.read(begin, end - begin)))
            if end != begin else ()
        )
        if len(set(values)) != len(values):
            raise NativeVendorDialogCaptureError("duplicate vendor queue ownership link")
        return values

    def hud_stack(self, root: int) -> tuple[int, ...]:
        head = self.word(root + 0x20)
        first, last = struct.unpack("<II", self.read(head, 8))
        node, previous = first, head
        seen = set()
        huds = []
        while node != head:
            if node in seen or len(seen) >= 128:
                raise NativeVendorDialogCaptureError("invalid active HUD list")
            seen.add(node)
            next_node, prev_node, hud = struct.unpack("<III", self.read(node, 12))
            if prev_node != previous or hud in huds:
                raise NativeVendorDialogCaptureError("broken active HUD ownership")
            huds.append(hud)
            previous, node = node, next_node
        if previous != last:
            raise NativeVendorDialogCaptureError("broken active HUD tail")
        return tuple(huds)

    def verify(self) -> None:
        # Recheck leaves first, root last. Reject any changed read, including
        # same-address pointer-array replacement; never retry silently into a new menu.
        for (address, size), expected in reversed(tuple(self.blocks.items())):
            if self.memory.read_block(address, size) != expected:
                raise NativeVendorDialogCaptureError("vendor queue changed during observation")


def _creation_recipe(
    r: _ReadSet, base: int, active_huds: tuple[int, ...], manager: int
) -> dict[str, object] | None:
    candidates = [hud for hud in active_huds if r.word(hud) == base + 0x116BF7C]
    if len(candidates) > 1:
        raise NativeVendorDialogCaptureError("ambiguous active crafting recipe")
    if not candidates:
        return None
    hud = candidates[0]
    r.require(hud + 0x3B8, manager, "crafting recipe owner")
    vendor_id, vendor_type = struct.unpack("<II", r.read(hud + 0x3C0, 8))
    if not vendor_id or vendor_type != 42:
        raise NativeVendorDialogCaptureError("invalid crafting vendor identity")
    selected = r.word(hud + 0x408)
    template = None
    if selected:
        r.require(selected, base + 0x1142748, "selected recipe item type")
        template_id, template_type = struct.unpack("<II", r.read(selected + 0x10, 8))
        if not template_id or template_type != 0:
            raise NativeVendorDialogCaptureError("invalid selected recipe template")
        template = {"object_id": template_id, "object_type": template_type}
    sentinel = r.word(hud + 0x400)
    mode = r.word(hud + 0x404)
    prefix = r.word(hud + 0x40C)
    suffix = r.word(hud + 0x434)
    modtable = r.word(hud + 0x47C)
    quantity = r.word(hud + 0x4D4)
    multiple = r.read(hud + 0x3D8, 4)[0]
    if multiple not in (0, 1):
        raise NativeVendorDialogCaptureError("invalid crafting slot mode")
    # The no-modifier choice is not wire token zero. Require the exact sentinel
    # observed at the qualified Create builder, plus its mode and recipe table.
    random_scepter = (
        template == {"object_id": 26990, "object_type": 0}
        and sentinel == prefix == suffix == 3362971591
        and mode == 1 and modtable == 12 and quantity == 1 and multiple == 0
    )
    return {
        "window_address": hud, "vendor": {"object_id": vendor_id, "object_type": vendor_type},
        "template": template, "template_address": selected,
        "prefix_selection_raw": prefix, "suffix_selection_raw": suffix,
        "random_sentinel_raw": sentinel, "mode_raw": mode,
        "modification_table": modtable, "quantity": quantity, "multiple_slots": bool(multiple),
        "qualified_random_scepter": random_scepter,
    }


def _inventory(
    r: _ReadSet, base: int, active_huds: tuple[int, ...], manager: int
) -> dict[str, object] | None:
    from shadowbane_lab.client_observation.native_inventory_item import decode_inventory_instance

    hud = r.word(manager + 0x7C)
    if not hud or hud not in active_huds:
        return None
    r.require(hud, base + 0x116C64C, "inventory HUD type")
    r.require(hud + 0x104, manager, "inventory HUD owner")
    r.require(hud + 0x3F4, manager, "inventory manager interface")
    listing = r.word(hud + 0x3F0)
    if listing not in r.vector(hud + 0x54, _MAX_CONTROLS):
        raise NativeVendorDialogCaptureError("inventory list is not owned by current HUD")
    r.require(listing, base + _LIST_BOX_VTABLE, "inventory list type")
    r.require(listing + 0x3BC, hud, "inventory list owner")

    class InstanceMemory:
        base_address = base

        def read_block(self, address: int, size: int) -> bytes:
            return r.read(address, size)

    memory = InstanceMemory()
    items = []
    seen_entries: set[int] = set()
    seen_items: set[int] = set()
    for control in r.vector(listing + 0x408, _MAX_LIST_ENTRIES):
        r.require(control, base + _LIST_CONTROL_VTABLE, "inventory control type")
        r.require(control + 0x3BC, hud, "inventory control HUD owner")
        r.require(control + 0x458, listing, "inventory control list owner")
        entry = r.word(control + 0x44C)
        r.require(entry, base + 0x11696C8, "inventory managing entry type")
        if entry in seen_entries:
            raise NativeVendorDialogCaptureError("duplicate inventory entry")
        seen_entries.add(entry)
        item_id, item_type = struct.unpack("<II", r.read(entry + 0x10, 8))
        if not item_id or item_type != 40 or item_id in seen_items:
            raise NativeVendorDialogCaptureError("invalid or duplicate inventory item")
        seen_items.add(item_id)
        instance = r.word(entry + 0x20)
        item = decode_inventory_instance(memory, instance)
        if item["item"] != {"object_id": item_id, "object_type": item_type}:
            raise NativeVendorDialogCaptureError("inventory entry and instance mismatch")
        native_item = r.word(entry + 0x24)
        r.require(native_item, base + 0x1142748, "inventory native item type")
        template_id, template_type, native_id, native_type = struct.unpack(
            "<IIII", r.read(native_item + 0x10, 16)
        )
        if (
            (native_id, native_type) != (item_id, item_type)
            or item["template"] != {"object_id": template_id, "object_type": template_type}
        ):
            raise NativeVendorDialogCaptureError("inventory native item identity mismatch")
        items.append({
            "control_address": control, "entry_address": entry,
            "instance_address": instance, "native_item_address": native_item, **item,
        })
    return {
        "window_address": hud, "list_address": listing, "items": items,
        # The displayed list proves presence. Filtering/paging and server
        # capacity have not been qualified; absence must never authorize retry.
        "scope": "displayed_entries", "complete_inventory": False, "capacity": None,
    }


def read_native_vendor_queue(memory: VendorQueueMemory) -> dict[str, object]:
    """Read slots owned by the active city manager, without scanning the heap.

    Native root construction at RVA 0x7949F3 assigns the city manager at +0xA4.
    Manager +0x78 owns its HUD; HUD +0x104 refers back to the manager.
    HUD lookup RVA 0x5DFA50 traverses +0x54; list-box insertion RVA 0x6127F0
    owns +0x408, assigns control +0x3BC/+0x458, and uses payload +0x44C.
    Production entry creation/population: RVA 0x5B9200 / 0x6DBE90.

    A returned slot is a selected-vendor menu observation only. Actual free-slot
    permission, server acceptance, and a native session fence remain separate.
    """
    if (
        memory.executable_name.casefold() != "sb.exe" or memory.pointer_size != 4
        or memory.executable_sha256 != _QUEUE_BUILD
    ):
        raise NativeVendorDialogCompatibilityError("unqualified vendor queue executable")
    lifetime = memory.process_creation_filetime_utc
    if type(lifetime) is not int or lifetime <= 0:
        raise NativeVendorDialogCompatibilityError("vendor queue requires process lifetime")
    if type(memory.pid) is not int or memory.pid <= 0:
        raise NativeVendorDialogCompatibilityError("vendor queue requires explicit process ID")
    r = _ReadSet(memory)
    base = memory.base_address
    root = r.word(base + _WINDOW_RVA)
    r.require(root, base + _WINDOW_VTABLE, "game window type")
    r.require(root + 0x64, 2, "in-world mode")
    manager = r.word(root + 0xA4)
    r.require(manager, base + _MANAGER_VTABLE, "city manager type")
    hud = r.word(manager + 0x78)
    r.require(hud, base + _HUD_VTABLE, "management menu type")
    r.require(hud + 0x104, manager, "management menu owner")
    active_huds = r.hud_stack(root)
    if hud not in active_huds:
        raise NativeVendorDialogCaptureError("management menu is not in the active HUD list")
    building_id, building_type = struct.unpack("<II", r.read(manager + 0xF0, 8))
    if not building_id or building_type != 8:
        raise NativeVendorDialogCaptureError("invalid vendor building identity")

    # ArcCityAssetManager's selected ArcHirelingEntry is also the identity
    # consumed by Keep at RVA 0x6D7127 -> getter RVA 0x567F90 (+0x10).
    # Do not infer the vendor solely from an independently open recipe window.
    r.require(manager + 0xD8, 0, "vendor management mode")
    selected_vendor = r.word(manager + 0x384)
    r.require(selected_vendor, base + 0x1169518, "selected hireling type")
    vendor_id, vendor_type = struct.unpack("<II", r.read(selected_vendor + 0x10, 8))
    if not vendor_id or vendor_type != 42:
        raise NativeVendorDialogCaptureError("invalid selected vendor identity")
    vendor = {"object_id": vendor_id, "object_type": vendor_type}
    # Create and Keep consume separate building fields. A menu transition may
    # leave one behind; a mixed observation cannot reconcile either command.
    keep_building = struct.unpack("<II", r.read(manager + 0xF8, 8))
    if keep_building != (building_id, building_type):
        raise NativeVendorDialogCaptureError("vendor building selection mismatch")

    slots = []
    seen_controls: set[int] = set()
    seen_entries: set[int] = set()
    seen_items: set[int] = set()
    production_list = None
    for child in r.vector(hud + 0x54, _MAX_CONTROLS):
        child_type = r.word(child)
        r.require(child + 0x3BC, hud, "menu child owner")
        if child_type != base + _LIST_BOX_VTABLE:
            continue
        for control in r.vector(child + 0x408, _MAX_LIST_ENTRIES):
            if control in seen_controls:
                raise NativeVendorDialogCaptureError("shared vendor list control")
            seen_controls.add(control)
            r.require(control, base + _LIST_CONTROL_VTABLE, "list control type")
            r.require(control + 0x3BC, hud, "list control menu owner")
            r.require(control + 0x458, child, "list control list owner")
            entry = r.word(control + 0x44C)
            if not entry:
                continue
            if r.word(entry) != base + _PRODUCTION_VTABLE:
                continue  # Service rows do not represent crafting slots.
            if production_list is not None and production_list != child:
                raise NativeVendorDialogCaptureError("ambiguous vendor production list")
            production_list = child
            if entry in seen_entries or len(slots) >= _MAX_SLOTS:
                raise NativeVendorDialogCaptureError("invalid vendor production slot collection")
            seen_entries.add(entry)
            item_id, item_type = struct.unpack("<II", r.read(entry + 0x10, 8))
            value, count, duration, elapsed_raw = struct.unpack("<IIII", r.read(entry + 0x40, 16))
            elapsed = struct.unpack("<d", r.read(entry + 0x50, 8))[0]
            complete, active, modified, reserved = r.read(entry + 0x58, 4)
            if any(flag not in (0, 1) for flag in (complete, active, modified)):
                raise NativeVendorDialogCaptureError("invalid vendor production flags")
            if not math.isfinite(elapsed) or elapsed < 0:
                raise NativeVendorDialogCaptureError("invalid vendor production elapsed time")
            if item_id == item_type == 0:
                if complete or active:
                    raise NativeVendorDialogCaptureError("empty vendor slot has active flags")
                state = "empty"
            elif item_id and item_type == 40 and active:
                if item_id in seen_items:
                    raise NativeVendorDialogCaptureError("duplicate vendor production item")
                seen_items.add(item_id)
                state = "complete" if complete else "cooking"
            else:
                raise NativeVendorDialogCaptureError("inconsistent vendor production identity")
            slots.append({
                "control_address": control, "entry_address": entry,
                "item": {"object_id": item_id, "object_type": item_type},
                "state": state, "value_raw": value, "remaining_count_raw": count,
                "duration_seconds_raw": duration, "elapsed_seconds_raw": elapsed_raw,
                "elapsed_seconds": elapsed, "modified_flag": modified, "reserved_flag": reserved,
            })
    if production_list is None:
        raise NativeVendorDialogCaptureError("current menu has no qualified production slots")
    recipe = _creation_recipe(r, base, active_huds, manager)
    if recipe is not None and recipe["vendor"] != vendor:
        raise NativeVendorDialogCaptureError("recipe and selected vendor mismatch")
    inventory = _inventory(r, base, active_huds, manager)
    if inventory is not None and any(
        item["item"]["object_id"] in seen_items for item in inventory["items"]
    ):
        raise NativeVendorDialogCaptureError("item appears in both production and inventory")
    r.verify()
    return {
        "schema_version": 4, "record_type": "vendor_queue_snapshot",
        "process_id": memory.pid, "process_creation_filetime_utc": lifetime,
        "executable_sha256": memory.executable_sha256,
        "native_window_address": root, "manager_address": manager, "menu_address": hud,
        "building": {"object_id": building_id, "object_type": building_type},
        "vendor": vendor, "selected_vendor_entry_address": selected_vendor,
        "production_list_address": production_list, "slots": slots, "creation_recipe": recipe,
        "inventory": inventory, "command_admitted": False,
    }
