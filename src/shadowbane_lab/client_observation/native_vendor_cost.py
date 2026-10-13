"""Read the owned random recipe's resource requirements without granting actions."""

from __future__ import annotations

import math
import struct
from fractions import Fraction

from .native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from .native_vendor_queue import _ReadSet, read_native_vendor_queue


def random_cost(amount: int, markup: float) -> int:
    """Mirror 640230/2df880: float32 multiplier, add 0.5, truncate.

    The client applies this once for random mode and again for quantity one.
    Fractions retain the exact float32 product used by the x87 path.
    Named production has a separate multiplier and is deliberately unavailable.
    """
    if (
        type(amount) is not int
        or not 0 < amount <= 2**31 - 1
        or not math.isfinite(markup)
        or not 0 <= markup <= 100
    ):
        raise NativeVendorDialogCaptureError("invalid random recipe cost")
    factor = struct.unpack("<f", struct.pack("<f", 1 + markup))[0]
    cost = int(Fraction(amount) * Fraction(factor) + Fraction(1, 2))
    if not 0 < cost <= 2**31 - 1:
        raise NativeVendorDialogCaptureError("random recipe cost exceeds gold bounds")
    return cost


def read_native_vendor_cost(memory):
    if memory.executable_sha256 != (
        "366ea471a47bf6f6cdc1da91ea415f5b202d307e4ec6e8272b349f39e63d142a"
    ):
        raise NativeVendorDialogCompatibilityError("unqualified recipe cost executable")
    r = _ReadSet(memory)

    class TrackedMemory:
        def __getattr__(self, name):
            return getattr(memory, name)

        def read_block(self, address, size):
            return r.read(address, size)

    queue = read_native_vendor_queue(TrackedMemory())
    recipe = queue["creation_recipe"]
    if (
        recipe is None
        or recipe["mode_raw"] != 1
        or recipe["quantity"] != 1
        or recipe["multiple_slots"]
        or recipe["template"] is None
        or recipe["prefix_selection_raw"] != recipe["suffix_selection_raw"]
        or recipe["prefix_selection_raw"] != recipe["random_sentinel_raw"]
    ):
        raise NativeVendorDialogCaptureError("an owned random single recipe is required")
    hud = recipe["window_address"]
    if r.read(hud + 0x540, 4)[1]:
        raise NativeVendorDialogCaptureError("named recipe funding is unavailable")
    markup = struct.unpack("<f", r.read(hud + 0x3DC, 4))[0]
    head = r.word(hud + 0x53C)
    node, previous, seen, costs = r.word(head), head, set(), {}
    while node != head:
        if node in seen or len(seen) >= 128:
            raise NativeVendorDialogCaptureError("invalid recipe requirement list")
        seen.add(node)
        r.require(node + 4, previous, "recipe requirement owner")
        key, amount = r.word(node + 8), r.word(node + 12)
        if not key or key in costs:
            raise NativeVendorDialogCaptureError("duplicate recipe resource")
        costs[key] = random_cost(amount, markup)
        previous, node = node, r.word(node)
    r.require(head + 4, previous, "recipe requirement tail")
    if not costs:
        raise NativeVendorDialogCaptureError("recipe resource costs are unavailable")
    r.verify()
    return queue, costs
