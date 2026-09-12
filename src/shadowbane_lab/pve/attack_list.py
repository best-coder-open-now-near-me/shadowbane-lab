"""Durable attack intent; runtime identity binding is deliberately separate."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

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
class AttackListEntry:
    entry_id: str
    label: str
    source: str
    evidence_id: str

    def __post_init__(self) -> None:
        for field in ("entry_id", "label", "evidence_id"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        if self.source not in {"manual", "response"}:
            raise ValueError("attack-list source must be manual or response")

    def as_dict(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in (
            "entry_id", "label", "source", "evidence_id",
        )}


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
        if raw["schema"] != 1 or raw["owner"] != [self.owner.server, self.owner.character]:
            raise ValueError("attack-list schema or owner mismatch")
        revision = raw["revision"]
        if type(revision) is not int or revision < 0 or not isinstance(raw["entries"], list):
            raise ValueError("invalid attack-list revision or entries")
        entries = []
        for entry in raw["entries"]:
            if not isinstance(entry, dict) or set(entry) != {
                "entry_id", "label", "source", "evidence_id",
            }:
                raise ValueError("invalid attack-list entry")
            entries.append(AttackListEntry(**entry))
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
        self, action: str, entry_id: str, entry: AttackListEntry | None = None,
    ) -> AttackListSnapshot:
        with exclusive_record_lock(self.path.with_suffix(".lock")):
            previous = self._read()
            entries = {item.entry_id: item for item in previous.entries}
            if action == "add":
                assert entry is not None
                # A repeated response never rewrites manual provenance or creates
                # another entry. Removal is explicit, not a background expiry.
                entries.setdefault(entry_id, entry)
            elif action == "remove":
                entries.pop(entry_id, None)
            elif action == "clear":
                entries.clear()
            ordered = tuple(sorted(entries.values(), key=lambda e: e.entry_id))
            if ordered == previous.entries:
                return previous
            result = AttackListSnapshot(previous.revision + 1, ordered)
            payload = json.dumps({
                "schema": 1,
                "owner": [self.owner.server, self.owner.character],
                "revision": result.revision,
                "entries": [item.as_dict() for item in ordered],
            }, ensure_ascii=True, sort_keys=True).encode()
            if len(payload) > 4 * 1024 * 1024:
                raise ValueError("attack list exceeds supported size")
            publish_atomic_record(self.path, payload, temporary_label="attack-list")
            return result
