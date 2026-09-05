"""Versioned host-to-client commands for the injected WonderBane extension.

This transport is independent of the desktop-input subsystem. A command is accepted only after
injected code reports native-client submission; there is no keyboard, mouse, ``SendInput``, or
``PostMessage`` fallback.
"""

from __future__ import annotations

import ctypes
import itertools
import struct
import sys
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from enum import IntEnum
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from shadowbane_lab.protocol import DispatchResult

CLIENT_ACTION_CHANNEL_MAGIC = b"WBACTV1\0"
CLIENT_ACTION_CHANNEL_SCHEMA_VERSION = 1
CLIENT_ACTION_CHANNEL_HEADER_SIZE = 128
CLIENT_ACTION_COMMAND_SLOT_SIZE = 192
CLIENT_ACTION_COMMAND_CAPACITY = 32
CLIENT_ACTION_RESULT_SLOT_SIZE = 128
CLIENT_ACTION_RESULT_CAPACITY = 64
CLIENT_ACTION_PAYLOAD_VERSION = 1
CLIENT_ACTION_ARGUMENT_CAPACITY = 96
CLIENT_ACTION_POWER_IDENTIFIER_CAPACITY = 32
CLIENT_ACTION_RESULT_DETAIL_CAPACITY = 72
CLIENT_ACTION_COMMAND_RING_OFFSET = CLIENT_ACTION_CHANNEL_HEADER_SIZE
CLIENT_ACTION_RESULT_RING_OFFSET = (
    CLIENT_ACTION_COMMAND_RING_OFFSET
    + CLIENT_ACTION_COMMAND_SLOT_SIZE * CLIENT_ACTION_COMMAND_CAPACITY
)
CLIENT_ACTION_CHANNEL_SIZE = (
    CLIENT_ACTION_RESULT_RING_OFFSET
    + CLIENT_ACTION_RESULT_SLOT_SIZE * CLIENT_ACTION_RESULT_CAPACITY
)

CLIENT_ACTION_TRANSPORT_CAPABILITY = 1 << 0
NATIVE_ACTION_DISPATCH_CAPABILITY = 1 << 1
LEARNED_POWER_DISPATCH_CAPABILITY = 1 << 2
KNOWN_CLIENT_ACTION_CAPABILITIES = (
    CLIENT_ACTION_TRANSPORT_CAPABILITY
    | NATIVE_ACTION_DISPATCH_CAPABILITY
    | LEARNED_POWER_DISPATCH_CAPABILITY
)

_HEADER = struct.Struct("<8s8IQ6q2iq2i8s")
_COMMAND = struct.Struct("<qQIIQQiiiIII96s32s")
_RESULT = struct.Struct("<qQqIIQII72s8s")

if _HEADER.size != CLIENT_ACTION_CHANNEL_HEADER_SIZE:
    raise RuntimeError("native action header ABI size drifted")
if _COMMAND.size != CLIENT_ACTION_COMMAND_SLOT_SIZE:
    raise RuntimeError("native action command ABI size drifted")
if _RESULT.size != CLIENT_ACTION_RESULT_SLOT_SIZE:
    raise RuntimeError("native action result ABI size drifted")

_COMMAND_WRITE_SEQUENCE_OFFSET = 48
_COMMAND_READ_SEQUENCE_OFFSET = 56
_RESULT_WRITE_SEQUENCE_OFFSET = 64
_RESULT_READ_SEQUENCE_OFFSET = 72
_HOST_PROCESS_ID_OFFSET = 96
_HOST_LEASE_GENERATION_OFFSET = 100
_HOST_HEARTBEAT_TICK_OFFSET = 104

_FILE_MAP_WRITE = 0x0002
_FILE_MAP_READ = 0x0004
_EVENT_MODIFY_STATE = 0x0002
_SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0x00000000
_WAIT_TIMEOUT = 0x00000102


def _non_empty_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _ascii_text(
    value: str,
    field_name: str,
    *,
    capacity: int,
    allow_empty: bool,
) -> bytes:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ValueError(f"{field_name} must be a string")
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{field_name} must be ASCII") from exc
    if len(encoded) > capacity:
        raise ValueError(f"{field_name} exceeds its native ABI capacity")
    if any(byte < 0x20 or byte > 0x7E for byte in encoded):
        raise ValueError(f"{field_name} must contain printable ASCII")
    return encoded


class NativeActionChannelError(RuntimeError):
    """Base error for the injected-client action transport."""


class NativeActionChannelUnavailable(NativeActionChannelError):
    """Raised when the injected action channel cannot be opened or validated."""


class NativeActionChannelBusy(NativeActionChannelError):
    """Raised when another live host owns the single-producer lease."""


class NativeActionChannelFull(NativeActionChannelError):
    """Raised when the bounded command ring has no free slot."""


class NativeActionChannelTimeout(NativeActionChannelError):
    """Raised when the extension does not publish a completion result in time."""


class NativeActionCommandKind(IntEnum):
    NATIVE_ACTION = 1
    LEARNED_POWER = 2


class NativeActionResultStage(IntEnum):
    RECEIVED = 1
    RESOLVED = 2
    SUBMITTED_TO_CLIENT = 3
    REJECTED_BY_CLIENT = 4
    ACTION_QUEUE_OBSERVED = 5
    EFFECT_OBSERVED = 6
    FAILED = 7

    @property
    def terminal(self) -> bool:
        return self in {
            NativeActionResultStage.REJECTED_BY_CLIENT,
            NativeActionResultStage.EFFECT_OBSERVED,
            NativeActionResultStage.FAILED,
        }

    @property
    def accepted_submission(self) -> bool:
        return self in {
            NativeActionResultStage.SUBMITTED_TO_CLIENT,
            NativeActionResultStage.ACTION_QUEUE_OBSERVED,
            NativeActionResultStage.EFFECT_OBSERVED,
        }


@dataclass(frozen=True, slots=True)
class NativeClientProcessIdentity:
    process_id: int
    creation_filetime_utc: int

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.process_id, "process_id"),
            (self.creation_filetime_utc, "creation_filetime_utc"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")

    @property
    def mapping_name(self) -> str:
        return (
            "Local\\ShadowbaneLab.Extension.Actions."
            f"{self.process_id}.{self.creation_filetime_utc}"
        )

    @property
    def command_signal_name(self) -> str:
        return (
            "Local\\ShadowbaneLab.Extension.ActionCommand."
            f"{self.process_id}.{self.creation_filetime_utc}"
        )

    @property
    def result_signal_name(self) -> str:
        return (
            "Local\\ShadowbaneLab.Extension.ActionResult."
            f"{self.process_id}.{self.creation_filetime_utc}"
        )


@dataclass(frozen=True, slots=True)
class NativeActionDescriptor:
    action_code: int
    parameter_one: int = 0
    parameter_two: int = 0
    argument: str = ""
    evidence_source: str = ""

    def __post_init__(self) -> None:
        if (
            isinstance(self.action_code, bool)
            or not isinstance(self.action_code, int)
            or self.action_code <= 0
            or self.action_code >= 2**31
        ):
            raise ValueError("action_code must be a positive signed 32-bit integer")
        for value, field_name in (
            (self.parameter_one, "parameter_one"),
            (self.parameter_two, "parameter_two"),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{field_name} must be an integer")
            if not -(2**31) <= value < 2**31:
                raise ValueError(f"{field_name} must fit signed 32-bit")
        _ascii_text(
            self.argument,
            "argument",
            capacity=CLIENT_ACTION_ARGUMENT_CAPACITY,
            allow_empty=True,
        )
        _non_empty_text(self.evidence_source, "evidence_source")


@dataclass(frozen=True, slots=True)
class LearnedPowerDescriptor:
    power_identifier: str
    evidence_source: str

    def __post_init__(self) -> None:
        encoded = _ascii_text(
            self.power_identifier,
            "power_identifier",
            capacity=CLIENT_ACTION_POWER_IDENTIFIER_CAPACITY,
            allow_empty=False,
        )
        if any(
            not (byte == 45 or byte == 95 or 48 <= byte <= 57 or 65 <= byte <= 90)
            for byte in encoded
        ):
            raise ValueError(
                "power_identifier may contain only A-Z, 0-9, hyphen, and underscore"
            )
        _non_empty_text(self.evidence_source, "evidence_source")


NativeActionTarget = NativeActionDescriptor | LearnedPowerDescriptor


@dataclass(frozen=True, slots=True)
class NativeActionCommand:
    command_id: int
    target: NativeActionTarget

    def __post_init__(self) -> None:
        if (
            isinstance(self.command_id, bool)
            or not isinstance(self.command_id, int)
            or not 0 < self.command_id < 2**64
        ):
            raise ValueError("command_id must be an unsigned non-zero 64-bit integer")
        if not isinstance(self.target, (NativeActionDescriptor, LearnedPowerDescriptor)):
            raise ValueError("target must be a native action or learned-power descriptor")

    @property
    def kind(self) -> NativeActionCommandKind:
        if isinstance(self.target, NativeActionDescriptor):
            return NativeActionCommandKind.NATIVE_ACTION
        return NativeActionCommandKind.LEARNED_POWER

    @property
    def evidence_source(self) -> str:
        return self.target.evidence_source

    def encode_slot(
        self,
        *,
        sequence: int,
        created_tick: int,
        deadline_tick: int,
    ) -> bytes:
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
            raise ValueError("sequence must be a positive integer")
        if (
            isinstance(created_tick, bool)
            or not isinstance(created_tick, int)
            or created_tick <= 0
        ):
            raise ValueError("created_tick must be a positive integer")
        if (
            isinstance(deadline_tick, bool)
            or not isinstance(deadline_tick, int)
            or deadline_tick < created_tick
        ):
            raise ValueError("deadline_tick must be at least created_tick")

        action_code = 0
        parameter_one = 0
        parameter_two = 0
        argument = b""
        power_identifier = b""
        if isinstance(self.target, NativeActionDescriptor):
            action_code = self.target.action_code
            parameter_one = self.target.parameter_one
            parameter_two = self.target.parameter_two
            argument = self.target.argument.encode("ascii")
        else:
            power_identifier = self.target.power_identifier.encode("ascii")

        return _COMMAND.pack(
            0,
            self.command_id,
            int(self.kind),
            CLIENT_ACTION_PAYLOAD_VERSION,
            created_tick,
            deadline_tick,
            action_code,
            parameter_one,
            parameter_two,
            len(argument),
            len(power_identifier),
            0,
            argument.ljust(CLIENT_ACTION_ARGUMENT_CAPACITY, b"\0"),
            power_identifier.ljust(CLIENT_ACTION_POWER_IDENTIFIER_CAPACITY, b"\0"),
        )


@dataclass(frozen=True, slots=True)
class NativeActionResult:
    result_sequence: int
    command_id: int
    command_sequence: int
    stage: NativeActionResultStage
    error_code: int
    observed_tick: int
    consumer_thread_id: int
    detail: str

    @classmethod
    def decode_slot(cls, payload: bytes) -> NativeActionResult:
        if len(payload) != CLIENT_ACTION_RESULT_SLOT_SIZE:
            raise ValueError("result slot has the wrong size")
        (
            result_sequence,
            command_id,
            command_sequence,
            stage_value,
            error_code,
            observed_tick,
            consumer_thread_id,
            detail_length,
            detail_bytes,
            reserved,
        ) = _RESULT.unpack(payload)
        if result_sequence <= 0 or command_id <= 0 or command_sequence <= 0:
            raise NativeActionChannelError("result contains invalid sequence identity")
        try:
            stage = NativeActionResultStage(stage_value)
        except ValueError as exc:
            raise NativeActionChannelError("result contains an unknown stage") from exc
        if detail_length > CLIENT_ACTION_RESULT_DETAIL_CAPACITY:
            raise NativeActionChannelError("result detail length exceeds the ABI capacity")
        if any(reserved):
            raise NativeActionChannelError("result reserved bytes must be zero")
        try:
            detail = detail_bytes[:detail_length].decode("ascii")
        except UnicodeDecodeError as exc:
            raise NativeActionChannelError("result detail is not ASCII") from exc
        return cls(
            result_sequence=result_sequence,
            command_id=command_id,
            command_sequence=command_sequence,
            stage=stage,
            error_code=error_code,
            observed_tick=observed_tick,
            consumer_thread_id=consumer_thread_id,
            detail=detail,
        )


@dataclass(frozen=True, slots=True)
class NativeActionChannelHeader:
    process_identity: NativeClientProcessIdentity
    capability_flags: int

    @classmethod
    def decode(cls, payload: bytes) -> NativeActionChannelHeader:
        if len(payload) != CLIENT_ACTION_CHANNEL_HEADER_SIZE:
            raise NativeActionChannelUnavailable("native action channel header is truncated")
        values = _HEADER.unpack(payload)
        (
            magic,
            schema_version,
            header_size,
            command_slot_size,
            command_capacity,
            result_slot_size,
            result_capacity,
            process_id,
            capability_flags,
            creation_filetime_utc,
            *_rest,
        ) = values
        if magic != CLIENT_ACTION_CHANNEL_MAGIC:
            raise NativeActionChannelUnavailable("native action channel magic does not match")
        if schema_version != CLIENT_ACTION_CHANNEL_SCHEMA_VERSION:
            raise NativeActionChannelUnavailable("native action channel schema is unsupported")
        if (
            header_size != CLIENT_ACTION_CHANNEL_HEADER_SIZE
            or command_slot_size != CLIENT_ACTION_COMMAND_SLOT_SIZE
            or command_capacity != CLIENT_ACTION_COMMAND_CAPACITY
            or result_slot_size != CLIENT_ACTION_RESULT_SLOT_SIZE
            or result_capacity != CLIENT_ACTION_RESULT_CAPACITY
        ):
            raise NativeActionChannelUnavailable("native action channel geometry does not match")
        if capability_flags & ~KNOWN_CLIENT_ACTION_CAPABILITIES:
            raise NativeActionChannelUnavailable("native action channel has unknown capabilities")
        if not capability_flags & CLIENT_ACTION_TRANSPORT_CAPABILITY:
            raise NativeActionChannelUnavailable("native action transport capability is absent")
        return cls(
            NativeClientProcessIdentity(process_id, creation_filetime_utc),
            capability_flags,
        )


@runtime_checkable
class NativeActionCommandTransport(Protocol):
    def submit(
        self,
        command: NativeActionCommand,
        *,
        timeout_ms: int,
    ) -> NativeActionResult: ...


class _WindowsKernel:
    def __init__(self) -> None:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel = kernel
        handle = ctypes.c_void_p
        dword = ctypes.c_uint32
        bool_type = ctypes.c_int

        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, bool_type, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = handle
        kernel.ReleaseMutex.argtypes = [handle]
        kernel.ReleaseMutex.restype = bool_type

        kernel.OpenFileMappingW.argtypes = [dword, bool_type, ctypes.c_wchar_p]
        kernel.OpenFileMappingW.restype = handle
        kernel.MapViewOfFile.argtypes = [handle, dword, dword, dword, ctypes.c_size_t]
        kernel.MapViewOfFile.restype = handle
        kernel.OpenEventW.argtypes = [dword, bool_type, ctypes.c_wchar_p]
        kernel.OpenEventW.restype = handle
        kernel.SetEvent.argtypes = [handle]
        kernel.SetEvent.restype = bool_type
        kernel.WaitForSingleObject.argtypes = [handle, dword]
        kernel.WaitForSingleObject.restype = dword
        kernel.UnmapViewOfFile.argtypes = [handle]
        kernel.UnmapViewOfFile.restype = bool_type
        kernel.CloseHandle.argtypes = [handle]
        kernel.CloseHandle.restype = bool_type
        kernel.GetTickCount64.argtypes = []
        kernel.GetTickCount64.restype = ctypes.c_uint64
        kernel.GetCurrentProcessId.argtypes = []
        kernel.GetCurrentProcessId.restype = dword
        kernel.GetCurrentProcess.argtypes = []
        kernel.GetCurrentProcess.restype = handle
        kernel.GetProcessTimes.argtypes = [handle] + [ctypes.POINTER(ctypes.c_uint64)] * 4
        kernel.GetProcessTimes.restype = bool_type
        # Interlocked functions are compiler intrinsics, not kernel32 exports on
        # 64-bit Windows. Aligned scalar loads/stores are atomic there; explicit
        # Windows memory barriers provide publication ordering. RMW ownership is
        # provided separately by the named producer mutex, never by these stores.
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            raise NativeActionChannelUnavailable(
                "native action transport requires a 64-bit Python host"
            )
        kernel.FlushProcessWriteBuffers.argtypes = []
        kernel.FlushProcessWriteBuffers.restype = None

    @contextmanager
    def producer_lock(self, name: str, timeout_ms: int) -> Iterator[None]:
        handle = self._checked_handle(
            self._kernel.CreateMutexW(None, False, name), "CreateMutexW"
        )
        acquired = False
        try:
            result = self.wait(handle, timeout_ms)
            # Abandonment transfers ownership after a producer process crashes.
            acquired = result in {_WAIT_OBJECT_0, 0x80}
            if not acquired:
                raise NativeActionChannelBusy("native action producer transaction is busy")
            yield
        finally:
            if acquired:
                self._kernel.ReleaseMutex(ctypes.c_void_p(handle))
            self.close_handle(handle)

    def open_file_mapping(self, name: str) -> int:
        handle = self._kernel.OpenFileMappingW(
            _FILE_MAP_READ | _FILE_MAP_WRITE,
            False,
            name,
        )
        return self._checked_handle(handle, "OpenFileMappingW")

    def map_view(self, mapping: int, size: int) -> int:
        view = self._kernel.MapViewOfFile(
            ctypes.c_void_p(mapping),
            _FILE_MAP_READ | _FILE_MAP_WRITE,
            0,
            0,
            size,
        )
        return self._checked_handle(view, "MapViewOfFile")

    def open_event(self, name: str) -> int:
        handle = self._kernel.OpenEventW(
            _EVENT_MODIFY_STATE | _SYNCHRONIZE,
            False,
            name,
        )
        return self._checked_handle(handle, "OpenEventW")

    def set_event(self, handle: int) -> None:
        if not self._kernel.SetEvent(ctypes.c_void_p(handle)):
            self._raise_last_error("SetEvent")

    def wait(self, handle: int, timeout_ms: int) -> int:
        return int(
            self._kernel.WaitForSingleObject(
                ctypes.c_void_p(handle),
                ctypes.c_uint32(timeout_ms),
            )
        )

    def unmap_view(self, view: int) -> None:
        self._kernel.UnmapViewOfFile(ctypes.c_void_p(view))

    def close_handle(self, handle: int) -> None:
        self._kernel.CloseHandle(ctypes.c_void_p(handle))

    def tick_count(self) -> int:
        return int(self._kernel.GetTickCount64())

    def process_id(self) -> int:
        return int(self._kernel.GetCurrentProcessId())

    def process_identity(self) -> NativeClientProcessIdentity:
        creation, exit_time, kernel_time, user_time = (ctypes.c_uint64() for _ in range(4))
        if not self._kernel.GetProcessTimes(
            self._kernel.GetCurrentProcess(), ctypes.byref(creation),
            ctypes.byref(exit_time), ctypes.byref(kernel_time), ctypes.byref(user_time),
        ):
            self._raise_last_error("GetProcessTimes")
        return NativeClientProcessIdentity(self.process_id(), creation.value)

    def _load_scalar(self, address: int, scalar: type) -> int:
        if address % ctypes.sizeof(scalar):
            raise NativeActionChannelError("unaligned native action scalar")
        self._kernel.FlushProcessWriteBuffers()
        value = scalar.from_address(address).value
        self._kernel.FlushProcessWriteBuffers()
        return int(value)

    def _store_scalar(self, address: int, value: int, scalar: type) -> int:
        previous = self._load_scalar(address, scalar)
        self._kernel.FlushProcessWriteBuffers()
        scalar.from_address(address).value = value
        self._kernel.FlushProcessWriteBuffers()
        return previous

    def read_i64(self, address: int) -> int:
        return self._load_scalar(address, ctypes.c_int64)

    def exchange_i64(self, address: int, value: int) -> int:
        return self._store_scalar(address, value, ctypes.c_int64)

    def read_i32(self, address: int) -> int:
        return self._load_scalar(address, ctypes.c_int32)

    def exchange_i32(self, address: int, value: int) -> int:
        return self._store_scalar(address, value, ctypes.c_int32)

    @staticmethod
    def _checked_handle(value: object, operation: str) -> int:
        numeric = int(value) if value else 0
        if numeric == 0:
            _WindowsKernel._raise_last_error(operation)
        return numeric

    @staticmethod
    def _raise_last_error(operation: str) -> None:
        error = ctypes.get_last_error()
        raise NativeActionChannelUnavailable(f"{operation} failed with Win32 error {error}")


class WindowsNativeActionCommandTransport:
    """Single-producer Windows shared-memory transport into the injected extension."""

    def __init__(
        self,
        process_identity: NativeClientProcessIdentity,
        *,
        host_lease_timeout_ms: int = 1000,
    ) -> None:
        if not isinstance(process_identity, NativeClientProcessIdentity):
            raise ValueError("process_identity must be NativeClientProcessIdentity")
        if (
            isinstance(host_lease_timeout_ms, bool)
            or not isinstance(host_lease_timeout_ms, int)
            or host_lease_timeout_ms <= 0
        ):
            raise ValueError("host_lease_timeout_ms must be positive")
        if sys.platform != "win32":
            raise NativeActionChannelUnavailable(
                "the native action shared-memory transport requires Windows"
            )
        self._identity = process_identity
        self._host_lease_timeout_ms = host_lease_timeout_ms
        self._kernel = _WindowsKernel()
        self._mapping: int | None = None
        self._view: int | None = None
        self._command_signal: int | None = None
        self._result_signal: int | None = None
        self._lock = threading.Lock()
        self._lease_generation: int | None = None
        self._producer_lock_name = self._identity.mapping_name + ".Producer"
        self._open()

    @property
    def process_identity(self) -> NativeClientProcessIdentity:
        return self._identity

    @property
    def host_process_identity(self) -> NativeClientProcessIdentity:
        return self._kernel.process_identity()

    @property
    def host_lease_generation(self) -> int:
        if self._lease_generation is None:
            raise NativeActionChannelUnavailable("native action host lease is not owned")
        return self._lease_generation

    @property
    def header(self) -> NativeActionChannelHeader:
        view = self._require_view()
        header = NativeActionChannelHeader.decode(
            ctypes.string_at(view, CLIENT_ACTION_CHANNEL_HEADER_SIZE)
        )
        if header.process_identity != self._identity:
            raise NativeActionChannelUnavailable(
                "native action channel belongs to a different client instance"
            )
        return header

    def submit(
        self,
        command: NativeActionCommand,
        *,
        timeout_ms: int,
    ) -> NativeActionResult:
        if not isinstance(command, NativeActionCommand):
            raise ValueError("command must be NativeActionCommand")
        if (
            isinstance(timeout_ms, bool)
            or not isinstance(timeout_ms, int)
            or timeout_ms <= 0
        ):
            raise ValueError("timeout_ms must be positive")
        with self._lock, self._kernel.producer_lock(self._producer_lock_name, timeout_ms):
            self._renew_host_lease()
            write_sequence = self._read_i64(_COMMAND_WRITE_SEQUENCE_OFFSET)
            read_sequence = self._read_i64(_COMMAND_READ_SEQUENCE_OFFSET)
            if (
                write_sequence < 0
                or read_sequence < 0
                or read_sequence > write_sequence
                or write_sequence - read_sequence > CLIENT_ACTION_COMMAND_CAPACITY
            ):
                raise NativeActionChannelError("native action command sequences are invalid")
            if write_sequence - read_sequence >= CLIENT_ACTION_COMMAND_CAPACITY:
                raise NativeActionChannelFull("native action command ring is full")

            created_tick = self._kernel.tick_count()
            deadline_tick = created_tick + timeout_ms
            sequence = write_sequence + 1
            slot_offset = (
                CLIENT_ACTION_COMMAND_RING_OFFSET
                + (write_sequence % CLIENT_ACTION_COMMAND_CAPACITY)
                * CLIENT_ACTION_COMMAND_SLOT_SIZE
            )
            encoded = command.encode_slot(
                sequence=sequence,
                created_tick=created_tick,
                deadline_tick=deadline_tick,
            )
            view = self._require_view()
            self._exchange_i64(slot_offset, 0)
            ctypes.memmove(view + slot_offset, encoded, len(encoded))
            self._exchange_i64(slot_offset, sequence)
            self._exchange_i64(_COMMAND_WRITE_SEQUENCE_OFFSET, sequence)
            self._kernel.set_event(
                self._require_handle(self._command_signal, "command signal")
            )
            return self._wait_for_completion(
                command_id=command.command_id,
                command_sequence=sequence,
                deadline_tick=deadline_tick,
            )

    def close(self) -> None:
        with self._lock:
            if self._view is not None:
                try:
                    with self._kernel.producer_lock(
                        self._producer_lock_name, self._host_lease_timeout_ms
                    ):
                        if self._owns_host_lease():
                            self._exchange_i32(_HOST_PROCESS_ID_OFFSET, 0)
                            self._exchange_i64(_HOST_HEARTBEAT_TICK_OFFSET, 0)
                except NativeActionChannelError:
                    # Expiry recovers a lease if another producer transaction is busy.
                    pass
                self._kernel.unmap_view(self._view)
                self._view = None
            self._lease_generation = None
            for field_name in ("_result_signal", "_command_signal", "_mapping"):
                handle = getattr(self, field_name)
                if handle is not None:
                    self._kernel.close_handle(handle)
                    setattr(self, field_name, None)

    def __enter__(self) -> WindowsNativeActionCommandTransport:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _open(self) -> None:
        try:
            self._mapping = self._kernel.open_file_mapping(self._identity.mapping_name)
            self._view = self._kernel.map_view(
                self._mapping,
                CLIENT_ACTION_CHANNEL_SIZE,
            )
            self._command_signal = self._kernel.open_event(
                self._identity.command_signal_name
            )
            self._result_signal = self._kernel.open_event(
                self._identity.result_signal_name
            )
            _ = self.header
            self._claim_host_lease()
        except Exception:
            self.close()
            raise

    def _claim_host_lease(self) -> None:
        with self._kernel.producer_lock(
            self._producer_lock_name, self._host_lease_timeout_ms
        ):
            now = self._kernel.tick_count()
            existing_process_id = self._read_i32(_HOST_PROCESS_ID_OFFSET)
            heartbeat = self._read_i64(_HOST_HEARTBEAT_TICK_OFFSET)
            active = (
                existing_process_id > 0
                and heartbeat > 0
                and now >= heartbeat
                and now - heartbeat <= self._host_lease_timeout_ms
            )
            if active:
                raise NativeActionChannelBusy(
                    f"native action channel is leased by host process {existing_process_id}"
                )
            generation = self._read_i32(_HOST_LEASE_GENERATION_OFFSET)
            if generation < 0 or generation >= 2**31 - 1:
                raise NativeActionChannelUnavailable("native action host generation exhausted")
            # Publish PID last: the consumer cannot admit a partially claimed lease.
            self._exchange_i32(_HOST_PROCESS_ID_OFFSET, 0)
            self._exchange_i32(_HOST_LEASE_GENERATION_OFFSET, generation + 1)
            self._exchange_i64(_HOST_HEARTBEAT_TICK_OFFSET, now)
            self._exchange_i32(_HOST_PROCESS_ID_OFFSET, self._kernel.process_id())
            self._lease_generation = generation + 1

    def _owns_host_lease(self) -> bool:
        return (
            self._lease_generation is not None
            and self._read_i32(_HOST_PROCESS_ID_OFFSET) == self._kernel.process_id()
            and self._read_i32(_HOST_LEASE_GENERATION_OFFSET) == self._lease_generation
        )

    def _renew_host_lease(self) -> None:
        # Callers serialize the entire command publication/completion transaction.
        if not self._owns_host_lease():
            raise NativeActionChannelBusy("native action channel host lease was lost")
        self._exchange_i64(_HOST_HEARTBEAT_TICK_OFFSET, self._kernel.tick_count())

    def _wait_for_completion(
        self,
        *,
        command_id: int,
        command_sequence: int,
        deadline_tick: int,
    ) -> NativeActionResult:
        while True:
            result = self._take_matching_result(command_id, command_sequence)
            if result is not None and (
                result.stage.accepted_submission or result.stage.terminal
            ):
                return result
            now = self._kernel.tick_count()
            if now >= deadline_tick:
                raise NativeActionChannelTimeout(
                    f"native action command {command_id} did not complete before its deadline"
                )
            self._renew_host_lease()
            wait_result = self._kernel.wait(
                self._require_handle(self._result_signal, "result signal"),
                min(deadline_tick - now, 100),
            )
            if wait_result not in {_WAIT_OBJECT_0, _WAIT_TIMEOUT}:
                raise NativeActionChannelError(
                    f"native action result wait failed with code {wait_result}"
                )

    def _take_matching_result(
        self,
        command_id: int,
        command_sequence: int,
    ) -> NativeActionResult | None:
        write_sequence = self._read_i64(_RESULT_WRITE_SEQUENCE_OFFSET)
        read_sequence = self._read_i64(_RESULT_READ_SEQUENCE_OFFSET)
        if (
            write_sequence < 0
            or read_sequence < 0
            or read_sequence > write_sequence
            or write_sequence - read_sequence > CLIENT_ACTION_RESULT_CAPACITY
        ):
            raise NativeActionChannelError("native action result sequences are invalid")
        matched = None
        view = self._require_view()
        while read_sequence < write_sequence:
            expected_sequence = read_sequence + 1
            slot_offset = (
                CLIENT_ACTION_RESULT_RING_OFFSET
                + (read_sequence % CLIENT_ACTION_RESULT_CAPACITY)
                * CLIENT_ACTION_RESULT_SLOT_SIZE
            )
            if self._read_i64(slot_offset) != expected_sequence:
                break
            payload = ctypes.string_at(view + slot_offset, CLIENT_ACTION_RESULT_SLOT_SIZE)
            if self._read_i64(slot_offset) != expected_sequence:
                break
            result = NativeActionResult.decode_slot(payload)
            self._exchange_i64(_RESULT_READ_SEQUENCE_OFFSET, expected_sequence)
            read_sequence = expected_sequence
            if (
                result.command_id == command_id
                and result.command_sequence == command_sequence
            ):
                matched = result
                if result.stage.accepted_submission or result.stage.terminal:
                    break
        return matched

    def _require_view(self) -> int:
        if self._view is None:
            raise NativeActionChannelUnavailable("native action channel is closed")
        return self._view

    @staticmethod
    def _require_handle(handle: int | None, label: str) -> int:
        if handle is None:
            raise NativeActionChannelUnavailable(f"native action {label} is closed")
        return handle

    def _address(self, offset: int) -> int:
        return self._require_view() + offset

    def _read_i64(self, offset: int) -> int:
        return self._kernel.read_i64(self._address(offset))

    def _exchange_i64(self, offset: int, value: int) -> int:
        return self._kernel.exchange_i64(self._address(offset), value)

    def _read_i32(self, offset: int) -> int:
        return self._kernel.read_i32(self._address(offset))

    def _exchange_i32(self, offset: int, value: int) -> int:
        return self._kernel.exchange_i32(self._address(offset), value)


@dataclass(frozen=True, slots=True)
class NativeExtensionDispatchAudit:
    correlation_id: str
    action_key: str
    command_id: int | None
    command_kind: NativeActionCommandKind | None
    evidence_source: str | None
    accepted: bool
    result_stage: NativeActionResultStage | None = None
    error_code: int | None = None
    reason: str | None = None


DEFAULT_NATIVE_ACTIONS: Mapping[str, NativeActionTarget] = MappingProxyType(
    {
        "client.pve.target_next_mobile": NativeActionDescriptor(
            action_code=188,
            evidence_source="ArcanePref.cfg:Target Next Mob",
        ),
        "client.pve.target_previous_mobile": NativeActionDescriptor(
            action_code=189,
            evidence_source="ArcanePref.cfg:Target Previous Mob",
        ),
        "shadowbane.basic_attack": NativeActionDescriptor(
            action_code=1551,
            evidence_source="captured ArcanePref Ctrl+A action",
        ),
        "shadowbane.assassin.shadow_touch": LearnedPowerDescriptor(
            power_identifier="ASS-013",
            evidence_source="Arcane hotbar POWERNAME",
        ),
    }
)


class NativeExtensionActionDispatcher:
    """Map semantic actions to injected-client commands without desktop-input fallback."""

    def __init__(
        self,
        transport: NativeActionCommandTransport,
        *,
        actions: Mapping[str, NativeActionTarget] = DEFAULT_NATIVE_ACTIONS,
        timeout_ms: int = 1000,
    ) -> None:
        if not isinstance(transport, NativeActionCommandTransport):
            raise ValueError("transport must implement NativeActionCommandTransport")
        if not isinstance(actions, Mapping):
            raise ValueError("actions must be a mapping")
        if (
            isinstance(timeout_ms, bool)
            or not isinstance(timeout_ms, int)
            or timeout_ms <= 0
        ):
            raise ValueError("timeout_ms must be positive")
        normalized: dict[str, NativeActionTarget] = {}
        for action_key, target in actions.items():
            _non_empty_text(action_key, "action key")
            if not isinstance(target, (NativeActionDescriptor, LearnedPowerDescriptor)):
                raise ValueError("native action mapping values must be descriptors")
            normalized[action_key] = target
        self._transport = transport
        self._actions = MappingProxyType(normalized)
        self._timeout_ms = timeout_ms
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._audits: list[NativeExtensionDispatchAudit] = []

    @property
    def name(self) -> str:
        return "client-extension/native-action"

    @property
    def audits(self) -> tuple[NativeExtensionDispatchAudit, ...]:
        return tuple(self._audits)

    @property
    def actions(self) -> Mapping[str, NativeActionTarget]:
        return self._actions

    def dispatch_action(
        self,
        action_key: str,
        *,
        correlation_id: str,
    ) -> DispatchResult:
        _non_empty_text(action_key, "action_key")
        _non_empty_text(correlation_id, "correlation_id")
        target = self._actions.get(action_key)
        if target is None:
            return self._reject(
                correlation_id=correlation_id,
                action_key=action_key,
                command=None,
                result=None,
                reason="native_extension_action_unmapped",
            )
        with self._lock:
            command = NativeActionCommand(next(self._ids), target)
            try:
                result = self._transport.submit(command, timeout_ms=self._timeout_ms)
            except NativeActionChannelError as exc:
                return self._reject(
                    correlation_id=correlation_id,
                    action_key=action_key,
                    command=command,
                    result=None,
                    reason=f"native_extension_transport:{type(exc).__name__}:{exc}",
                )
            if not result.stage.accepted_submission:
                detail = result.detail or result.stage.name.lower()
                return self._reject(
                    correlation_id=correlation_id,
                    action_key=action_key,
                    command=command,
                    result=result,
                    reason=f"native_extension_{result.stage.name.lower()}:{detail}",
                )
            self._audits.append(
                NativeExtensionDispatchAudit(
                    correlation_id=correlation_id,
                    action_key=action_key,
                    command_id=command.command_id,
                    command_kind=command.kind,
                    evidence_source=command.evidence_source,
                    accepted=True,
                    result_stage=result.stage,
                    error_code=result.error_code,
                )
            )
            return DispatchResult(
                adapter_name=self.name,
                correlation_id=correlation_id,
                accepted=True,
            )

    def _reject(
        self,
        *,
        correlation_id: str,
        action_key: str,
        command: NativeActionCommand | None,
        result: NativeActionResult | None,
        reason: str,
    ) -> DispatchResult:
        self._audits.append(
            NativeExtensionDispatchAudit(
                correlation_id=correlation_id,
                action_key=action_key,
                command_id=None if command is None else command.command_id,
                command_kind=None if command is None else command.kind,
                evidence_source=None if command is None else command.evidence_source,
                accepted=False,
                result_stage=None if result is None else result.stage,
                error_code=None if result is None else result.error_code,
                reason=reason,
            )
        )
        return DispatchResult(
            adapter_name=self.name,
            correlation_id=correlation_id,
            accepted=False,
            reason=reason,
        )
