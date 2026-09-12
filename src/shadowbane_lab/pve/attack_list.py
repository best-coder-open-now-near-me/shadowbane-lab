"""Durable attack intent; runtime identity binding is deliberately separate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path

from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.record_store import exclusive_record_lock, publish_atomic_record


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError(f"{label} must be non-empty text of at most 256 characters")
    return value.strip()


@dataclass(frozen=True, slots=True)
class AttackListOwner:
    server: str
    character: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "server", _text(self.server, "server"))
        object.__setattr__(self, "character", _text(self.character, "character"))

    @property
    def storage_key(self) -> str:
        # Server and active-character provenance comes from CharacterConfigSession.
        payload = json.dumps([self.server, self.character], ensure_ascii=True)
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class AttackTargetObservation:
    """Historical native evidence, not durable identity or current action authority."""

    executable_sha256: str
    process_id: int
    process_started_at_100ns: int
    local_player_key: NativeObjectKey
    target_key: NativeObjectKey
    character_kind: str

    def __post_init__(self) -> None:
        digest = self.executable_sha256
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("executable_sha256 must be a lowercase SHA-256")
        for value in (self.process_id, self.process_started_at_100ns):
            if type(value) is not int or value <= 0:
                raise ValueError("observed process lifetime must contain positive integers")
        for key in (self.local_player_key, self.target_key):
            if not isinstance(key, NativeObjectKey) or not key.object_type or not key.object_uuid:
                raise ValueError("observed native keys must contain two nonzero fields")
        if self.local_player_key == self.target_key:
            raise ValueError("local character cannot be an attack-list target")
        if self.character_kind not in {"player", "npc", "pet", "unknown"}:
            raise ValueError("invalid observed character kind")

    @property
    def entry_id(self) -> str:
        scope = [
            self.executable_sha256,
            self.process_id,
            self.process_started_at_100ns,
            self.local_player_key.canonical_token,
            self.target_key.canonical_token,
        ]
        return hashlib.sha256(json.dumps(scope).encode()).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {
            "executable_sha256": self.executable_sha256,
            "process_id": self.process_id,
            "process_started_at_100ns": self.process_started_at_100ns,
            "local_player_key": self.local_player_key.as_dict(),
            "target_key": self.target_key.as_dict(),
            "character_kind": self.character_kind,
        }

    @classmethod
    def from_dict(cls, raw: object) -> AttackTargetObservation:
        fields = {
            "executable_sha256",
            "process_id",
            "process_started_at_100ns",
            "local_player_key",
            "target_key",
            "character_kind",
        }
        if not isinstance(raw, dict) or set(raw) != fields:
            raise ValueError("invalid target observation")
        values = dict(raw)
        for field in ("local_player_key", "target_key"):
            values[field] = NativeObjectKey.from_dict(values[field])
        return cls(**values)


@dataclass(frozen=True, slots=True)
class AttackPlayerIdentity:
    """Server-scoped player key, with exact observed name retained for validation."""

    server: str
    object_key: NativeObjectKey
    name: str

    def __post_init__(self) -> None:
        _text(self.server, "server")
        _text(self.name, "name")
        if (
            not isinstance(self.object_key, NativeObjectKey)
            or not self.object_key.object_type
            or self.object_key.object_uuid != 53
        ):
            raise ValueError("persistent player identity requires a calibrated player key")

    @property
    def entry_id(self) -> str:
        payload = ["player", self.server, self.object_key.canonical_token]
        return hashlib.sha256(json.dumps(payload).encode()).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {"server": self.server, "object_key": self.object_key.as_dict(), "name": self.name}

    @classmethod
    def from_dict(cls, raw: object) -> AttackPlayerIdentity:
        if not isinstance(raw, dict) or set(raw) != {"server", "object_key", "name"}:
            raise ValueError("invalid persistent player identity")
        return cls(raw["server"], NativeObjectKey.from_dict(raw["object_key"]), raw["name"])


@dataclass(frozen=True, slots=True)
class AttackListEntry:
    entry_id: str
    label: str
    source: str
    evidence_id: str
    observation: AttackTargetObservation | None = None
    player_identity: AttackPlayerIdentity | None = None

    def __post_init__(self) -> None:
        for field in ("entry_id", "label", "evidence_id"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        if self.source not in {"manual", "response"}:
            raise ValueError("attack-list source must be manual or response")

        if self.player_identity is not None and not isinstance(
            self.player_identity, AttackPlayerIdentity
        ):
            raise ValueError("invalid player identity")
        if self.observation is not None:
            if not isinstance(self.observation, AttackTargetObservation):
                raise ValueError("observation must be AttackTargetObservation")
            expected_id = (
                self.observation.entry_id
                if self.player_identity is None
                else self.player_identity.entry_id
            )
            if self.entry_id != expected_id:
                raise ValueError("entry identity does not match observed evidence")
        if self.player_identity is not None:
            if not isinstance(self.player_identity, AttackPlayerIdentity):
                raise ValueError("invalid player identity")
            if (
                self.entry_id != self.player_identity.entry_id
                or self.observation is None
                or self.observation.target_key != self.player_identity.object_key
                or self.observation.character_kind != "player"
            ):
                raise ValueError("persistent player identity disagrees with native evidence")

    def as_dict(self) -> dict[str, object]:
        result = {
            field: getattr(self, field)
            for field in (
                "entry_id",
                "label",
                "source",
                "evidence_id",
            )
        }
        result["observation"] = None if self.observation is None else self.observation.as_dict()
        result["player_identity"] = (
            None if self.player_identity is None else self.player_identity.as_dict()
        )
        return result


@dataclass(frozen=True, slots=True)
class AttackListSnapshot:
    revision: int
    entries: tuple[AttackListEntry, ...]


class AttackListStore:
    """One locked read/modify/replace transaction per character.

    Both entry sources persist until explicit removal. An entry is saved intent,
    never proof that a live object or same-name character is its target. Consumers
    must independently bind the entry to the current exact identity and honor party
    protection. Atomic replace preserves the previous complete state after a failed
    publication; a crashed process releases the OS lock. No historical cleanup can
    silently erase intent. Concurrent updates merge under the interprocess lock.
    """

    def __init__(self, root: Path, owner: AttackListOwner) -> None:
        self.path = Path(root) / f"{owner.storage_key}.json"
        self.owner = owner

    def _read(self) -> AttackListSnapshot:
        try:
            with self.path.open("rb") as stream:
                payload = stream.read(4 * 1024 * 1024 + 1)
        except FileNotFoundError:
            return AttackListSnapshot(0, ())
        if len(payload) > 4 * 1024 * 1024:
            raise ValueError("attack list exceeds supported size")
        raw = json.loads(payload)
        if not isinstance(raw, dict) or set(raw) != {"schema", "owner", "revision", "entries"}:
            raise ValueError("invalid attack-list record")
        if (
            type(raw["schema"]) is not int
            or raw["schema"] not in (1, 2, 3)
            or raw["owner"] != [self.owner.server, self.owner.character]
        ):
            raise ValueError("attack-list schema or owner mismatch")
        revision = raw["revision"]
        if type(revision) is not int or revision < 0 or not isinstance(raw["entries"], list):
            raise ValueError("invalid attack-list revision or entries")
        entries = []
        for entry in raw["entries"]:
            fields = {"entry_id", "label", "source", "evidence_id"}
            if raw["schema"] >= 2:
                fields.add("observation")
            if raw["schema"] == 3:
                fields.add("player_identity")
            if not isinstance(entry, dict) or set(entry) != fields:
                raise ValueError("invalid attack-list entry")
            values = dict(entry)
            if values.get("observation") is not None:
                values["observation"] = AttackTargetObservation.from_dict(values["observation"])
            if values.get("player_identity") is not None:
                values["player_identity"] = AttackPlayerIdentity.from_dict(
                    values["player_identity"]
                )
            # Version 1 did not retain enough evidence to reconstruct a binding.
            # Keep it unresolved rather than inferring identity from its label.
            entries.append(AttackListEntry(**values))
        if len({entry.entry_id for entry in entries}) != len(entries):
            raise ValueError("duplicate attack-list identity")
        return AttackListSnapshot(revision, tuple(sorted(entries, key=lambda e: e.entry_id)))

    def snapshot(self) -> AttackListSnapshot:
        with exclusive_record_lock(self.path.with_suffix(".lock")):
            return self._read()

    def add(self, entry: AttackListEntry) -> AttackListSnapshot:
        if not isinstance(entry, AttackListEntry):
            raise ValueError("entry must be AttackListEntry")
        return self._update("add", entry.entry_id, entry)

    def remove(self, entry_id: str) -> AttackListSnapshot:
        return self._update("remove", _text(entry_id, "entry_id"))

    def clear(self) -> AttackListSnapshot:
        return self._update("clear", "")

    def _update(
        self,
        action: str,
        entry_id: str,
        entry: AttackListEntry | None = None,
    ) -> AttackListSnapshot:
        with exclusive_record_lock(self.path.with_suffix(".lock")):
            previous = self._read()
            entries = {item.entry_id: item for item in previous.entries}
            if action == "add":
                assert entry is not None
                # A repeated response never rewrites manual provenance or creates
                # another entry. Removal is explicit, not a background expiry.
                old = entries.get(entry_id)
                if old is None:
                    entries[entry_id] = entry
                elif old.player_identity != entry.player_identity:
                    raise ValueError("saved player identity differs; explicit resolution required")
                elif old.observation is None and entry.observation is not None:
                    # An explicit fresh observation can enrich a legacy entry
                    # only when its full session-scoped digest is the same.
                    entries[entry_id] = replace(old, observation=entry.observation)
            elif action == "remove":
                entries.pop(entry_id, None)
            elif action == "clear":
                entries.clear()
            ordered = tuple(sorted(entries.values(), key=lambda e: e.entry_id))
            if ordered == previous.entries:
                return previous
            result = AttackListSnapshot(previous.revision + 1, ordered)
            payload = json.dumps(
                {
                    "schema": 3,
                    "owner": [self.owner.server, self.owner.character],
                    "revision": result.revision,
                    "entries": [item.as_dict() for item in ordered],
                },
                ensure_ascii=True,
                sort_keys=True,
            ).encode()
            if len(payload) > 4 * 1024 * 1024:
                raise ValueError("attack list exceeds supported size")
            publish_atomic_record(self.path, payload, temporary_label="attack-list")
            return result
