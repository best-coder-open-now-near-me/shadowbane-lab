"""Build-guarded, read-only access to Shadowbane's selected-target health."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import struct
from collections.abc import Mapping
from ctypes import wintypes
from dataclasses import dataclass
from importlib.resources import files
from math import isfinite
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

NATIVE_HEALTH_PROFILE_SCHEMA_VERSION = 1
_BUNDLED_PROFILE_NAME = "wonderbane-0889b39a.native-health.json"
_ERROR_BAD_LENGTH = 24
_ERROR_NO_MORE_FILES = 18
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_MAX_PATH = 260
_MAX_MODULE_NAME32 = 255
_PROCESS_QUERY_INFORMATION = 0x0400
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PROCESS_VM_READ = 0x0010
_TH32CS_SNAPPROCESS = 0x00000002
_TH32CS_SNAPMODULE = 0x00000008
_TH32CS_SNAPMODULE32 = 0x00000010


class NativeTargetHealthError(RuntimeError):
    """Base error for guarded native target-health observation."""


class NativeTargetHealthCompatibilityError(NativeTargetHealthError):
    """Raised when the running executable does not match its calibrated build."""


class NativeTargetHealthReadError(NativeTargetHealthError):
    """Raised when a native value cannot be read or validated safely."""


class NativeHealthProfileLoadError(ValueError):
    """Raised when a native health profile is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class NativeTargetHealthProfile:
    """Exact executable identity and offsets for one verified client build."""

    profile_id: str
    executable_name: str
    executable_sha256: str
    pointer_size: int
    selected_pointer_rva: int
    current_health_offset: int
    maximum_health_offset: int
    minimum_user_address: int
    maximum_user_address: int
    maximum_plausible_health: float
    schema_version: int = NATIVE_HEALTH_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.profile_id, "profile_id"),
            (self.executable_name, "executable_name"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        digest = self.executable_sha256.lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("executable_sha256 must be a 64-character hexadecimal digest")
        if self.pointer_size != 4:
            raise ValueError("only the verified 32-bit Shadowbane client is supported")
        for value, field_name in (
            (self.selected_pointer_rva, "selected_pointer_rva"),
            (self.current_health_offset, "current_health_offset"),
            (self.maximum_health_offset, "maximum_health_offset"),
            (self.minimum_user_address, "minimum_user_address"),
            (self.maximum_user_address, "maximum_user_address"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.selected_pointer_rva == 0:
            raise ValueError("selected_pointer_rva must be positive")
        if self.maximum_health_offset != self.current_health_offset + 4:
            raise ValueError("verified current and maximum health fields must be adjacent")
        if self.minimum_user_address < 0x10000:
            raise ValueError("minimum_user_address must exclude the null-allocation region")
        if self.maximum_user_address > 0xFFFFFFFF:
            raise ValueError("maximum_user_address must fit a 32-bit client pointer")
        if self.maximum_user_address <= self.minimum_user_address:
            raise ValueError("maximum_user_address must exceed minimum_user_address")
        if (
            isinstance(self.maximum_plausible_health, bool)
            or not isinstance(self.maximum_plausible_health, (int, float))
            or not isfinite(self.maximum_plausible_health)
            or self.maximum_plausible_health <= 0
        ):
            raise ValueError("maximum_plausible_health must be finite and positive")
        if self.schema_version != NATIVE_HEALTH_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported native health profile version")


@dataclass(frozen=True, slots=True)
class NativeTargetHealthObservation:
    """One stable selected-target health snapshot."""

    target_present: bool
    current_health: float | None = None
    maximum_health: float | None = None
    target_token: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.target_present, bool):
            raise ValueError("target_present must be a boolean")
        if not self.target_present:
            if (
                self.current_health is not None
                or self.maximum_health is not None
                or self.target_token is not None
            ):
                raise ValueError("an absent target cannot contain native target values")
            return
        if self.current_health is None or self.maximum_health is None:
            raise ValueError("a present target requires current and maximum health")
        if self.target_token is None or not self.target_token.strip():
            raise ValueError("a present target requires an opaque target token")
        if not isfinite(self.current_health) or not isfinite(self.maximum_health):
            raise ValueError("target health values must be finite")
        if self.current_health < 0 or self.maximum_health <= 0:
            raise ValueError("target health values are outside valid bounds")
        if self.current_health > self.maximum_health:
            raise ValueError("current health cannot exceed maximum health")

    @property
    def health_fraction(self) -> float | None:
        if not self.target_present:
            return None
        assert self.current_health is not None
        assert self.maximum_health is not None
        return self.current_health / self.maximum_health


@runtime_checkable
class ReadOnlyProcessMemory(Protocol):
    pid: int
    executable_name: str
    executable_path: Path
    executable_sha256: str
    base_address: int
    pointer_size: int

    def read(self, address: int, size: int) -> bytes: ...

    def close(self) -> None: ...


class NativeTargetHealthReader:
    """Decodes stable health snapshots from an already opened read-only process."""

    def __init__(
        self,
        profile: NativeTargetHealthProfile,
        process: ReadOnlyProcessMemory,
        *,
        stability_attempts: int = 3,
    ) -> None:
        if not isinstance(profile, NativeTargetHealthProfile):
            raise ValueError("profile must be NativeTargetHealthProfile")
        if not isinstance(process, ReadOnlyProcessMemory):
            raise ValueError("process must implement ReadOnlyProcessMemory")
        if isinstance(stability_attempts, bool) or not isinstance(stability_attempts, int):
            raise ValueError("stability_attempts must be an integer")
        if stability_attempts <= 0:
            raise ValueError("stability_attempts must be positive")
        if process.executable_name.casefold() != profile.executable_name.casefold():
            raise NativeTargetHealthCompatibilityError(
                f"expected {profile.executable_name}, found {process.executable_name}"
            )
        if process.executable_sha256.casefold() != profile.executable_sha256.casefold():
            raise NativeTargetHealthCompatibilityError(
                "running Shadowbane executable does not match the calibrated SHA-256"
            )
        if process.pointer_size != profile.pointer_size:
            raise NativeTargetHealthCompatibilityError(
                "running Shadowbane pointer size does not match the calibrated build"
            )
        if process.base_address <= 0:
            raise NativeTargetHealthCompatibilityError("process image base is invalid")
        pointer_slot = process.base_address + profile.selected_pointer_rva
        if pointer_slot + profile.pointer_size > profile.maximum_user_address:
            raise NativeTargetHealthCompatibilityError(
                "calibrated selection pointer lies outside the 32-bit user address range"
            )
        self._profile = profile
        self._process = process
        self._pointer_slot = pointer_slot
        self._stability_attempts = stability_attempts
        self._closed = False

    @property
    def profile(self) -> NativeTargetHealthProfile:
        return self._profile

    @property
    def process_id(self) -> int:
        return self._process.pid

    def observe(self) -> NativeTargetHealthObservation:
        if self._closed:
            raise NativeTargetHealthReadError("native target-health reader is closed")
        for _ in range(self._stability_attempts):
            selected_pointer = self._read_pointer()
            if selected_pointer == 0:
                return NativeTargetHealthObservation(target_present=False)
            self._require_plausible_target_pointer(selected_pointer)
            try:
                health_bytes = self._process.read(
                    selected_pointer + self._profile.current_health_offset,
                    8,
                )
            except NativeTargetHealthReadError:
                if self._read_pointer() != selected_pointer:
                    continue
                raise
            if len(health_bytes) != 8:
                raise NativeTargetHealthReadError(
                    "native process backend returned a partial target-health value"
                )
            if self._read_pointer() != selected_pointer:
                continue
            current_health, maximum_health = struct.unpack("<ff", health_bytes)
            return self._validated_observation(
                selected_pointer,
                current_health,
                maximum_health,
            )
        raise NativeTargetHealthReadError(
            "selected target changed during every stable-read attempt"
        )

    def close(self) -> None:
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self) -> NativeTargetHealthReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _read_pointer(self) -> int:
        try:
            value = self._process.read(self._pointer_slot, self._profile.pointer_size)
        except NativeTargetHealthReadError:
            raise
        except Exception as exc:
            raise NativeTargetHealthReadError(
                f"could not read selected-target pointer: {type(exc).__name__}"
            ) from exc
        if len(value) != self._profile.pointer_size:
            raise NativeTargetHealthReadError(
                "native process backend returned a partial selected-target pointer"
            )
        return struct.unpack("<I", value)[0]

    def _require_plausible_target_pointer(self, pointer: int) -> None:
        profile = self._profile
        final_address = pointer + profile.maximum_health_offset + 4
        if (
            pointer < profile.minimum_user_address
            or final_address > profile.maximum_user_address
            or pointer % profile.pointer_size != 0
        ):
            raise NativeTargetHealthReadError(
                "selected-target pointer is outside the calibrated 32-bit user range"
            )

    def _validated_observation(
        self,
        selected_pointer: int,
        current_health: float,
        maximum_health: float,
    ) -> NativeTargetHealthObservation:
        maximum_plausible = self._profile.maximum_plausible_health
        if (
            not isfinite(current_health)
            or not isfinite(maximum_health)
            or current_health < 0
            or maximum_health <= 0
            or maximum_health > maximum_plausible
        ):
            raise NativeTargetHealthReadError(
                "selected-target health is outside calibrated plausible bounds"
            )
        tolerance = max(0.001, maximum_health * 0.00001)
        if current_health > maximum_health + tolerance:
            raise NativeTargetHealthReadError("selected-target current health exceeds maximum")
        return NativeTargetHealthObservation(
            target_present=True,
            current_health=min(current_health, maximum_health),
            maximum_health=maximum_health,
            target_token=self._target_token(selected_pointer),
        )

    def _target_token(self, selected_pointer: int) -> str:
        digest = hashlib.blake2s(digest_size=12)
        digest.update(self._profile.executable_sha256.encode("ascii"))
        digest.update(struct.pack("<II", self._process.pid, selected_pointer))
        return digest.hexdigest()


class _ProcessEntry32W(ctypes.Structure):
    _fields_ = (
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
    )


class _ModuleEntry32W(ctypes.Structure):
    _fields_ = (
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(wintypes.BYTE)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", wintypes.WCHAR * (_MAX_MODULE_NAME32 + 1)),
        ("szExePath", wintypes.WCHAR * _MAX_PATH),
    )


class _WindowsApi:
    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("native Shadowbane health observation requires Windows")
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
        self.kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        self.kernel32.Process32FirstW.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(_ProcessEntry32W),
        )
        self.kernel32.Process32FirstW.restype = wintypes.BOOL
        self.kernel32.Process32NextW.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(_ProcessEntry32W),
        )
        self.kernel32.Process32NextW.restype = wintypes.BOOL
        self.kernel32.Module32FirstW.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(_ModuleEntry32W),
        )
        self.kernel32.Module32FirstW.restype = wintypes.BOOL
        self.kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.ReadProcessMemory.argtypes = (
            wintypes.HANDLE,
            wintypes.LPCVOID,
            wintypes.LPVOID,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        )
        self.kernel32.ReadProcessMemory.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.kernel32.CloseHandle.restype = wintypes.BOOL


class WindowsReadOnlyProcessMemory:
    """Minimal Win32 process handle opened without write or execution rights."""

    pointer_size = 4

    def __init__(
        self,
        *,
        api: _WindowsApi,
        pid: int,
        executable_name: str,
        executable_path: Path,
        base_address: int,
    ) -> None:
        access = (
            _PROCESS_VM_READ
            | _PROCESS_QUERY_INFORMATION
            | _PROCESS_QUERY_LIMITED_INFORMATION
        )
        handle = api.kernel32.OpenProcess(access, False, pid)
        if not handle:
            raise NativeTargetHealthReadError(_windows_error("OpenProcess failed"))
        self._api = api
        self._handle = handle
        self.pid = pid
        self.executable_name = executable_name
        self.executable_path = executable_path
        self.executable_sha256 = _sha256(executable_path)
        self.base_address = base_address

    @classmethod
    def open_unique(cls, executable_name: str) -> WindowsReadOnlyProcessMemory:
        api = _WindowsApi()
        process_ids = _matching_process_ids(api, executable_name)
        if not process_ids:
            raise NativeTargetHealthReadError(
                f"no running process named {executable_name} was found"
            )
        if len(process_ids) != 1:
            joined = ", ".join(str(process_id) for process_id in process_ids)
            raise NativeTargetHealthReadError(
                f"multiple running {executable_name} processes were found: {joined}"
            )
        return cls._open_process(api, process_ids[0], executable_name)

    @classmethod
    def open_for_process(
        cls,
        executable_name: str,
        process_id: int,
    ) -> WindowsReadOnlyProcessMemory:
        if (
            isinstance(process_id, bool)
            or not isinstance(process_id, int)
            or process_id <= 0
        ):
            raise NativeTargetHealthReadError("process_id must be a positive integer")
        return cls._open_process(_WindowsApi(), process_id, executable_name)

    @classmethod
    def _open_process(
        cls,
        api: _WindowsApi,
        process_id: int,
        executable_name: str,
    ) -> WindowsReadOnlyProcessMemory:
        pid = process_id
        module = _main_module(api, pid)
        if module.szModule.casefold() != executable_name.casefold():
            raise NativeTargetHealthReadError(
                f"process {pid} is {module.szModule}, not {executable_name}"
            )
        return cls(
            api=api,
            pid=pid,
            executable_name=module.szModule,
            executable_path=Path(module.szExePath),
            base_address=cast(int, ctypes.cast(module.modBaseAddr, ctypes.c_void_p).value),
        )

    def read(self, address: int, size: int) -> bytes:
        if not self._handle:
            raise NativeTargetHealthReadError("native process handle is closed")
        if isinstance(address, bool) or not isinstance(address, int) or address <= 0:
            raise NativeTargetHealthReadError("read address must be a positive integer")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0 or size > 64:
            raise NativeTargetHealthReadError("bounded native reads must contain 1 to 64 bytes")
        buffer = (ctypes.c_ubyte * size)()
        bytes_read = ctypes.c_size_t()
        if not self._api.kernel32.ReadProcessMemory(
            self._handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(bytes_read),
        ):
            raise NativeTargetHealthReadError(_windows_error("ReadProcessMemory failed"))
        if bytes_read.value != size:
            raise NativeTargetHealthReadError("ReadProcessMemory returned a partial value")
        return bytes(buffer)

    def close(self) -> None:
        if self._handle:
            self._api.kernel32.CloseHandle(self._handle)
            self._handle = None


def open_windows_native_target_health_reader(
    profile: NativeTargetHealthProfile,
) -> NativeTargetHealthReader:
    process = WindowsReadOnlyProcessMemory.open_unique(profile.executable_name)
    try:
        return NativeTargetHealthReader(profile, process)
    except Exception:
        process.close()
        raise


def load_bundled_native_health_profile() -> NativeTargetHealthProfile:
    resource = files("shadowbane_lab.client_observation").joinpath(
        "data", _BUNDLED_PROFILE_NAME
    )
    return load_native_health_profile_text(resource.read_text(encoding="utf-8"))


def load_native_health_profile(path: str | Path) -> NativeTargetHealthProfile:
    return load_native_health_profile_text(Path(path).read_text(encoding="utf-8"))


def load_native_health_profile_text(text: str) -> NativeTargetHealthProfile:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NativeHealthProfileLoadError("native health profile is not valid JSON") from exc
    try:
        data = _mapping(raw, "native health profile")
        expected = {
            "schema_version",
            "profile_id",
            "executable_name",
            "executable_sha256",
            "pointer_size",
            "selected_pointer_rva",
            "current_health_offset",
            "maximum_health_offset",
            "minimum_user_address",
            "maximum_user_address",
            "maximum_plausible_health",
        }
        missing = expected - set(data)
        unknown = set(data) - expected
        if missing:
            raise NativeHealthProfileLoadError(
                f"missing required fields: {', '.join(sorted(missing))}"
            )
        if unknown:
            raise NativeHealthProfileLoadError(
                f"unknown fields: {', '.join(sorted(unknown))}"
            )
        if _integer(data, "schema_version") != NATIVE_HEALTH_PROFILE_SCHEMA_VERSION:
            raise NativeHealthProfileLoadError("unsupported native health profile version")
        return NativeTargetHealthProfile(
            profile_id=_string(data, "profile_id"),
            executable_name=_string(data, "executable_name"),
            executable_sha256=_string(data, "executable_sha256"),
            pointer_size=_integer(data, "pointer_size"),
            selected_pointer_rva=_integer(data, "selected_pointer_rva"),
            current_health_offset=_integer(data, "current_health_offset"),
            maximum_health_offset=_integer(data, "maximum_health_offset"),
            minimum_user_address=_integer(data, "minimum_user_address"),
            maximum_user_address=_integer(data, "maximum_user_address"),
            maximum_plausible_health=_number(data, "maximum_plausible_health"),
        )
    except NativeHealthProfileLoadError:
        raise
    except (TypeError, ValueError) as exc:
        raise NativeHealthProfileLoadError(str(exc)) from exc


def _matching_process_ids(api: _WindowsApi, executable_name: str) -> tuple[int, ...]:
    snapshot = api.kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snapshot == _INVALID_HANDLE_VALUE:
        raise NativeTargetHealthReadError(_windows_error("process snapshot failed"))
    try:
        entry = _ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(entry)
        if not api.kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            error = ctypes.get_last_error()
            if error == _ERROR_NO_MORE_FILES:
                return ()
            raise NativeTargetHealthReadError(_windows_error("process enumeration failed"))
        matches: list[int] = []
        while True:
            if entry.szExeFile.casefold() == executable_name.casefold():
                matches.append(entry.th32ProcessID)
            if not api.kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                error = ctypes.get_last_error()
                if error != _ERROR_NO_MORE_FILES:
                    raise NativeTargetHealthReadError(
                        _windows_error("process enumeration failed")
                    )
                break
        return tuple(matches)
    finally:
        api.kernel32.CloseHandle(snapshot)


def _main_module(api: _WindowsApi, pid: int) -> _ModuleEntry32W:
    flags = _TH32CS_SNAPMODULE | _TH32CS_SNAPMODULE32
    snapshot = None
    for _ in range(3):
        snapshot = api.kernel32.CreateToolhelp32Snapshot(flags, pid)
        if snapshot != _INVALID_HANDLE_VALUE:
            break
        if ctypes.get_last_error() != _ERROR_BAD_LENGTH:
            raise NativeTargetHealthReadError(_windows_error("module snapshot failed"))
    if snapshot == _INVALID_HANDLE_VALUE or snapshot is None:
        raise NativeTargetHealthReadError(_windows_error("module snapshot failed"))
    try:
        entry = _ModuleEntry32W()
        entry.dwSize = ctypes.sizeof(entry)
        if not api.kernel32.Module32FirstW(snapshot, ctypes.byref(entry)):
            raise NativeTargetHealthReadError(_windows_error("module enumeration failed"))
        return entry
    finally:
        api.kernel32.CloseHandle(snapshot)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _windows_error(prefix: str) -> str:
    code = ctypes.get_last_error()
    return f"{prefix} (Win32 error {code})"


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NativeHealthProfileLoadError(f"{field_name} must be an object")
    return cast(Mapping[str, Any], value)


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise NativeHealthProfileLoadError(f"{key} must be a non-empty string")
    return value


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise NativeHealthProfileLoadError(f"{key} must be an integer")
    return value


def _number(data: Mapping[str, Any], key: str) -> float:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NativeHealthProfileLoadError(f"{key} must be a number")
    return float(value)
