"""Windows mapping and mutex implementation shared with combat_fence.h.

Mappings are created once by their producer, never by consumers or mutators. The
explicit protected DACL grants only the current Windows user access. Names cannot
be reused while any native consumer retains a handle.
"""

from __future__ import annotations

import ctypes as c
import os
from collections.abc import Iterator
from contextlib import contextmanager

from .combat_fence import SIZE, STATE_OFFSET, Binding, State


class FenceError(RuntimeError):
    pass


class _Security(c.Structure):
    _fields_ = [("size", c.c_uint32), ("descriptor", c.c_void_p), ("inherit", c.c_int)]


class Windows:
    def __init__(self) -> None:
        if os.name != "nt":
            raise FenceError("combat admission mappings require Windows")
        self.k = c.WinDLL("kernel32", use_last_error=True)
        self.a = c.WinDLL("advapi32", use_last_error=True)
        signatures = {
            "CreateMutexW": ([c.c_void_p, c.c_int, c.c_wchar_p], c.c_void_p),
            "OpenMutexW": ([c.c_uint32, c.c_int, c.c_wchar_p], c.c_void_p),
            "ReleaseMutex": ([c.c_void_p], c.c_int),
            "WaitForSingleObject": ([c.c_void_p, c.c_uint32], c.c_uint32),
            "CreateFileMappingW": ([c.c_void_p, c.c_void_p, c.c_uint32, c.c_uint32,
                                    c.c_uint32, c.c_wchar_p], c.c_void_p),
            "OpenFileMappingW": ([c.c_uint32, c.c_int, c.c_wchar_p], c.c_void_p),
            "MapViewOfFile": ([c.c_void_p, c.c_uint32, c.c_uint32, c.c_uint32,
                               c.c_size_t], c.c_void_p),
            "UnmapViewOfFile": ([c.c_void_p], c.c_int),
            "CloseHandle": ([c.c_void_p], c.c_int),
            "GetCurrentProcess": ([], c.c_void_p),
            "OpenProcess": ([c.c_uint32, c.c_int, c.c_uint32], c.c_void_p),
            "GetProcessTimes": ([c.c_void_p] + [c.POINTER(c.c_uint64)] * 4, c.c_int),
            "LocalFree": ([c.c_void_p], c.c_void_p),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.k, name)
            fn.argtypes, fn.restype = args, result
        for name, args in {
            "OpenProcessToken": [c.c_void_p, c.c_uint32, c.POINTER(c.c_void_p)],
            "GetTokenInformation": [c.c_void_p, c.c_uint32, c.c_void_p, c.c_uint32,
                                    c.POINTER(c.c_uint32)],
            "ConvertSidToStringSidW": [c.c_void_p, c.POINTER(c.c_void_p)],
            "ConvertStringSecurityDescriptorToSecurityDescriptorW": [c.c_wchar_p,
                c.c_uint32, c.POINTER(c.c_void_p), c.c_void_p],
        }.items():
            fn = getattr(self.a, name)
            fn.argtypes, fn.restype = args, c.c_int

    @staticmethod
    def checked(value: int, operation: str) -> int:
        if not value:
            error = c.get_last_error()
            if error == 2:
                raise FileNotFoundError(error, operation)
            raise OSError(error, operation)
        return value

    def creation(self, process: int) -> int:
        times = [c.c_uint64() for _ in range(4)]
        self.checked(self.k.GetProcessTimes(process, *(c.byref(v) for v in times)),
                     "GetProcessTimes")
        return times[0].value

    def identity(self) -> tuple[int, int]:
        return os.getpid(), self.creation(self.k.GetCurrentProcess())

    def alive(self, pid: int, creation: int) -> bool:
        handle = self.k.OpenProcess(0x101000, False, pid)
        if not handle:
            if c.get_last_error() == 87:  # no such PID
                return False
            self.checked(handle, "OpenProcess")
        try:
            return (self.creation(handle) == creation
                    and self.k.WaitForSingleObject(handle, 0) == 258)
        finally:
            self.k.CloseHandle(handle)

    @contextmanager
    def security(self) -> Iterator[_Security]:
        token, sid_text, descriptor = c.c_void_p(), c.c_void_p(), c.c_void_p()
        try:
            self.checked(self.a.OpenProcessToken(self.k.GetCurrentProcess(), 8,
                                                c.byref(token)), "OpenProcessToken")
            length = c.c_uint32()
            self.a.GetTokenInformation(token, 1, None, 0, c.byref(length))
            if not 0 < length.value <= 65536:
                raise FenceError("invalid token user size")
            buffer = c.create_string_buffer(length.value)
            self.checked(self.a.GetTokenInformation(token, 1, buffer, length,
                                                     c.byref(length)), "GetTokenInformation")
            sid = c.c_void_p.from_buffer(buffer).value
            self.checked(self.a.ConvertSidToStringSidW(sid, c.byref(sid_text)),
                         "ConvertSidToStringSidW")
            sddl = "D:P(A;;GA;;;" + c.wstring_at(sid_text) + ")"
            self.checked(self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl, 1, c.byref(descriptor), None), "ConvertSecurityDescriptor")
            yield _Security(c.sizeof(_Security), descriptor, False)
        finally:
            for value in (sid_text, descriptor):
                if value.value:
                    self.k.LocalFree(value)
            if token.value:
                self.k.CloseHandle(token)


class Ticket:
    """Retain until native cancellation completes; close revokes future admission."""

    def __init__(self, binding: Binding, *, create: bool = False) -> None:
        self.binding, self.api = binding, Windows()
        self.mutex = self.mapping = self.view = 0
        k = self.api.k
        try:
            if create:
                if self.api.identity() != (binding.producer_pid, binding.producer_creation):
                    raise FenceError("only the bound producer may create a ticket")
                if not self.api.alive(binding.client_pid, binding.client_creation):
                    raise FenceError("client process lifetime is no longer active")
                with self.api.security() as security:
                    self.mutex = self.api.checked(k.CreateMutexW(c.byref(security), False,
                        binding.name + ".lock"), "CreateMutexW")
                    if c.get_last_error() == 183:
                        raise FenceError("ticket mutex already exists; UUID reuse rejected")
                    self.mapping = self.api.checked(k.CreateFileMappingW(c.c_void_p(-1),
                        c.byref(security), 4, 0, SIZE, binding.name), "CreateFileMappingW")
                    if c.get_last_error() == 183:
                        raise FenceError("ticket mapping already exists; UUID reuse rejected")
            else:
                self.mutex = self.api.checked(k.OpenMutexW(0x100001, False,
                    binding.name + ".lock"), "OpenMutexW")
                self.mapping = self.api.checked(k.OpenFileMappingW(6, False, binding.name),
                                                "OpenFileMappingW")
            self.view = self.api.checked(k.MapViewOfFile(self.mapping, 6, 0, 0, SIZE),
                                         "MapViewOfFile")
            if create:
                # Not discoverable through the registry or returned descriptor yet.
                c.memmove(self.view, binding.encode(), SIZE)
        except BaseException:
            self.close(revoke=False)
            raise

    @contextmanager
    def locked(self, timeout_ms: int = 5000) -> Iterator[State]:
        if not self.view or not self.mutex:
            raise FenceError("ticket is closed")
        result = self.api.k.WaitForSingleObject(self.mutex, timeout_ms)
        if result not in (0, 128):
            raise FenceError("ticket transition busy or unavailable")
        try:
            observed, state = Binding.decode(c.string_at(self.view, SIZE))
            if observed != self.binding:
                raise FenceError("immutable ticket identity changed")
            if result == 128:
                state = State.ENTERED_REVOKED if state in (
                    State.ENTERED, State.ENTERED_REVOKED) else State.REVOKED
                self._state(state)
            yield state
        finally:
            self.api.checked(self.api.k.ReleaseMutex(self.mutex), "ReleaseMutex")

    def _state(self, state: State) -> None:
        c.c_uint32.from_address(self.view + STATE_OFFSET).value = int(state)

    def arm(self) -> None:
        """Store calls this only after durable registration under its record lock."""
        with self.locked() as state:
            if state != State.REGISTERING or self.api.identity() != (
                self.binding.producer_pid, self.binding.producer_creation
            ):
                raise FenceError("ticket cannot be armed")
            self._state(State.PENDING)

    def state(self) -> State:
        with self.locked() as state:
            return state

    def revoke(self, *, timeout_ms: int = 5000) -> State:
        with self.locked(timeout_ms) as state:
            state = (State.ENTERED_REVOKED if state in (State.ENTERED, State.ENTERED_REVOKED)
                     else State.REVOKED)
            self._state(state)
            return state

    def close(self, *, revoke: bool = True, timeout_ms: int = 5000) -> None:
        # A failed revocation is not retirement. Retain handles so the caller can
        # retry cancellation; a native consumer may still hold a pending mapping.
        if revoke and self.view:
            self.revoke(timeout_ms=timeout_ms)
        if self.view:
            self.api.k.UnmapViewOfFile(self.view)
            self.view = 0
        for name in ("mapping", "mutex"):
            handle = getattr(self, name)
            if handle:
                self.api.k.CloseHandle(handle)
                setattr(self, name, 0)

    def __enter__(self) -> Ticket:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
