"""Read-only process memory access and bounded discovery scans.

The live backend requests only query and VM-read rights.  It does not inject,
write memory, create remote threads, hook APIs, or emit a whole-process dump.
"""

from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from pathlib import Path

from shadowbane_lab.character_capture.model import (
    MemoryRegion,
    ModuleInfo,
    ProcessInfo,
    ScanMatch,
)


class MemoryAccessError(RuntimeError):
    """Raised when a declared read cannot be completed exactly."""


class ProcessSelectionError(RuntimeError):
    """Raised when a target process cannot be identified unambiguously."""


_READABLE_PROTECTIONS = frozenset({0x02, 0x04, 0x08, 0x20, 0x40, 0x80})
_MEM_COMMIT = 0x1000
_PAGE_GUARD = 0x100
_PAGE_NOACCESS = 0x01


def _is_readable_region(state: int, protection: int) -> bool:
    if state != _MEM_COMMIT or protection & _PAGE_GUARD:
        return False
    base_protection = protection & 0xFF
    return base_protection != _PAGE_NOACCESS and base_protection in _READABLE_PROTECTIONS


def _printable_preview(data: bytes) -> str:
    return "".join(chr(value) if 32 <= value < 127 else "." for value in data)


class MemoryReader(ABC):
    """Minimal random-access reader shared by the live and replay backends."""

    @property
    @abstractmethod
    def process_info(self) -> ProcessInfo:
        raise NotImplementedError

    @property
    def pointer_size(self) -> int:
        return self.process_info.pointer_size

    @abstractmethod
    def read(self, address: int, size: int) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def modules(self) -> tuple[ModuleInfo, ...]:
        raise NotImplementedError

    @abstractmethod
    def regions(self) -> Iterable[MemoryRegion]:
        raise NotImplementedError

    def module(self, name: str) -> ModuleInfo:
        matches = tuple(item for item in self.modules() if item.name.casefold() == name.casefold())
        if len(matches) != 1:
            raise MemoryAccessError(f"expected exactly one loaded module named {name!r}")
        return matches[0]

    def read_pointer(self, address: int) -> int:
        if self.pointer_size not in (4, 8):
            raise MemoryAccessError(f"unsupported pointer size: {self.pointer_size}")
        return int.from_bytes(self.read(address, self.pointer_size), "little", signed=False)

    def read_cstring(self, address: int, *, max_length: int, encoding: str) -> str:
        if max_length < 1:
            raise ValueError("max_length must be positive")
        raw = self.read(address, max_length)
        terminator = raw.find(b"\x00")
        if terminator >= 0:
            raw = raw[:terminator]
        return raw.decode(encoding, errors="strict")

    def read_wstring(self, address: int, *, max_characters: int) -> str:
        if max_characters < 1:
            raise ValueError("max_characters must be positive")
        raw = self.read(address, max_characters * 2)
        terminator = -1
        for index in range(0, len(raw) - 1, 2):
            if raw[index : index + 2] == b"\x00\x00":
                terminator = index
                break
        if terminator >= 0:
            raw = raw[:terminator]
        return raw.decode("utf-16le", errors="strict")

    def scan_bytes(
        self,
        needle: bytes,
        *,
        encoding: str = "bytes",
        max_matches: int = 50,
        max_scan_bytes: int = 256 * 1024 * 1024,
        context_bytes: int = 32,
        chunk_size: int = 1024 * 1024,
    ) -> tuple[ScanMatch, ...]:
        """Stream readable pages and retain only small contexts around matches."""

        if not needle:
            raise ValueError("needle must not be empty")
        for value, name in (
            (max_matches, "max_matches"),
            (max_scan_bytes, "max_scan_bytes"),
            (chunk_size, "chunk_size"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if (
            isinstance(context_bytes, bool)
            or not isinstance(context_bytes, int)
            or context_bytes < 0
        ):
            raise ValueError("context_bytes must be a non-negative integer")

        matches: list[ScanMatch] = []
        seen_addresses: set[int] = set()
        scanned = 0
        overlap_length = max(0, len(needle) - 1)

        for region in self.regions():
            if not region.readable or scanned >= max_scan_bytes:
                continue
            region_limit = min(region.size, max_scan_bytes - scanned)
            offset = 0
            tail = b""
            while offset < region_limit and len(matches) < max_matches:
                read_size = min(chunk_size, region_limit - offset)
                address = region.base_address + offset
                try:
                    block = self.read(address, read_size)
                except MemoryAccessError:
                    offset += read_size
                    tail = b""
                    scanned += read_size
                    continue
                haystack = tail + block
                haystack_base = address - len(tail)
                search_from = 0
                while len(matches) < max_matches:
                    found = haystack.find(needle, search_from)
                    if found < 0:
                        break
                    absolute = haystack_base + found
                    if absolute not in seen_addresses:
                        seen_addresses.add(absolute)
                        preview_start = max(region.base_address, absolute - context_bytes)
                        preview_end = min(
                            region.end_address, absolute + len(needle) + context_bytes
                        )
                        try:
                            preview = self.read(preview_start, preview_end - preview_start)
                        except MemoryAccessError:
                            preview = needle
                        matches.append(
                            ScanMatch(
                                address=absolute,
                                encoding=encoding,
                                region_base_address=region.base_address,
                                region_size=region.size,
                                preview_hex=preview.hex(" "),
                                preview_text=_printable_preview(preview),
                            )
                        )
                    search_from = found + 1
                tail = haystack[-overlap_length:] if overlap_length else b""
                offset += read_size
                scanned += read_size
            if len(matches) >= max_matches:
                break
        return tuple(matches)

    def scan_text(
        self,
        text: str,
        *,
        encodings: Sequence[str] = ("cp1252", "utf-8", "utf-16le"),
        max_matches: int = 50,
        max_scan_bytes: int = 256 * 1024 * 1024,
        context_bytes: int = 32,
    ) -> tuple[ScanMatch, ...]:
        if not isinstance(text, str) or not text:
            raise ValueError("text must be a non-empty string")
        if not encodings:
            raise ValueError("encodings must not be empty")
        collected: list[ScanMatch] = []
        seen: set[tuple[int, str]] = set()
        for encoding in encodings:
            try:
                needle = text.encode(encoding)
            except (LookupError, UnicodeEncodeError) as exc:
                raise ValueError(f"text cannot be encoded as {encoding}: {exc}") from exc
            remaining = max_matches - len(collected)
            if remaining <= 0:
                break
            for match in self.scan_bytes(
                needle,
                encoding=encoding,
                max_matches=remaining,
                max_scan_bytes=max_scan_bytes,
                context_bytes=context_bytes,
            ):
                key = (match.address, match.encoding)
                if key not in seen:
                    seen.add(key)
                    collected.append(match)
        return tuple(sorted(collected, key=lambda item: (item.address, item.encoding)))

    def scan_pointer(
        self,
        address: int,
        *,
        max_matches: int = 100,
        max_scan_bytes: int = 256 * 1024 * 1024,
        context_bytes: int = 32,
    ) -> tuple[ScanMatch, ...]:
        if isinstance(address, bool) or not isinstance(address, int) or address <= 0:
            raise ValueError("address must be a positive integer")
        limit = (1 << (self.pointer_size * 8)) - 1
        if address > limit:
            raise ValueError(f"address does not fit in a {self.pointer_size}-byte pointer")
        return self.scan_bytes(
            address.to_bytes(self.pointer_size, "little"),
            encoding=f"pointer{self.pointer_size * 8}",
            max_matches=max_matches,
            max_scan_bytes=max_scan_bytes,
            context_bytes=context_bytes,
        )


class BufferMemoryReader(MemoryReader):
    """Deterministic backend for layout development and regression tests."""

    def __init__(
        self,
        data: bytes | bytearray,
        *,
        base_address: int = 0x1000,
        pointer_size: int = 4,
        module_name: str = "Shadowbane.exe",
    ) -> None:
        if pointer_size not in (4, 8):
            raise ValueError("pointer_size must be 4 or 8")
        if base_address < 0:
            raise ValueError("base_address must be non-negative")
        self._data = bytes(data)
        self._base_address = base_address
        self._module = ModuleInfo(module_name, base_address, len(self._data), module_name)
        self._process_info = ProcessInfo(
            process_id=0,
            executable_name=module_name,
            executable_path=module_name,
            executable_sha256=hashlib.sha256(self._data).hexdigest(),
            pointer_size=pointer_size,
        )

    @property
    def process_info(self) -> ProcessInfo:
        return self._process_info

    def read(self, address: int, size: int) -> bytes:
        if isinstance(address, bool) or not isinstance(address, int) or address < 0:
            raise MemoryAccessError("address must be a non-negative integer")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise MemoryAccessError("size must be a non-negative integer")
        start = address - self._base_address
        end = start + size
        if start < 0 or end > len(self._data):
            raise MemoryAccessError(f"read outside buffer: address=0x{address:x} size={size}")
        return self._data[start:end]

    def modules(self) -> tuple[ModuleInfo, ...]:
        return (self._module,)

    def regions(self) -> tuple[MemoryRegion, ...]:
        return (
            MemoryRegion(
                base_address=self._base_address,
                size=len(self._data),
                state=_MEM_COMMIT,
                protection=0x04,
                region_type=0x20000,
                readable=True,
            ),
        )


if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _MAX_PATH = 260
    _MAX_MODULE_NAME32 = 255
    _TH32CS_SNAPPROCESS = 0x00000002
    _TH32CS_SNAPMODULE = 0x00000008
    _TH32CS_SNAPMODULE32 = 0x00000010
    _PROCESS_VM_READ = 0x0010
    _PROCESS_QUERY_INFORMATION = 0x0400
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class _PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * _MAX_PATH),
        ]

    class _MODULEENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("th32ModuleID", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("GlblcntUsage", wintypes.DWORD),
            ("ProccntUsage", wintypes.DWORD),
            ("modBaseAddr", ctypes.POINTER(ctypes.c_ubyte)),
            ("modBaseSize", wintypes.DWORD),
            ("hModule", wintypes.HMODULE),
            ("szModule", wintypes.WCHAR * (_MAX_MODULE_NAME32 + 1)),
            ("szExePath", wintypes.WCHAR * _MAX_PATH),
        ]

    class _MEMORY_BASIC_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BaseAddress", ctypes.c_void_p),
            ("AllocationBase", ctypes.c_void_p),
            ("AllocationProtect", wintypes.DWORD),
            ("RegionSize", ctypes.c_size_t),
            ("State", wintypes.DWORD),
            ("Protect", wintypes.DWORD),
            ("Type", wintypes.DWORD),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    _kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W))
    _kernel32.Process32FirstW.restype = wintypes.BOOL
    _kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W))
    _kernel32.Process32NextW.restype = wintypes.BOOL
    _kernel32.Module32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_MODULEENTRY32W))
    _kernel32.Module32FirstW.restype = wintypes.BOOL
    _kernel32.Module32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_MODULEENTRY32W))
    _kernel32.Module32NextW.restype = wintypes.BOOL
    _kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    _kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    _kernel32.IsWow64Process.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL))
    _kernel32.IsWow64Process.restype = wintypes.BOOL
    _kernel32.ReadProcessMemory.argtypes = (
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    )
    _kernel32.ReadProcessMemory.restype = wintypes.BOOL
    _kernel32.VirtualQueryEx.argtypes = (
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.POINTER(_MEMORY_BASIC_INFORMATION),
        ctypes.c_size_t,
    )
    _kernel32.VirtualQueryEx.restype = ctypes.c_size_t


def _sha256_file(path: str) -> str | None:
    candidate = Path(path)
    if not candidate.is_file():
        return None
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class WindowsProcessMemory(MemoryReader):
    """External, read-only accessor for a running Windows client process."""

    def __init__(
        self,
        handle: object,
        process_info: ProcessInfo,
        modules: tuple[ModuleInfo, ...],
    ) -> None:
        self._handle = handle
        self._process_info = process_info
        self._modules = modules
        self._closed = False

    @classmethod
    def open(
        cls,
        *,
        executable_names: Sequence[str] = ("Shadowbane.exe",),
        process_id: int | None = None,
        expected_sha256: str | None = None,
        required_pointer_size: int | None = None,
    ) -> WindowsProcessMemory:
        if os.name != "nt":
            raise OSError("live character capture is available only on Windows")
        if not executable_names:
            raise ValueError("executable_names must not be empty")
        if process_id is not None and (
            isinstance(process_id, bool) or not isinstance(process_id, int) or process_id < 1
        ):
            raise ValueError("process_id must be a positive integer")
        pid, discovered_name = cls._select_process(executable_names, process_id)
        handle = _kernel32.OpenProcess(_PROCESS_VM_READ | _PROCESS_QUERY_INFORMATION, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            raise OSError(error, f"OpenProcess failed for PID {pid}")
        try:
            path = cls._query_image_path(handle)
            pointer_size = cls._detect_pointer_size(handle)
            if required_pointer_size is not None and pointer_size != required_pointer_size:
                raise ProcessSelectionError(
                    f"layout requires {required_pointer_size}-byte pointers but target uses "
                    f"{pointer_size}-byte pointers"
                )
            file_hash = _sha256_file(path)
            if expected_sha256:
                expected = expected_sha256.lower().removeprefix("sha256:")
                if file_hash is None or file_hash.lower() != expected:
                    raise ProcessSelectionError(
                        "Shadowbane executable hash mismatch: "
                        f"expected {expected}, found {file_hash}"
                    )
            modules = cls._enumerate_modules(pid)
            info = ProcessInfo(
                process_id=pid,
                executable_name=Path(path).name or discovered_name,
                executable_path=path,
                executable_sha256=file_hash,
                pointer_size=pointer_size,
            )
            return cls(handle, info, modules)
        except Exception:
            _kernel32.CloseHandle(handle)
            raise

    @staticmethod
    def _select_process(executable_names: Sequence[str], process_id: int | None) -> tuple[int, str]:
        wanted = {name.casefold() for name in executable_names}
        snapshot = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if snapshot == _INVALID_HANDLE_VALUE:
            error = ctypes.get_last_error()
            raise OSError(error, "CreateToolhelp32Snapshot failed")
        try:
            entry = _PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(entry)
            candidates: list[tuple[int, str]] = []
            ok = _kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while ok:
                pid = int(entry.th32ProcessID)
                name = str(entry.szExeFile)
                if (process_id is not None and pid == process_id) or (
                    process_id is None and name.casefold() in wanted
                ):
                    candidates.append((pid, name))
                ok = _kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            _kernel32.CloseHandle(snapshot)
        if process_id is not None:
            if len(candidates) != 1:
                raise ProcessSelectionError(f"no process exists with PID {process_id}")
            if candidates[0][1].casefold() not in wanted:
                raise ProcessSelectionError(
                    f"PID {process_id} is {candidates[0][1]!r}, not one of {sorted(wanted)}"
                )
            return candidates[0]
        if len(candidates) != 1:
            details = ", ".join(f"{name}({pid})" for pid, name in candidates) or "none"
            raise ProcessSelectionError(
                "expected exactly one matching Shadowbane process; "
                f"found {details}. Pass --pid when multiple clients are open."
            )
        return candidates[0]

    @staticmethod
    def _query_image_path(handle: object) -> str:
        capacity = 32768
        buffer = ctypes.create_unicode_buffer(capacity)
        size = wintypes.DWORD(capacity)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            error = ctypes.get_last_error()
            raise OSError(error, "QueryFullProcessImageNameW failed")
        return buffer.value

    @staticmethod
    def _detect_pointer_size(handle: object) -> int:
        if ctypes.sizeof(ctypes.c_void_p) == 4:
            return 4
        wow64 = wintypes.BOOL()
        if not _kernel32.IsWow64Process(handle, ctypes.byref(wow64)):
            error = ctypes.get_last_error()
            raise OSError(error, "IsWow64Process failed")
        return 4 if wow64.value else 8

    @staticmethod
    def _enumerate_modules(process_id: int) -> tuple[ModuleInfo, ...]:
        flags = _TH32CS_SNAPMODULE | _TH32CS_SNAPMODULE32
        snapshot = _kernel32.CreateToolhelp32Snapshot(flags, process_id)
        if snapshot == _INVALID_HANDLE_VALUE:
            error = ctypes.get_last_error()
            raise OSError(error, f"module snapshot failed for PID {process_id}")
        modules: list[ModuleInfo] = []
        try:
            entry = _MODULEENTRY32W()
            entry.dwSize = ctypes.sizeof(entry)
            ok = _kernel32.Module32FirstW(snapshot, ctypes.byref(entry))
            while ok:
                address = int(ctypes.cast(entry.modBaseAddr, ctypes.c_void_p).value or 0)
                modules.append(
                    ModuleInfo(
                        name=str(entry.szModule),
                        base_address=address,
                        size=int(entry.modBaseSize),
                        path=str(entry.szExePath),
                    )
                )
                ok = _kernel32.Module32NextW(snapshot, ctypes.byref(entry))
        finally:
            _kernel32.CloseHandle(snapshot)
        if not modules:
            raise ProcessSelectionError(f"no modules could be enumerated for PID {process_id}")
        return tuple(modules)

    @property
    def process_info(self) -> ProcessInfo:
        return self._process_info

    def modules(self) -> tuple[ModuleInfo, ...]:
        return self._modules

    def read(self, address: int, size: int) -> bytes:
        if self._closed:
            raise MemoryAccessError("process handle is closed")
        if isinstance(address, bool) or not isinstance(address, int) or address < 0:
            raise MemoryAccessError("address must be a non-negative integer")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise MemoryAccessError("size must be a non-negative integer")
        if size == 0:
            return b""
        buffer = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t()
        ok = _kernel32.ReadProcessMemory(
            self._handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(bytes_read),
        )
        if not ok or bytes_read.value != size:
            error = ctypes.get_last_error()
            raise MemoryAccessError(
                f"ReadProcessMemory failed at 0x{address:x} for {size} bytes "
                f"(read {bytes_read.value}, error {error})"
            )
        return buffer.raw

    def regions(self) -> Iterable[MemoryRegion]:
        if self._closed:
            raise MemoryAccessError("process handle is closed")
        address = 0
        maximum_address = 0xFFFFFFFF if self.pointer_size == 4 else 0x7FFFFFFFFFFF
        while address < maximum_address:
            info = _MEMORY_BASIC_INFORMATION()
            result = _kernel32.VirtualQueryEx(
                self._handle,
                ctypes.c_void_p(address),
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not result:
                break
            base = int(info.BaseAddress or 0)
            size = int(info.RegionSize)
            if size <= 0:
                break
            yield MemoryRegion(
                base_address=base,
                size=size,
                state=int(info.State),
                protection=int(info.Protect),
                region_type=int(info.Type),
                readable=_is_readable_region(int(info.State), int(info.Protect)),
            )
            next_address = base + size
            if next_address <= address:
                break
            address = next_address

    def close(self) -> None:
        if not self._closed:
            _kernel32.CloseHandle(self._handle)
            self._closed = True

    def __enter__(self) -> WindowsProcessMemory:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
