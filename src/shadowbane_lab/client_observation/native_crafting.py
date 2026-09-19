"""Build-locked ArcItemProductionMessage capture using hardware breakpoints.

This observes the client's serializer/deserializer. It neither creates crafting
requests nor treats local serialization as server acceptance.
"""

from __future__ import annotations

import json
import math
import struct
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from shadowbane_lab.client_observation.native_health import NativeTargetHealthReadError
from shadowbane_lab.client_observation.native_inventory_item import decode_inventory_instance
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
    NativeVendorDialogDebugBackend,
    WindowsVendorDialogDebugBackend,
)
from shadowbane_lab.equipment.crafting_assessment import assess_native_crafting_roll

# Exact inspected executables; do not broaden this through a layout alias.
CRAFTING_EXECUTABLE_HASHES = frozenset(
    {
        "55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc",
        "bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87",
        "b646ae32ebc44be45a7a65da3c764e1cd67f63f45fca91262b75f21fd11002f3",
        "e277e5a4e1e4e1df048a32c07bdbac6fec0591c7d01588b984577251cf475891",
    }
)
NATIVE_CRAFTING_SCHEMA_VERSION = 2
CRAFTING_VTABLE_RVA = 0x115BFD8
CRAFTING_OBJECT_BYTES = 0x120
CRAFTING_BREAKPOINTS = {
    "inbound_entry": (0x3FA240, bytes.fromhex("558bec6aff68073bd70064a100000000")),
    "inbound_complete": (0x3FA5B9, bytes.fromhex("8b4df45f5e64890d")),
    "outbound_entry": (0x3FA6C0, bytes.fromhex("558bec6aff68383bd70064a100000000")),
    "outbound_complete": (0x3FA91A, bytes.fromhex("8b4df45f5e5b64890d")),
}


def _exact(backend: NativeVendorDialogDebugBackend, address: int, size: int) -> bytes:
    if address < 0x10000 or address + size > 0x80000000:
        raise NativeVendorDialogCaptureError("crafting read is outside the client address space")
    raw = backend.read_block(address, size)
    if len(raw) != size:
        raise NativeVendorDialogCaptureError("short crafting memory read")
    return raw


def decode_crafting_object(
    backend: NativeVendorDialogDebugBackend, address: int
) -> dict[str, object]:
    """Decode only fields owned by this message variant while its thread is stopped."""
    raw = _exact(backend, address, CRAFTING_OBJECT_BYTES)

    def word(offset: int) -> int:
        return struct.unpack_from("<I", raw, offset)[0]

    def reference(offset: int) -> dict[str, int]:
        # ArcCacheID stores ID then type in memory; its wire serializer reverses them.
        return {"object_id": word(offset), "object_type": word(offset + 4)}

    if word(0) != backend.base_address + CRAFTING_VTABLE_RVA:
        raise NativeVendorDialogCaptureError("crafting message vtable mismatch")
    action = word(0x70)
    if action > 11:
        raise NativeVendorDialogCaptureError("unknown native crafting action")
    begin, end, capacity = word(0xE8), word(0xEC), word(0xF0)
    if begin == end == capacity == 0:
        name = ""
    else:
        if not 0x10000 <= begin <= end <= capacity < 0x80000000:
            raise NativeVendorDialogCaptureError("invalid crafting name pointers")
        if (end - begin) % 2 or end - begin > 8192:
            raise NativeVendorDialogCaptureError("invalid crafting name length")
        try:
            name = "" if begin == end else _exact(backend, begin, end - begin).decode("utf-16-le")
        except UnicodeDecodeError as exc:
            raise NativeVendorDialogCaptureError("invalid crafting UTF-16 name") from exc

    result: dict[str, object] = {
        "action_id": action,
        "building": reference(0x78),
        "vendor": reference(0x80),
        "item_or_template": reference(0x88),
        "quantity_raw": word(0x90),
        "production_marker_raw": word(0x94),
        "prefix_token": word(0x98),
        "suffix_token": word(0x9C),
        "name": name,
        "error_code": word(0xA0),
    }
    if action == 1:
        result["multiple_slot_request"] = raw[0x11D]
    if action == 8:
        result["roll"] = {
            "item": reference(0xC0),
            "template_id": word(0xC8),
            "remaining_count": word(0xCC),
            "value": word(0xD0),
            "seconds_remaining": word(0xD4),
            "duration_seconds": word(0xD8),
            "in_progress": word(0xDC),
            "reserved_flag": raw[0xE0],
            "complete_flag": raw[0xE1],
        }
    if action == 10:
        result["deposited_item"] = (
            decode_inventory_instance(backend, word(0x100)) if word(0x100) else None
        )
        result["strongbox_gold"] = word(0x10C)
    if raw[0x11C] == 1:
        result["strongbox_gold"] = word(0x10C)
    elif raw[0x11C] != 0:
        raise NativeVendorDialogCaptureError("invalid crafting strongbox flag")
    return result


def capture_crafting_callers(
    backend: NativeVendorDialogDebugBackend, registers: Mapping[str, int]
) -> dict[str, object]:
    """Capture return-address candidates at function entry, never stack arguments.

    Frame pointers are only diagnostic hints: optimized callers may omit them.
    Bound reads to 16 addresses and the first MiB above ESP; stop on malformed
    chains or unreadable memory without losing the crafting observation.
    """
    addresses: list[int] = []
    result: dict[str, object] = {
        "method": "x86_frame_pointer_candidates",
        "return_addresses": addresses,
    }

    def finish(reason: str) -> dict[str, object]:
        result["stop_reason"] = reason
        return result

    esp, frame = registers.get("esp"), registers.get("ebp")
    if type(esp) is not int or not 0x10000 <= esp <= 0x7FFFFFFC or esp % 4:
        return finish("invalid_stack_pointer")
    upper = min(esp + 0x100000, 0x80000000)
    try:
        caller = struct.unpack("<I", _exact(backend, esp, 4))[0]
        if not 0x10000 <= caller < 0x80000000:
            return finish("invalid_return_address")
        addresses.append(caller)
        previous = esp
        while len(addresses) < 16:
            if frame == 0:
                return finish("chain_end")
            if (
                type(frame) is not int
                or frame % 4
                or not previous + 4 <= frame <= upper - 8
            ):
                return finish("invalid_frame_pointer")
            next_frame, caller = struct.unpack("<II", _exact(backend, frame, 8))
            if not 0x10000 <= caller < 0x80000000:
                return finish("invalid_return_address")
            addresses.append(caller)
            previous, frame = frame, next_frame
        return finish("frame_limit")
    except (NativeTargetHealthReadError, NativeVendorDialogCaptureError, OSError):
        return finish("unreadable_stack")


class NativeCraftingTracer:
    """Own a bounded trace and deliver copied observations after resuming the client.

    Consumers must independently reconcile queue/inventory and server acceptance
    before issuing any follow-up action. Callback failure terminates capture and
    detaches; no callback executes while a debug event is suspended.
    """

    def __init__(self, backend: NativeVendorDialogDebugBackend) -> None:
        self.backend = backend

    def _validate(self) -> None:
        b = self.backend
        if b.executable_name.casefold() != "sb.exe" or b.pointer_size != 4:
            raise NativeVendorDialogCompatibilityError("crafting requires the inspected x86 sb.exe")
        if b.executable_sha256 not in CRAFTING_EXECUTABLE_HASHES:
            raise NativeVendorDialogCompatibilityError("unrecognized crafting executable SHA-256")
        if not isinstance(b.process_creation_filetime_utc, int) or (
            isinstance(b.process_creation_filetime_utc, bool)
            or b.process_creation_filetime_utc <= 0
        ):
            raise NativeVendorDialogCompatibilityError("crafting process lifetime is unavailable")
        for role, (rva, signature) in CRAFTING_BREAKPOINTS.items():
            if _exact(b, b.base_address + rva, len(signature)) != signature:
                raise NativeVendorDialogCompatibilityError(f"crafting signature mismatch: {role}")

    def trace(
        self,
        output: Path,
        *,
        timeout_seconds: float = 60,
        max_messages: int = 32,
        on_message: Callable[[dict[str, object]], None] | None = None,
        armed_callback: Callable[[], None] | None = None,
        capture_callers: bool = False,
    ) -> dict[str, object]:
        b = self.backend
        count = 0
        pending: dict[tuple[str, int], list[tuple[int, dict[str, object] | None]]] = {}
        try:
            if (
                isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, int | float)
                or not math.isfinite(timeout_seconds)
                or not 0 < timeout_seconds <= 300
            ):
                raise ValueError("timeout_seconds must be finite and within (0, 300]")
            if type(max_messages) is not int or not 1 <= max_messages <= 4096:
                raise ValueError("max_messages must be an integer in [1, 4096]")
            if type(capture_callers) is not bool:
                raise ValueError("capture_callers must be a boolean")
            self._validate()
            identity = {
                "process_id": b.pid,
                "process_creation_filetime_utc": b.process_creation_filetime_utc,
                "executable_sha256": b.executable_sha256,
                "image_base": b.base_address,
            }
            # Reserve the evidence file before attaching; never overwrite a capture.
            with output.open("x", encoding="utf-8") as journal:

                def emit(record: dict[str, object]) -> None:
                    journal.write(json.dumps(record, sort_keys=True) + "\n")
                    journal.flush()

                emit(
                    {
                        "schema_version": NATIVE_CRAFTING_SCHEMA_VERSION,
                        "record_type": "session_start",
                        "capture_callers": capture_callers,
                        **identity,
                    }
                )
                b.attach(
                    {
                        role: b.base_address + value[0]
                        for role, value in CRAFTING_BREAKPOINTS.items()
                    }
                )
                if armed_callback:
                    armed_callback()
                deadline = time.monotonic() + timeout_seconds
                try:
                    while time.monotonic() < deadline and count < max_messages:
                        hit = b.wait_for_hit(100)
                        if hit is None:
                            continue
                        record = None
                        try:
                            if hit.process_id != b.pid or hit.role not in CRAFTING_BREAKPOINTS:
                                raise NativeVendorDialogCaptureError("foreign crafting debug hit")
                            expected = b.base_address + CRAFTING_BREAKPOINTS[hit.role][0]
                            if hit.instruction_address != expected:
                                raise NativeVendorDialogCaptureError(
                                    "crafting hit address mismatch"
                                )
                            direction, phase = hit.role.split("_")
                            key = (direction, hit.thread_id)
                            stack = pending.setdefault(key, [])
                            if phase == "entry":
                                if len(stack) >= 16:
                                    raise NativeVendorDialogCaptureError(
                                        "crafting nesting exceeded"
                                    )
                                callers = (
                                    capture_crafting_callers(b, hit.registers)
                                    if capture_callers else None
                                )
                                stack.append((hit.registers["ecx"], callers))
                            else:
                                if not stack:
                                    raise NativeVendorDialogCaptureError(
                                        "crafting completion without entry"
                                    )
                                address, callers = stack.pop()
                                message = decode_crafting_object(b, address)
                                count += 1
                                record = {
                                    "schema_version": NATIVE_CRAFTING_SCHEMA_VERSION,
                                    "record_type": "crafting_message",
                                    **identity,
                                    "sequence": count,
                                    "thread_id": hit.thread_id,
                                    "direction": (
                                        "server_to_client"
                                        if direction == "inbound"
                                        else "client_to_server"
                                    ),
                                    "object_address": address,
                                    "observed_at_unix_ns": time.time_ns(),
                                    "message": message,
                                }
                                if callers is not None:
                                    record["callers"] = callers
                        finally:
                            b.continue_hit(hit)
                        if record is not None:
                            if (
                                record["direction"] == "server_to_client"
                                and record["message"]["action_id"] == 8
                            ):
                                record["roll_assessment"] = (
                                    assess_native_crafting_roll(record).to_dict()
                                )
                            emit(record)
                            if on_message:
                                on_message(record)
                    summary = {
                        "schema_version": NATIVE_CRAFTING_SCHEMA_VERSION,
                        "record_type": "session_end",
                        **identity,
                        "message_count": count,
                        "incomplete_invocations": sum(len(stack) for stack in pending.values()),
                        "timed_out_without_messages": count == 0,
                    }
                    emit(summary)
                    return summary
                except BaseException as exc:
                    emit(
                        {
                            "record_type": "session_error",
                            "error_type": type(exc).__name__,
                            "message_count": count,
                        }
                    )
                    raise
        finally:
            b.close()


def open_native_crafting_tracer(process_id: int) -> NativeCraftingTracer:
    """Select an explicit process; trace validation runs before any breakpoint is armed."""
    return NativeCraftingTracer(
        WindowsVendorDialogDebugBackend.open_unique("sb.exe", process_id=process_id)
    )
