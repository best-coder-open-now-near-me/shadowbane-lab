"""Observe the exact structure and typed gold in an ordinary deposit prompt."""
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


def read_native_structure_deposit(memory: VendorQueueMemory) -> dict[str, object]:
    if (memory.executable_name.casefold() != "sb.exe" or memory.pointer_size != 4
            or memory.executable_sha256 not in REVIEWED_VENDOR_EXECUTABLES):
        raise NativeVendorDialogCompatibilityError("unsupported structure deposit executable")
    r = _ReadSet(memory)
    base = memory.base_address
    root = r.word(base + 0x16A7BFC)
    r.require(root, base + 0x1174884, "game window type")
    r.require(root + 0x64, 2, "in-world state")
    manager = r.word(root + 0xA4)
    r.require(manager, base + 0x1171ADC, "asset manager type")
    r.require(manager + 0xD8, 0, "online management")
    r.require(manager + 0xD0, 13, "gold deposit mode")
    r.require(manager + 0x48, 1, "building initialized")
    building = struct.unpack("<II", r.read(manager + 0xF0, 8))
    if not building[0] or building[1] != 8:
        raise NativeVendorDialogCaptureError("invalid deposit building key")
    if r.read(manager + 0xF8, 8) != struct.pack("<II", *building):
        raise NativeVendorDialogCaptureError("deposit building selection changed")
    active = r.hud_stack(root)
    menu, quote = r.word(manager + 0x68), r.word(manager + 0x74)
    if menu == quote or menu not in active or quote not in active:
        raise NativeVendorDialogCaptureError("deposit or building window is not active")
    for hud, vtable in ((menu, 0x116A058), (quote, 0x1168044)):
        r.require(hud, base + vtable, "deposit HUD type")
        r.require(hud + 0x104, manager, "deposit HUD owner")
    controls = {}
    for control in r.vector(quote + 0x54, 32):
        r.require(control + 0x3BC, quote, "deposit control owner")
        name = _text(r, control + 0x164)
        if name not in ("SLIDEHELPER", "ACCEPT", "CANCEL"):
            continue
        if name in controls:
            raise NativeVendorDialogCaptureError("duplicate deposit control")
        r.require(control, base + 0x1169EC0, "deposit control type")
        r.require(control + 0x1A8, 0, "deposit control enabled")
        if r.read(control + 0x304, 4)[1] != 0:
            raise NativeVendorDialogCaptureError("deposit control is hidden")
        if name != "SLIDEHELPER":
            for offset in (0x1D4, 0x1F8, 0x21C):
                r.require(control + offset, 13, "deposit event mode")
        controls[name] = control
    if len(controls) != 3:
        raise NativeVendorDialogCaptureError("missing deposit controls")
    # GetAmount (0x595390) parses SLIDEHELPER, not its stale +3c4 cache.
    entered = _text(r, controls["SLIDEHELPER"] + 0xA4)
    if not re.fullmatch(r"[0-9]{1,10}", entered):
        raise NativeVendorDialogCaptureError("invalid deposit amount text")
    amount, limit = int(entered), r.word(quote + 0x3C0)
    if not 0 < amount <= limit <= 0x7FFFFFFF:
        raise NativeVendorDialogCaptureError("deposit exceeds quote bounds or is zero")
    result = {
        "schema_version": 1, "scope": "active_structure_gold_deposit_quote",
        "process_id": memory.pid,
        "process_creation_filetime_utc": memory.process_creation_filetime_utc,
        "building": {"object_id": building[0], "object_type": building[1]},
        "building_name": _text(r, manager + 0x15C),
        "displayed_building_funds_gold": r.word(manager + 0x1CC),
        "entered_amount_gold": amount,
        "purse_limit_at_prompt_open_gold": limit,
        "current_purse_verified": False, "server_acceptance_verified": False,
        "command_admitted": False,
    }
    r.verify()
    return result
