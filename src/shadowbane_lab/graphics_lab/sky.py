"""Exact-process native sky settings and portable appearance presets."""

from __future__ import annotations

import ctypes
import json
import math
import os
import struct
import tempfile
from dataclasses import asdict, astuple, dataclass, replace
from pathlib import Path

from . import control

ASSET_SHA256 = "c4143315072e94413db211cc81164121ce8331af2a4497ab8229ac611cac73ce"
HEADER = struct.Struct("<4IQ4i")
SETTINGS = struct.Struct("<I7f")
SIZE = 136
RANGES = {
    "orientation": (-180, 180),
    "intensity": (0, 2),
    "horizon_height": (-0.4, 0.4),
    "horizon_width": (0.02, 0.8),
    "clouds": (0, 1),
    "sun": (0, 1),
    "fog_match": (0, 1),
}


@dataclass(frozen=True)
class SkySettings:
    enabled: int = 0
    orientation: float = 0
    intensity: float = 1
    horizon_height: float = 0
    horizon_width: float = 0.22
    clouds: float = 0.7
    sun: float = 0.6
    fog_match: float = 1

    def validate(self) -> None:
        if type(self.enabled) is not int or self.enabled not in (0, 1):
            raise ValueError("enabled must be 0 or 1")
        for key, (low, high) in RANGES.items():
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError(f"{key} must be a number")
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{key} must be finite in {low}..{high}")

    def pack(self) -> bytes:
        self.validate()
        return SETTINGS.pack(*astuple(self))


def unpack(data: bytes) -> SkySettings:
    settings = SkySettings(*SETTINGS.unpack(data))
    settings = replace(
        settings,
        **{
            key: min(high, max(low, getattr(settings, key)))
            for key, (low, high) in RANGES.items()
            if math.isfinite(getattr(settings, key))
            and low - 1e-6 <= getattr(settings, key) <= high + 1e-6
        },
    )
    settings.validate()
    return settings


def save_settings(path: Path, settings: SkySettings) -> None:
    settings.validate()
    data = {"schema": 1, "asset_sha256": ASSET_SHA256, "settings": asdict(settings)}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".sky-", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def load_settings(path: Path) -> SkySettings:
    if path.stat().st_size > 16384:
        raise ValueError("Sky preset exceeds 16 KiB")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"schema", "asset_sha256", "settings"}:
        raise ValueError("Invalid sky preset")
    if data["schema"] != 1 or data["asset_sha256"] != ASSET_SHA256:
        raise ValueError("Sky preset schema or asset identity mismatch")
    values = data["settings"]
    if not isinstance(values, dict) or set(values) != set(asdict(SkySettings())):
        raise ValueError("Invalid sky settings fields")
    settings = SkySettings(**values)
    settings.validate()
    return settings


class SkyClient:
    def __init__(self, target: control.GraphicsControlTarget) -> None:
        self.target = target
        self._mapping = self._address = self._mutex = None
        kernel = control._kernel32
        name = f"Local\\WonderBaneSky-{target.process_id}-{target.process_creation_filetime_utc}"
        try:
            self._mapping = kernel.OpenFileMappingW(0x000F001F, False, name)
            if not self._mapping:
                raise OSError("Sky unavailable: connect the full-profile sky package")
            self._address = kernel.MapViewOfFile(self._mapping, 0x000F001F, 0, 0, SIZE)
            if not self._address:
                raise OSError("Could not map sky settings")
            self._mutex = kernel.CreateMutexW(None, False, name + "-writer")
            if not self._mutex:
                raise OSError("Could not open sky writer mutex")
            self.read()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        kernel = control._kernel32
        if self._address:
            kernel.UnmapViewOfFile(self._address)
        if self._mapping:
            kernel.CloseHandle(self._mapping)
        if self._mutex:
            kernel.CloseHandle(self._mutex)
        self._mapping = self._address = self._mutex = None

    def _snapshot(self) -> bytes:
        if not self._address:
            raise OSError("Sky connection closed")
        for _ in range(3):
            before = ctypes.string_at(self._address, HEADER.size)
            data = ctypes.string_at(self._address, SIZE)
            after = ctypes.string_at(self._address, HEADER.size)
            magic, version, size, pid, creation, desired, applied, error, status = HEADER.unpack(
                data[: HEADER.size]
            )
            if (magic, version, size, pid, creation) != (
                0x534B4257,
                1,
                SIZE,
                self.target.process_id,
                self.target.process_creation_filetime_utc,
            ) or data[104:136].hex() != ASSET_SHA256:
                raise ValueError("Sky process, channel, or asset identity mismatch")
            if before == after == data[:40] and not (desired & 1 or status & 1):
                return data
        raise RuntimeError("Sky settings are being updated")

    def read(self) -> tuple[SkySettings, tuple[int, ...], int, int, int]:
        data = self._snapshot()
        desired, applied, error = HEADER.unpack(data[:40])[5:8]
        return unpack(data[40:72]), struct.unpack("<8I", data[72:104]), desired, applied, error

    def write(self, settings: SkySettings) -> int:
        settings.validate()
        kernel = control._kernel32
        if not self._mutex or kernel.WaitForSingleObject(self._mutex, 100) not in (0, 0x80):
            raise TimeoutError("Sky settings are busy")
        try:
            desired = HEADER.unpack(self._snapshot()[:40])[5]
            sequence = 2 if desired >= 0x7FFFFFFC else (desired & ~1) + 2
            marker = ctypes.c_long.from_address(self._address + 24)
            marker.value = sequence - 1
            ctypes.memmove(self._address + 40, settings.pack(), SETTINGS.size)
            marker.value = sequence
            return sequence
        finally:
            kernel.ReleaseMutex(self._mutex)
