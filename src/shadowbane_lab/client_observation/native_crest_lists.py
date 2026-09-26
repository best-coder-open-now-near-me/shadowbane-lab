"""Read loaded crest lists without selecting or condemning anything.

HUD-stack membership alone does not prove a window is visible. A loaded list is not a
server acknowledgement or proof of complete nation coverage.
See docs/handoffs/guard-crest-lists.md for reviewed layouts and limitations.
"""
from __future__ import annotations

import struct

from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from shadowbane_lab.client_observation.native_vendor_queue import VendorQueueMemory, _ReadSet
from shadowbane_lab.client_observation.native_vendor_roster import _text

REVIEWED_CREST_EXECUTABLES = frozenset({
    "e277e5a4e1e4e1df048a32c07bdbac6fec0591c7d01588b984577251cf475891",
    "761f375e422332cac2512398bb935af38b30267b9b3a7a5cede9f87e98982442",
    "7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f",
    "2dc0e19c3fcf43bc19508939fb9c63982bc370a868f810208394324a12cdc289",
})
CREST_HUD_CLASSES = {
    0x1168CA8: "heraldry",
    0x1168E94: "kos",
    0x1169080: "antagonist",
    0x1168AD4: "crest_options",
}


def _key(r: _ReadSet, address: int) -> dict[str, int]:
    object_id, object_type = struct.unpack("<II", r.read(address, 8))
    return {"object_id": object_id, "object_type": object_type}


def read_native_crest_lists(memory: VendorQueueMemory) -> dict[str, object]:
    """Retain character, guild and nation keys separately, including unknown types.

    Raw row keys and flags are not action targets or permissions. KOS context can
    be zero in a cached window; never bind it to the asset manager's current target.
    Only the prepared build whose crest code was compared is admitted.
    """
    if (
        memory.executable_name.casefold() != "sb.exe" or memory.pointer_size != 4
        or memory.executable_sha256 not in REVIEWED_CREST_EXECUTABLES
    ):
        raise NativeVendorDialogCompatibilityError("unsupported crest-list executable")
    r, base = _ReadSet(memory), memory.base_address
    root = r.word(base + 0x16A7BFC)
    r.require(root, base + 0x1174884, "game window type")
    r.require(root + 0x64, 2, "in-world state")
    refresh_pending = r.read(root + 0x138, 4)[0]
    windows = []
    for hud in r.hud_stack(root):
        kind = r.word(hud) - base
        if kind not in CREST_HUD_CLASSES:
            continue
        window = {
            "address": hud, "class_rva": kind, "kind": CREST_HUD_CLASSES[kind],
            "hud_kind_raw": r.word(hud + 0xDC),
            "hud_flag_fc_raw": r.read(hud + 0xFC, 4)[0],
            "lookup_excluded_raw": r.read(hud + 0x270, 4)[1],
            "visibility_verified": False,
        }
        if kind == 0x1168AD4:
            window["options_raw"] = list(r.read(hud + 0x3E8, 8)[:5])
            window["owner_address_raw"] = r.word(hud + 0x104)
        else:
            children = r.vector(hud + 0x54, 512)
            listing = r.word(hud + 0x3C8)
            if listing not in children:
                raise NativeVendorDialogCaptureError("crest list is not a window child")
            r.require(listing, base + 0x116ACF0, "crest list type")
            r.require(listing + 0x3BC, hud, "crest list owner")
            selected = r.word(hud + 0x3B8)
            rows, seen = [], set()
            for control in r.vector(listing + 0x408, 512):
                r.require(control, base + 0x116AEBC, "crest row control type")
                r.require(control + 0x3BC, hud, "crest row window owner")
                r.require(control + 0x458, listing, "crest row list owner")
                entry = r.word(control + 0x44C)
                r.require(entry, base + 0x11693EC, "heraldry entry type")
                r.require(entry + 8, 0x1D, "heraldry entry kind")
                if entry in seen:
                    raise NativeVendorDialogCaptureError("duplicate crest entry ownership")
                seen.add(entry)
                rows.append({
                    "entry_address": entry, "selected": entry == selected,
                    "row_key_raw": _key(r, entry + 0x10),
                    "identities": {
                        label: _key(r, entry + key_offset)
                        for label, key_offset in (
                            ("character", 0x68), ("guild", 0x70), ("nation", 0x78),
                        )
                    },
                    # KOS may place a nation label in the first text field;
                    # text-field position does not establish identity scope.
                    "display_labels_raw": [_text(r, entry + offset)
                                           for offset in (0x20, 0x38, 0x50)],
                    "flags_raw": list(r.read(entry + 0x84, 4)[:3]),
                })
            if selected and selected not in seen:
                raise NativeVendorDialogCaptureError("selected crest is outside its list")
            window["entries"] = rows
            if kind == 0x1168E94:
                window["context_key_raw"] = _key(r, hud + 0x3D0)
                window["pending_identities_raw"] = {
                    label: _key(r, hud + offset) for label, offset in (
                        ("character", 0x3E0), ("guild", 0x3E8), ("nation", 0x3F0),
                    )
                }
                window["flags_raw"] = list(r.read(hud + 0x3F8, 4)[:2])
        windows.append(window)
    r.verify()
    return {
        "root_address": root, "root_refresh_pending_raw": refresh_pending,
        "windows": windows, "command_admitted": False,
        "server_acceptance_verified": False, "town_coverage_verified": False,
    }
