"""Copy the owned recipe list for display; native selection retains action authority.

The external reader proves repeated-read consistency, not an atomic scene lease,
server freshness, crafting permission, or a complete server recipe catalog.
"""
from __future__ import annotations

import struct

from .native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from .native_vendor_queue import VendorQueueMemory, _ReadSet
from .native_vendor_roster import _text

EXACT_EXECUTABLE_SHA256 = "7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f"
# The .12 image changes only its version digit; see docs/client-update-20260926.md.
REVIEWED_RECIPE_EXECUTABLES = frozenset({
    EXACT_EXECUTABLE_SHA256,
    "2dc0e19c3fcf43bc19508939fb9c63982bc370a868f810208394324a12cdc289",
})
_PANEL_CLASSES = {0x1169EC0, 0x11657C8}
# The extra leaf is present in all three September 24 Balanced Dagger samples
# from the private recipe_controls tab-zero graph (snapshot 1790285225894507000).
# Its internals are not interpreted. Only qualified containers own +0x40.
_LEAF_CLASSES = {0x116ACF0, 0x116B138}
_MAX_GRAPH = 256
_MAX_ROWS = 256


def _identity(memory):
    values = (memory.pid, memory.process_creation_filetime_utc, memory.base_address,
              memory.executable_name, memory.executable_sha256, memory.pointer_size)
    pid, creation, base, name, digest, pointer_size = values
    if (type(pid) is not int or not 0 < pid < 2**32
            or type(creation) is not int or not 0 < creation < 2**64
            or type(base) is not int or not 0x10000 <= base < 0x80000000 or base % 4
            or not isinstance(name, str) or name.casefold() != "sb.exe"
            or digest not in REVIEWED_RECIPE_EXECUTABLES or type(pointer_size) is not int
            or pointer_size != 4):
        raise NativeVendorDialogCompatibilityError("unqualified recipe catalog build or lifetime")
    return values


def _key(r, address, kind, label):
    object_id, object_type = struct.unpack("<II", r.read(address, 8))
    if not object_id or object_type != kind:
        raise NativeVendorDialogCaptureError(f"invalid recipe catalog {label}")
    return {"object_id": object_id, "object_type": object_type}


def read_native_vendor_recipe_catalog(memory: VendorQueueMemory) -> dict[str, object]:
    """Read the active first recipe tab with exact typed identities and ownership.

    No process attachment, command channel, native call, or retry occurs here.
    The caller owns the read-only handle. A missing menu/list is unavailable,
    rather than an invented empty catalog; an owned empty list is reported as
    empty without claiming that the server offers no recipes.
    """
    identity = _identity(memory)
    r, base = _ReadSet(memory), memory.base_address
    root = r.word(base + 0x16A7BFC)
    r.require(root, base + 0x1174884, "recipe game window")
    r.require(root + 0x64, 2, "recipe in-world mode")
    manager = r.word(root + 0xA4)
    r.require(manager, base + 0x1171ADC, "recipe asset manager")
    r.require(manager + 0xD8, 0, "recipe online management")
    active = r.hud_stack(root)
    menu = r.word(manager + 0x78)
    r.require(menu, base + 0x116A058, "recipe vendor menu")
    r.require(menu + 0x104, manager, "recipe vendor menu owner")
    if menu not in active:
        raise NativeVendorDialogCaptureError("recipe vendor menu is not active")
    building = _key(r, manager + 0xF0, 8, "building")
    if _key(r, manager + 0xF8, 8, "selected building") != building:
        raise NativeVendorDialogCaptureError("recipe building selection changed")
    hireling = r.word(manager + 0x384)
    r.require(hireling, base + 0x1169518, "recipe hireling")
    vendor = _key(r, hireling + 0x10, 42, "vendor")
    candidates = [hud for hud in active if r.word(hud) == base + 0x116BF7C]
    if len(candidates) != 1:
        raise NativeVendorDialogCaptureError("expected exactly one active recipe window")
    recipe = candidates[0]
    r.require(recipe + 0x3B8, manager, "recipe manager owner")
    if _key(r, recipe + 0x3C0, 42, "recipe vendor") != vendor:
        raise NativeVendorDialogCaptureError("recipe vendor ownership mismatch")
    children = r.vector(recipe + 0x54, 512)
    for child in children:
        r.require(child + 0x3BC, recipe, "recipe child owner")
    pages = r.word(recipe + 0x518)
    if pages not in children:
        raise NativeVendorDialogCaptureError("recipe pages are detached")
    r.require(pages, base + 0x116B510, "recipe pages type")
    r.require(pages + 0x40C, 0, "active recipe tab")
    if _text(r, pages + 0x164) != "ItemCreationPages":
        raise NativeVendorDialogCaptureError("unknown recipe pages")
    tabs = r.vector(pages + 0x400, 8)
    if not tabs:
        raise NativeVendorDialogCaptureError("recipe tab zero is unavailable")
    panel = r.word(tabs[0] + 4)
    r.require(panel, base + 0x1169EC0, "recipe tab panel")
    r.require(panel + 0x3BC, recipe, "recipe panel owner")
    callback = r.word(tabs[0] + 0x50)
    for offset, wanted in ((0, base + 0x116C2C0), (4, recipe), (8, base + 0x238AD), (12, 0)):
        r.require(callback + offset, wanted, "recipe tab callback")
    nodes, pending = {panel}, [(panel, 0)]
    while pending:
        container, depth = pending.pop()
        descendants = r.vector(container + 0x40, _MAX_GRAPH)
        if descendants and depth >= 8:
            raise NativeVendorDialogCaptureError("recipe graph depth exceeds bound")
        for child in descendants:
            if child in nodes or len(nodes) >= _MAX_GRAPH:
                raise NativeVendorDialogCaptureError("recipe graph repeated node or bound exceeded")
            nodes.add(child)
            r.require(child + 0x3BC, recipe, "recipe graph owner")
            cls = r.word(child) - base
            if cls in _PANEL_CLASSES:
                pending.append((child, depth + 1))
            elif cls not in _LEAF_CLASSES:
                raise NativeVendorDialogCaptureError("unqualified recipe graph class")
    listing = r.word(recipe + 0x520)
    if listing not in nodes or listing == panel:
        raise NativeVendorDialogCaptureError("recipe list is detached from tab zero")
    r.require(listing, base + 0x116ACF0, "recipe list type")
    if _text(r, listing + 0x164) != "ITEMLIST":
        raise NativeVendorDialogCaptureError("unknown recipe list")
    rows = r.vector(listing + 0x408, _MAX_ROWS)
    selected_row = r.word(listing + 0x404)
    activated_entry = r.word(recipe + 0x45C)
    if selected_row and selected_row not in rows:
        raise NativeVendorDialogCaptureError("selected recipe row is detached")
    entries, keys, recipes = set(), set(), []
    selected, activated = None, None
    for row in rows:
        r.require(row, base + 0x116AEBC, "recipe row type")
        r.require(row + 0x3BC, recipe, "recipe row owner")
        r.require(row + 0x458, listing, "recipe row list")
        entry = r.word(row + 0x44C)
        r.require(entry, base + 0x116C2D0, "recipe entry type")
        template = _key(r, entry + 0x10, 0, "template")
        if entry in entries or template["object_id"] in keys:
            raise NativeVendorDialogCaptureError("duplicate recipe key or payload")
        entries.add(entry)
        keys.add(template["object_id"])
        item = dict(template=template, display_name=_text(r, entry + 0x20),
                    selected=row == selected_row, activated=entry == activated_entry)
        recipes.append(item)
        if item["selected"]:
            selected = template
        if item["activated"]:
            activated = template
    if activated_entry and activated_entry not in entries:
        raise NativeVendorDialogCaptureError("activated recipe payload is detached")
    retained_pointer = r.word(recipe + 0x408)
    retained = None
    if retained_pointer:
        r.require(retained_pointer, base + 0x1142748, "retained recipe type")
        retained = _key(r, retained_pointer + 0x10, 0, "retained template")
    if retained != activated:
        raise NativeVendorDialogCaptureError("activated and retained recipe disagree")
    sentinel, mode = r.word(recipe + 0x400), r.word(recipe + 0x404)
    prefix, suffix = r.word(recipe + 0x40C), r.word(recipe + 0x434)
    table, quantity = r.word(recipe + 0x47C), r.word(recipe + 0x4D4)
    multiple = r.read(recipe + 0x3D8, 4)[0]
    if sentinel != 3362971591 or mode > 2 or multiple > 1:
        raise NativeVendorDialogCaptureError("invalid observed recipe state")
    r.verify()
    if _identity(memory) != identity:
        raise NativeVendorDialogCaptureError("recipe catalog process identity changed")
    return dict(
        schema_version=1, scope="active_owned_recipe_tab_zero",
        process_id=identity[0], process_creation_filetime_utc=identity[1],
        executable_sha256=identity[4], root_address=root, manager_address=manager,
        menu_address=menu, hireling_address=hireling, recipe_address=recipe,
        pages_address=pages, panel_address=panel, list_address=listing,
        building=building, vendor=vendor, recipes=recipes, recipe_count=len(recipes),
        selected_template=selected, activated_template=activated, retained_template=retained,
        recipe_state=dict(mode=mode, table=table, sentinel=sentinel, prefix=prefix,
                          suffix=suffix, quantity=quantity, multiple=bool(multiple)),
        in_world=True, scene_epoch=None, scene_lifetime_verified=False,
        read_consistency_verified=True, cache_freshness_verified=False,
        complete_server_catalog_verified=False, command_admitted=False,
    )
