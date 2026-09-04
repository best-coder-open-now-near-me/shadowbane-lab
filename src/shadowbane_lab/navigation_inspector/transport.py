"""Windows shared-memory transport. Open only a channel created by the exact client.

Producer and panel each hold a separate nonblocking lifetime mutex; movement
callbacks never acquire it. All handle ownership stays on the opening thread.
"""

from __future__ import annotations

import ctypes
import os
import platform
import struct
import threading
import zlib
from ctypes import wintypes
from dataclasses import dataclass

from shadowbane_lab.graphics_lab.control import GraphicsControlTarget, verify_target_identity

from .geometry import ALL_LAYERS
from .protocol import (
    HEADER,
    MAGIC,
    MAX_FRAME_BYTES,
    SEQUENCE_OFFSET,
    VERSION,
    Frame,
    decode_frame,
    mapping_name,
)
from .snapshot import Clearance, Snapshot

CONTROL = struct.Struct("<4I2Q4I3fI")
CONTROL_MAGIC = 0x434E4257
MAPPING_BYTES = MAX_FRAME_BYTES + CONTROL.size
CONTROL_ENABLED = 1
CONTROL_XRAY = 2
CONTROL_FREEZE_FAILURE = 4
_registry_lock = threading.Lock()
_owners: set[tuple[str, str]] = set()


@dataclass(frozen=True, slots=True)
class Controls:
    sequence: int
    session_id: int
    enabled: bool = True
    xray: bool = False
    freeze_on_failure: bool = True
    command: int = 0  # 0 keeps current state, 1 freezes, 2 resumes.
    layers: int = ALL_LAYERS
    clearance: Clearance = Clearance()

    def encode(self, target: GraphicsControlTarget) -> bytes:
        if (
            not 0 < self.sequence <= 0xFFFFFFFE
            or self.sequence % 2
            or not 0 <= self.session_id < (1 << 64)
        ):
            raise ValueError("invalid control sequence/session")
        if self.command not in (0, 1, 2) or self.layers < 0 or self.layers & ~ALL_LAYERS:
            raise ValueError("invalid inspector controls")
        flags = int(self.enabled) | (int(self.xray) << 1) | (int(self.freeze_on_failure) << 2)
        payload = bytearray(
            CONTROL.pack(
                CONTROL_MAGIC,
                VERSION,
                CONTROL.size,
                self.sequence,
                target.process_creation_filetime_utc,
                self.session_id,
                target.process_id,
                flags,
                self.layers,
                self.command,
                self.clearance.character_radius,
                self.clearance.movement_uncertainty,
                self.clearance.margin,
                0,
            )
        )
        struct.pack_into("<I", payload, 60, zlib.crc32(payload))
        return bytes(payload)

    @classmethod
    def decode(
        cls, payload: bytes, target: GraphicsControlTarget, session: int, after: int
    ) -> Controls:
        if len(payload) != CONTROL.size:
            raise ValueError("invalid control size")
        (
            magic,
            version,
            size,
            sequence,
            creation,
            requested_session,
            pid,
            flags,
            layers,
            command,
            radius,
            uncertainty,
            margin,
            checksum,
        ) = CONTROL.unpack(payload)
        if magic != CONTROL_MAGIC or version != VERSION or size != CONTROL.size:
            raise ValueError("unsupported controls")
        if not sequence or sequence % 2 or sequence != after:
            raise ValueError("torn controls")
        if (
            pid != target.process_id
            or creation != target.process_creation_filetime_utc
            or requested_session != session
        ):
            raise ValueError("controls belong to another process/session")
        if flags & ~7 or layers & ~ALL_LAYERS or command not in (0, 1, 2):
            raise ValueError("invalid controls")
        checked = bytearray(payload)
        struct.pack_into("<I", checked, 60, 0)
        if zlib.crc32(checked) != checksum:
            raise ValueError("control checksum mismatch")
        return cls(
            sequence,
            session,
            bool(flags & 1),
            bool(flags & 2),
            bool(flags & 4),
            command,
            layers,
            Clearance(radius, uncertainty, margin),
        )


def _windows_api():
    if os.name != "nt":
        raise OSError("the live navigation inspector requires Windows")
    if platform.machine().lower() not in ("amd64", "x86_64", "x86", "i386", "i686"):
        raise OSError("the navigation mapping requires reviewed x86/x64 memory ordering")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "OpenFileMappingW": ([wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
        "MapViewOfFile": (
            [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t],
            ctypes.c_void_p,
        ),
        "UnmapViewOfFile": ([ctypes.c_void_p], wintypes.BOOL),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        "CreateMutexW": ([ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
        "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        "ReleaseMutex": ([wintypes.HANDLE], wintypes.BOOL),
        "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        "GetTickCount64": ([], ctypes.c_uint64),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(api, name)
        function.argtypes, function.restype = arguments, result
    return api


class Channel:
    def __init__(self, target: GraphicsControlTarget, *, role: str = "reader"):
        if role not in ("reader", "producer", "panel"):
            raise ValueError("unknown channel role")
        self.target, self.role = target, role
        self._api = _windows_api()
        self._thread = threading.get_ident()
        self._process = self._mapping = self._address = self._mutex = None
        self._owned = False
        self._key = (mapping_name(target.process_id, target.process_creation_filetime_utc), role)
        try:
            self._process = self._api.OpenProcess(0x101000, False, target.process_id)
            if not self._process or not verify_target_identity(target) or not self.alive:
                raise OSError("inspector target identity is no longer valid")
            if role != "reader":
                with _registry_lock:
                    if self._key in _owners:
                        raise OSError(f"an inspector {role} already owns this client")
                    _owners.add(self._key)
                    self._owned = True
                self._mutex = self._api.CreateMutexW(None, False, f"{self._key[0]}-{role}")
                if not self._mutex:
                    raise ctypes.WinError(ctypes.get_last_error())
                if self._api.WaitForSingleObject(self._mutex, 0) not in (0, 0x80):
                    self._api.CloseHandle(self._mutex)
                    self._mutex = None
                    raise OSError(f"an inspector {role} already owns this client")
            access = 4 if role == "reader" else 6
            self._mapping = self._api.OpenFileMappingW(access, False, self._key[0])
            if not self._mapping:
                raise OSError(
                    "this client has no navigation inspector channel; "
                    "use the full inspector extension"
                )
            self._address = self._api.MapViewOfFile(self._mapping, access, 0, 0, MAPPING_BYTES)
            if not self._address:
                raise ctypes.WinError(ctypes.get_last_error())
            header = HEADER.unpack(ctypes.string_at(self._address, HEADER.size))
            if (
                header[0:2] != (MAGIC, VERSION)
                or header[4] != target.process_id
                or header[6] != target.process_creation_filetime_utc
            ):
                raise OSError("inspector channel identity/version mismatch")
        except Exception:
            self.close()
            raise

    @property
    def alive(self) -> bool:
        return bool(self._process and self._api.WaitForSingleObject(self._process, 0) == 0x102)

    def clock_ms(self) -> int:
        return int(self._api.GetTickCount64())

    def _sequence(self, offset: int) -> int:
        # On supported x86/x64 Windows, aligned DWORD loads/stores are atomic
        # and ordered. Separate ctypes calls preserve the sequence/body ordering;
        # no RMW is attempted on a FILE_MAP_READ consumer view. Native readers
        # additionally fence and validate the sequence and complete-frame CRC.
        return ctypes.c_uint32.from_address(self._address + offset).value

    def _check_open(self) -> None:
        if not self._address or threading.get_ident() != self._thread:
            raise RuntimeError("channel is closed or used from a different thread")

    def read(self) -> Frame:
        self._check_open()
        if not self.alive:
            raise OSError("inspector client exited")
        before = self._sequence(SEQUENCE_OFFSET)
        if not before or before % 2:
            raise ValueError("waiting for a complete inspector frame")
        header = HEADER.unpack(ctypes.string_at(self._address, HEADER.size))
        size = header[2]
        if not HEADER.size <= size <= MAX_FRAME_BYTES:
            raise ValueError("invalid shared frame capacity")
        payload = ctypes.string_at(self._address, size)
        after = self._sequence(SEQUENCE_OFFSET)
        if before != after:
            raise ValueError("inspector frame changed during read")
        return decode_frame(
            payload,
            process_id=self.target.process_id,
            process_creation=self.target.process_creation_filetime_utc,
            now_ms=self.clock_ms(),
            sequence_after=after,
        )

    def snapshot(self, frame: Frame) -> Snapshot:
        snapshot = Snapshot.from_bytes(frame.capture)
        identity = snapshot.identity
        if (
            identity.process_id != self.target.process_id
            or identity.process_creation_filetime != self.target.process_creation_filetime_utc
            or identity.executable_sha256 != self.target.executable_sha256
            or snapshot.session_id != frame.session_id
            or snapshot.map_revision != frame.map_revision
            or snapshot.route_revision != frame.route_revision
        ):
            raise ValueError("saved evidence does not match its live frame")
        return snapshot

    def _write(self, payload: bytes, offset: int) -> None:
        self._check_open()
        if not self.alive:
            raise OSError("inspector client exited")
        sequence = struct.unpack_from("<I", payload, SEQUENCE_OFFSET)[0]
        marker = ctypes.c_uint32.from_address(self._address + offset + SEQUENCE_OFFSET)
        marker.value = sequence - 1
        ctypes.memmove(self._address + offset, payload[:SEQUENCE_OFFSET], SEQUENCE_OFFSET)
        ctypes.memmove(self._address + offset + 16, payload[16:], len(payload) - 16)
        marker.value = sequence

    def publish(self, payload: bytes) -> None:
        if self.role != "producer" or not HEADER.size <= len(payload) <= MAX_FRAME_BYTES:
            raise ValueError("only the bounded producer may publish frames")
        header = HEADER.unpack_from(payload)
        if (
            header[0:2] != (MAGIC, VERSION)
            or header[2] != len(payload)
            or header[4] != self.target.process_id
            or header[6] != self.target.process_creation_filetime_utc
            or not header[3]
            or header[3] % 2
        ):
            raise ValueError("invalid producer frame identity")
        self._write(payload, 0)

    def set_controls(self, controls: Controls) -> None:
        if self.role != "panel":
            raise ValueError("only the panel may write controls")
        self._write(controls.encode(self.target), MAX_FRAME_BYTES)

    def startup_controls(self) -> Controls | None:
        """Read panel defaults for the next session; never apply its old freeze command."""
        self._check_open()
        payload = ctypes.string_at(self._address + MAX_FRAME_BYTES, CONTROL.size)
        session = CONTROL.unpack(payload)[5]
        return self.controls(session)

    def controls(self, session_id: int) -> Controls | None:
        self._check_open()
        before = self._sequence(MAX_FRAME_BYTES + SEQUENCE_OFFSET)
        if not before or before % 2:
            return None
        payload = ctypes.string_at(self._address + MAX_FRAME_BYTES, CONTROL.size)
        after = self._sequence(MAX_FRAME_BYTES + SEQUENCE_OFFSET)
        if before != after:
            return None
        try:
            return Controls.decode(payload, self.target, session_id, after)
        except ValueError:
            return None

    def close(self) -> None:
        if threading.get_ident() != self._thread:
            raise RuntimeError("close channel on its owning thread")
        if self._address:
            self._api.UnmapViewOfFile(self._address)
        if self._mapping:
            self._api.CloseHandle(self._mapping)
        if self._mutex:
            self._api.ReleaseMutex(self._mutex)
            self._api.CloseHandle(self._mutex)
        if self._process:
            self._api.CloseHandle(self._process)
        self._process = self._mapping = self._address = self._mutex = None
        if self._owned:
            with _registry_lock:
                _owners.discard(self._key)
            self._owned = False

    def __enter__(self) -> Channel:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
