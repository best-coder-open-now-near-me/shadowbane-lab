"""Complete owned building hireling observation, independent of selection or crafting."""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from .native_vendor_queue import VendorQueueMemory, _ReadSet
from .native_vendor_roster import _text
from .reviewed_vendor_builds import REVIEWED_VENDOR_EXECUTABLES


class BuildingHirelingsUnavailable(NativeVendorDialogCaptureError):
    """An owned stable zero-slot menu cannot establish a hireling roster."""

    def __init__(self, observation):
        super().__init__("This building exposes no hireling slots; coverage is unverified.")
        self.observation = observation


@dataclass(frozen=True)
class _BuildingHirelings:
    reads: _ReadSet
    root: int
    manager: int
    menu: int
    active: tuple[int, ...]
    entries: set[int]
    keys: set[tuple[int, int]]
    result: dict[str, object]


def _capture_building_hirelings(memory: VendorQueueMemory) -> _BuildingHirelings:
    if (memory.executable_name.casefold() != "sb.exe" or memory.pointer_size != 4
            or memory.executable_sha256 not in REVIEWED_VENDOR_EXECUTABLES):
        raise NativeVendorDialogCompatibilityError("unsupported guard executable")
    r = _ReadSet(memory)
    base = memory.base_address
    root = r.word(base + 0x16A7BFC)
    r.require(root, base + 0x1174884, "game window type")
    r.require(root + 0x64, 2, "in-world state")
    manager = r.word(root + 0xA4)
    r.require(manager, base + 0x1171ADC, "asset manager type")
    if r.word(manager + 0xD0) not in (0, 6):
        raise NativeVendorDialogCaptureError("unsupported building management mode")
    r.require(manager + 0xD8, 0, "online management")
    r.require(manager + 0x48, 1, "building initialized")
    active = r.hud_stack(root)
    building_menu = r.word(manager + 0x68)
    r.require(building_menu, base + 0x116A058, "management HUD type")
    r.require(building_menu + 0x104, manager, "management HUD owner")
    if building_menu not in active:
        raise NativeVendorDialogCaptureError("building menu is not active")
    building = struct.unpack("<II", r.read(manager + 0xF0, 8))
    if not building[0] or building[1] != 8:
        raise NativeVendorDialogCaptureError("invalid guard building key")
    if r.read(manager + 0xF8, 8) != struct.pack("<II", *building):
        raise NativeVendorDialogCaptureError("guard building selection changed")
    capacity, occupied = r.word(manager + 0x380), r.word(manager + 0x37C)
    if not (0 <= occupied <= capacity <= 128):
        raise NativeVendorDialogCaptureError("invalid guard building occupancy")
    rows, keys, entries = [], set(), set()
    positions = vacancies = 0
    roster_list = None
    for child in r.vector(building_menu + 0x54, 512):
        r.require(child + 0x3BC, building_menu, "building child owner")
        if r.word(child) != base + 0x116ACF0:
            continue
        for control in r.vector(child + 0x408, 128):
            r.require(control, base + 0x116AEBC, "hireling control type")
            r.require(control + 0x3BC, building_menu, "hireling HUD owner")
            r.require(control + 0x458, child, "hireling list owner")
            entry = r.word(control + 0x44C)
            if not entry or r.word(entry) != base + 0x1169518:
                continue
            if roster_list is not None and roster_list != child:
                raise NativeVendorDialogCaptureError("ambiguous guard roster")
            roster_list = child
            if entry in entries:
                raise NativeVendorDialogCaptureError("duplicate hireling entry")
            entries.add(entry)
            r.require(entry + 8, 9, "hireling row kind")
            row_key = struct.unpack("<II", r.read(entry + 0x10, 8))
            populated = r.read(entry + 0x6C, 4)[1]
            positions += 1
            if populated == 0 and not row_key[0]:
                vacancies += 1
                continue
            if populated != 1 or not all(row_key) or row_key in keys:
                raise NativeVendorDialogCaptureError("invalid guard roster identity or vacancy")
            keys.add(row_key)
            rows.append({
                "hireling": {"object_id": row_key[0], "object_type": row_key[1]},
                "display_name": _text(r, entry + 0x30),
                "service_label": _text(r, entry + 0x48),
                "rank": r.word(entry + 0x28),
                "qualified_guard_type": row_key[1] == 37,
            })
    if positions != capacity or len(rows) != occupied:
        raise NativeVendorDialogCaptureError("building hireling roster is incomplete")
    result = {
        "schema_version": 1, "scope": "current_building_hirelings",
        "process_id": memory.pid,
        "process_creation_filetime_utc": memory.process_creation_filetime_utc,
        "building": {"object_id": building[0], "object_type": building[1]},
        "building_name": _text(r, manager + 0x15C),
        "hireling_slots": capacity, "vacant_hireling_slots": vacancies,
        "hirelings": rows, "building_roster_verified": True,
        "town_coverage_verified": False, "server_acceptance_verified": False,
        "management_permission_verified": False, "command_admitted": False,
    }
    if capacity == 0:
        r.verify()
        result["building_roster_verified"] = False
        raise BuildingHirelingsUnavailable(result)
    return _BuildingHirelings(r, root, manager, building_menu, active, entries, keys, result)


def read_native_building_hirelings(memory: VendorQueueMemory) -> dict[str, object]:
    """Read every owned slot, retaining unknown types without upgrade authority.

    An all-vacant result requires a positive, fully observed slot count. Zero
    capacity or an absent list does not prove that a building has no hirelings.
    This proves only the current local menu, never town membership or coverage.
    """
    capture = _capture_building_hirelings(memory)
    capture.reads.verify()
    return capture.result
