"""Build-guarded, read-only access to selected-target role identity."""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

from shadowbane_lab.client_observation.build_compatibility import (
    native_layout_is_compatible,
)
from shadowbane_lab.client_observation.native_health import (
    ReadOnlyProcessMemory,
    WindowsReadOnlyProcessMemory,
)

NATIVE_TARGET_IDENTITY_PROFILE_SCHEMA_VERSION = 2
_BUNDLED_PROFILE_NAME = "wonderbane-ef43784b.native-target-identity.json"


class NativeTargetIdentityError(RuntimeError):
    """Base error for guarded selected-target identity observation."""


class NativeTargetIdentityCompatibilityError(NativeTargetIdentityError):
    """Raised when the running executable does not match its calibrated build."""


class NativeTargetIdentityReadError(NativeTargetIdentityError):
    """Raised when selected-target identity cannot be read safely."""


class NativeTargetIdentityProfileLoadError(ValueError):
    """Raised when a native selected-target identity profile is invalid."""


@dataclass(frozen=True, slots=True)
class NativeTargetIdentityProfile:
    """Exact ArcCharacter sparse-role layout for one verified client build."""

    profile_id: str
    executable_name: str
    executable_sha256: str
    pointer_size: int
    selected_pointer_rva: int
    arc_character_vtable_rva: int
    sparse_data_offset: int
    merchant_data_descriptor_rva: int
    shopkeeper_descriptor_rva: int
    banker_descriptor_rva: int
    trainer_descriptor_rva: int
    minion_descriptor_rva: int
    descriptor_key_offset: int
    sparse_value_pointer_offset: int
    maximum_sparse_table_bits: int
    minimum_user_address: int
    maximum_user_address: int
    schema_version: int = NATIVE_TARGET_IDENTITY_PROFILE_SCHEMA_VERSION

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
            (self.arc_character_vtable_rva, "arc_character_vtable_rva"),
            (self.sparse_data_offset, "sparse_data_offset"),
            (self.merchant_data_descriptor_rva, "merchant_data_descriptor_rva"),
            (self.shopkeeper_descriptor_rva, "shopkeeper_descriptor_rva"),
            (self.banker_descriptor_rva, "banker_descriptor_rva"),
            (self.trainer_descriptor_rva, "trainer_descriptor_rva"),
            (self.minion_descriptor_rva, "minion_descriptor_rva"),
            (self.descriptor_key_offset, "descriptor_key_offset"),
            (self.sparse_value_pointer_offset, "sparse_value_pointer_offset"),
            (self.maximum_sparse_table_bits, "maximum_sparse_table_bits"),
            (self.minimum_user_address, "minimum_user_address"),
            (self.maximum_user_address, "maximum_user_address"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        for value, field_name in (
            (self.sparse_data_offset, "sparse_data_offset"),
            (self.descriptor_key_offset, "descriptor_key_offset"),
            (self.sparse_value_pointer_offset, "sparse_value_pointer_offset"),
        ):
            if value % self.pointer_size != 0:
                raise ValueError(f"{field_name} must be pointer-aligned")
        if self.maximum_sparse_table_bits > 16:
            raise ValueError("maximum_sparse_table_bits cannot exceed 16")
        if self.minimum_user_address < 0x10000:
            raise ValueError("minimum_user_address must exclude the null-allocation region")
        if self.maximum_user_address > 0xFFFFFFFF:
            raise ValueError("maximum_user_address must fit a 32-bit client pointer")
        if self.maximum_user_address <= self.minimum_user_address:
            raise ValueError("maximum_user_address must exceed minimum_user_address")
        if self.schema_version != NATIVE_TARGET_IDENTITY_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported native target-identity profile version")


@dataclass(frozen=True, slots=True)
class NativeTargetIdentityObservation:
    """One coherent selected-target service-role snapshot."""

    target_present: bool
    classification_available: bool = True
    arc_character: bool | None = None
    merchant: bool | None = None
    shopkeeper: bool | None = None
    banker: bool | None = None
    trainer: bool | None = None
    minion: bool | None = None
    target_token: str | None = None
    classification_error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.target_present, bool):
            raise ValueError("target_present must be boolean")
        if not isinstance(self.classification_available, bool):
            raise ValueError("classification_available must be boolean")
        values = (
            self.arc_character,
            self.merchant,
            self.shopkeeper,
            self.banker,
            self.trainer,
            self.minion,
        )
        if not self.target_present:
            if not self.classification_available:
                raise ValueError("an absent target cannot have unavailable classification")
            if any(
                value is not None
                for value in (*values, self.target_token, self.classification_error)
            ):
                raise ValueError("an absent target cannot contain identity values")
            return
        if self.target_token is None or not self.target_token.strip():
            raise ValueError("a present target requires an opaque target token")
        if self.classification_available:
            if any(not isinstance(value, bool) for value in values):
                raise ValueError("a classified target requires boolean role flags")
            if self.classification_error is not None:
                raise ValueError("a classified target cannot contain a classification error")
            return
        if any(value is not None for value in values):
            raise ValueError("an unclassified target cannot contain role flags")
        if (
            self.classification_error is None
            or not isinstance(self.classification_error, str)
            or not self.classification_error.strip()
        ):
            raise ValueError("an unclassified target requires a classification error")

    @classmethod
    def unavailable(
        cls,
        *,
        target_token: str,
        error: str,
    ) -> NativeTargetIdentityObservation:
        """Represent a present target that must be skipped after a guarded read failure."""

        return cls(
            target_present=True,
            classification_available=False,
            target_token=target_token,
            classification_error=error,
        )

    @property
    def protected_roles(self) -> tuple[str, ...]:
        if not self.target_present:
            return ()
        return tuple(
            role
            for role, active in (
                ("merchant", self.merchant),
                ("shopkeeper", self.shopkeeper),
                ("banker", self.banker),
                ("trainer", self.trainer),
                ("minion", self.minion),
            )
            if active
        )

    @property
    def protected_role(self) -> bool:
        return bool(self.protected_roles)

    @property
    def attack_eligible(self) -> bool:
        return (
            self.target_present
            and self.classification_available
            and bool(self.arc_character)
            and not self.protected_role
        )


@dataclass(frozen=True, slots=True)
class _TargetIdentitySnapshot:
    selected: int
    vtable: int
    buckets: int | None
    table_bits: int | None
    observation: NativeTargetIdentityObservation


class NativeTargetIdentityReader:
    """Reads the ArcCharacter sparse flags used by native role classification."""

    def __init__(
        self,
        profile: NativeTargetIdentityProfile,
        process: ReadOnlyProcessMemory,
        *,
        stability_attempts: int = 3,
    ) -> None:
        if not isinstance(profile, NativeTargetIdentityProfile):
            raise ValueError("profile must be NativeTargetIdentityProfile")
        if not isinstance(process, ReadOnlyProcessMemory):
            raise ValueError("process must implement ReadOnlyProcessMemory")
        if isinstance(stability_attempts, bool) or not isinstance(stability_attempts, int):
            raise ValueError("stability_attempts must be an integer")
        if stability_attempts <= 0:
            raise ValueError("stability_attempts must be positive")
        if process.executable_name.casefold() != profile.executable_name.casefold():
            raise NativeTargetIdentityCompatibilityError(
                f"expected {profile.executable_name}, found {process.executable_name}"
            )
        if not native_layout_is_compatible(
            profile.executable_sha256,
            process.executable_sha256,
        ):
            raise NativeTargetIdentityCompatibilityError(
                "running Shadowbane executable does not match the calibrated SHA-256"
            )
        if process.pointer_size != profile.pointer_size:
            raise NativeTargetIdentityCompatibilityError(
                "running Shadowbane pointer size does not match the calibrated build"
            )
        if process.base_address <= 0:
            raise NativeTargetIdentityCompatibilityError("process image base is invalid")
        self._profile = profile
        self._process = process
        self._pointer_slot = process.base_address + profile.selected_pointer_rva
        self._character_vtable = process.base_address + profile.arc_character_vtable_rva
        self._stability_attempts = stability_attempts
        self._closed = False
        self._require_user_range(self._pointer_slot, profile.pointer_size, "target slot")
        self._require_user_range(self._character_vtable, profile.pointer_size, "vtable")
        self._descriptor_keys = {
            role: self._read_descriptor_key(rva, role)
            for role, rva in (
                ("merchant", profile.merchant_data_descriptor_rva),
                ("shopkeeper", profile.shopkeeper_descriptor_rva),
                ("banker", profile.banker_descriptor_rva),
                ("trainer", profile.trainer_descriptor_rva),
                ("minion", profile.minion_descriptor_rva),
            )
        }
        if len(set(self._descriptor_keys.values())) != len(self._descriptor_keys):
            raise NativeTargetIdentityCompatibilityError(
                "calibrated sparse role descriptors do not have unique keys"
            )

    @property
    def profile(self) -> NativeTargetIdentityProfile:
        return self._profile

    @property
    def process_id(self) -> int:
        return self._process.pid

    def observe(self) -> NativeTargetIdentityObservation:
        if self._closed:
            raise NativeTargetIdentityReadError("native target-identity reader is closed")
        last_error: NativeTargetIdentityReadError | None = None
        for _ in range(self._stability_attempts):
            selected = self._read_pointer(self._pointer_slot, "selected target")
            if selected == 0:
                return NativeTargetIdentityObservation(target_present=False)
            try:
                snapshot = self._read_snapshot(selected)
                if self._snapshot_is_stable(snapshot):
                    return snapshot.observation
            except NativeTargetIdentityReadError as exc:
                last_error = exc
                if self._read_pointer(self._pointer_slot, "selected target") != selected:
                    continue
        if last_error is not None:
            raise NativeTargetIdentityReadError(
                "selected-target identity remained unreadable during every stable-read "
                f"attempt: {last_error}"
            ) from last_error
        raise NativeTargetIdentityReadError(
            "selected-target identity changed during every stable-read attempt"
        )

    def close(self) -> None:
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self) -> NativeTargetIdentityReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _read_snapshot(self, selected: int) -> _TargetIdentitySnapshot:
        profile = self._profile
        self._require_object_pointer(
            selected,
            profile.sparse_data_offset + profile.pointer_size * 2,
            "selected target",
        )
        vtable = self._read_pointer(selected, "selected-target vtable")
        if vtable != self._character_vtable:
            self._require_object_pointer(vtable, profile.pointer_size, "selected-target vtable")
            return _TargetIdentitySnapshot(
                selected=selected,
                vtable=vtable,
                buckets=None,
                table_bits=None,
                observation=NativeTargetIdentityObservation(
                    target_present=True,
                    arc_character=False,
                    merchant=False,
                    shopkeeper=False,
                    banker=False,
                    trainer=False,
                    minion=False,
                    target_token=self._target_token(selected),
                ),
            )
        sparse_header = self._read_exact(
            selected + profile.sparse_data_offset,
            profile.pointer_size * 2,
            "selected-target sparse-data header",
        )
        buckets, table_bits = struct.unpack("<II", sparse_header)
        if table_bits > profile.maximum_sparse_table_bits:
            raise NativeTargetIdentityReadError(
                "selected-target sparse-data table exceeds the calibrated bound"
            )
        values = self._read_sparse_values(buckets, table_bits)
        observation = NativeTargetIdentityObservation(
            target_present=True,
            arc_character=True,
            merchant=values["merchant"],
            shopkeeper=values["shopkeeper"],
            banker=values["banker"],
            trainer=values["trainer"],
            minion=values["minion"],
            target_token=self._target_token(selected),
        )
        return _TargetIdentitySnapshot(
            selected=selected,
            vtable=vtable,
            buckets=buckets,
            table_bits=table_bits,
            observation=observation,
        )

    def _snapshot_is_stable(self, snapshot: _TargetIdentitySnapshot) -> bool:
        profile = self._profile
        if self._read_pointer(self._pointer_slot, "selected target") != snapshot.selected:
            return False
        if self._read_pointer(snapshot.selected, "selected-target vtable") != snapshot.vtable:
            return False
        if snapshot.buckets is None:
            return True
        assert snapshot.table_bits is not None
        header = self._read_exact(
            snapshot.selected + profile.sparse_data_offset,
            profile.pointer_size * 2,
            "selected-target sparse-data header",
        )
        if struct.unpack("<II", header) != (snapshot.buckets, snapshot.table_bits):
            return False
        values = self._read_sparse_values(snapshot.buckets, snapshot.table_bits)
        observation = snapshot.observation
        return values == {
            "merchant": observation.merchant,
            "shopkeeper": observation.shopkeeper,
            "banker": observation.banker,
            "trainer": observation.trainer,
            "minion": observation.minion,
        }

    def _read_sparse_values(self, buckets: int, table_bits: int) -> dict[str, bool]:
        profile = self._profile
        values = dict.fromkeys(self._descriptor_keys, False)
        if buckets == 0:
            return values
        table_size = (1 << table_bits) * 8
        self._require_object_pointer(buckets, table_size, "sparse-data bucket table")
        table = self._read_exact(buckets, table_size, "sparse-data bucket table")
        nodes: dict[str, int] = {}
        matched_roles: set[str] = set()
        roles_by_key = {key: role for role, key in self._descriptor_keys.items()}
        for key, value_node in struct.iter_unpack("<II", table):
            role = roles_by_key.get(key)
            if role is None:
                continue
            if role in matched_roles:
                raise NativeTargetIdentityReadError(
                    "selected-target sparse-data table contains a duplicate role key"
                )
            matched_roles.add(role)
            if role == "merchant":
                values[role] = True
                continue
            nodes[role] = value_node
        for role, value_node in nodes.items():
            self._require_object_pointer(
                value_node,
                profile.sparse_value_pointer_offset + profile.pointer_size,
                f"{role} sparse value node",
            )
            value_pointer = self._read_pointer(
                value_node + profile.sparse_value_pointer_offset,
                f"{role} sparse value",
            )
            self._require_object_pointer(value_pointer, 1, f"{role} sparse value")
            raw_value = self._read_exact(value_pointer, 1, f"{role} role flag")[0]
            if raw_value not in (0, 1):
                raise NativeTargetIdentityReadError(
                    f"selected-target {role} role flag is not boolean"
                )
            values[role] = bool(raw_value)
        return values

    def _read_descriptor_key(self, rva: int, role: str) -> int:
        address = self._process.base_address + rva + self._profile.descriptor_key_offset
        try:
            self._require_user_range(address, self._profile.pointer_size, f"{role} descriptor")
            key = self._read_pointer(address, f"{role} descriptor key")
        except NativeTargetIdentityReadError as exc:
            raise NativeTargetIdentityCompatibilityError(str(exc)) from exc
        if key in (0, 0xFFFFFFFF):
            raise NativeTargetIdentityCompatibilityError(
                f"calibrated {role} descriptor key is invalid"
            )
        return key

    def _read_pointer(self, address: int, label: str) -> int:
        return struct.unpack(
            "<I",
            self._read_exact(address, self._profile.pointer_size, f"{label} pointer"),
        )[0]

    def _read_exact(self, address: int, size: int, label: str) -> bytes:
        try:
            value = self._process.read(address, size)
        except Exception as exc:
            raise NativeTargetIdentityReadError(
                f"could not read {label}: {type(exc).__name__}"
            ) from exc
        if len(value) != size:
            raise NativeTargetIdentityReadError(
                f"native process backend returned a partial {label}"
            )
        return value

    def _require_user_range(self, pointer: int, size: int, label: str) -> None:
        profile = self._profile
        if pointer < profile.minimum_user_address or pointer + size > profile.maximum_user_address:
            raise NativeTargetIdentityReadError(
                f"{label} is outside the calibrated 32-bit user range"
            )

    def _require_object_pointer(self, pointer: int, size: int, label: str) -> None:
        self._require_user_range(pointer, size, f"{label} pointer")
        if pointer % self._profile.pointer_size != 0:
            raise NativeTargetIdentityReadError(f"{label} pointer is not aligned")

    def _target_token(self, selected: int) -> str:
        digest = hashlib.blake2s(digest_size=12)
        digest.update(self._profile.executable_sha256.encode("ascii"))
        digest.update(struct.pack("<II", self._process.pid, selected))
        return digest.hexdigest()


def open_windows_native_target_identity_reader(
    profile: NativeTargetIdentityProfile,
    *,
    process_id: int | None = None,
) -> NativeTargetIdentityReader:
    process = (
        WindowsReadOnlyProcessMemory.open_unique(profile.executable_name)
        if process_id is None
        else WindowsReadOnlyProcessMemory.open_for_process(
            profile.executable_name,
            process_id,
        )
    )
    try:
        return NativeTargetIdentityReader(profile, process)
    except Exception:
        process.close()
        raise


def load_bundled_native_target_identity_profile() -> NativeTargetIdentityProfile:
    resource = files("shadowbane_lab.client_observation").joinpath("data", _BUNDLED_PROFILE_NAME)
    return load_native_target_identity_profile_text(resource.read_text(encoding="utf-8"))


def load_native_target_identity_profile(path: str | Path) -> NativeTargetIdentityProfile:
    return load_native_target_identity_profile_text(Path(path).read_text(encoding="utf-8"))


def load_native_target_identity_profile_text(text: str) -> NativeTargetIdentityProfile:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NativeTargetIdentityProfileLoadError(
            "native target-identity profile is not valid JSON"
        ) from exc
    try:
        data = _mapping(raw, "native target-identity profile")
        expected = set(NativeTargetIdentityProfile.__dataclass_fields__)
        missing = expected - set(data)
        unknown = set(data) - expected
        if missing:
            raise NativeTargetIdentityProfileLoadError(
                f"missing required fields: {', '.join(sorted(missing))}"
            )
        if unknown:
            raise NativeTargetIdentityProfileLoadError(
                f"unknown fields: {', '.join(sorted(unknown))}"
            )
        values = {
            key: (
                _string(data, key)
                if key in {"profile_id", "executable_name", "executable_sha256"}
                else _integer(data, key)
            )
            for key in expected
        }
        return NativeTargetIdentityProfile(**values)
    except NativeTargetIdentityProfileLoadError:
        raise
    except (TypeError, ValueError) as exc:
        raise NativeTargetIdentityProfileLoadError(str(exc)) from exc


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NativeTargetIdentityProfileLoadError(f"{field_name} must be an object")
    return cast(Mapping[str, Any], value)


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise NativeTargetIdentityProfileLoadError(f"{key} must be a non-empty string")
    return value


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise NativeTargetIdentityProfileLoadError(f"{key} must be an integer")
    return value
