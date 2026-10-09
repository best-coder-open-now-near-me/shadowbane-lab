"""Bounded Windows system-census fallback for denied per-process handles.

SystemProcessInformation contains kernel creation FILETIMEs, including protected
processes. No name, age, heartbeat state or access denial is evidence of exit.
The native 32/64-bit layouts follow SYSTEM_PROCESS_INFORMATION and
SYSTEM_THREAD_INFORMATION (winternl/PHNT); no image-name pointer is dereferenced.
"""

from __future__ import annotations

import ctypes
import os
import struct
from dataclasses import dataclass

_MAX_BYTES = 32 * 1024 * 1024
_STATUS_INFO_LENGTH_MISMATCH = 0xC0000004


@dataclass(frozen=True, slots=True)
class SystemProcessIdentity:
    process_id: int
    creation_filetime: int
    parent_process_id: int | None


def parse_process_snapshot(data: bytes, *, pointer_size: int) -> dict[int, SystemProcessIdentity]:
    """Validate the entire linked snapshot before returning presence or absence."""
    if pointer_size not in (4, 8) or not isinstance(data, bytes) or not 0 < len(data) <= _MAX_BYTES:
        raise ValueError("invalid process census buffer")
    base_size, thread_size, pid_offset = (256, 80, 80) if pointer_size == 8 else (184, 64, 68)
    pointer_format = "<Q" if pointer_size == 8 else "<I"
    records = {}
    offset = 0
    while True:
        if len(data) - offset < base_size:
            raise ValueError("truncated process census entry")
        next_offset, threads = struct.unpack_from("<II", data, offset)
        end = offset + next_offset if next_offset else len(data)
        if (
            end > len(data)
            or end - offset < base_size
            or next_offset
            and next_offset % pointer_size
            or threads > (end - offset - base_size) // thread_size
        ):
            raise ValueError("invalid process census entry extent")
        pid = struct.unpack_from(pointer_format, data, offset + pid_offset)[0]
        parent = struct.unpack_from(pointer_format, data, offset + pid_offset + pointer_size)[0]
        created = struct.unpack_from("<q", data, offset + 32)[0]
        if pid > 0xFFFFFFFF or parent > 0xFFFFFFFF or pid in records:
            raise ValueError("invalid or duplicate process census PID")
        # PID 0 is the idle process and may have a zero creation time. Every
        # addressable process needs positive, exact creation evidence.
        if created < 0 or pid and created == 0:
            raise ValueError("process census has no valid creation time")
        records[pid] = SystemProcessIdentity(
            pid, created, parent if parent and parent != pid else None
        )
        if not next_offset:
            return records
        offset = end


def query_process_snapshot() -> dict[int, SystemProcessIdentity]:
    """Take one complete census; bounded growth handles concurrent process churn."""
    if os.name != "nt":
        raise RuntimeError("system process census requires Windows")
    query = ctypes.WinDLL("ntdll").NtQuerySystemInformation
    query.argtypes = (
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
    )
    query.restype = ctypes.c_long
    size = 65536
    for _ in range(8):
        if size > _MAX_BYTES:
            raise OSError("system process census exceeds size limit")
        buffer = ctypes.create_string_buffer(size)
        returned = ctypes.c_ulong()
        status = query(5, buffer, size, ctypes.byref(returned)) & 0xFFFFFFFF
        if status == _STATUS_INFO_LENGTH_MISMATCH:
            size = max(size * 2, returned.value + 65536)
            continue
        if status != 0:
            raise OSError(f"NtQuerySystemInformation failed: 0x{status:08x}")
        if not 0 < returned.value <= size:
            raise OSError("invalid completed system process census size")
        return parse_process_snapshot(
            buffer.raw[: returned.value], pointer_size=ctypes.sizeof(ctypes.c_void_p)
        )
    raise OSError("system process census did not stabilize within bounded query attempts")
