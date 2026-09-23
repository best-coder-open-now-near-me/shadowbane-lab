"""Read guard upgrade state from owned, visible menus; never send game actions."""
from __future__ import annotations

import struct

from .native_building_hirelings import _capture_building_hirelings
from .native_vendor_dialog import NativeVendorDialogCaptureError
from .native_vendor_queue import VendorQueueMemory
from .native_vendor_roster import _text


def read_native_guard_upgrade(memory: VendorQueueMemory) -> dict[str, object]:
    """Observe the selected type-37 guard and its complete building list.

    Type 37 is live-qualified for wall archers. Other hireling types are retained
    in the roster without granting guard eligibility. This is neither a town
    census nor proof that an upgrade request was accepted by the server.
    """
    capture = _capture_building_hirelings(memory)
    r, manager, base = capture.reads, capture.manager, memory.base_address
    r.require(manager + 0x50, 1, "hireling initialized")
    guard_menu = r.word(manager + 0x78)
    if capture.menu == guard_menu:
        raise NativeVendorDialogCaptureError("aliased building and guard windows")
    r.require(guard_menu, base + 0x116A058, "management HUD type")
    r.require(guard_menu + 0x104, manager, "management HUD owner")
    if guard_menu not in capture.active:
        raise NativeVendorDialogCaptureError("guard menu is not active")
    selected = r.word(manager + 0x384)
    r.require(selected, base + 0x1169518, "selected hireling type")
    key = struct.unpack("<II", r.read(selected + 0x10, 8))
    if not key[0] or key[1] != 37:
        raise NativeVendorDialogCaptureError("selected hireling is not a qualified guard type")
    if selected not in capture.entries or key not in capture.keys:
        raise NativeVendorDialogCaptureError("guard selection is detached from building roster")
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
        **capture.result, "scope": "current_building_selected_guard",
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
