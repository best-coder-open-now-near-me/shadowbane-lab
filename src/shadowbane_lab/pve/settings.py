"""Durable PvE preferences keyed by native server/character, never by worker or hotbar.

Saved selectors are user intent, not native action authority. Each run resolves
its selector against the current exact character's learned powers. Settings are
snapshotted at run admission, so editing them does not alter an active engagement.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from shadowbane_lab.record_store import (
    exclusive_record_lock,
    publish_atomic_record,
    read_record_bytes,
)

from .buff_intent import BuffSettings
from .tracking import TrackingSettings

_MAX_BYTES = 16_384


@dataclass(frozen=True, slots=True)
class GroupCommandSettings:
    enabled: bool = False

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("group commands enabled must be boolean")

    def as_dict(self):
        return {"enabled": self.enabled}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {"enabled"}:
            raise ValueError("invalid group commands settings")
        return cls(value["enabled"])


@dataclass(frozen=True, slots=True)
class PvESettings:
    policy: str = "basic"
    opening_skill: str | None = None
    revision: int = 0
    buffs: BuffSettings = BuffSettings()
    tracking: TrackingSettings = TrackingSettings()
    group_commands: GroupCommandSettings = GroupCommandSettings()

    def __post_init__(self) -> None:
        if not isinstance(self.group_commands, GroupCommandSettings):
            raise ValueError("group command settings must be typed")
        if not isinstance(self.tracking, TrackingSettings):
            raise ValueError("tracking settings must be typed")
        if not isinstance(self.buffs, BuffSettings):
            raise ValueError("buff settings must be typed")
        if self.policy not in ("basic", "proc-assassin"):
            raise ValueError("PvE policy must be basic or proc-assassin")
        if self.opening_skill is not None:
            if (
                not isinstance(self.opening_skill, str)
                or not self.opening_skill
                or self.opening_skill != self.opening_skill.strip()
                or len(self.opening_skill) > 256
                or any(ord(char) < 32 for char in self.opening_skill)
            ):
                raise ValueError(
                    "opening skill must be canonical nonempty text of at most 256 characters"
                )
        if type(self.revision) is not int or not 0 <= self.revision < 2**63:
            raise ValueError("settings revision must be a nonnegative 63-bit integer")

    def as_dict(self) -> dict[str, object]:
        return {
            "policy": self.policy,
            "opening_skill": self.opening_skill,
            "revision": self.revision,
            "buffs": self.buffs.as_dict(),
            "tracking": self.tracking.as_dict(),
            "group_commands": self.group_commands.as_dict(),
        }


def _owner(identity) -> tuple[str, str]:
    values = identity.server_name, identity.character_name
    for value in values:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > 256
            or any(ord(char) < 32 for char in value)
        ):
            raise ValueError("PvE settings require exact native server and character names")
    return values


def _path(identity, root: Path | None) -> Path:
    owner = _owner(identity)
    if root is None:
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            raise ValueError("LOCALAPPDATA is required for PvE settings")
        root = Path(local) / "ShadowbaneLab" / "pve-settings"
    key = hashlib.sha256(json.dumps(owner, ensure_ascii=True).encode()).hexdigest()
    return Path(root) / f"{key}.json"


def _unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("PvE settings contain duplicate fields")
        result[key] = value
    return result


def load_pve_settings(identity, *, root: Path | None = None) -> PvESettings:
    path = _path(identity, root)
    if path.is_symlink():
        raise ValueError("PvE settings must not be a symlink")
    try:
        raw = read_record_bytes(path, _MAX_BYTES)
    except FileNotFoundError:
        return PvESettings()
    if len(raw) > _MAX_BYTES:
        raise ValueError("PvE settings exceed bounded record size")
    value = json.loads(raw, object_pairs_hook=_unique_object)
    fields = {"schema_version", "server", "character", "policy", "opening_skill", "revision"}
    if (not isinstance(value, dict) or type(value.get("schema_version")) is not int
            or value["schema_version"] not in (1, 2, 3, 4, 5)
            or set(value) != (fields if value["schema_version"] == 1 else
                              fields | {"buffs"} if value["schema_version"] == 2 else
                              fields | {"buffs", "tracking"} if value["schema_version"] < 5 else
                              fields | {"buffs", "tracking", "group_commands"})):
        raise ValueError("PvE settings schema is invalid")

    if (value["server"], value["character"]) != _owner(identity):
        raise ValueError("PvE settings belong to another character")
    # Loading schema 1 is a pure migration: no write, no implicit buff enablement.
    buffs = (BuffSettings() if value["schema_version"] == 1
             else BuffSettings.from_dict(value["buffs"]))
    if value["schema_version"] == 3:
        old = value["tracking"]
        if not isinstance(old, dict) or set(old) != {"enabled", "refresh_interval_seconds"}:
            raise ValueError("invalid schema3 tracking settings")
        value["tracking"] = {**old, "group_callouts_enabled": False}
    tracking = (TrackingSettings() if value["schema_version"] < 3
                else TrackingSettings.from_dict(value["tracking"]))
    commands = (GroupCommandSettings() if value["schema_version"] < 5
                else GroupCommandSettings.from_dict(value["group_commands"]))
    return PvESettings(value["policy"], value["opening_skill"], value["revision"],
                       buffs, tracking, commands)


def save_pve_settings(
    identity,
    settings: PvESettings,
    *,
    expected: PvESettings,
    require_current: Callable[[], None],
    root: Path | None = None,
) -> PvESettings:
    """Compare and replace one owner's intent after a fresh exact-session check."""
    if not isinstance(settings, PvESettings) or not isinstance(expected, PvESettings):
        raise ValueError("settings and expected revision must be typed")
    if not callable(require_current):
        raise ValueError("save requires an exact-character current check")
    path = _path(identity, root)
    with exclusive_record_lock(path.with_suffix(".lock")):
        if load_pve_settings(identity, root=root) != expected:
            raise ValueError("PvE settings changed; reload before saving")
        updated = replace(settings, revision=expected.revision + 1)
        server, character = _owner(identity)
        payload = json.dumps(
            {"schema_version": 5, "server": server, "character": character, **updated.as_dict()},
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
        if len(payload) > _MAX_BYTES:
            raise ValueError("PvE settings exceed bounded record size")
        require_current()
        publish_atomic_record(path, payload, temporary_label="pve-settings")
    return updated
