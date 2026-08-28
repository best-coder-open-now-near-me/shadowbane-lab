"""Build-locked, non-patching capture of native Shadowbane vendor-dialog messages."""

from __future__ import annotations

import ctypes
import json
import os
import struct
import time
from collections.abc import Mapping
from ctypes import wintypes
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

from shadowbane_lab.client_observation.native_health import (
    NativeMemoryRegion,
    WindowsReadOnlyProcessMemory,
)

NATIVE_VENDOR_DIALOG_PROFILE_SCHEMA_VERSION = 1
NATIVE_VENDOR_DIALOG_TRACE_SCHEMA_VERSION = 1
_BUNDLED_PROFILE_NAME = "wonderbane-ef43784b.native-vendor-dialog.json"

_REQUIRED_BREAKPOINT_ROLES = frozenset(
    {"inbound_entry", "inbound_complete", "outbound_entry", "outbound_complete"}
)
_ENTRY_ROLES = frozenset({"inbound_entry", "outbound_entry"})
_COMPLETE_ROLES = frozenset({"inbound_complete", "outbound_complete"})
_DIRECTIONS = {"inbound": "server_to_client", "outbound": "client_to_server"}

_EXCEPTION_DEBUG_EVENT = 1
_CREATE_THREAD_DEBUG_EVENT = 2
_CREATE_PROCESS_DEBUG_EVENT = 3
_EXIT_THREAD_DEBUG_EVENT = 4
_EXIT_PROCESS_DEBUG_EVENT = 5
_LOAD_DLL_DEBUG_EVENT = 6
_UNLOAD_DLL_DEBUG_EVENT = 7
_OUTPUT_DEBUG_STRING_EVENT = 8
_RIP_EVENT = 9
_EXCEPTION_BREAKPOINT = 0x80000003
_EXCEPTION_SINGLE_STEP = 0x80000004
_DBG_CONTINUE = 0x00010002
_DBG_EXCEPTION_NOT_HANDLED = 0x80010001
_ERROR_SEM_TIMEOUT = 121
_THREAD_GET_CONTEXT = 0x0008
_THREAD_SET_CONTEXT = 0x0010
_THREAD_QUERY_INFORMATION = 0x0040
_THREAD_SUSPEND_RESUME = 0x0002
_CONTEXT_i386 = 0x00010000
_CONTEXT_CONTROL = _CONTEXT_i386 | 0x00000001
_CONTEXT_INTEGER = _CONTEXT_i386 | 0x00000002
_CONTEXT_SEGMENTS = _CONTEXT_i386 | 0x00000004
_CONTEXT_DEBUG_REGISTERS = _CONTEXT_i386 | 0x00000010
_CONTEXT_FULL = _CONTEXT_CONTROL | _CONTEXT_INTEGER | _CONTEXT_SEGMENTS
_CONTEXT_TRACE = _CONTEXT_FULL | _CONTEXT_DEBUG_REGISTERS
_RESUME_FLAG = 0x00010000


class NativeVendorDialogError(RuntimeError):
    """Base error for native vendor-dialog diagnostics."""


class NativeVendorDialogCompatibilityError(NativeVendorDialogError):
    """Raised when the running client does not match the calibrated build."""


class NativeVendorDialogCaptureError(NativeVendorDialogError):
    """Raised when a debugger event or bounded memory capture fails."""


class NativeVendorDialogProfileLoadError(ValueError):
    """Raised when a native vendor-dialog profile is malformed."""


@dataclass(frozen=True, slots=True)
class NativeVendorDialogBreakpoint:
    role: str
    rva: int
    signature_hex: str

    def __post_init__(self) -> None:
        if self.role not in _REQUIRED_BREAKPOINT_ROLES:
            raise ValueError(f"unsupported vendor-dialog breakpoint role: {self.role}")
        if isinstance(self.rva, bool) or not isinstance(self.rva, int) or self.rva <= 0:
            raise ValueError("vendor-dialog breakpoint rva must be a positive integer")
        try:
            signature = bytes.fromhex(self.signature_hex)
        except ValueError as exc:
            raise ValueError("vendor-dialog breakpoint signature must be hexadecimal") from exc
        if not 4 <= len(signature) <= 32:
            raise ValueError("vendor-dialog breakpoint signatures must contain 4 to 32 bytes")

    @property
    def signature(self) -> bytes:
        return bytes.fromhex(self.signature_hex)


@dataclass(frozen=True, slots=True)
class NativeVendorDialogProfile:
    """Exact executable identity, message layout, and four hardware breakpoints."""

    profile_id: str
    executable_name: str
    executable_sha256: str
    pointer_size: int
    preferred_image_base: int
    message_vtable_rva: int
    message_object_size: int
    message_type_offset: int
    language_offset: int
    language_text_offset: int
    source_cache_id_offset: int
    vendor_cache_id_offset: int
    options_tree_offset: int
    options_count_offset: int
    string_begin_offset: int
    string_end_offset: int
    string_capacity_offset: int
    stream_snapshot_size: int
    pointer_window_size: int
    maximum_pointer_windows: int
    maximum_string_bytes: int
    maximum_option_count: int
    minimum_user_address: int
    maximum_user_address: int
    breakpoints: tuple[NativeVendorDialogBreakpoint, ...]
    schema_version: int = NATIVE_VENDOR_DIALOG_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, name in (
            (self.profile_id, "profile_id"),
            (self.executable_name, "executable_name"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        digest = self.executable_sha256.casefold()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("executable_sha256 must be a 64-character hexadecimal digest")
        if self.pointer_size != 4:
            raise ValueError("only the verified 32-bit vendor-dialog layout is supported")
        for name in (
            "preferred_image_base",
            "message_vtable_rva",
            "message_object_size",
            "message_type_offset",
            "language_offset",
            "language_text_offset",
            "source_cache_id_offset",
            "vendor_cache_id_offset",
            "options_tree_offset",
            "options_count_offset",
            "string_begin_offset",
            "string_end_offset",
            "string_capacity_offset",
            "stream_snapshot_size",
            "pointer_window_size",
            "maximum_pointer_windows",
            "maximum_string_bytes",
            "maximum_option_count",
            "minimum_user_address",
            "maximum_user_address",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.message_object_size > 4096:
            raise ValueError("message_object_size exceeds the bounded diagnostic limit")
        if self.stream_snapshot_size > 4096 or self.pointer_window_size > 4096:
            raise ValueError("stream capture bounds cannot exceed 4096 bytes")
        if self.maximum_pointer_windows > 64 or self.maximum_option_count > 4096:
            raise ValueError("vendor-dialog collection bounds exceed diagnostic limits")
        if self.maximum_string_bytes > 1_048_576 or self.maximum_string_bytes % 2:
            raise ValueError("maximum_string_bytes must be even and no larger than 1 MiB")
        if self.minimum_user_address < 0x10000:
            raise ValueError("minimum_user_address must exclude the null-allocation region")
        if self.maximum_user_address > 0xFFFFFFFF:
            raise ValueError("maximum_user_address must fit the 32-bit client")
        if self.maximum_user_address <= self.minimum_user_address:
            raise ValueError("maximum_user_address must exceed minimum_user_address")
        final_field = max(
            self.message_type_offset + 4,
            self.language_offset + 4,
            self.language_text_offset + self.string_capacity_offset + 4,
            self.source_cache_id_offset + 8,
            self.vendor_cache_id_offset + 8,
            self.options_tree_offset + 4,
            self.options_count_offset + 4,
        )
        if final_field > self.message_object_size:
            raise ValueError("vendor-dialog field offsets exceed message_object_size")
        roles = tuple(item.role for item in self.breakpoints)
        if len(roles) != len(set(roles)):
            raise ValueError("vendor-dialog breakpoint roles must be unique")
        if set(roles) != _REQUIRED_BREAKPOINT_ROLES:
            raise ValueError("vendor-dialog profile must define all four breakpoint roles")
        if len({item.rva for item in self.breakpoints}) != len(self.breakpoints):
            raise ValueError("vendor-dialog breakpoint addresses must be unique")
        if self.schema_version != NATIVE_VENDOR_DIALOG_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported native vendor-dialog profile version")


@dataclass(frozen=True, slots=True)
class NativeVendorDialogDebugHit:
    role: str
    process_id: int
    thread_id: int
    instruction_address: int
    registers: Mapping[str, int]


@runtime_checkable
class NativeVendorDialogDebugBackend(Protocol):
    pid: int
    executable_name: str
    executable_path: Path
    executable_sha256: str
    base_address: int
    pointer_size: int

    def read_block(self, address: int, size: int) -> bytes: ...

    def query_region(self, address: int) -> NativeMemoryRegion: ...

    def attach(self, breakpoints: Mapping[str, int]) -> None: ...

    def wait_for_hit(self, timeout_ms: int) -> NativeVendorDialogDebugHit | None: ...

    def continue_hit(self, hit: NativeVendorDialogDebugHit) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class NativeVendorDialogTraceSummary:
    profile_id: str
    process_id: int
    label: str
    output_path: Path
    hit_count: int
    complete_message_count: int
    timed_out_without_events: bool
    elapsed_seconds: float

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": True,
            "profile_id": self.profile_id,
            "process_id": self.process_id,
            "label": self.label,
            "output_path": str(self.output_path),
            "hit_count": self.hit_count,
            "complete_message_count": self.complete_message_count,
            "timed_out_without_events": self.timed_out_without_events,
            "elapsed_seconds": self.elapsed_seconds,
        }


@dataclass(frozen=True, slots=True)
class _MessageInvocation:
    message_address: int
    stream_address: int


class NativeVendorDialogTraceJournal:
    """Flushes each evidence record independently so partial sessions remain useful."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._stream: Any = None

    def __enter__(self) -> NativeVendorDialogTraceJournal:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.path.open("x", encoding="utf-8", newline="\n")
        return self

    def append(self, record: Mapping[str, object]) -> None:
        if self._stream is None:
            raise NativeVendorDialogCaptureError("vendor-dialog trace journal is not open")
        self._stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")))
        self._stream.write("\n")
        self._stream.flush()

    def __exit__(self, *_: object) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None


class NativeVendorDialogTracer:
    """Captures ArcMerchantMessage entry/completion pairs without altering client code."""

    def __init__(
        self,
        profile: NativeVendorDialogProfile,
        backend: NativeVendorDialogDebugBackend,
    ) -> None:
        if not isinstance(profile, NativeVendorDialogProfile):
            raise ValueError("profile must be NativeVendorDialogProfile")
        if not isinstance(backend, NativeVendorDialogDebugBackend):
            raise ValueError("backend must implement NativeVendorDialogDebugBackend")
        self.profile = profile
        self.backend = backend
        self._validate_compatibility()
        self._breakpoints = {
            item.role: backend.base_address + item.rva for item in profile.breakpoints
        }
        self._inflight: dict[tuple[str, int], _MessageInvocation] = {}

    def trace(
        self,
        output_path: Path,
        *,
        label: str,
        timeout_seconds: float,
        settle_seconds: float,
        armed_callback: Any | None = None,
    ) -> NativeVendorDialogTraceSummary:
        if not isinstance(label, str) or not label.strip():
            raise ValueError("trace label must be a non-empty string")
        for value, name in (
            (timeout_seconds, "timeout_seconds"),
            (settle_seconds, "settle_seconds"),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f"{name} must be positive")
        if settle_seconds >= timeout_seconds:
            raise ValueError("settle_seconds must be less than timeout_seconds")

        started = time.monotonic()
        deadline = started + float(timeout_seconds)
        last_hit_at: float | None = None
        hit_count = 0
        complete_count = 0
        sequence = 0
        self.backend.attach(self._breakpoints)
        try:
            with NativeVendorDialogTraceJournal(output_path) as journal:
                journal.append(
                    {
                        "schema_version": NATIVE_VENDOR_DIALOG_TRACE_SCHEMA_VERSION,
                        "record_type": "session_start",
                        "timestamp_utc": _utc_now(),
                        "label": label,
                        "profile_id": self.profile.profile_id,
                        "executable_name": self.backend.executable_name,
                        "executable_sha256": self.backend.executable_sha256,
                        "process_id": self.backend.pid,
                        "image_base": _hex32(self.backend.base_address),
                        "hardware_breakpoints": {
                            role: _hex32(address) for role, address in self._breakpoints.items()
                        },
                        "capture_method": "x86_hardware_execution_breakpoints",
                        "client_code_modified": False,
                    }
                )
                if armed_callback is not None:
                    armed_callback()
                while True:
                    now = time.monotonic()
                    if now >= deadline:
                        break
                    if last_hit_at is not None and now - last_hit_at >= settle_seconds:
                        break
                    remaining = deadline - now
                    if last_hit_at is not None:
                        remaining = min(remaining, settle_seconds - (now - last_hit_at))
                    wait_ms = max(1, min(250, int(remaining * 1000)))
                    hit = self.backend.wait_for_hit(wait_ms)
                    if hit is None:
                        continue
                    try:
                        sequence += 1
                        record = self._capture_hit(hit, sequence, label, started)
                        journal.append(record)
                        hit_count += 1
                        if hit.role in _COMPLETE_ROLES:
                            complete_count += 1
                        last_hit_at = time.monotonic()
                    finally:
                        self.backend.continue_hit(hit)
                elapsed = time.monotonic() - started
                journal.append(
                    {
                        "schema_version": NATIVE_VENDOR_DIALOG_TRACE_SCHEMA_VERSION,
                        "record_type": "session_end",
                        "timestamp_utc": _utc_now(),
                        "label": label,
                        "hit_count": hit_count,
                        "complete_message_count": complete_count,
                        "timed_out_without_events": hit_count == 0,
                        "elapsed_seconds": elapsed,
                    }
                )
        finally:
            self.backend.close()
        return NativeVendorDialogTraceSummary(
            profile_id=self.profile.profile_id,
            process_id=self.backend.pid,
            label=label,
            output_path=output_path,
            hit_count=hit_count,
            complete_message_count=complete_count,
            timed_out_without_events=hit_count == 0,
            elapsed_seconds=elapsed,
        )

    def _validate_compatibility(self) -> None:
        profile = self.profile
        backend = self.backend
        if backend.executable_name.casefold() != profile.executable_name.casefold():
            raise NativeVendorDialogCompatibilityError(
                f"expected {profile.executable_name}, found {backend.executable_name}"
            )
        if backend.executable_sha256.casefold() != profile.executable_sha256.casefold():
            raise NativeVendorDialogCompatibilityError(
                "running Shadowbane executable does not match the calibrated SHA-256"
            )
        if backend.pointer_size != profile.pointer_size:
            raise NativeVendorDialogCompatibilityError(
                "running Shadowbane pointer size does not match the calibrated profile"
            )
        if backend.base_address <= 0:
            raise NativeVendorDialogCompatibilityError("process image base is invalid")
        for breakpoint in profile.breakpoints:
            address = backend.base_address + breakpoint.rva
            try:
                actual = backend.read_block(address, len(breakpoint.signature))
            except Exception as exc:
                raise NativeVendorDialogCompatibilityError(
                    f"could not verify {breakpoint.role} code signature"
                ) from exc
            if actual != breakpoint.signature:
                raise NativeVendorDialogCompatibilityError(
                    f"{breakpoint.role} code signature does not match the calibrated build"
                )

    def _capture_hit(
        self,
        hit: NativeVendorDialogDebugHit,
        sequence: int,
        label: str,
        started: float,
    ) -> dict[str, object]:
        direction = hit.role.split("_", maxsplit=1)[0]
        phase = hit.role.split("_", maxsplit=1)[1]
        if hit.role == "inbound_entry":
            invocation = _MessageInvocation(
                message_address=hit.registers["ecx"],
                stream_address=self._read_stack_argument(hit.registers["esp"]),
            )
            self._inflight[(direction, hit.thread_id)] = invocation
        elif hit.role == "outbound_entry":
            invocation = _MessageInvocation(
                message_address=hit.registers["ecx"],
                stream_address=self._read_stack_argument(hit.registers["esp"]),
            )
            self._inflight[(direction, hit.thread_id)] = invocation
        elif hit.role == "outbound_complete":
            invocation = self._inflight.pop(
                (direction, hit.thread_id),
                _MessageInvocation(hit.registers["ebx"], hit.registers["esi"]),
            )
        else:
            invocation = self._inflight.pop((direction, hit.thread_id), None)
            if invocation is None:
                raise NativeVendorDialogCaptureError(
                    "inbound completion was observed without its entry breakpoint"
                )

        object_raw = self._read_exact(
            invocation.message_address,
            self.profile.message_object_size,
            "ArcMerchantMessage object",
        )
        decoded, decode_warnings = self._decode_message(invocation.message_address, object_raw)
        stream = self._capture_stream(invocation.stream_address)
        return {
            "schema_version": NATIVE_VENDOR_DIALOG_TRACE_SCHEMA_VERSION,
            "record_type": "vendor_dialog_hit",
            "sequence": sequence,
            "timestamp_utc": _utc_now(),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "label": label,
            "direction": _DIRECTIONS[direction],
            "phase": phase,
            "breakpoint_role": hit.role,
            "process_id": hit.process_id,
            "thread_id": hit.thread_id,
            "instruction_address": _hex32(hit.instruction_address),
            "message_address": _hex32(invocation.message_address),
            "stream_address": _hex32(invocation.stream_address),
            "registers": {name: _hex32(value) for name, value in hit.registers.items()},
            "decoded_message": decoded,
            "message_object_hex": object_raw.hex(),
            "stream_snapshot": stream,
            "decode_warnings": decode_warnings,
        }

    def _read_stack_argument(self, stack_pointer: int) -> int:
        raw = self._read_exact(stack_pointer + 4, 4, "ArcMerchantMessage stream argument")
        return struct.unpack("<I", raw)[0]

    def _decode_message(
        self,
        address: int,
        raw: bytes,
    ) -> tuple[dict[str, object], list[str]]:
        profile = self.profile
        warnings: list[str] = []
        vtable = struct.unpack_from("<I", raw, 0)[0]
        expected_vtable = self.backend.base_address + profile.message_vtable_rva
        if vtable != expected_vtable:
            warnings.append(
                f"ArcMerchantMessage vtable was {_hex32(vtable)}, "
                f"expected {_hex32(expected_vtable)}"
            )
        message_type = struct.unpack_from("<I", raw, profile.message_type_offset)[0]
        language = struct.unpack_from("<I", raw, profile.language_offset)[0]
        decoded: dict[str, object] = {
            "vtable": _hex32(vtable),
            "message_type": message_type,
            "message_type_semantics": _message_type_semantics(message_type),
            "language": language,
            "language_text": self._decode_arc_string(
                address + profile.language_text_offset,
                raw[profile.language_text_offset :],
                "language_text",
                warnings,
            ),
            "source_cache_id": _cache_id(
                raw, profile.source_cache_id_offset
            ),
            "vendor_cache_id": _cache_id(
                raw, profile.vendor_cache_id_offset
            ),
        }
        for name, offset in (
            ("type_2_text_a", 0x90),
            ("type_2_text_b", 0xA8),
            ("type_5_or_11_text", 0xC4),
        ):
            if offset + profile.string_capacity_offset + 4 <= len(raw):
                decoded[name] = self._decode_arc_string(
                    address + offset,
                    raw[offset:],
                    name,
                    warnings,
                )
        for name, offset in (
            ("field_0xC0", 0xC0),
            ("field_0xDC", 0xDC),
            ("field_0x100", 0x100),
            ("field_0x104", 0x104),
            ("field_0x110", 0x110),
        ):
            if offset + 4 <= len(raw):
                value = struct.unpack_from("<I", raw, offset)[0]
                decoded[name] = {"value": value, "hex": _hex32(value)}
        for name, offset in (
            ("field_0xE0_cache_id", 0xE0),
            ("field_0xF8_cache_id", 0xF8),
            ("field_0x108_cache_id", 0x108),
        ):
            if offset + 8 <= len(raw):
                decoded[name] = _cache_id(raw, offset)
        option_count = struct.unpack_from("<I", raw, profile.options_count_offset)[0]
        decoded["option_count"] = option_count
        if option_count > profile.maximum_option_count:
            warnings.append(
                f"option_count {option_count} exceeds calibrated maximum "
                f"{profile.maximum_option_count}"
            )
            decoded["options"] = []
        else:
            decoded["options"] = self._decode_options(raw, option_count, warnings)
        return decoded, warnings

    def _decode_arc_string(
        self,
        address: int,
        raw: bytes,
        label: str,
        warnings: list[str],
    ) -> dict[str, object]:
        profile = self.profile
        header_size = profile.string_capacity_offset + 4
        if len(raw) < header_size:
            warnings.append(f"{label} header is truncated")
            return {"text": None, "error": "truncated_header"}
        allocator = struct.unpack_from("<I", raw, 0)[0]
        begin = struct.unpack_from("<I", raw, profile.string_begin_offset)[0]
        end = struct.unpack_from("<I", raw, profile.string_end_offset)[0]
        capacity = struct.unpack_from("<I", raw, profile.string_capacity_offset)[0]
        result: dict[str, object] = {
            "address": _hex32(address),
            "allocator": _hex32(allocator),
            "begin": _hex32(begin),
            "end": _hex32(end),
            "capacity": _hex32(capacity),
        }
        if (begin, end, capacity) == (0, 0, 0):
            result["text"] = ""
            return result
        byte_count = end - begin
        if (
            begin < profile.minimum_user_address
            or end < begin
            or capacity < end + 2
            or capacity > profile.maximum_user_address
            or byte_count > profile.maximum_string_bytes
            or byte_count % 2
        ):
            warnings.append(f"{label} has invalid ArcString bounds")
            result["text"] = None
            result["error"] = "invalid_bounds"
            return result
        try:
            encoded = self._read_exact(begin, byte_count, label) if byte_count else b""
        except NativeVendorDialogCaptureError as exc:
            warnings.append(f"{label} could not be read: {exc}")
            result["text"] = None
            result["error"] = "unreadable"
            return result
        result["text"] = encoded.decode("utf-16-le", errors="replace")
        result["utf16le_hex"] = encoded.hex()
        return result

    def _decode_options(
        self,
        raw: bytes,
        option_count: int,
        warnings: list[str],
    ) -> list[dict[str, object]]:
        if option_count == 0:
            return []
        profile = self.profile
        header = struct.unpack_from("<I", raw, profile.options_tree_offset)[0]
        if not self._plausible_pointer(header, 16):
            warnings.append("options tree header is outside the calibrated user range")
            return []
        try:
            header_raw = self._read_exact(header, 16, "options tree header")
        except NativeVendorDialogCaptureError as exc:
            warnings.append(f"options tree header could not be read: {exc}")
            return []
        root = struct.unpack_from("<I", header_raw, 8)[0]
        stack: list[int] = []
        current = root
        seen: set[int] = set()
        options: list[dict[str, object]] = []
        while (current not in (0, header) or stack) and len(options) < option_count:
            while current not in (0, header):
                if current in seen:
                    warnings.append("options tree contains a pointer cycle")
                    return options
                if not self._plausible_pointer(current, 0x1C):
                    warnings.append("options tree node is outside the calibrated user range")
                    return options
                seen.add(current)
                stack.append(current)
                node = self._read_exact(current, 0x1C, "options tree node")
                current = struct.unpack_from("<I", node, 8)[0]
            if not stack:
                break
            node_address = stack.pop()
            node = self._read_exact(node_address, 0x1C, "options tree node")
            cache_type, cache_value, option_id = struct.unpack_from("<III", node, 0x10)
            options.append(
                {
                    "node_address": _hex32(node_address),
                    "text_cache_id": {
                        "type": cache_type,
                        "type_hex": _hex32(cache_type),
                        "value": cache_value,
                        "value_hex": _hex32(cache_value),
                        "raw_hex": node[0x10:0x18].hex(),
                    },
                    "option_id": option_id,
                    "option_id_hex": _hex32(option_id),
                }
            )
            current = struct.unpack_from("<I", node, 0x0C)[0]
        if len(options) != option_count:
            warnings.append(
                f"decoded {len(options)} option nodes but message reports {option_count}"
            )
        return options

    def _capture_stream(self, stream_address: int) -> dict[str, object]:
        profile = self.profile
        raw = self._read_exact(
            stream_address,
            profile.stream_snapshot_size,
            "message stream object",
        )
        windows: list[dict[str, object]] = []
        seen: set[int] = set()
        for offset in range(0, len(raw) - 3, profile.pointer_size):
            pointer = struct.unpack_from("<I", raw, offset)[0]
            if pointer in seen or not self._plausible_pointer(pointer, 1):
                continue
            seen.add(pointer)
            try:
                region = self.backend.query_region(pointer)
                available = region.base_address + region.size - pointer
                size = min(profile.pointer_window_size, available)
                if size <= 0:
                    continue
                value = self.backend.read_block(pointer, size)
            except Exception:
                continue
            windows.append(
                {
                    "stream_offset": _hex32(offset),
                    "pointer": _hex32(pointer),
                    "region_base": _hex32(region.base_address),
                    "region_size": region.size,
                    "region_protection": _hex32(region.protection),
                    "region_type": _hex32(region.memory_type),
                    "captured_size": len(value),
                    "hex": value.hex(),
                }
            )
            if len(windows) >= profile.maximum_pointer_windows:
                break
        return {
            "address": _hex32(stream_address),
            "size": len(raw),
            "hex": raw.hex(),
            "pointer_windows": windows,
        }

    def _read_exact(self, address: int, size: int, label: str) -> bytes:
        if not self._plausible_pointer(address, size):
            raise NativeVendorDialogCaptureError(
                f"{label} is outside the calibrated 32-bit user range"
            )
        try:
            value = self.backend.read_block(address, size)
        except Exception as exc:
            raise NativeVendorDialogCaptureError(
                f"could not read {label}: {type(exc).__name__}"
            ) from exc
        if len(value) != size:
            raise NativeVendorDialogCaptureError(f"native backend returned partial {label}")
        return value

    def _plausible_pointer(self, pointer: int, size: int) -> bool:
        profile = self.profile
        return (
            pointer >= profile.minimum_user_address
            and pointer + size <= profile.maximum_user_address
            and pointer % profile.pointer_size == 0
        )


class _FloatingSaveArea(ctypes.Structure):
    _fields_ = (
        ("ControlWord", wintypes.DWORD),
        ("StatusWord", wintypes.DWORD),
        ("TagWord", wintypes.DWORD),
        ("ErrorOffset", wintypes.DWORD),
        ("ErrorSelector", wintypes.DWORD),
        ("DataOffset", wintypes.DWORD),
        ("DataSelector", wintypes.DWORD),
        ("RegisterArea", wintypes.BYTE * 80),
        ("Cr0NpxState", wintypes.DWORD),
    )


class _X86Context(ctypes.Structure):
    _fields_ = (
        ("ContextFlags", wintypes.DWORD),
        ("Dr0", wintypes.DWORD),
        ("Dr1", wintypes.DWORD),
        ("Dr2", wintypes.DWORD),
        ("Dr3", wintypes.DWORD),
        ("Dr6", wintypes.DWORD),
        ("Dr7", wintypes.DWORD),
        ("FloatSave", _FloatingSaveArea),
        ("SegGs", wintypes.DWORD),
        ("SegFs", wintypes.DWORD),
        ("SegEs", wintypes.DWORD),
        ("SegDs", wintypes.DWORD),
        ("Edi", wintypes.DWORD),
        ("Esi", wintypes.DWORD),
        ("Ebx", wintypes.DWORD),
        ("Edx", wintypes.DWORD),
        ("Ecx", wintypes.DWORD),
        ("Eax", wintypes.DWORD),
        ("Ebp", wintypes.DWORD),
        ("Eip", wintypes.DWORD),
        ("SegCs", wintypes.DWORD),
        ("EFlags", wintypes.DWORD),
        ("Esp", wintypes.DWORD),
        ("SegSs", wintypes.DWORD),
        ("ExtendedRegisters", wintypes.BYTE * 512),
    )


class _ExceptionRecord(ctypes.Structure):
    pass


_ExceptionRecord._fields_ = (
    ("ExceptionCode", wintypes.DWORD),
    ("ExceptionFlags", wintypes.DWORD),
    ("ExceptionRecord", ctypes.POINTER(_ExceptionRecord)),
    ("ExceptionAddress", ctypes.c_void_p),
    ("NumberParameters", wintypes.DWORD),
    ("ExceptionInformation", ctypes.c_size_t * 15),
)


class _ExceptionDebugInfo(ctypes.Structure):
    _fields_ = (("ExceptionRecord", _ExceptionRecord), ("dwFirstChance", wintypes.DWORD))


class _CreateThreadDebugInfo(ctypes.Structure):
    _fields_ = (
        ("hThread", wintypes.HANDLE),
        ("lpThreadLocalBase", ctypes.c_void_p),
        ("lpStartAddress", ctypes.c_void_p),
    )


class _CreateProcessDebugInfo(ctypes.Structure):
    _fields_ = (
        ("hFile", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("lpBaseOfImage", ctypes.c_void_p),
        ("dwDebugInfoFileOffset", wintypes.DWORD),
        ("nDebugInfoSize", wintypes.DWORD),
        ("lpThreadLocalBase", ctypes.c_void_p),
        ("lpStartAddress", ctypes.c_void_p),
        ("lpImageName", ctypes.c_void_p),
        ("fUnicode", wintypes.WORD),
    )


class _ExitThreadDebugInfo(ctypes.Structure):
    _fields_ = (("dwExitCode", wintypes.DWORD),)


class _ExitProcessDebugInfo(ctypes.Structure):
    _fields_ = (("dwExitCode", wintypes.DWORD),)


class _LoadDllDebugInfo(ctypes.Structure):
    _fields_ = (
        ("hFile", wintypes.HANDLE),
        ("lpBaseOfDll", ctypes.c_void_p),
        ("dwDebugInfoFileOffset", wintypes.DWORD),
        ("nDebugInfoSize", wintypes.DWORD),
        ("lpImageName", ctypes.c_void_p),
        ("fUnicode", wintypes.WORD),
    )


class _UnloadDllDebugInfo(ctypes.Structure):
    _fields_ = (("lpBaseOfDll", ctypes.c_void_p),)


class _OutputDebugStringInfo(ctypes.Structure):
    _fields_ = (
        ("lpDebugStringData", ctypes.c_void_p),
        ("fUnicode", wintypes.WORD),
        ("nDebugStringLength", wintypes.WORD),
    )


class _RipInfo(ctypes.Structure):
    _fields_ = (("dwError", wintypes.DWORD), ("dwType", wintypes.DWORD))


class _DebugEventUnion(ctypes.Union):
    _fields_ = (
        ("Exception", _ExceptionDebugInfo),
        ("CreateThread", _CreateThreadDebugInfo),
        ("CreateProcessInfo", _CreateProcessDebugInfo),
        ("ExitThread", _ExitThreadDebugInfo),
        ("ExitProcess", _ExitProcessDebugInfo),
        ("LoadDll", _LoadDllDebugInfo),
        ("UnloadDll", _UnloadDllDebugInfo),
        ("DebugString", _OutputDebugStringInfo),
        ("RipInfo", _RipInfo),
    )


class _DebugEvent(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = (
        ("dwDebugEventCode", wintypes.DWORD),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
        ("u", _DebugEventUnion),
    )


class _WindowsVendorDialogDebugApi:
    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("native vendor-dialog tracing requires Windows")
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.DebugActiveProcess.argtypes = (wintypes.DWORD,)
        self.kernel32.DebugActiveProcess.restype = wintypes.BOOL
        self.kernel32.DebugActiveProcessStop.argtypes = (wintypes.DWORD,)
        self.kernel32.DebugActiveProcessStop.restype = wintypes.BOOL
        self.kernel32.DebugSetProcessKillOnExit.argtypes = (wintypes.BOOL,)
        self.kernel32.DebugSetProcessKillOnExit.restype = wintypes.BOOL
        self.kernel32.WaitForDebugEvent.argtypes = (
            ctypes.POINTER(_DebugEvent),
            wintypes.DWORD,
        )
        self.kernel32.WaitForDebugEvent.restype = wintypes.BOOL
        self.kernel32.ContinueDebugEvent.argtypes = (
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
        )
        self.kernel32.ContinueDebugEvent.restype = wintypes.BOOL
        self.kernel32.OpenThread.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        self.kernel32.OpenThread.restype = wintypes.HANDLE
        self.kernel32.SuspendThread.argtypes = (wintypes.HANDLE,)
        self.kernel32.SuspendThread.restype = wintypes.DWORD
        self.kernel32.ResumeThread.argtypes = (wintypes.HANDLE,)
        self.kernel32.ResumeThread.restype = wintypes.DWORD
        self.kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.kernel32.CloseHandle.restype = wintypes.BOOL
        self._is_64_bit_python = ctypes.sizeof(ctypes.c_void_p) == 8
        if self._is_64_bit_python:
            self._get_context = self.kernel32.Wow64GetThreadContext
            self._set_context = self.kernel32.Wow64SetThreadContext
        else:
            self._get_context = self.kernel32.GetThreadContext
            self._set_context = self.kernel32.SetThreadContext
        self._get_context.argtypes = (wintypes.HANDLE, ctypes.POINTER(_X86Context))
        self._get_context.restype = wintypes.BOOL
        self._set_context.argtypes = (wintypes.HANDLE, ctypes.POINTER(_X86Context))
        self._set_context.restype = wintypes.BOOL


class WindowsVendorDialogDebugBackend:
    """Win32 debugger backend using four per-thread x86 execution breakpoints."""

    pointer_size = 4

    def __init__(self, process: WindowsReadOnlyProcessMemory) -> None:
        self._process = process
        self._api = _WindowsVendorDialogDebugApi()
        self.pid = process.pid
        self.executable_name = process.executable_name
        self.executable_path = process.executable_path
        self.executable_sha256 = process.executable_sha256
        self.base_address = process.base_address
        self._breakpoints: dict[str, int] = {}
        self._roles_by_slot: tuple[str, ...] = ()
        self._attached = False
        self._closed = False
        self._pending: tuple[_DebugEvent, wintypes.HANDLE, _X86Context] | None = None
        self._thread_ids: set[int] = set()

    @classmethod
    def open_unique(
        cls,
        executable_name: str,
        *,
        process_id: int | None = None,
    ) -> WindowsVendorDialogDebugBackend:
        process = (
            WindowsReadOnlyProcessMemory.open_unique(executable_name)
            if process_id is None
            else WindowsReadOnlyProcessMemory.open_for_process(executable_name, process_id)
        )
        try:
            return cls(process)
        except Exception:
            process.close()
            raise

    def read_block(self, address: int, size: int) -> bytes:
        return self._process.read_block(address, size)

    def query_region(self, address: int) -> NativeMemoryRegion:
        return self._process.query_region(address)

    def attach(self, breakpoints: Mapping[str, int]) -> None:
        if self._closed:
            raise NativeVendorDialogCaptureError("vendor-dialog backend is closed")
        if self._attached:
            raise NativeVendorDialogCaptureError("vendor-dialog backend is already attached")
        if set(breakpoints) != _REQUIRED_BREAKPOINT_ROLES or len(breakpoints) != 4:
            raise NativeVendorDialogCaptureError(
                "exactly four vendor-dialog breakpoints are required"
            )
        self._roles_by_slot = tuple(
            role
            for role in (
                "inbound_entry",
                "inbound_complete",
                "outbound_entry",
                "outbound_complete",
            )
        )
        self._breakpoints = dict(breakpoints)
        if not self._api.kernel32.DebugActiveProcess(self.pid):
            raise NativeVendorDialogCaptureError(_windows_error("DebugActiveProcess failed"))
        self._attached = True
        if not self._api.kernel32.DebugSetProcessKillOnExit(False):
            try:
                self._api.kernel32.DebugActiveProcessStop(self.pid)
            finally:
                self._attached = False
            raise NativeVendorDialogCaptureError(
                _windows_error("DebugSetProcessKillOnExit failed")
            )

    def wait_for_hit(self, timeout_ms: int) -> NativeVendorDialogDebugHit | None:
        if not self._attached:
            raise NativeVendorDialogCaptureError("vendor-dialog debugger is not attached")
        if self._pending is not None:
            raise NativeVendorDialogCaptureError("previous vendor-dialog hit was not continued")
        if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or timeout_ms < 0:
            raise ValueError("timeout_ms must be a non-negative integer")
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            event = _DebugEvent()
            if not self._api.kernel32.WaitForDebugEvent(ctypes.byref(event), remaining_ms):
                error = ctypes.get_last_error()
                if error == _ERROR_SEM_TIMEOUT:
                    return None
                raise NativeVendorDialogCaptureError(_windows_error("WaitForDebugEvent failed"))
            status = _DBG_CONTINUE
            hit: NativeVendorDialogDebugHit | None = None
            code = int(event.dwDebugEventCode)
            if code == _CREATE_PROCESS_DEBUG_EVENT:
                info = event.CreateProcessInfo
                self._thread_ids.add(int(event.dwThreadId))
                try:
                    self._install_breakpoints(info.hThread)
                finally:
                    for handle in (info.hFile, info.hThread, info.hProcess):
                        if handle:
                            self._api.kernel32.CloseHandle(handle)
            elif code == _CREATE_THREAD_DEBUG_EVENT:
                handle = event.CreateThread.hThread
                self._thread_ids.add(int(event.dwThreadId))
                try:
                    self._install_breakpoints(handle)
                finally:
                    if handle:
                        self._api.kernel32.CloseHandle(handle)
            elif code == _LOAD_DLL_DEBUG_EVENT:
                handle = event.LoadDll.hFile
                if handle:
                    self._api.kernel32.CloseHandle(handle)
            elif code == _EXIT_THREAD_DEBUG_EVENT:
                self._thread_ids.discard(int(event.dwThreadId))
            elif code == _EXIT_PROCESS_DEBUG_EVENT:
                self._continue_event(event, _DBG_CONTINUE)
                self._attached = False
                raise NativeVendorDialogCaptureError(
                    f"{self.executable_name} exited during vendor-dialog tracing"
                )
            elif code == _EXCEPTION_DEBUG_EVENT:
                exception_code = int(event.Exception.ExceptionRecord.ExceptionCode)
                if exception_code == _EXCEPTION_SINGLE_STEP:
                    hit = self._hardware_hit(event)
                    if hit is None:
                        status = _DBG_EXCEPTION_NOT_HANDLED
                elif exception_code != _EXCEPTION_BREAKPOINT:
                    status = _DBG_EXCEPTION_NOT_HANDLED
            if hit is not None:
                return hit
            self._continue_event(event, status)
            if time.monotonic() >= deadline:
                return None

    def continue_hit(self, hit: NativeVendorDialogDebugHit) -> None:
        if self._pending is None:
            raise NativeVendorDialogCaptureError("no vendor-dialog debugger hit is pending")
        event, thread, context = self._pending
        if int(event.dwThreadId) != hit.thread_id:
            raise NativeVendorDialogCaptureError("pending debugger hit does not match the caller")
        try:
            context.EFlags = int(context.EFlags) | _RESUME_FLAG
            context.Dr6 = 0
            self._apply_breakpoint_registers(context)
            if not self._api._set_context(thread, ctypes.byref(context)):
                raise NativeVendorDialogCaptureError(
                    _windows_error("SetThreadContext failed while continuing vendor dialog")
                )
            self._continue_event(event, _DBG_CONTINUE)
        finally:
            self._api.kernel32.CloseHandle(thread)
            self._pending = None

    def close(self) -> None:
        if self._closed:
            return
        pending = self._pending
        if pending is not None:
            event, thread, context = pending
            try:
                context.EFlags = int(context.EFlags) | _RESUME_FLAG
                self._clear_breakpoint_registers(context)
                self._api._set_context(thread, ctypes.byref(context))
                self._continue_event(event, _DBG_CONTINUE)
            finally:
                self._api.kernel32.CloseHandle(thread)
                self._pending = None
        close_error: NativeVendorDialogCaptureError | None = None
        if self._attached:
            try:
                self._clear_breakpoints_from_threads()
            except NativeVendorDialogCaptureError as exc:
                close_error = exc
            if not self._api.kernel32.DebugActiveProcessStop(self.pid):
                close_error = NativeVendorDialogCaptureError(
                    _windows_error("DebugActiveProcessStop failed")
                )
            self._attached = False
        self._process.close()
        self._closed = True
        if close_error is not None:
            raise close_error

    def _install_breakpoints(self, thread: wintypes.HANDLE) -> None:
        context = self._get_context(thread)
        self._apply_breakpoint_registers(context)
        if not self._api._set_context(thread, ctypes.byref(context)):
            raise NativeVendorDialogCaptureError(
                _windows_error("SetThreadContext failed while arming vendor dialog")
            )

    def _hardware_hit(self, event: _DebugEvent) -> NativeVendorDialogDebugHit | None:
        access = _THREAD_GET_CONTEXT | _THREAD_SET_CONTEXT | _THREAD_QUERY_INFORMATION
        thread = self._api.kernel32.OpenThread(access, False, event.dwThreadId)
        if not thread:
            raise NativeVendorDialogCaptureError(_windows_error("OpenThread failed"))
        try:
            context = self._get_context(thread)
            triggered = [index for index in range(4) if int(context.Dr6) & (1 << index)]
            if not triggered:
                triggered = [
                    index
                    for index, role in enumerate(self._roles_by_slot)
                    if int(context.Eip) == self._breakpoints[role]
                ]
            if not triggered:
                self._api.kernel32.CloseHandle(thread)
                return None
            index = next(
                (
                    candidate
                    for candidate in triggered
                    if int(context.Eip)
                    == self._breakpoints[self._roles_by_slot[candidate]]
                ),
                triggered[0],
            )
            role = self._roles_by_slot[index]
            hit = NativeVendorDialogDebugHit(
                role=role,
                process_id=int(event.dwProcessId),
                thread_id=int(event.dwThreadId),
                instruction_address=int(context.Eip),
                registers={
                    "eax": int(context.Eax),
                    "ebx": int(context.Ebx),
                    "ecx": int(context.Ecx),
                    "edx": int(context.Edx),
                    "esi": int(context.Esi),
                    "edi": int(context.Edi),
                    "ebp": int(context.Ebp),
                    "esp": int(context.Esp),
                    "eip": int(context.Eip),
                    "eflags": int(context.EFlags),
                    "dr6": int(context.Dr6),
                    "dr7": int(context.Dr7),
                },
            )
            self._pending = (event, thread, context)
            return hit
        except Exception:
            if self._pending is None:
                self._api.kernel32.CloseHandle(thread)
            raise

    def _get_context(self, thread: wintypes.HANDLE) -> _X86Context:
        context = _X86Context()
        context.ContextFlags = _CONTEXT_TRACE
        if not self._api._get_context(thread, ctypes.byref(context)):
            raise NativeVendorDialogCaptureError(_windows_error("GetThreadContext failed"))
        return context

    def _apply_breakpoint_registers(self, context: _X86Context) -> None:
        addresses = [self._breakpoints[role] for role in self._roles_by_slot]
        context.Dr0, context.Dr1, context.Dr2, context.Dr3 = addresses
        context.Dr7 = 0x55

    @staticmethod
    def _clear_breakpoint_registers(context: _X86Context) -> None:
        context.Dr0 = 0
        context.Dr1 = 0
        context.Dr2 = 0
        context.Dr3 = 0
        context.Dr6 = 0
        context.Dr7 = 0

    def _clear_breakpoints_from_threads(self) -> None:
        access = (
            _THREAD_GET_CONTEXT
            | _THREAD_SET_CONTEXT
            | _THREAD_QUERY_INFORMATION
            | _THREAD_SUSPEND_RESUME
        )
        failures: list[int] = []
        for thread_id in tuple(self._thread_ids):
            handle = self._api.kernel32.OpenThread(access, False, thread_id)
            if not handle:
                continue
            suspended = self._api.kernel32.SuspendThread(handle)
            if suspended == 0xFFFFFFFF:
                self._api.kernel32.CloseHandle(handle)
                continue
            try:
                context = self._get_context(handle)
                self._clear_breakpoint_registers(context)
                if not self._api._set_context(handle, ctypes.byref(context)):
                    failures.append(thread_id)
            except NativeVendorDialogCaptureError:
                failures.append(thread_id)
            finally:
                self._api.kernel32.ResumeThread(handle)
                self._api.kernel32.CloseHandle(handle)
        if failures:
            joined = ", ".join(str(item) for item in failures)
            raise NativeVendorDialogCaptureError(
                f"could not clear hardware breakpoints from thread(s): {joined}"
            )

    def _continue_event(self, event: _DebugEvent, status: int) -> None:
        if not self._api.kernel32.ContinueDebugEvent(
            event.dwProcessId,
            event.dwThreadId,
            status,
        ):
            raise NativeVendorDialogCaptureError(_windows_error("ContinueDebugEvent failed"))


def load_bundled_native_vendor_dialog_profile() -> NativeVendorDialogProfile:
    resource = files("shadowbane_lab.client_observation").joinpath(
        "data", _BUNDLED_PROFILE_NAME
    )
    return load_native_vendor_dialog_profile_text(resource.read_text(encoding="utf-8"))


def load_native_vendor_dialog_profile(path: str | Path) -> NativeVendorDialogProfile:
    return load_native_vendor_dialog_profile_text(Path(path).read_text(encoding="utf-8"))


def load_native_vendor_dialog_profile_text(text: str) -> NativeVendorDialogProfile:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NativeVendorDialogProfileLoadError(
            "native vendor-dialog profile is not valid JSON"
        ) from exc
    try:
        data = _mapping(raw, "native vendor-dialog profile")
        expected = set(NativeVendorDialogProfile.__dataclass_fields__)
        missing = expected - set(data)
        unknown = set(data) - expected
        if missing:
            raise NativeVendorDialogProfileLoadError(
                f"missing required fields: {', '.join(sorted(missing))}"
            )
        if unknown:
            raise NativeVendorDialogProfileLoadError(
                f"unknown fields: {', '.join(sorted(unknown))}"
            )
        values: dict[str, object] = {}
        for key in expected:
            if key in {"profile_id", "executable_name", "executable_sha256"}:
                values[key] = _string(data, key)
            elif key == "breakpoints":
                items = data[key]
                if not isinstance(items, list):
                    raise NativeVendorDialogProfileLoadError("breakpoints must be an array")
                values[key] = tuple(_load_breakpoint(item) for item in items)
            else:
                values[key] = _integer(data, key)
        return NativeVendorDialogProfile(**values)
    except NativeVendorDialogProfileLoadError:
        raise
    except (TypeError, ValueError) as exc:
        raise NativeVendorDialogProfileLoadError(str(exc)) from exc


def open_windows_native_vendor_dialog_tracer(
    profile: NativeVendorDialogProfile,
    *,
    process_id: int | None = None,
) -> NativeVendorDialogTracer:
    backend = WindowsVendorDialogDebugBackend.open_unique(
        profile.executable_name,
        process_id=process_id,
    )
    try:
        return NativeVendorDialogTracer(profile, backend)
    except Exception:
        backend.close()
        raise


def _load_breakpoint(value: Any) -> NativeVendorDialogBreakpoint:
    data = _mapping(value, "vendor-dialog breakpoint")
    expected = {"role", "rva", "signature_hex"}
    if set(data) != expected:
        raise NativeVendorDialogProfileLoadError(
            "every vendor-dialog breakpoint requires role, rva, and signature_hex"
        )
    return NativeVendorDialogBreakpoint(
        role=_string(data, "role"),
        rva=_integer(data, "rva"),
        signature_hex=_string(data, "signature_hex"),
    )


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NativeVendorDialogProfileLoadError(f"{field_name} must be an object")
    return cast(Mapping[str, Any], value)


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise NativeVendorDialogProfileLoadError(f"{key} must be a non-empty string")
    return value


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise NativeVendorDialogProfileLoadError(f"{key} must be an integer")
    return value


def _cache_id(raw: bytes, offset: int) -> dict[str, object]:
    object_type, object_id = struct.unpack_from("<II", raw, offset)
    return {
        "object_type": object_type,
        "object_type_hex": _hex32(object_type),
        "object_id": object_id,
        "object_id_hex": _hex32(object_id),
        "raw_hex": raw[offset : offset + 8].hex(),
    }


def _message_type_semantics(message_type: int) -> str:
    return {
        1: "initial_request",
        3: "dialog_menu",
        4: "close_dialog",
    }.get(message_type, "special_case")


def _hex32(value: int) -> str:
    return f"0x{value & 0xFFFFFFFF:08X}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _windows_error(prefix: str) -> str:
    error = ctypes.get_last_error()
    return f"{prefix}: [WinError {error}] {ctypes.FormatError(error).strip()}"
