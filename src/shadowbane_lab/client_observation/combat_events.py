"""Typed interpretation of exact records from Shadowbane's native combat log."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from shadowbane_lab.client_observation.native_log import NativeCombatLogEntry


class NativeCombatEventKind(StrEnum):
    PLAYER_HIT_TARGET = "player_hit_target"
    PLAYER_MISSED_TARGET = "player_missed_target"
    TARGET_HIT_PLAYER = "target_hit_player"
    TARGET_MISSED_PLAYER = "target_missed_player"
    TARGET_KILLED = "target_killed"
    PLAYER_KILLED = "player_killed"
    EXPERIENCE_GAINED = "experience_gained"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class NativeCombatEvent:
    sequence: int
    timestamp: str
    kind: NativeCombatEventKind
    message: str
    target_name: str | None = None
    amount: float | None = None

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise ValueError("sequence must be an integer")
        if self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        if not isinstance(self.kind, NativeCombatEventKind):
            raise ValueError("kind must be NativeCombatEventKind")
        for value, field_name in (
            (self.timestamp, "timestamp"),
            (self.message, "message"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.target_name is not None and not self.target_name.strip():
            raise ValueError("target_name must be non-empty when present")
        if self.amount is not None and self.amount < 0:
            raise ValueError("amount must be non-negative when present")


_PLAYER_HIT = re.compile(
    r"^You hit (?P<target>.+?) for (?P<amount>\d+(?:\.\d+)?) points? of damage!$"
)
_PLAYER_MISS = re.compile(r"^You miss (?P<target>.+?)!$")
_TARGET_HIT = re.compile(
    r"^(?P<target>.+?) hits YOU for (?P<amount>\d+(?:\.\d+)?) points? of damage!$"
)
_TARGET_MISS = re.compile(r"^(?P<target>.+?) misses YOU!$")
_TARGET_KILLED = re.compile(
    r"^(?:\[Combat\] Info: )?You have killed (?P<target>.+?)!$"
)
_EXPERIENCE = re.compile(
    r"^\[Combat\] Info: You have received (?P<amount>\d+(?:\.\d+)?) Experience Points!$"
)
_PLAYER_DEATH = (
    re.compile(r"^(?:\[Combat\] Info: )?You have been killed(?: by (?P<target>.+?))?!$"),
    re.compile(r"^(?P<target>.+?) has killed YOU!$"),
)


class NativeCombatEventParser:
    """Classifies only verified combat semantics while preserving every raw message."""

    def parse(self, entry: NativeCombatLogEntry) -> NativeCombatEvent:
        if not isinstance(entry, NativeCombatLogEntry):
            raise ValueError("entry must be NativeCombatLogEntry")
        message = entry.message
        for pattern in _PLAYER_DEATH:
            if match := pattern.fullmatch(message):
                return self._event(
                    entry,
                    NativeCombatEventKind.PLAYER_KILLED,
                    target_name=match.groupdict().get("target"),
                )
        matchers = (
            (_PLAYER_HIT, NativeCombatEventKind.PLAYER_HIT_TARGET, True),
            (_PLAYER_MISS, NativeCombatEventKind.PLAYER_MISSED_TARGET, False),
            (_TARGET_HIT, NativeCombatEventKind.TARGET_HIT_PLAYER, True),
            (_TARGET_MISS, NativeCombatEventKind.TARGET_MISSED_PLAYER, False),
            (_TARGET_KILLED, NativeCombatEventKind.TARGET_KILLED, False),
            (_EXPERIENCE, NativeCombatEventKind.EXPERIENCE_GAINED, True),
        )
        for pattern, kind, has_amount in matchers:
            if match := pattern.fullmatch(message):
                groups = match.groupdict()
                amount = float(groups["amount"]) if has_amount else None
                return self._event(
                    entry,
                    kind,
                    target_name=groups.get("target"),
                    amount=amount,
                )
        return self._event(entry, NativeCombatEventKind.OTHER)

    @staticmethod
    def _event(
        entry: NativeCombatLogEntry,
        kind: NativeCombatEventKind,
        *,
        target_name: str | None = None,
        amount: float | None = None,
    ) -> NativeCombatEvent:
        return NativeCombatEvent(
            sequence=entry.sequence,
            timestamp=entry.timestamp,
            kind=kind,
            message=entry.message,
            target_name=target_name,
            amount=amount,
        )
