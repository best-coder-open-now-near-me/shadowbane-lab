"""Read guard upgrade state from owned, visible menus; never send game actions."""
from __future__ import annotations

import struct

from .native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from .native_vendor_queue import VendorQueueMemory, _ReadSet
from .native_vendor_roster import _text
from .reviewed_vendor_builds import REVIEWED_VENDOR_EXECUTABLES


def read_native_guard_upgrade(memory: VendorQueueMemory) -> dict[str, object]:
    """Observe the selected type-37 guard and its complete building list.

    Type 37 is live-qualified for wall archers. Other hireling types are retained
    in the roster without granting guard eligibility. This is neither a town
    census nor proof that an upgrade request was accepted by the server.
    """
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
    r.require(manager + 0xD0, 6, "building management mode")
    r.require(manager + 0xD8, 0, "online management")
    r.require(manager + 0x48, 1, "building initialized")
    r.require(manager + 0x50, 1, "hireling initialized")
    active = r.hud_stack(root)
    building_menu, guard_menu = r.word(manager + 0x68), r.word(manager + 0x78)
    if building_menu == guard_menu:
        raise NativeVendorDialogCaptureError("aliased building and guard windows")
    for menu in (building_menu, guard_menu):
        r.require(menu, base + 0x116A058, "management HUD type")
        r.require(menu + 0x104, manager, "management HUD owner")
        if menu not in active:
            raise NativeVendorDialogCaptureError("guard or building menu is not active")
    building = struct.unpack("<II", r.read(manager + 0xF0, 8))
    if not building[0] or building[1] != 8:
        raise NativeVendorDialogCaptureError("invalid guard building key")
    if r.read(manager + 0xF8, 8) != struct.pack("<II", *building):
        raise NativeVendorDialogCaptureError("guard building selection changed")
    selected = r.word(manager + 0x384)
    r.require(selected, base + 0x1169518, "selected hireling type")
    key = struct.unpack("<II", r.read(selected + 0x10, 8))
    if not key[0] or key[1] != 37:
        raise NativeVendorDialogCaptureError("selected hireling is not a qualified guard type")
    capacity, occupied = r.word(manager + 0x380), r.word(manager + 0x37C)
    if not 0 < occupied <= capacity <= 128:
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
    if positions != capacity or len(rows) != occupied or selected not in entries or key not in keys:
        raise NativeVendorDialogCaptureError("guard roster is incomplete or selection detached")
    controls = {}
    for child in r.vector(guard_menu + 0x54, 512):
        r.require(child + 0x3BC, guard_menu, "guard control owner")
        name = _text(r, child + 0x164)
        if name not in ("BTNUPGRADE", "BTNUPGRADECOST", "SLIDEUPGRADE"):
            continue
        if name in controls:
            raise NativeVendorDialogCaptureError("duplicate guard upgrade control")
        r.require(child, base + 0x1169EC0, "guard upgrade control type")
        disabled = r.word(child + 0x1A8)
        hidden = r.read(child + 0x304, 4)[1]
        if disabled not in (0, 1) or hidden not in (0, 1):
            raise NativeVendorDialogCaptureError("invalid guard control state")
        controls[name] = {"enabled": not disabled, "visible": not hidden}
    if len(controls) != 3:
        raise NativeVendorDialogCaptureError("missing guard upgrade controls")
    upgrading, can_upgrade = r.read(manager + 0x2AC, 4)[:2]
    if upgrading not in (0, 1) or can_upgrade not in (0, 1):
        raise NativeVendorDialogCaptureError("invalid guard upgrade flags")
    result = {
        "schema_version": 1, "scope": "current_building_selected_guard",
        "process_id": memory.pid,
        "process_creation_filetime_utc": memory.process_creation_filetime_utc,
        "building": {"object_id": building[0], "object_type": building[1]},
        "building_name": _text(r, manager + 0x15C),
        "hireling_slots": capacity, "vacant_hireling_slots": vacancies,
        "hirelings": rows,
        "selected_guard": {"object_id": key[0], "object_type": key[1]},
        "upgrade_cost_gold": r.word(manager + 0x274),
        "displayed_building_funds_gold": r.word(manager + 0x1CC),
        "upgrade_in_progress": bool(upgrading), "can_upgrade": bool(can_upgrade),
        "controls": controls,
        "town_coverage_verified": False, "server_acceptance_verified": False,
        "management_permission_verified": False, "command_admitted": False,
    }
    r.verify()
    return result
