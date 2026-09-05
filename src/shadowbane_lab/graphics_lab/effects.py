"""Actor-root effect controls using the native extension's exact-process channel."""

from __future__ import annotations

import ctypes
import math
import struct
from dataclasses import astuple, dataclass, replace

from . import control

CONFIG = struct.Struct("<6I15f")
HEADER = struct.Struct("<4IQ4i")
RANGES = {
    "rate": (0, 500),
    "lifetime": (0.05, 10),
    "speed": (0, 30),
    "size": (0.01, 5),
    "trail_lifetime": (0.05, 10),
    "sample_seconds": (0.005, 0.5),
    "sample_distance": (0.01, 10),
    "width": (0.01, 5),
    "teleport_distance": (1, 100),
    "red": (0, 1),
    "green": (0, 1),
    "blue": (0, 1),
    "opacity": (0, 1),
    "height": (-5, 10),
    "gravity": (-30, 30),
}


@dataclass(frozen=True)
class EffectsConfig:
    flags: int = 0
    attachment: int = 0
    burst: int = 0
    burst_count: int = 48
    particle_budget: int = 512
    sample_budget: int = 128
    rate: float = 40
    lifetime: float = 1.5
    speed: float = 2
    size: float = 0.25
    trail_lifetime: float = 2
    sample_seconds: float = 0.025
    sample_distance: float = 0.2
    width: float = 0.35
    teleport_distance: float = 30
    red: float = 0.25
    green: float = 0.8
    blue: float = 1
    opacity: float = 0.7
    height: float = 0
    gravity: float = -1

    def validate(self) -> None:
        for name, low, high in (
            ("flags", 0, 15),
            ("attachment", 0, 1),
            ("burst", 0, 0xFFFFFFFF),
            ("burst_count", 0, 256),
            ("particle_budget", 1, 1024),
            ("sample_budget", 2, 256),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer in {low}..{high}")
        for name, (low, high) in RANGES.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{name} must be finite in {low}..{high}")

    def pack(self) -> bytes:
        self.validate()
        return CONFIG.pack(*astuple(self))


PRESETS = {
    "Azure wake": EffectsConfig(flags=7),
    "Embers": EffectsConfig(flags=11, red=1, green=0.35, blue=0.05, gravity=1, rate=65),
    "Violet ribbon": EffectsConfig(flags=5, red=0.7, green=0.25, blue=1, width=0.55),
    "Burst only": EffectsConfig(flags=1, red=1, green=0.8, blue=0.25),
}


class EffectsClient:
    def __init__(self, target: control.GraphicsControlTarget) -> None:
        self.target = target
        self._mapping = self._address = self._mutex = None
        kernel = control._kernel32
        name = (
            f"Local\\WonderBaneEffects-{target.process_id}-{target.process_creation_filetime_utc}"
        )
        try:
            self._mapping = kernel.OpenFileMappingW(0x000F001F, False, name)
            if not self._mapping:
                raise OSError("Effects unavailable: requires the effects full-profile package")
            self._address = kernel.MapViewOfFile(self._mapping, 0x000F001F, 0, 0, 256)
            if not self._address:
                raise OSError("Could not map effects controls")
            self._mutex = kernel.CreateMutexW(None, False, name + "-writer")
            if not self._mutex:
                raise OSError("Could not open effects writer mutex")
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

    def read(self) -> tuple[EffectsConfig, tuple[int, ...], int, int, int]:
        if not self._address:
            raise OSError("Effects connection closed")
        for _ in range(3):
            before = ctypes.string_at(self._address, 40)
            data = ctypes.string_at(self._address, 256)
            after = ctypes.string_at(self._address, 40)
            magic, version, size, pid, creation, desired, applied, error, status = HEADER.unpack(
                data[:40]
            )
            if (magic, version, size, pid, creation) != (
                0x46584257,
                1,
                256,
                self.target.process_id,
                self.target.process_creation_filetime_utc,
            ):
                raise ValueError("Effects control identity or version mismatch")
            if before == after == data[:40] and not (desired & 1 or status & 1):
                config = EffectsConfig(*CONFIG.unpack(data[40:124]))
                # Float32 endpoints can round outside Python decimal limits.
                config = replace(
                    config,
                    **{
                        key: min(high, max(low, getattr(config, key)))
                        for key, (low, high) in RANGES.items()
                        if math.isfinite(getattr(config, key))
                        and low - 1e-6 <= getattr(config, key) <= high + 1e-6
                    },
                )
                config.validate()
                return config, struct.unpack("<8I", data[124:156]), desired, applied, error
        raise RuntimeError("Effects controls are being updated")

    def write(self, config: EffectsConfig, *, burst: bool = False) -> int:
        config.validate()
        kernel = control._kernel32
        if not self._mutex or kernel.WaitForSingleObject(self._mutex, 100) not in (0, 0x80):
            raise TimeoutError("Effects controls are busy")
        try:
            current, _, desired, _, _ = self.read()
            config = replace(config, burst=(current.burst + int(burst)) & 0xFFFFFFFF)
            sequence = 2 if desired >= 0x7FFFFFFC else (desired & ~1) + 2
            marker = ctypes.c_long.from_address(self._address + 24)
            marker.value = sequence - 1
            ctypes.memmove(self._address + 40, config.pack(), CONFIG.size)
            marker.value = sequence
            return sequence
        finally:
            kernel.ReleaseMutex(self._mutex)
