"""Read-only evidence for the existing Furniture Placement HUD.

This is an externally copied diagnostic snapshot, never a render-thread lease,
placement decision, or server receipt. Exact native mappings and remaining
qualification are documented in docs/handoffs/furnishing-preview.md.
"""
from __future__ import annotations

import math
import struct

from .native_furnishing_resources import _reference, read_render_resources
from .native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from .native_vendor_queue import VendorQueueMemory, _ReadSet
from .native_vendor_roster import _text

# Narrower than the historical vendor family: inspected 1.3.38.11 images only.
REVIEWED_FURNISHING_EXECUTABLES = frozenset({
    "6347b420c6c151995f168f16fd1624408dd8911698d11a4a74b26d211fb49f19",
    "7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f",
})
FURNITURE_HUD_RVA = 0x1167C68
FURNITURE_ENTRY_RVA = 0x1169908
ACTOR_RVA = 0x114165C
STRUCTURE_RVA = 0x1177C0C


def _occupancy(r: _ReadSet, structure: dict[str, int] | None) -> dict[str, object]:
    """Identify the occupied building from the actor, not the open HUD.

    This copies the same pose-parent link used by the native lifetime observer.
    Only the reviewed actor and structure classes grant field interpretation;
    null/loading and other parent classes cannot establish building identity.
    """
    actor = _reference(r, r.memory.base_address + 0x16A2D98)
    result: dict[str, object] = {
        "actor_reference": actor, "parent_reference": None,
        "occupied_building_key_raw": None,
        "hud_matches_occupied_building": False,
    }
    if not actor or actor["class_rva"] != ACTOR_RVA:
        return result
    component = r.word(actor["address"] + 0x4B0)
    pose = r.word(component) if component else 0
    if not pose:
        return result
    parent = _reference(r, pose + 8)
    result["parent_reference"] = parent
    if not parent or parent["class_rva"] != STRUCTURE_RVA:
        return result
    object_id, object_type = struct.unpack("<II", r.read(parent["address"] + 0x18, 8))
    if not object_id or object_type != 8:
        raise NativeVendorDialogCaptureError("invalid occupied building identity")
    result["occupied_building_key_raw"] = {
        "object_id": object_id, "object_type": object_type,
    }
    result["hud_matches_occupied_building"] = parent == structure
    return result


def read_native_furnishing_preview(
    memory: VendorQueueMemory, *, resource_entry_key: tuple[int, int] | None = None,
) -> dict[str, object]:
    """Copy the one active furnishings HUD, its owned rows and selected references.

    Native row selection updates text; it does not establish a preview pose.
    Null model/selection/layout references are reported, not fabricated. No native
    functions are invoked and no objects are retained or changed. All copied
    bytes are rechecked; even a stable copy cannot prevent native address reuse.
    Optional resource evidence is keyed to one owned row, not to selection.
    """
    if (
        memory.executable_name.casefold() != "sb.exe"
        or memory.executable_sha256 not in REVIEWED_FURNISHING_EXECUTABLES
        or memory.pointer_size != 4
    ):
        raise NativeVendorDialogCompatibilityError("unsupported furnishing executable")
    if resource_entry_key is not None and (
        type(resource_entry_key) is not tuple or len(resource_entry_key) != 2
        or any(type(value) is not int or not 0 <= value <= 0xFFFFFFFF
               for value in resource_entry_key) or not resource_entry_key[0]
    ):
        raise NativeVendorDialogCaptureError("invalid furnishing resource entry key")
    resource_matches = 0
    r, base = _ReadSet(memory), memory.base_address
    root = r.word(base + 0x16A7BFC)
    r.require(root, base + 0x1174884, "game window type")
    r.require(root + 0x64, 2, "in-world state")
    huds = r.hud_stack(root)
    candidates = [hud for hud in huds if r.word(hud) == base + FURNITURE_HUD_RVA]
    if len(candidates) != 1:
        raise NativeVendorDialogCaptureError("expected one active furnishings HUD")
    hud = candidates[0]
    manager = r.word(root + 0xA4)
    r.require(manager, base + 0x1171ADC, "city manager type")
    r.require(hud + 0x104, manager, "furnishing HUD owner")
    r.require(manager + 0xA8, hud, "manager furnishing HUD")
    children = r.vector(hud + 0x54, 512)
    listing, layout, selected = (r.word(hud + offset) for offset in (0x524, 0x648, 0x660))
    if not listing or listing not in children:
        raise NativeVendorDialogCaptureError("furnishing list is not owned by HUD")
    r.require(listing, base + 0x116ACF0, "furnishing list type")
    r.require(listing + 0x3BC, hud, "furnishing list owner")
    layout_control = None
    if layout:
        if layout not in children:
            raise NativeVendorDialogCaptureError("furnishing layout is not owned by HUD")
        r.require(layout + 0x3BC, hud, "furnishing layout owner")
        layout_control = {"address": layout, "name": _text(r, layout + 0x164)}
        if layout_control["name"] != "BTNPROPLAYOUT":
            raise NativeVendorDialogCaptureError("unexpected furnishing layout control")
    controls = r.vector(listing + 0x408, 128)
    list_selected = r.word(listing + 0x404)
    if list_selected and list_selected not in controls:
        raise NativeVendorDialogCaptureError("list selection is outside the owned controls")
    rows, entries = [], set()
    for control in controls:
        r.require(control, base + 0x116AEBC, "furnishing row control type")
        r.require(control + 0x3BC, hud, "furnishing row owner")
        r.require(control + 0x458, listing, "furnishing row list")
        entry = r.word(control + 0x44C)
        if entry in entries:
            raise NativeVendorDialogCaptureError("duplicate furnishing row entry")
        entries.add(entry)
        r.require(entry, base + FURNITURE_ENTRY_RVA, "furnishing entry type")
        r.require(entry + 8, 0x25, "furnishing entry kind")
        key = struct.unpack("<II", r.read(entry + 0x10, 8))
        source = _reference(r, entry + 0x20)
        furnishing_key = None
        # ArcDeed only. Native getter 0x5c2c50 copies this exact key; an unknown
        # source class remains diagnostic data, never an assumed deed layout.
        if source and source["class_rva"] == 0x1142468:
            key_id, key_type = struct.unpack("<II", r.read(source["address"] + 0x7B8, 8))
            furnishing_key = {"object_id": key_id, "object_type": key_type}
        rows.append({
            "control_address": control, "entry_address": entry,
            "control_name": _text(r, control + 0x164),
            "entry_key_raw": {"object_id": key[0], "object_type": key[1]},
            "selected": entry == selected,
            "source_reference": source, "furnishing_key_raw": furnishing_key,
            "model_reference": _reference(r, entry + 0x24),
        })
        if resource_entry_key is not None and key == resource_entry_key:
            resource_matches += 1
            rows[-1]["render_resources_raw"] = read_render_resources(
                r, rows[-1]["model_reference"],
            )
    if resource_entry_key is not None and resource_matches != 1:
        raise NativeVendorDialogCaptureError("expected one owned furnishing resource row")
    if selected and selected not in entries:
        raise NativeVendorDialogCaptureError("selected furnishing is outside the owned list")
    width, height = struct.unpack("<ii", r.read(hud + 0x630, 8))
    x, y = struct.unpack("<ff", r.read(hud + 0x638, 8))
    zoom = struct.unpack("<f", r.read(hud + 0x37C, 4))[0]
    if not all(math.isfinite(v) for v in (x, y, zoom)) or width < 0 or height < 0:
        raise NativeVendorDialogCaptureError("invalid furnishing layout measurements")
    structure = _reference(r, hud + 0x64C)
    result = {
        "schema_version": 1, "scope": "current_furnishing_hud_diagnostic",
        "process_id": memory.pid,
        "process_creation_filetime_utc": memory.process_creation_filetime_utc,
        "executable_sha256": memory.executable_sha256,
        "window_address": hud, "owner_address": manager,
        "selected_entry_address": selected, "rows": rows,
        "list_selected_control_address_raw": list_selected,
        "layout_control": layout_control,
        "layout_raw": {"width": width, "height": height, "x": x, "y": y, "zoom": zoom},
        "floor_index_raw": r.word(hud + 0x628),
        "structure_reference": structure,
        "occupancy_raw": _occupancy(r, structure),
        # A scene entry is not the selected deed and is not placement confirmation.
        "scene_selection_address_raw": r.word(hud + 0x508),
        "preview_pose_verified": False, "render_lifetime_owned": False,
        "placement_confirmed": False, "command_admitted": False,
    }
    r.verify()
    return result
