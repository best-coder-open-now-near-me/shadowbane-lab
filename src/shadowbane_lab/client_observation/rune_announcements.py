"""Typed parsing and passive waiting for native rune-drop announcements."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from shadowbane_lab.client_observation.native_log import (
    NativeCombatLogEntry,
    NativeCombatLogReader,
)

_RUNE_ANNOUNCEMENT = re.compile(
    r"^(?:\[System\] Info: )?"
    r"(?P<mob>.+?) in (?P<location>.+?) has found the (?P<rune>.+?)\. "
    r"Are you tough enough to take it\?$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class NativeRuneAnnouncement:
    """One lossless server announcement that a mob spawned holding a rare rune."""

    sequence: int
    timestamp: str
    mob_name: str
    location_name: str
    rune_name: str
    message: str

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise ValueError("sequence must be an integer")
        if self.sequence < 0:
            raise ValueError("sequence must not be negative")
        for field_name in (
            "timestamp",
            "mob_name",
            "location_name",
            "rune_name",
            "message",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

    def matches_all(self, terms: Sequence[str]) -> bool:
        """Return whether every case-insensitive term occurs in the announcement."""

        searchable = "\n".join(
            (self.mob_name, self.location_name, self.rune_name, self.message)
        ).casefold()
        for term in terms:
            if not isinstance(term, str) or not term.strip():
                raise ValueError("announcement match terms must be non-empty strings")
            if term.casefold() not in searchable:
                return False
        return True

    def as_dict(self) -> dict[str, str | int]:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "mob_name": self.mob_name,
            "location_name": self.location_name,
            "rune_name": self.rune_name,
            "message": self.message,
        }


class NativeRuneAnnouncementParser:
    """Recognize only the exact MagicBane/WonderBane rare-rune announcement shape."""

    def parse(self, entry: NativeCombatLogEntry) -> NativeRuneAnnouncement | None:
        if not isinstance(entry, NativeCombatLogEntry):
            raise ValueError("entry must be NativeCombatLogEntry")
        match = _RUNE_ANNOUNCEMENT.fullmatch(entry.message)
        if match is None:
            return None
        return NativeRuneAnnouncement(
            sequence=entry.sequence,
            timestamp=entry.timestamp,
            mob_name=match.group("mob"),
            location_name=match.group("location"),
            rune_name=match.group("rune"),
            message=entry.message,
        )


class NativeRuneAnnouncementWatcher:
    """Poll a native System-HUD log until a matching rune announcement arrives."""

    def __init__(
        self,
        reader: NativeCombatLogReader,
        *,
        parser: NativeRuneAnnouncementParser | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(reader, NativeCombatLogReader):
            raise ValueError("reader must be NativeCombatLogReader")
        self._reader = reader
        self._parser = parser or NativeRuneAnnouncementParser()
        self._monotonic = monotonic
        self._sleeper = sleeper

    def wait(
        self,
        *,
        terms: Sequence[str] = (),
        timeout_seconds: float | None = None,
        poll_seconds: float = 0.5,
    ) -> NativeRuneAnnouncement | None:
        if timeout_seconds is not None and (
            isinstance(timeout_seconds, bool) or timeout_seconds < 0
        ):
            raise ValueError("timeout_seconds must be non-negative when supplied")
        if isinstance(poll_seconds, bool) or poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        match_terms = tuple(terms)
        for term in match_terms:
            if not isinstance(term, str) or not term.strip():
                raise ValueError("announcement match terms must be non-empty strings")

        deadline = None if timeout_seconds is None else self._monotonic() + timeout_seconds
        while True:
            for entry in self._reader.read_new_entries():
                announcement = self._parser.parse(entry)
                if announcement is not None and announcement.matches_all(match_terms):
                    return announcement
            if deadline is None:
                self._sleeper(poll_seconds)
                continue
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                return None
            self._sleeper(min(poll_seconds, remaining))
