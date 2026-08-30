"""Lossless incremental reading of Shadowbane's native per-HUD message log."""

from __future__ import annotations

import codecs
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

_TIMESTAMPED_LINE = re.compile(r"^\((?P<timestamp>\d{1,2}:\d{2}:\d{2})\) (?P<message>.*)$")
_TIMESTAMP = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")


class NativeCombatLogFormatError(ValueError):
    """Raised when a non-empty native log record has an unknown shape."""


@dataclass(frozen=True, slots=True)
class NativeCombatLogEntry:
    """One complete message emitted by a combat-only Shadowbane text HUD."""

    sequence: int
    timestamp: str
    message: str

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise ValueError("sequence must be an integer")
        if self.sequence < 0:
            raise ValueError("sequence must not be negative")
        if _TIMESTAMP.fullmatch(self.timestamp) is None:
            raise ValueError("timestamp must use Shadowbane's H:MM:SS format")
        if not self.message:
            raise ValueError("message must not be empty")


class NativeCombatLogReader:
    """Tails one native log without locking it or re-reading emitted records."""

    def __init__(
        self,
        path: str | Path,
        *,
        start_at_end: bool = False,
        encoding: str = "cp1252",
    ) -> None:
        self._path = Path(path)
        self._start_at_end = start_at_end
        self._encoding = encoding
        codecs.lookup(encoding)
        self._decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
        self._initialized = False
        self._identity: tuple[int, int] | None = None
        self._position = 0
        self._text_buffer = ""
        self._pending_timestamp: str | None = None
        self._pending_message_lines: list[str] = []
        self._next_sequence = 0

    @property
    def path(self) -> Path:
        return self._path

    @property
    def position(self) -> int:
        return self._position

    def read_new_entries(self, *, finalize: bool = False) -> tuple[NativeCombatLogEntry, ...]:
        """Return records appended since the previous read.

        ``finalize`` treats the current end of file as a record boundary. It is intended for
        snapshots and should remain false for a continuously written log.
        """

        try:
            stream = self._path.open("rb")
        except FileNotFoundError:
            return ()
        with stream:
            identity, end = self._stream_state(stream)
            if not self._initialized:
                self._initialized = True
                self._identity = identity
                self._position = end if self._start_at_end else 0
            elif identity != self._identity:
                self._reset_file(identity)
            elif end < self._position:
                self._reset_file(identity)

            stream.seek(self._position)
            payload = stream.read()
            self._position = stream.tell()

        decoded = self._decoder.decode(payload, final=finalize)
        self._text_buffer += decoded
        return self._consume_text(finalize=finalize)

    @staticmethod
    def _stream_state(stream: BinaryIO) -> tuple[tuple[int, int], int]:
        stat = os.fstat(stream.fileno())
        identity = (stat.st_dev, stat.st_ino)
        stream.seek(0, os.SEEK_END)
        return identity, stream.tell()

    def _reset_file(self, identity: tuple[int, int]) -> None:
        self._identity = identity
        self._position = 0
        self._decoder = codecs.getincrementaldecoder(self._encoding)(errors="strict")
        self._text_buffer = ""
        self._pending_timestamp = None
        self._pending_message_lines.clear()

    def _consume_text(self, *, finalize: bool) -> tuple[NativeCombatLogEntry, ...]:
        lines = self._text_buffer.splitlines(keepends=True)
        self._text_buffer = ""
        if lines and not finalize and not _has_line_ending(lines[-1]):
            self._text_buffer = lines.pop()

        emitted: list[NativeCombatLogEntry] = []
        for raw_line in lines:
            line = raw_line.rstrip("\r\n")
            if self._next_sequence == 0 and self._pending_timestamp is None:
                line = line.removeprefix("\ufeff")
            if not line:
                self._emit_pending(emitted)
                continue
            match = _TIMESTAMPED_LINE.fullmatch(line)
            if match is not None:
                self._emit_pending(emitted)
                self._pending_timestamp = match.group("timestamp")
                self._pending_message_lines = [match.group("message")]
                continue
            if self._pending_timestamp is None:
                raise NativeCombatLogFormatError(f"unrecognized native combat log line: {line!r}")
            self._pending_message_lines.append(line)

        if finalize:
            if self._text_buffer:
                line = self._text_buffer.removeprefix("\ufeff")
                self._text_buffer = ""
                match = _TIMESTAMPED_LINE.fullmatch(line)
                if match is not None:
                    self._emit_pending(emitted)
                    self._pending_timestamp = match.group("timestamp")
                    self._pending_message_lines = [match.group("message")]
                elif self._pending_timestamp is not None:
                    self._pending_message_lines.append(line)
                else:
                    raise NativeCombatLogFormatError(
                        f"unrecognized native combat log line: {line!r}"
                    )
            self._emit_pending(emitted)
        return tuple(emitted)

    def _emit_pending(self, emitted: list[NativeCombatLogEntry]) -> None:
        if self._pending_timestamp is None:
            return
        message = "\n".join(self._pending_message_lines)
        if not message:
            raise NativeCombatLogFormatError("native combat log message must not be empty")
        emitted.append(
            NativeCombatLogEntry(
                sequence=self._next_sequence,
                timestamp=self._pending_timestamp,
                message=message,
            )
        )
        self._next_sequence += 1
        self._pending_timestamp = None
        self._pending_message_lines.clear()


def _has_line_ending(value: str) -> bool:
    return value.endswith("\n") or value.endswith("\r")
