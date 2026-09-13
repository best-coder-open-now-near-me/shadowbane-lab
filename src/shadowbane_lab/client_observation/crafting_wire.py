"""Source-pinned ITEMPRODUCTION observations; no live dispatch authority.

Grammar: MagicBane Server 7c3a3fb84c55c1efaa615f4ef2711173629a27c8,
ItemProductionMsg, ProductionActionType, and ByteBufferUtils. WonderBane
compatibility must be established separately with a build-bound capture.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from enum import IntEnum

from shadowbane_lab.client_observation.vendor_wire import VendorWireFormatError, _Reader

ITEM_PRODUCTION_OPCODE = 0x3CCE8E30
CRAFTING_SOURCE_REVISION = "7c3a3fb84c55c1efaa615f4ef2711173629a27c8"
MAX_CRAFTING_PAYLOAD_BYTES = 65_536


class ProductionAction(IntEnum):
    NONE = 0
    PRODUCE = 1
    JUNK = 2
    RECYCLE = 3
    COMPLETE = 4
    SETPRICE = 5
    DEPOSIT = 6
    TAKE = 7
    CONFIRM_PRODUCE = 8
    CONFIRM_SETPRICE = 9
    CONFIRM_DEPOSIT = 10
    CONFIRM_TAKE = 11


@dataclass(frozen=True, slots=True)
class CraftingMessage:
    """Lossless supported message fields, scoped to a building and vendor.

    Object IDs and effect tokens retain their unsigned wire bit patterns. Virtual
    item IDs may represent negative Java ints; never substitute a template ID for
    one when completing/junking a roll. Opaque fields carry no inferred authority.
    """

    direction: str
    action: ProductionAction
    building_type: int
    building_id: int
    vendor_type: int
    vendor_id: int
    fields: tuple[tuple[str, int | str], ...]
    payload_sha256: str

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result.update(
            schema_version=1,
            protocol_opcode=f"0x{ITEM_PRODUCTION_OPCODE:08X}",
            source_revision=CRAFTING_SOURCE_REVISION,
            compatibility="upstream_source_only",
            action=self.action.name.lower(),
            action_id=int(self.action),
            fields=dict(self.fields),
        )
        return result


def parse_crafting_wire(payload: bytes, *, direction: str) -> CraftingMessage:
    """Decode one opcode-prefixed plaintext request or production update.

    Direction is mandatory: server serialization and request deserialization have
    different bodies. Unsupported variants and trailing bytes fail closed. This
    is an observation hook for capture consumers, not a packet sender or a queue
    snapshot. A CONFIRM_PRODUCE can describe an unfinished item.
    """
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    if direction not in ("client_to_server", "server_to_client"):
        raise ValueError("direction must be client_to_server or server_to_client")
    if len(payload) > MAX_CRAFTING_PAYLOAD_BYTES:
        raise VendorWireFormatError("crafting payload exceeds 65536 bytes")
    reader = _Reader(payload)
    if reader.u32("opcode") != ITEM_PRODUCTION_OPCODE:
        raise VendorWireFormatError("expected ITEMPRODUCTION opcode 0x3CCE8E30")
    try:
        action = ProductionAction(reader.u32("action"))
    except ValueError as exc:
        raise VendorWireFormatError("unknown production action") from exc
    header = [
        reader.u32(name) for name in ("building type", "building id", "vendor type", "vendor id")
    ]
    fields: dict[str, int | str] = {}

    def ints(*names: str) -> None:
        for name in names:
            fields[name] = reader.u32(name)

    if direction == "client_to_server":
        if action not in (
            ProductionAction.PRODUCE,
            ProductionAction.COMPLETE,
            ProductionAction.JUNK,
        ):
            raise VendorWireFormatError(f"unsupported crafting request: {action.name}")
        ints(
            "item_type",
            "item_or_template_id",
            "total_to_produce",
            "unknown03",
            "prefix_token",
            "suffix_token",
        )
        fields["name"] = reader.string("name")
        ints("size", "reserved")
        trailer_size = 2 if action == ProductionAction.PRODUCE else 1
        fields["trailer_hex"] = reader.take(trailer_size, "request trailer").hex()
    else:
        if action != ProductionAction.CONFIRM_PRODUCE:
            raise VendorWireFormatError(f"unsupported crafting update: {action.name}")
        ints(
            "reserved_item_type",
            "reserved_item_id",
            "count",
            "production_marker",
            "prefix_token",
            "suffix_token",
        )
        fields["name"] = reader.string("name")
        ints(
            "item_type",
            "item_id",
            "remaining_count",
            "template_id",
            "value",
            "seconds_remaining",
            "duration_seconds",
            "in_progress",
        )
        for name in ("reserved_flag", "complete_flag", "reserved_flag_2", "add_flag"):
            fields[name] = reader.u8(name)
        ints("strongbox_gold", "reserved_1", "reserved_2")
        if fields["in_progress"] not in (0, 1) or fields["complete_flag"] not in (0, 1):
            raise VendorWireFormatError("invalid crafting completion flags")
        if fields["in_progress"] == fields["complete_flag"]:
            raise VendorWireFormatError("conflicting crafting completion flags")
        if fields["complete_flag"] == 1 and fields["seconds_remaining"] != 0:
            raise VendorWireFormatError("completed crafting item has time remaining")
    if reader.remaining:
        raise VendorWireFormatError(f"crafting message has {reader.remaining} trailing bytes")
    return CraftingMessage(
        direction, action, *header, tuple(fields.items()), hashlib.sha256(payload).hexdigest()
    )
