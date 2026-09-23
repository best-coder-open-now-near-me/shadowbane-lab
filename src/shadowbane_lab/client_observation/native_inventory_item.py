"""Bounded InstanceInfo decoding for native crafting deposit confirmations.

Layout inspected in the same exact x86 client builds as native_crafting:
InstanceInfo constructor RVA 0x26DFF0; reader RVA 0x273070; effect reader 0x14F5B0.
Ownership and consistency belong to the caller; this decoder does not scan memory.
"""

from __future__ import annotations

import math
import struct
from typing import Protocol

from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCaptureError,
)

INSTANCE_INFO_VTABLE_RVA = 0x114BB68
INSTANCE_INFO_BYTES = 0xF8
MAX_DEPOSIT_EFFECTS = 64


class InventoryInstanceMemory(Protocol):
    base_address: int

    def read_block(self, address: int, size: int) -> bytes: ...


def _read(backend: InventoryInstanceMemory, address: int, size: int) -> bytes:
    if address < 0x10000 or address + size > 0x80000000 or size <= 0:
        raise NativeVendorDialogCaptureError("invalid inventory instance read bounds")
    raw = backend.read_block(address, size)
    if len(raw) != size:
        raise NativeVendorDialogCaptureError("short inventory instance read")
    return raw


def decode_inventory_instance(
    backend: InventoryInstanceMemory, address: int
) -> dict[str, object]:
    """Read identity and effects from a caller-owned, consistency-checked instance.

    A deposit event provides server-reported content, not proof the client has
    processed it into the current vendor inventory. Callers must reconcile that
    transition separately. Effects have no inferred tier or prefix/suffix role.
    """
    raw = _read(backend, address, INSTANCE_INFO_BYTES)

    def word(offset: int) -> int:
        return struct.unpack_from("<I", raw, offset)[0]

    def reference(offset: int) -> dict[str, int]:
        return {"object_id": word(offset), "object_type": word(offset + 4)}

    if word(0) != backend.base_address + INSTANCE_INFO_VTABLE_RVA:
        raise NativeVendorDialogCaptureError("inventory instance vtable mismatch")
    if word(0x14) != 0 or word(0x1C) != 40 or not word(0x10) or not word(0x18):
        raise NativeVendorDialogCaptureError("deposit does not describe a concrete item")
    for flag in (8, 9):
        if raw[flag] not in (0, 1):
            raise NativeVendorDialogCaptureError("invalid inventory instance presence flag")
    begin, end, capacity = (word(offset) for offset in (0xD4, 0xD8, 0xDC))
    name = ""
    if (begin, end, capacity) != (0, 0, 0):
        if not 0x10000 <= begin <= end <= capacity < 0x80000000:
            raise NativeVendorDialogCaptureError("invalid inventory name bounds")
        if (end - begin) % 2 or end - begin > 8192:
            raise NativeVendorDialogCaptureError("invalid inventory name length")
        if end != begin:
            try:
                name = _read(backend, begin, end - begin).decode("utf-16-le")
            except UnicodeDecodeError as exc:
                raise NativeVendorDialogCaptureError("invalid inventory name UTF-16") from exc
    result: dict[str, object] = {
        "template": reference(0x10),
        "item": reference(0x18),
        "name": name,
        "has_item_data": bool(raw[9]),
    }
    if raw[8]:
        full, current = struct.unpack_from("<ff", raw, 0x60)
        if not math.isfinite(full) or not math.isfinite(current):
            raise NativeVendorDialogCaptureError("nonfinite inventory durability")
        result["durability"] = {"full": full, "current": current}
    if raw[9]:
        start, end, capacity = (word(offset) for offset in (0xB4, 0xB8, 0xBC))
        if (start, end, capacity) == (0, 0, 0):
            pointers = b""
        else:
            if (
                not 0x10000 <= start <= end <= capacity < 0x80000000
                or (end - start) % 4
                or end - start > MAX_DEPOSIT_EFFECTS * 4
            ):
                raise NativeVendorDialogCaptureError("invalid inventory effect collection")
            pointers = _read(backend, start, end - start) if start != end else b""
        effects = []
        for (pointer,) in struct.iter_unpack("<I", pointers):
            effect = _read(backend, pointer, 12)
            token, trains, source_type = struct.unpack("<III", effect)
            effects.append({"token": token, "trains": trains, "source_type": source_type})
        result.update(
            base_value=word(0x70),
            value=word(0x74),
            quantity_raw=word(0xF4),
            effects=effects,
        )
    return result
