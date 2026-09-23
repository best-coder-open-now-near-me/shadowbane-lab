"""One identity-bound player snapshot composed through a single process handle."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from shadowbane_lab.client_observation.native_health import (
    ReadOnlyProcessMemory,
    WindowsReadOnlyProcessMemory,
)
from shadowbane_lab.client_observation.native_progression_core import (
    NativePlayerProgressionCoreObservation,
    NativePlayerProgressionCoreProfile,
    NativePlayerProgressionCoreReader,
    load_bundled_native_progression_core_profile,
)
from shadowbane_lab.client_observation.native_training import (
    NativePlayerTrainingObservation,
    NativePlayerTrainingProfile,
    NativePlayerTrainingReader,
    load_bundled_native_training_profile,
)
from shadowbane_lab.client_observation.native_vitals import (
    NativePlayerVitalsObservation,
    NativePlayerVitalsProfile,
    NativePlayerVitalsReader,
    load_bundled_native_vitals_profile,
)

NATIVE_PLAYER_SNAPSHOT_SCHEMA_VERSION = 2
_FILETIME_UNIX_EPOCH = 116_444_736_000_000_000


class NativePlayerSnapshotError(RuntimeError):
    """Base error for an exact-process player snapshot."""


class NativePlayerSnapshotCompatibilityError(NativePlayerSnapshotError):
    """Raised when snapshot profiles do not describe one exact client layout."""


class NativePlayerSnapshotReadError(NativePlayerSnapshotError):
    """Raised when exact process identity or capture timing cannot be established."""


@dataclass(frozen=True, slots=True)
class NativePlayerSnapshotProfiles:
    progression: NativePlayerProgressionCoreProfile
    training: NativePlayerTrainingProfile
    vitals: NativePlayerVitalsProfile

    def __post_init__(self) -> None:
        if not isinstance(self.progression, NativePlayerProgressionCoreProfile):
            raise ValueError("progression must be a native progression profile")
        if not isinstance(self.training, NativePlayerTrainingProfile):
            raise ValueError("training must be a native training profile")
        if not isinstance(self.vitals, NativePlayerVitalsProfile):
            raise ValueError("vitals must be a native vitals profile")
        layouts = {
            (
                profile.executable_name.casefold(),
                profile.executable_sha256.casefold(),
                profile.pointer_size,
                profile.player_pointer_rva,
            )
            for profile in (self.progression, self.training, self.vitals)
        }
        if len(layouts) != 1:
            raise NativePlayerSnapshotCompatibilityError(
                "snapshot profiles must share one executable hash, pointer size, and player slot"
            )

    @property
    def executable_name(self) -> str:
        return self.progression.executable_name


@dataclass(frozen=True, slots=True)
class NativePlayerSnapshot:
    process_id: int
    process_creation_filetime_utc: int
    executable_path: Path
    executable_sha256: str
    capture_started_at_filetime_utc: int
    captured_at_filetime_utc: int
    progression_profile_id: str
    training_profile_id: str
    vitals_profile_id: str
    progression: NativePlayerProgressionCoreObservation
    training: NativePlayerTrainingObservation
    vitals: NativePlayerVitalsObservation
    snapshot_token: str
    schema_version: int = NATIVE_PLAYER_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.process_id, bool) or not isinstance(self.process_id, int):
            raise ValueError("process_id must be an integer")
        if self.process_id <= 0:
            raise ValueError("process_id must be positive")
        for value, field_name in (
            (self.process_creation_filetime_utc, "process_creation_filetime_utc"),
            (self.capture_started_at_filetime_utc, "capture_started_at_filetime_utc"),
            (self.captured_at_filetime_utc, "captured_at_filetime_utc"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.capture_started_at_filetime_utc < self.process_creation_filetime_utc:
            raise ValueError("snapshot capture predates process creation")
        if self.captured_at_filetime_utc < self.capture_started_at_filetime_utc:
            raise ValueError("snapshot capture end predates its start")
        if not isinstance(self.executable_path, Path):
            raise ValueError("executable_path must be a Path")
        digest = self.executable_sha256.casefold()
        if len(digest) != 64 or any(value not in "0123456789abcdef" for value in digest):
            raise ValueError("executable_sha256 must be a hexadecimal SHA-256")
        for value, field_name in (
            (self.progression_profile_id, "progression_profile_id"),
            (self.training_profile_id, "training_profile_id"),
            (self.vitals_profile_id, "vitals_profile_id"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be non-empty text")
        if not isinstance(self.progression, NativePlayerProgressionCoreObservation):
            raise ValueError("progression must be a native progression observation")
        if not isinstance(self.training, NativePlayerTrainingObservation):
            raise ValueError("training must be a native training observation")
        if not isinstance(self.vitals, NativePlayerVitalsObservation):
            raise ValueError("vitals must be a native vitals observation")
        if (
            not isinstance(self.snapshot_token, str)
            or len(self.snapshot_token) != 16
            or any(value not in "0123456789abcdef" for value in self.snapshot_token)
        ):
            raise ValueError("snapshot_token must contain 16 lowercase hexadecimal digits")
        if self.schema_version != NATIVE_PLAYER_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("unsupported native player snapshot schema")

    @property
    def exact_process_identity(self) -> tuple[int, int]:
        return self.process_id, self.process_creation_filetime_utc

    def as_dict(self) -> dict[str, object]:
        return _snapshot_payload(
            process_id=self.process_id,
            process_creation_filetime_utc=self.process_creation_filetime_utc,
            executable_path=self.executable_path,
            executable_sha256=self.executable_sha256,
            capture_started_at_filetime_utc=self.capture_started_at_filetime_utc,
            captured_at_filetime_utc=self.captured_at_filetime_utc,
            progression_profile_id=self.progression_profile_id,
            training_profile_id=self.training_profile_id,
            vitals_profile_id=self.vitals_profile_id,
            progression=self.progression,
            training=self.training,
            vitals=self.vitals,
            snapshot_token=self.snapshot_token,
        )


class NativePlayerSnapshotReader:
    """Own one process handle and compose all simulator-facing player observations."""

    def __init__(
        self,
        profiles: NativePlayerSnapshotProfiles,
        process: ReadOnlyProcessMemory,
        *,
        filetime_clock: Callable[[], int] | None = None,
    ) -> None:
        if not isinstance(profiles, NativePlayerSnapshotProfiles):
            raise ValueError("profiles must be NativePlayerSnapshotProfiles")
        if not isinstance(process, ReadOnlyProcessMemory):
            raise ValueError("process must implement ReadOnlyProcessMemory")
        creation = getattr(process, "process_creation_filetime_utc", None)
        if isinstance(creation, bool) or not isinstance(creation, int) or creation <= 0:
            raise NativePlayerSnapshotReadError(
                "process backend does not expose a positive creation FILETIME"
            )
        self._profiles = profiles
        self._process = process
        self._process_creation_filetime_utc = creation
        self._clock = _utc_filetime_now if filetime_clock is None else filetime_clock
        self._progression = NativePlayerProgressionCoreReader(profiles.progression, process)
        self._training = NativePlayerTrainingReader(profiles.training, process)
        self._vitals = NativePlayerVitalsReader(profiles.vitals, process)
        self._closed = False

    @property
    def process_id(self) -> int:
        return self._process.pid

    @property
    def process_creation_filetime_utc(self) -> int:
        return self._process_creation_filetime_utc

    @property
    def exact_process_identity(self) -> tuple[int, int]:
        return self.process_id, self.process_creation_filetime_utc

    def observe(self) -> NativePlayerSnapshot:
        if self._closed:
            raise NativePlayerSnapshotReadError("native player snapshot reader is closed")
        started = self._read_clock("capture start")
        progression = self._progression.observe()
        training = self._training.observe()
        vitals = self._vitals.observe()
        captured = self._read_clock("capture end")
        if started < self.process_creation_filetime_utc:
            raise NativePlayerSnapshotReadError("snapshot capture predates process creation")
        if captured < started:
            raise NativePlayerSnapshotReadError("snapshot capture clock moved backwards")
        profiles = self._profiles
        token_payload = _snapshot_payload(
            process_id=self._process.pid,
            process_creation_filetime_utc=self.process_creation_filetime_utc,
            executable_path=self._process.executable_path,
            executable_sha256=self._process.executable_sha256,
            capture_started_at_filetime_utc=started,
            captured_at_filetime_utc=captured,
            progression_profile_id=profiles.progression.profile_id,
            training_profile_id=profiles.training.profile_id,
            vitals_profile_id=profiles.vitals.profile_id,
            progression=progression,
            training=training,
            vitals=vitals,
            snapshot_token=None,
        )
        encoded = json.dumps(
            token_payload,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        token = hashlib.sha256(encoded).hexdigest()[:16]
        return NativePlayerSnapshot(
            process_id=self._process.pid,
            process_creation_filetime_utc=self.process_creation_filetime_utc,
            executable_path=self._process.executable_path,
            executable_sha256=self._process.executable_sha256,
            capture_started_at_filetime_utc=started,
            captured_at_filetime_utc=captured,
            progression_profile_id=profiles.progression.profile_id,
            training_profile_id=profiles.training.profile_id,
            vitals_profile_id=profiles.vitals.profile_id,
            progression=progression,
            training=training,
            vitals=vitals,
            snapshot_token=token,
        )

    def close(self) -> None:
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self) -> NativePlayerSnapshotReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _read_clock(self, boundary: str) -> int:
        value = self._clock()
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise NativePlayerSnapshotReadError(f"{boundary} FILETIME is invalid")
        return value


def load_bundled_native_player_snapshot_profiles() -> NativePlayerSnapshotProfiles:
    return NativePlayerSnapshotProfiles(
        progression=load_bundled_native_progression_core_profile(),
        training=load_bundled_native_training_profile(),
        vitals=load_bundled_native_vitals_profile(),
    )


def open_windows_native_player_snapshot_reader(
    profiles: NativePlayerSnapshotProfiles,
    *,
    process_id: int | None = None,
) -> NativePlayerSnapshotReader:
    process = (
        WindowsReadOnlyProcessMemory.open_unique(profiles.executable_name)
        if process_id is None
        else WindowsReadOnlyProcessMemory.open_for_process(
            profiles.executable_name,
            process_id,
        )
    )
    try:
        return NativePlayerSnapshotReader(profiles, process)
    except Exception:
        process.close()
        raise


def _utc_filetime_now() -> int:
    return _FILETIME_UNIX_EPOCH + time.time_ns() // 100


def _filetime_iso8601(value: int) -> str:
    unix_seconds = (value - _FILETIME_UNIX_EPOCH) / 10_000_000
    return datetime.fromtimestamp(unix_seconds, tz=UTC).isoformat().replace("+00:00", "Z")


def _snapshot_payload(
    *,
    process_id: int,
    process_creation_filetime_utc: int,
    executable_path: Path,
    executable_sha256: str,
    capture_started_at_filetime_utc: int,
    captured_at_filetime_utc: int,
    progression_profile_id: str,
    training_profile_id: str,
    vitals_profile_id: str,
    progression: NativePlayerProgressionCoreObservation,
    training: NativePlayerTrainingObservation,
    vitals: NativePlayerVitalsObservation,
    snapshot_token: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": NATIVE_PLAYER_SNAPSHOT_SCHEMA_VERSION,
        "ok": True,
        "captured_at_utc": _filetime_iso8601(captured_at_filetime_utc),
        "capture_started_at_filetime_utc": capture_started_at_filetime_utc,
        "captured_at_filetime_utc": captured_at_filetime_utc,
        "process_identity": {
            "process_id": process_id,
            "process_creation_filetime_utc": process_creation_filetime_utc,
            "executable_path": str(executable_path),
            "executable_name": executable_path.name,
            "executable_sha256": executable_sha256,
        },
        "progression": {
            "ok": True,
            "profile_id": progression_profile_id,
            "process_id": process_id,
            **progression.as_dict(),
        },
        "training": {
            "ok": True,
            "profile_id": training_profile_id,
            "process_id": process_id,
            **training.as_dict(),
        },
        "vitals": {
            "ok": True,
            "profile_id": vitals_profile_id,
            "process_id": process_id,
            "current_health": vitals.current_health,
            "maximum_health": vitals.maximum_health,
            "health_fraction": vitals.health_fraction,
            "current_mana": vitals.current_mana,
            "maximum_mana": vitals.maximum_mana,
            "mana_fraction": vitals.mana_fraction,
            "current_stamina": vitals.current_stamina,
            "maximum_stamina": vitals.maximum_stamina,
            "stamina_fraction": vitals.stamina_fraction,
        },
    }
    if snapshot_token is not None:
        payload["snapshot_token"] = snapshot_token
    return payload
