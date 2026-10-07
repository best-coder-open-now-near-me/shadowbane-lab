"""Qualified passive ArcWorld registry membership, never native reference ownership.

The ordinary client resolves world+94 on its owner thread. This external reader
cannot retain references or make reads atomic; complete structural rereads reject
observed churn. Native action admission must still resolve and retain exact keys.
"""

from __future__ import annotations

import struct
import time
from collections.abc import Callable
from dataclasses import dataclass

from shadowbane_lab.client_observation.native_health import BlockReadOnlyProcessMemory
from shadowbane_lab.client_observation.native_object import NativeObjectKey


class NativeObjectRegistryReadError(RuntimeError):
    """No complete, stable registry membership observation is available."""


class NativeObjectRegistrySnapshotChanged(NativeObjectRegistryReadError):
    """Successful reads disagreed within one complete membership transaction."""


@dataclass(frozen=True, slots=True)
class NativeObjectRegistryProfile:
    executable_name: str
    executable_sha256s: tuple[str, ...]
    pointer_size: int
    world_pointer_rva: int
    registry_pointer_offset: int
    buckets_pointer_offset: int
    exponent_offset: int
    object_key_offset: int
    maximum_table_bits: int
    maximum_objects: int
    minimum_user_address: int
    maximum_user_address: int
    maximum_transaction_ms: int = 200
    maximum_reads: int = 32768
    maximum_bytes: int = 2 * 1024 * 1024
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.executable_name, str) or not self.executable_name:
            raise ValueError("registry executable name is required")
        if (
            not isinstance(self.executable_sha256s, tuple)
            or not self.executable_sha256s
            or len(set(self.executable_sha256s)) != len(self.executable_sha256s)
            or any(
                not isinstance(h, str)
                or len(h) != 64
                or any(c not in "0123456789abcdef" for c in h)
                for h in self.executable_sha256s
            )
        ):
            raise ValueError("registry requires unique exact executable SHA-256 pins")
        for field in (
            "world_pointer_rva",
            "registry_pointer_offset",
            "buckets_pointer_offset",
            "exponent_offset",
            "object_key_offset",
            "maximum_table_bits",
            "maximum_objects",
            "minimum_user_address",
            "maximum_user_address",
            "maximum_transaction_ms",
            "maximum_reads",
            "maximum_bytes",
        ):
            value = getattr(self, field)
            if type(value) is not int or value <= 0:
                raise ValueError(f"registry {field} must be a positive integer")
        if (
            self.pointer_size != 4
            or self.schema_version != 1
            or self.maximum_table_bits > 16
            or self.maximum_objects > 65536
            or self.object_key_offset > 4096
            or self.maximum_transaction_ms > 250
            or self.maximum_reads > 32768
            or self.maximum_bytes > 2 * 1024 * 1024
            or not 0x10000 <= self.minimum_user_address < self.maximum_user_address <= 0xFFFFFFFF
        ):
            raise ValueError("unsupported registry geometry or bounds")
        if any(
            getattr(self, name) % 4
            for name in (
                "world_pointer_rva",
                "registry_pointer_offset",
                "buckets_pointer_offset",
                "exponent_offset",
                "object_key_offset",
            )
        ):
            raise ValueError("registry pointer/key fields must be aligned")


@dataclass(frozen=True, slots=True)
class NativeRegistryObject:
    address: int
    vtable: int
    key: NativeObjectKey


@dataclass(slots=True)
class _ReadBudget:
    deadline: float
    reads: int = 0
    bytes: int = 0


@dataclass(frozen=True, slots=True)
class NativeRegistrySnapshot:
    world: int
    registry: int
    objects: tuple[NativeRegistryObject, ...]
    # Only structural membership bytes: no mutable health/animation snapshots.
    evidence: tuple[tuple[int, bytes], ...]
    budget: _ReadBudget


class NativeObjectRegistryReader:
    def __init__(
        self,
        profile: NativeObjectRegistryProfile,
        process: BlockReadOnlyProcessMemory,
        *,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not isinstance(process, BlockReadOnlyProcessMemory):
            raise ValueError("registry requires bounded block read support")
        if not isinstance(profile, NativeObjectRegistryProfile):
            raise ValueError("registry profile is required")
        if (
            process.executable_name.casefold() != profile.executable_name.casefold()
            or process.executable_sha256.lower() not in profile.executable_sha256s
            or process.pointer_size != profile.pointer_size
        ):
            raise NativeObjectRegistryReadError(
                "executable is not an exact qualified registry image"
            )
        self.profile, self.process, self._clock = profile, process, clock

    def _check_budget(self, budget: _ReadBudget) -> None:
        if (
            self._clock() >= budget.deadline
            or budget.reads > self.profile.maximum_reads
            or budget.bytes > self.profile.maximum_bytes
        ):
            raise NativeObjectRegistryReadError("registry transaction budget exhausted")

    def _pointer(self, value: int) -> None:
        if (
            value % 4
            or value < self.profile.minimum_user_address
            or value + 4 > self.profile.maximum_user_address
        ):
            raise NativeObjectRegistryReadError("registry pointer is outside bounded user memory")

    def _read(self, address: int, size: int, budget: _ReadBudget) -> bytes:
        p = self.profile
        if (
            type(address) is not int
            or address % 4
            or address < p.minimum_user_address
            or address + size > p.maximum_user_address
            or not 0 < size <= 65536
        ):
            raise NativeObjectRegistryReadError(
                "registry read is outside bounded aligned user memory"
            )
        budget.reads += 1
        budget.bytes += size
        self._check_budget(budget)
        try:
            read = self.process.read if size <= 64 else self.process.read_block
            value = read(address, size)
        except Exception as exc:
            raise NativeObjectRegistryReadError(
                f"registry read failed: {type(exc).__name__}"
            ) from exc
        self._check_budget(budget)
        if len(value) != size:
            raise NativeObjectRegistryReadError("registry read was partial")
        return value

    def capture(self) -> NativeRegistrySnapshot:
        p = self.profile
        evidence: list[tuple[int, bytes]] = []
        budget = _ReadBudget(self._clock() + p.maximum_transaction_ms / 1000)

        def read(address: int, size: int) -> bytes:
            value = self._read(address, size, budget)
            evidence.append((address, value))
            return value

        def word(address: int) -> int:
            return struct.unpack("<I", read(address, 4))[0]

        world = word(self.process.base_address + p.world_pointer_rva)
        self._pointer(world)
        registry = word(world + p.registry_pointer_offset)
        self._pointer(registry)
        buckets = word(registry + p.buckets_pointer_offset)
        self._pointer(buckets)
        bits = word(registry + p.exponent_offset)
        if bits > p.maximum_table_bits:
            raise NativeObjectRegistryReadError("registry capacity exceeds qualified bound")
        capacity = 1 << bits
        addresses: list[int] = []
        seen_addresses: set[int] = set()
        for start in range(0, capacity, 4096):
            block = read(buckets + start * 4, min(4096, capacity - start) * 4)
            for (address,) in struct.iter_unpack("<I", block):
                if address in (0, 0xFFFFFFFF):
                    continue
                self._pointer(address)
                if address in seen_addresses:
                    raise NativeObjectRegistryReadError("registry object addresses are duplicated")
                seen_addresses.add(address)
                addresses.append(address)
                if len(addresses) > p.maximum_objects:
                    raise NativeObjectRegistryReadError(
                        "registry object count exceeds qualified bound"
                    )
        objects: list[NativeRegistryObject] = []
        keys: set[NativeObjectKey] = set()
        for address in addresses:
            vtable = word(address)
            if vtable % 4 or not p.minimum_user_address <= vtable < p.maximum_user_address:
                raise NativeObjectRegistryReadError("registry object vtable is invalid")
            key = NativeObjectKey(*struct.unpack("<II", read(address + p.object_key_offset, 8)))
            if not key.object_type or not key.object_uuid:
                raise NativeObjectRegistryReadError("registry object key contains zero")
            if key in keys:
                raise NativeObjectRegistryReadError("registry object identities are duplicated")
            keys.add(key)
            objects.append(NativeRegistryObject(address, vtable, key))
        snapshot = NativeRegistrySnapshot(world, registry, tuple(objects), tuple(evidence), budget)
        self.verify(snapshot)
        return snapshot

    def check_budget(self, snapshot: NativeRegistrySnapshot) -> None:
        """Finish a caller's detail transaction without resetting its original deadline."""
        self._check_budget(snapshot.budget)

    def verify(self, snapshot: NativeRegistrySnapshot) -> None:
        for address, expected in snapshot.evidence:
            if self._read(address, len(expected), snapshot.budget) != expected:
                raise NativeObjectRegistrySnapshotChanged("registry membership changed during read")
        # Recheck roots after object reads as well as before them.
        for address, expected in snapshot.evidence[:4]:
            if self._read(address, len(expected), snapshot.budget) != expected:
                raise NativeObjectRegistrySnapshotChanged(
                    "registry roots changed during verification"
                )
