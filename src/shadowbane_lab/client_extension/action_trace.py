"""Versioned passive call-entry traces for the native Shadowbane action probe.

The checked-in action-188 profile intentionally has no target or callsite RVA. The parser
therefore distinguishes an available trace transport from an armed native probe and never
interprets an empty channel as evidence that native dispatch was observed.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum, StrEnum

CLIENT_ACTION_TRACE_MAGIC = b"WBACTR1\0"
CLIENT_ACTION_TRACE_SCHEMA_VERSION = 1
CLIENT_ACTION_TRACE_HEADER_SIZE = 128
CLIENT_ACTION_TRACE_SLOT_SIZE = 192
CLIENT_ACTION_TRACE_CAPACITY = 256
CLIENT_ACTION_TRACE_ARGUMENT_CAPACITY = 32
CLIENT_ACTION_TRACE_STACK_CAPACITY = 8
CLIENT_ACTION_TRACE_SIZE = (
    CLIENT_ACTION_TRACE_HEADER_SIZE
    + CLIENT_ACTION_TRACE_SLOT_SIZE * CLIENT_ACTION_TRACE_CAPACITY
)

CLIENT_ACTION_TRACE_TRANSPORT_CAPABILITY = 1 << 0
CLIENT_ACTION_TRACE_CPU_CONTEXT_CAPABILITY = 1 << 1
CLIENT_ACTION_TRACE_STACK_CAPABILITY = 1 << 2
CLIENT_ACTION_TRACE_ARCANE_TUPLE_CAPABILITY = 1 << 3
CLIENT_ACTION_TRACE_CAPABILITIES = (
    CLIENT_ACTION_TRACE_TRANSPORT_CAPABILITY
    | CLIENT_ACTION_TRACE_CPU_CONTEXT_CAPABILITY
    | CLIENT_ACTION_TRACE_STACK_CAPABILITY
    | CLIENT_ACTION_TRACE_ARCANE_TUPLE_CAPABILITY
)

CLIENT_ACTION_TRACE_CONTEXT_COMPLETE_FLAG = 1 << 0
CLIENT_ACTION_TRACE_STACK_COMPLETE_FLAG = 1 << 1
CLIENT_ACTION_TRACE_TUPLE_COMPLETE_FLAG = 1 << 2
CLIENT_ACTION_TRACE_ARGUMENT_PRESENT_FLAG = 1 << 3
CLIENT_ACTION_TRACE_ACTION_188_CANDIDATE_FLAG = 1 << 4
CLIENT_ACTION_TRACE_KNOWN_FLAGS = (
    CLIENT_ACTION_TRACE_CONTEXT_COMPLETE_FLAG
    | CLIENT_ACTION_TRACE_STACK_COMPLETE_FLAG
    | CLIENT_ACTION_TRACE_TUPLE_COMPLETE_FLAG
    | CLIENT_ACTION_TRACE_ARGUMENT_PRESENT_FLAG
    | CLIENT_ACTION_TRACE_ACTION_188_CANDIDATE_FLAG
)

REVIEWED_WONDERBANE_PE_TIMESTAMP = 0x50A3A4E3
REVIEWED_WONDERBANE_IMAGE_SIZE = 0x0063D000
REVIEWED_WONDERBANE_PREFERRED_BASE = 0x00400000
TARGET_NEXT_MOB_ACTION_CODE = 188

_HEADER = struct.Struct("<8s6I6Q12I")
_SLOT = struct.Struct("<QIIQIiII8IIiiII32s8I36s")

if _HEADER.size != CLIENT_ACTION_TRACE_HEADER_SIZE:
    raise RuntimeError("native action trace header ABI size drifted")
if _SLOT.size != CLIENT_ACTION_TRACE_SLOT_SIZE:
    raise RuntimeError("native action trace slot ABI size drifted")


class ClientActionTraceError(ValueError):
    """Raised when a native action trace mapping violates its bounded ABI."""


class ClientActionTraceProbeStatus(IntEnum):
    UNCONFIGURED = 0
    PROFILE_REJECTED = 1
    ARMED = 2
    OBSERVING = 3
    FAILED = 4

    @property
    def label(self) -> str:
        return {
            ClientActionTraceProbeStatus.UNCONFIGURED: "unconfigured",
            ClientActionTraceProbeStatus.PROFILE_REJECTED: "profile_rejected",
            ClientActionTraceProbeStatus.ARMED: "armed",
            ClientActionTraceProbeStatus.OBSERVING: "observing",
            ClientActionTraceProbeStatus.FAILED: "failed",
        }[self]


class ClientActionTraceRecordKind(StrEnum):
    CALL_ENTRY = "call_entry"


@dataclass(frozen=True, slots=True)
class ClientActionTraceHeader:
    process_id: int
    capability_flags: int
    process_creation_filetime_utc: int
    qpc_frequency: int
    started_qpc: int
    write_sequence: int
    overwritten_record_count: int
    observed_record_count: int
    producer_error: int
    probe_status: ClientActionTraceProbeStatus
    target_action_code: int
    configured_target_rva: int
    configured_callsite_rva: int
    configured_stack_dword_count: int
    active_probe_count: int
    reviewed_pe_timestamp: int
    reviewed_image_size: int
    reviewed_preferred_base: int

    @property
    def configured(self) -> bool:
        return self.probe_status in {
            ClientActionTraceProbeStatus.ARMED,
            ClientActionTraceProbeStatus.OBSERVING,
        }

    @property
    def ready_for_capture(self) -> bool:
        return self.configured and self.active_probe_count == 1

    def ticks_to_milliseconds(self, ticks: int) -> float:
        if isinstance(ticks, bool) or not isinstance(ticks, int) or ticks < 0:
            raise ValueError("ticks must be a non-negative integer")
        return ticks * 1000.0 / self.qpc_frequency

    def as_dict(self) -> dict[str, object]:
        return {
            "process_id": self.process_id,
            "capability_flags": self.capability_flags,
            "process_creation_filetime_utc": self.process_creation_filetime_utc,
            "qpc_frequency": self.qpc_frequency,
            "started_qpc": self.started_qpc,
            "write_sequence": self.write_sequence,
            "overwritten_record_count": self.overwritten_record_count,
            "observed_record_count": self.observed_record_count,
            "producer_error": self.producer_error,
            "probe_status": self.probe_status.label,
            "target_action_code": self.target_action_code,
            "configured_target_rva": self.configured_target_rva,
            "configured_callsite_rva": self.configured_callsite_rva,
            "configured_stack_dword_count": self.configured_stack_dword_count,
            "active_probe_count": self.active_probe_count,
            "reviewed_pe_timestamp": self.reviewed_pe_timestamp,
            "reviewed_image_size": self.reviewed_image_size,
            "reviewed_preferred_base": self.reviewed_preferred_base,
            "ready_for_capture": self.ready_for_capture,
        }


@dataclass(frozen=True, slots=True)
class ClientActionTraceRecord:
    sequence: int
    kind: ClientActionTraceRecordKind
    flags: int
    observed_qpc: int
    thread_id: int
    action_code: int
    target_rva: int
    caller_rva: int
    eax: int
    ebx: int
    ecx: int
    edx: int
    esi: int
    edi: int
    ebp: int
    esp: int
    eflags: int
    parameter_one: int
    parameter_two: int
    argument: str
    stack_dwords: tuple[int, ...]

    @property
    def context_complete(self) -> bool:
        return bool(self.flags & CLIENT_ACTION_TRACE_CONTEXT_COMPLETE_FLAG)

    @property
    def tuple_complete(self) -> bool:
        return bool(self.flags & CLIENT_ACTION_TRACE_TUPLE_COMPLETE_FLAG)

    @property
    def action_188_candidate(self) -> bool:
        return bool(self.flags & CLIENT_ACTION_TRACE_ACTION_188_CANDIDATE_FLAG)

    def as_dict(self, header: ClientActionTraceHeader) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "kind": self.kind.value,
            "at_ms": header.ticks_to_milliseconds(
                self.observed_qpc - header.started_qpc
            ),
            "thread_id": self.thread_id,
            "action_code": self.action_code,
            "target_rva": self.target_rva,
            "caller_rva": self.caller_rva,
            "registers": {
                "eax": self.eax,
                "ebx": self.ebx,
                "ecx": self.ecx,
                "edx": self.edx,
                "esi": self.esi,
                "edi": self.edi,
                "ebp": self.ebp,
                "esp": self.esp,
                "eflags": self.eflags,
            },
            "arcane_tuple": (
                {
                    "action_code": self.action_code,
                    "parameter_one": self.parameter_one,
                    "parameter_two": self.parameter_two,
                    "argument": self.argument,
                }
                if self.tuple_complete
                else None
            ),
            "stack_dwords": list(self.stack_dwords),
            "context_complete": self.context_complete,
            "tuple_complete": self.tuple_complete,
            "action_188_candidate": self.action_188_candidate,
        }


@dataclass(frozen=True, slots=True)
class ClientActionTraceSnapshot:
    header: ClientActionTraceHeader
    records: tuple[ClientActionTraceRecord, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": CLIENT_ACTION_TRACE_SCHEMA_VERSION,
            "header": self.header.as_dict(),
            "records": [record.as_dict(self.header) for record in self.records],
        }


def client_action_trace_mapping_name(
    process_id: int,
    process_creation_filetime_utc: int,
) -> str:
    _bounded_positive(process_id, "process_id", 0xFFFFFFFF)
    _bounded_positive(
        process_creation_filetime_utc,
        "process_creation_filetime_utc",
        0xFFFFFFFFFFFFFFFF,
    )
    return (
        "Local\\ShadowbaneLab.Extension.ActionTrace."
        f"{process_id}.{process_creation_filetime_utc}"
    )


def client_action_trace_signal_name(
    process_id: int,
    process_creation_filetime_utc: int,
) -> str:
    _bounded_positive(process_id, "process_id", 0xFFFFFFFF)
    _bounded_positive(
        process_creation_filetime_utc,
        "process_creation_filetime_utc",
        0xFFFFFFFFFFFFFFFF,
    )
    return (
        "Local\\ShadowbaneLab.Extension.ActionTraceSignal."
        f"{process_id}.{process_creation_filetime_utc}"
    )


def parse_client_action_trace(
    payload: bytes | bytearray | memoryview,
    *,
    expected_process_id: int,
    expected_process_creation_filetime_utc: int,
) -> ClientActionTraceSnapshot:
    source = bytes(payload)
    if len(source) != CLIENT_ACTION_TRACE_SIZE:
        raise ClientActionTraceError("native action trace has an unexpected size")

    (
        magic,
        schema_version,
        header_size,
        slot_size,
        capacity,
        process_id,
        capability_flags,
        creation,
        qpc_frequency,
        started_qpc,
        write_sequence,
        overwritten_record_count,
        observed_record_count,
        producer_error,
        probe_status_value,
        target_action_code,
        configured_target_rva,
        configured_callsite_rva,
        configured_stack_dword_count,
        active_probe_count,
        reviewed_pe_timestamp,
        reviewed_image_size,
        reviewed_preferred_base,
        reserved0,
        reserved1,
    ) = _HEADER.unpack_from(source)

    if magic != CLIENT_ACTION_TRACE_MAGIC:
        raise ClientActionTraceError("native action trace magic is invalid")
    if (
        schema_version != CLIENT_ACTION_TRACE_SCHEMA_VERSION
        or header_size != CLIENT_ACTION_TRACE_HEADER_SIZE
        or slot_size != CLIENT_ACTION_TRACE_SLOT_SIZE
        or capacity != CLIENT_ACTION_TRACE_CAPACITY
    ):
        raise ClientActionTraceError("native action trace layout is unsupported")
    if (
        capability_flags != CLIENT_ACTION_TRACE_CAPABILITIES
        or not capability_flags & CLIENT_ACTION_TRACE_TRANSPORT_CAPABILITY
    ):
        raise ClientActionTraceError("native action trace capabilities are unsupported")
    if reserved0 != 0 or reserved1 != 0:
        raise ClientActionTraceError("native action trace reserved header fields are non-zero")
    if process_id != expected_process_id:
        raise ClientActionTraceError("native action trace belongs to another process")
    if creation != expected_process_creation_filetime_utc:
        raise ClientActionTraceError(
            "native action trace belongs to another process lifetime"
        )
    if process_id <= 0 or creation <= 0 or qpc_frequency <= 0 or started_qpc <= 0:
        raise ClientActionTraceError("native action trace identity or clock is invalid")
    if overwritten_record_count != max(
        0, write_sequence - CLIENT_ACTION_TRACE_CAPACITY
    ):
        raise ClientActionTraceError("native action trace overwrite count is inconsistent")
    if observed_record_count != write_sequence:
        raise ClientActionTraceError("native action trace observed count is inconsistent")
    try:
        probe_status = ClientActionTraceProbeStatus(probe_status_value)
    except ValueError as exc:
        raise ClientActionTraceError("native action trace probe status is unknown") from exc

    if target_action_code != TARGET_NEXT_MOB_ACTION_CODE:
        raise ClientActionTraceError("native action trace is not scoped to action 188")
    if (
        reviewed_pe_timestamp != REVIEWED_WONDERBANE_PE_TIMESTAMP
        or reviewed_image_size != REVIEWED_WONDERBANE_IMAGE_SIZE
        or reviewed_preferred_base != REVIEWED_WONDERBANE_PREFERRED_BASE
    ):
        raise ClientActionTraceError("native action trace build identity is unsupported")
    if configured_stack_dword_count > CLIENT_ACTION_TRACE_STACK_CAPACITY:
        raise ClientActionTraceError("configured native action stack capture is too large")
    if active_probe_count > 1:
        raise ClientActionTraceError("native action trace has an impossible probe count")

    if probe_status is ClientActionTraceProbeStatus.UNCONFIGURED:
        if any(
            (
                configured_target_rva,
                configured_callsite_rva,
                configured_stack_dword_count,
                active_probe_count,
            )
        ):
            raise ClientActionTraceError(
                "unconfigured native action trace exposes active profile fields"
            )
    elif probe_status in {
        ClientActionTraceProbeStatus.ARMED,
        ClientActionTraceProbeStatus.OBSERVING,
    }:
        if (
            configured_target_rva <= 0
            or configured_target_rva >= reviewed_image_size
            or configured_callsite_rva <= 0
            or configured_callsite_rva >= reviewed_image_size
            or active_probe_count != 1
        ):
            raise ClientActionTraceError("armed native action trace profile is incomplete")
    elif active_probe_count != 0:
        raise ClientActionTraceError("inactive native action trace reports an active probe")

    header = ClientActionTraceHeader(
        process_id=process_id,
        capability_flags=capability_flags,
        process_creation_filetime_utc=creation,
        qpc_frequency=qpc_frequency,
        started_qpc=started_qpc,
        write_sequence=write_sequence,
        overwritten_record_count=overwritten_record_count,
        observed_record_count=observed_record_count,
        producer_error=producer_error,
        probe_status=probe_status,
        target_action_code=target_action_code,
        configured_target_rva=configured_target_rva,
        configured_callsite_rva=configured_callsite_rva,
        configured_stack_dword_count=configured_stack_dword_count,
        active_probe_count=active_probe_count,
        reviewed_pe_timestamp=reviewed_pe_timestamp,
        reviewed_image_size=reviewed_image_size,
        reviewed_preferred_base=reviewed_preferred_base,
    )

    records: list[ClientActionTraceRecord] = []
    first_sequence = max(1, write_sequence - CLIENT_ACTION_TRACE_CAPACITY + 1)
    for sequence in range(first_sequence, write_sequence + 1):
        slot_index = (sequence - 1) % CLIENT_ACTION_TRACE_CAPACITY
        offset = (
            CLIENT_ACTION_TRACE_HEADER_SIZE
            + slot_index * CLIENT_ACTION_TRACE_SLOT_SIZE
        )
        records.append(_parse_record(source, offset, sequence, header))
    return ClientActionTraceSnapshot(header=header, records=tuple(records))


def _parse_record(
    source: bytes,
    offset: int,
    sequence: int,
    header: ClientActionTraceHeader,
) -> ClientActionTraceRecord:
    fields = _SLOT.unpack_from(source, offset)
    (
        committed_sequence,
        kind_value,
        flags,
        observed_qpc,
        thread_id,
        action_code,
        target_rva,
        caller_rva,
        eax,
        ebx,
        ecx,
        edx,
        esi,
        edi,
        ebp,
        esp,
        eflags,
        parameter_one,
        parameter_two,
        argument_length,
        stack_dword_count,
        argument_bytes,
        *tail,
    ) = fields
    stack_values = tuple(tail[:CLIENT_ACTION_TRACE_STACK_CAPACITY])
    reserved = tail[CLIENT_ACTION_TRACE_STACK_CAPACITY]

    if committed_sequence != sequence:
        raise ClientActionTraceError("native action trace record is not coherently committed")
    if kind_value != 1:
        raise ClientActionTraceError("native action trace record kind is unknown")
    if flags & ~CLIENT_ACTION_TRACE_KNOWN_FLAGS:
        raise ClientActionTraceError("native action trace record has unknown flags")
    if not flags & CLIENT_ACTION_TRACE_CONTEXT_COMPLETE_FLAG:
        raise ClientActionTraceError("native action trace record lacks a complete CPU context")
    if not flags & CLIENT_ACTION_TRACE_ACTION_188_CANDIDATE_FLAG:
        raise ClientActionTraceError("native action trace record is not marked as action 188")
    if observed_qpc < header.started_qpc or thread_id <= 0:
        raise ClientActionTraceError("native action trace time or thread identity is invalid")
    if action_code != TARGET_NEXT_MOB_ACTION_CODE:
        raise ClientActionTraceError("native action trace record action code is not 188")
    if target_rva >= header.reviewed_image_size or caller_rva >= header.reviewed_image_size:
        raise ClientActionTraceError("native action trace RVA exceeds the reviewed image")
    if argument_length > CLIENT_ACTION_TRACE_ARGUMENT_CAPACITY:
        raise ClientActionTraceError("native action trace argument exceeds its capacity")
    if stack_dword_count > CLIENT_ACTION_TRACE_STACK_CAPACITY:
        raise ClientActionTraceError("native action trace stack exceeds its capacity")
    if any(argument_bytes[argument_length:]):
        raise ClientActionTraceError("native action trace argument padding is non-zero")
    if any(stack_values[stack_dword_count:]):
        raise ClientActionTraceError("native action trace stack padding is non-zero")
    if any(reserved):
        raise ClientActionTraceError("native action trace reserved bytes are non-zero")
    try:
        argument = argument_bytes[:argument_length].decode("ascii")
    except UnicodeDecodeError as exc:
        raise ClientActionTraceError("native action trace argument is not ASCII") from exc
    if any(ord(character) < 0x20 or ord(character) > 0x7E for character in argument):
        raise ClientActionTraceError("native action trace argument is not printable ASCII")

    has_argument = argument_length > 0
    if has_argument != bool(flags & CLIENT_ACTION_TRACE_ARGUMENT_PRESENT_FLAG):
        raise ClientActionTraceError("native action trace argument flag is inconsistent")
    has_stack = stack_dword_count > 0
    if has_stack != bool(flags & CLIENT_ACTION_TRACE_STACK_COMPLETE_FLAG):
        raise ClientActionTraceError("native action trace stack flag is inconsistent")
    tuple_complete = bool(flags & CLIENT_ACTION_TRACE_TUPLE_COMPLETE_FLAG)
    if not tuple_complete and (parameter_one != 0 or parameter_two != 0 or has_argument):
        raise ClientActionTraceError(
            "native action trace exposes a partial Arcane action tuple"
        )

    return ClientActionTraceRecord(
        sequence=sequence,
        kind=ClientActionTraceRecordKind.CALL_ENTRY,
        flags=flags,
        observed_qpc=observed_qpc,
        thread_id=thread_id,
        action_code=action_code,
        target_rva=target_rva,
        caller_rva=caller_rva,
        eax=eax,
        ebx=ebx,
        ecx=ecx,
        edx=edx,
        esi=esi,
        edi=edi,
        ebp=ebp,
        esp=esp,
        eflags=eflags,
        parameter_one=parameter_one,
        parameter_two=parameter_two,
        argument=argument,
        stack_dwords=stack_values[:stack_dword_count],
    )


def _bounded_positive(value: object, name: str, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 < value <= maximum
    ):
        raise ValueError(f"{name} must be a positive bounded integer")
    return value


__all__ = [
    "CLIENT_ACTION_TRACE_ACTION_188_CANDIDATE_FLAG",
    "CLIENT_ACTION_TRACE_ARGUMENT_CAPACITY",
    "CLIENT_ACTION_TRACE_ARGUMENT_PRESENT_FLAG",
    "CLIENT_ACTION_TRACE_ARCANE_TUPLE_CAPABILITY",
    "CLIENT_ACTION_TRACE_CAPABILITIES",
    "CLIENT_ACTION_TRACE_CAPACITY",
    "CLIENT_ACTION_TRACE_CONTEXT_COMPLETE_FLAG",
    "CLIENT_ACTION_TRACE_CPU_CONTEXT_CAPABILITY",
    "CLIENT_ACTION_TRACE_HEADER_SIZE",
    "CLIENT_ACTION_TRACE_MAGIC",
    "CLIENT_ACTION_TRACE_SCHEMA_VERSION",
    "CLIENT_ACTION_TRACE_SIZE",
    "CLIENT_ACTION_TRACE_SLOT_SIZE",
    "CLIENT_ACTION_TRACE_STACK_CAPABILITY",
    "CLIENT_ACTION_TRACE_STACK_CAPACITY",
    "CLIENT_ACTION_TRACE_STACK_COMPLETE_FLAG",
    "CLIENT_ACTION_TRACE_TRANSPORT_CAPABILITY",
    "CLIENT_ACTION_TRACE_TUPLE_COMPLETE_FLAG",
    "ClientActionTraceError",
    "ClientActionTraceHeader",
    "ClientActionTraceProbeStatus",
    "ClientActionTraceRecord",
    "ClientActionTraceRecordKind",
    "ClientActionTraceSnapshot",
    "REVIEWED_WONDERBANE_IMAGE_SIZE",
    "REVIEWED_WONDERBANE_PE_TIMESTAMP",
    "REVIEWED_WONDERBANE_PREFERRED_BASE",
    "TARGET_NEXT_MOB_ACTION_CODE",
    "client_action_trace_mapping_name",
    "client_action_trace_signal_name",
    "parse_client_action_trace",
]
