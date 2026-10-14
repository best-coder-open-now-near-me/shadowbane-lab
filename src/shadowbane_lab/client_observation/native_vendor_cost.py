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
from .native_vendor_roster import _text


def _displayed_costs(r, base, hud):
    lists = []
    for child in r.vector(hud + 0x54, 512):
        r.require(child + 0x3BC, hud, "recipe cost child owner")
        if r.word(child) == base + 0x116ACF0 and _text(r, child + 0x164) == "ResourceCostList":
            lists.append(child)
    if len(lists) != 1:
        raise NativeVendorDialogCaptureError("one owned recipe resource cost list is required")
    listing, result = lists[0], {}
    for control in r.vector(listing + 0x408, 128):
        r.require(control, base + 0x116AEBC, "recipe resource control type")
        r.require(control + 0x3BC, hud, "recipe resource control owner")
        r.require(control + 0x458, listing, "recipe resource listing owner")
        entry = r.word(control + 0x44C)
        r.require(entry, base + 0x116F258, "recipe resource entry type")
        key, amount, label = r.word(entry + 0x20), r.word(entry + 0x48), _text(r, entry + 0x30)
        if not key or key in result or not label or not 0 < amount <= 2**31 - 1:
            raise NativeVendorDialogCaptureError("invalid or duplicate displayed recipe resource")
        result[key] = dict(label=label, amount=amount)
    return result


def random_cost(amount: int, markup: float, quantity: int = 1) -> int:
    """Mirror 640230/2df880: float32 multiplier, add 0.5, truncate.

    The client rounds the random markup first, then scales and rounds the
    resulting integer for the per-slot quantity. Fractions retain the exact
    float32 product used by the x87 path; combining the two multipliers changes
    the native result.
    Named production has a separate multiplier and is deliberately unavailable.
    """
    if (
        type(amount) is not int
        or not 0 < amount <= 2**31 - 1
        or not math.isfinite(markup)
        or not 0 <= markup <= 100
        or type(quantity) is not int
        or not 1 <= quantity <= 10
    ):
        raise NativeVendorDialogCaptureError("invalid random recipe cost")
    factor = struct.unpack("<f", struct.pack("<f", 1 + markup))[0]
    cost = int(Fraction(amount) * Fraction(factor) + Fraction(1, 2))
    if not 0 < cost <= 2**31 - 1:
        raise NativeVendorDialogCaptureError("random recipe cost exceeds gold bounds")
    cost *= quantity
    if cost > 2**31 - 1:
        raise NativeVendorDialogCaptureError("random recipe quantity cost exceeds gold bounds")
    return cost


def read_native_vendor_cost(memory):
    if memory.executable_sha256 not in (
        "366ea471a47bf6f6cdc1da91ea415f5b202d307e4ec6e8272b349f39e63d142a",
        "6bd0e391edc1c773b4c96d8a9801db45f96db9e34202afcfc8d383d4971fe5ad",
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
        or type(recipe["quantity"]) is not int
        or not 1 <= recipe["quantity"] <= 10
        or recipe["template"] is None
        or recipe["prefix_selection_raw"] != recipe["suffix_selection_raw"]
        or recipe["prefix_selection_raw"] != recipe["random_sentinel_raw"]
    ):
        raise NativeVendorDialogCaptureError(
            "an owned random recipe quantity from 1 to 10 is required")
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
        costs[key] = random_cost(amount, markup, recipe["quantity"])
        previous, node = node, r.word(node)
    r.require(head + 4, previous, "recipe requirement tail")
    if not costs:
        raise NativeVendorDialogCaptureError("recipe resource costs are unavailable")
    displayed = _displayed_costs(r, memory.base_address, hud)
    if costs != {key: row["amount"] for key, row in displayed.items()}:
        raise NativeVendorDialogCaptureError(
            "displayed recipe costs disagree with native requirements")
    queue["recipe_resource_costs"] = {str(key): row for key, row in displayed.items()}
    r.verify()
    return queue, costs
