"""Strict, transport-independent decoding of Shadowbane vendor wire messages.

The caller is responsible for obtaining plaintext bytes.  This module deliberately
does not know about packet capture, session ciphers, process memory, or input.  That
keeps captured secrets out of the semantic observation boundary and makes the wire
format testable with sanitized payloads.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import IntEnum, StrEnum

VENDOR_DIALOG_OPCODE = 0x98ACD594
VENDOR_BUY_WINDOW_OPCODE = 0x682DAB4D
VENDOR_SELL_WINDOW_OPCODE = 0x267DAB90

_MAX_STRING_CODE_UNITS = 4_096
_MAX_MENU_ENTRIES = 128


class VendorWireFormatError(ValueError):
    """Raised when a plaintext vendor message violates the bounded wire grammar."""


class VendorWireOpcode(IntEnum):
    """Vendor-family opcodes verified against the emulator protocol catalog."""

    DIALOG = VENDOR_DIALOG_OPCODE
    BUY_WINDOW = VENDOR_BUY_WINDOW_OPCODE
    SELL_WINDOW = VENDOR_SELL_WINDOW_OPCODE


class VendorMenuAction(StrEnum):
    """Stable semantic actions represented by a vendor menu entry."""

    SELECT_DIALOG_OPTION = "vendor.select_dialog_option"
    OPEN_MERCHANT_OPTIONS = "vendor.open_merchant_options"
    CLOSE_DIALOG = "vendor.close_dialog"
    UNKNOWN = "vendor.unknown_option"


@dataclass(frozen=True, slots=True)
class VendorObjectReference:
    object_type: int
    object_id: int

    def to_dict(self) -> dict[str, int]:
        return {"object_type": self.object_type, "object_id": self.object_id}


@dataclass(frozen=True, slots=True)
class VendorDialogWireHeader:
    """Common request/reply fields, including still-opaque protocol values."""

    message_type: int
    language: str
    vendor: VendorObjectReference
    prefix_values: tuple[int, int, int]
    routing_values: tuple[int, int, int]
    routing_flags: tuple[int, int]
    message_values: tuple[int, int, int, int]
    object_marker: int
    object_token: int
    payload_marker: int


@dataclass(frozen=True, slots=True)
class VendorDialogRequest:
    """A client request to begin or continue a vendor dialog."""

    header: VendorDialogWireHeader
    trailing_bytes: bytes
    payload_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "vendor_dialog_request",
            "protocol_opcode": f"0x{VENDOR_DIALOG_OPCODE:08X}",
            "message_type": self.header.message_type,
            "language": self.header.language,
            "vendor": self.header.vendor.to_dict(),
            "object_token": self.header.object_token,
            "payload_sha256": self.payload_sha256,
        }


@dataclass(frozen=True, slots=True)
class VendorMenuOption:
    action_type: int
    label: str
    option_id: int | None
    semantic_action: VendorMenuAction
    marker_values: tuple[int, int, int]
    enabled_value: int
    trailing_values: tuple[int, int, int, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "action_type": self.action_type,
            "label": self.label,
            "option_id": self.option_id,
            "semantic_action": self.semantic_action.value,
        }


@dataclass(frozen=True, slots=True)
class VendorDialogMenu:
    """One fully decoded server-to-client vendor menu."""

    header: VendorDialogWireHeader
    dialog_resource: str
    dialog_type: str
    intro: str
    menu_type: int
    heading: str
    options: tuple[VendorMenuOption, ...]
    resource_values: tuple[int, int, int, int]
    resource_marker: int
    intro_marker: int
    trailing_values: tuple[int, int, int, int]
    payload_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "vendor_dialog_menu",
            "protocol_opcode": f"0x{VENDOR_DIALOG_OPCODE:08X}",
            "message_type": self.header.message_type,
            "language": self.header.language,
            "vendor": self.header.vendor.to_dict(),
            "object_token": self.header.object_token,
            "dialog_resource": self.dialog_resource,
            "dialog_type": self.dialog_type,
            "intro": self.intro,
            "menu_type": self.menu_type,
            "heading": self.heading,
            "options": [option.to_dict() for option in self.options],
            "payload_sha256": self.payload_sha256,
        }


VendorDialogWireMessage = VendorDialogRequest | VendorDialogMenu


class _Reader:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self.offset = 0

    @property
    def remaining(self) -> int:
        return len(self._payload) - self.offset

    def take(self, size: int, label: str) -> bytes:
        if size < 0 or self.remaining < size:
            raise VendorWireFormatError(f"{label} is truncated at byte offset {self.offset}")
        start = self.offset
        self.offset += size
        return self._payload[start : start + size]

    def u8(self, label: str) -> int:
        return self.take(1, label)[0]

    def u32(self, label: str) -> int:
        return int.from_bytes(self.take(4, label), "big")

    def string(self, label: str) -> str:
        code_units = self.u32(f"{label} length")
        if code_units > _MAX_STRING_CODE_UNITS:
            raise VendorWireFormatError(
                f"{label} length {code_units} exceeds {_MAX_STRING_CODE_UNITS} code units"
            )
        raw = self.take(code_units * 2, label)
        try:
            return raw.decode("utf-16-be")
        except UnicodeDecodeError as exc:
            raise VendorWireFormatError(f"{label} is not valid UTF-16BE") from exc


def vendor_wire_opcode(payload: bytes) -> VendorWireOpcode | None:
    """Classify a vendor-family payload without attempting body decoding."""

    if not isinstance(payload, bytes | bytearray | memoryview) or len(payload) < 4:
        return None
    value = int.from_bytes(bytes(payload[:4]), "big")
    try:
        return VendorWireOpcode(value)
    except ValueError:
        return None


def parse_vendor_dialog_wire(payload: bytes) -> VendorDialogWireMessage:
    """Decode one complete plaintext ``VENDORDIALOG`` request or menu reply."""

    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    reader = _Reader(payload)
    opcode = reader.u32("protocol opcode")
    if opcode != VENDOR_DIALOG_OPCODE:
        raise VendorWireFormatError(
            f"expected VENDORDIALOG opcode 0x{VENDOR_DIALOG_OPCODE:08X}, got 0x{opcode:08X}"
        )
    header = _parse_header(reader)
    digest = hashlib.sha256(payload).hexdigest()
    if header.message_type == 1:
        trailing = reader.take(reader.remaining, "request trailer")
        if len(trailing) != 6:
            raise VendorWireFormatError(
                f"vendor dialog request trailer must be 6 bytes, got {len(trailing)}"
            )
        return VendorDialogRequest(header, trailing, digest)
    if header.message_type != 3:
        raise VendorWireFormatError(f"unsupported VENDORDIALOG message type {header.message_type}")
    return _parse_menu(reader, header, digest)


def _parse_header(reader: _Reader) -> VendorDialogWireHeader:
    message_type = reader.u32("message type")
    prefix_values = tuple(reader.u32(f"prefix value {index}") for index in range(3))
    language = reader.string("language")
    vendor = VendorObjectReference(
        reader.u32("vendor object type"),
        reader.u32("vendor object id"),
    )
    routing_values = tuple(reader.u32(f"routing value {index}") for index in range(3))
    routing_flags = (
        reader.u8("routing flag 0"),
        reader.u8("routing flag 1"),
    )
    message_values = tuple(reader.u32(f"message value {index}") for index in range(4))
    return VendorDialogWireHeader(
        message_type=message_type,
        language=language,
        vendor=vendor,
        prefix_values=prefix_values,
        routing_values=routing_values,
        routing_flags=routing_flags,
        message_values=message_values,
        object_marker=reader.u8("object marker"),
        object_token=reader.u32("object token"),
        payload_marker=reader.u8("payload marker"),
    )


def _parse_menu(
    reader: _Reader,
    header: VendorDialogWireHeader,
    digest: str,
) -> VendorDialogMenu:
    dialog_resource = reader.string("dialog resource")
    resource_values = tuple(reader.u32(f"resource value {index}") for index in range(4))
    resource_marker = reader.u8("resource marker")
    dialog_type = reader.string("dialog type")
    intro = reader.string("dialog intro")
    intro_marker = reader.u8("dialog intro marker")
    menu_type = reader.u32("menu type")
    heading = reader.string("menu heading")
    entry_count = reader.u32("menu entry count")
    if entry_count > _MAX_MENU_ENTRIES:
        raise VendorWireFormatError(f"menu entry count {entry_count} exceeds {_MAX_MENU_ENTRIES}")
    options = tuple(_parse_option(reader, index) for index in range(entry_count))
    trailing_values = tuple(reader.u32(f"menu trailer {index}") for index in range(4))
    if reader.remaining:
        raise VendorWireFormatError(
            f"vendor dialog menu has {reader.remaining} unexpected trailing bytes"
        )
    return VendorDialogMenu(
        header=header,
        dialog_resource=dialog_resource,
        dialog_type=dialog_type,
        intro=intro,
        menu_type=menu_type,
        heading=heading,
        options=options,
        resource_values=resource_values,
        resource_marker=resource_marker,
        intro_marker=intro_marker,
        trailing_values=trailing_values,
        payload_sha256=digest,
    )


def _parse_option(reader: _Reader, index: int) -> VendorMenuOption:
    action_type = reader.u32(f"menu option {index} action type")
    marker_values = (
        reader.u8(f"menu option {index} marker 0"),
        reader.u32(f"menu option {index} marker value"),
        reader.u8(f"menu option {index} marker 1"),
    )
    enabled = reader.u32(f"menu option {index} enabled")
    label = reader.string(f"menu option {index} label")
    trailing_values = tuple(
        reader.u32(f"menu option {index} trailing value {value_index}") for value_index in range(4)
    )
    semantic_action = _semantic_action(action_type)
    option_id = None if semantic_action is VendorMenuAction.CLOSE_DIALOG else trailing_values[0]
    return VendorMenuOption(
        action_type=action_type,
        label=label,
        option_id=option_id,
        semantic_action=semantic_action,
        marker_values=marker_values,
        enabled_value=enabled,
        trailing_values=trailing_values,
    )


def _semantic_action(action_type: int) -> VendorMenuAction:
    if action_type == 16:
        return VendorMenuAction.OPEN_MERCHANT_OPTIONS
    if action_type == 14:
        return VendorMenuAction.SELECT_DIALOG_OPTION
    if action_type == 10:
        return VendorMenuAction.CLOSE_DIALOG
    return VendorMenuAction.UNKNOWN


__all__ = [
    "VENDOR_BUY_WINDOW_OPCODE",
    "VENDOR_DIALOG_OPCODE",
    "VENDOR_SELL_WINDOW_OPCODE",
    "VendorDialogMenu",
    "VendorDialogRequest",
    "VendorDialogWireHeader",
    "VendorDialogWireMessage",
    "VendorMenuAction",
    "VendorMenuOption",
    "VendorObjectReference",
    "VendorWireFormatError",
    "VendorWireOpcode",
    "parse_vendor_dialog_wire",
    "vendor_wire_opcode",
]
