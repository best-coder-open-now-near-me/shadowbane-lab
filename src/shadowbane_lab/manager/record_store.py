"""Shared durable replacement for node-local manager records.

Manager ledgers own their schemas, identities, and size limits.  This module
owns only the filesystem transaction used once a ledger has encoded a valid
record: create a unique sibling, flush it to disk, and atomically replace the
published record despite bounded transient Windows reader locks.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from time import sleep

DEFAULT_ATOMIC_REPLACE_RETRY_DELAYS_SECONDS = (
    0.01,
    0.02,
    0.04,
    0.08,
    0.16,
    0.32,
    0.5,
)

_RECORD_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}\Z")
RecordReplacer = Callable[[Path, Path], object]


def replace_record_with_retry(
    temporary: Path,
    target: Path,
    *,
    retry_delays_seconds: Sequence[float] = DEFAULT_ATOMIC_REPLACE_RETRY_DELAYS_SECONDS,
    sleeper: Callable[[float], object] | None = None,
) -> None:
    """Replace a record after bounded retries for transient Windows locks."""

    pause = sleep if sleeper is None else sleeper
    for delay in (*retry_delays_seconds, None):
        try:
            temporary.replace(target)
            return
        except OSError as exc:
            retryable = isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in {
                5,
                32,
            }
            if not retryable or delay is None:
                raise
            pause(delay)


def publish_atomic_record(
    target: Path,
    payload: bytes,
    *,
    temporary_label: str,
    replacer: RecordReplacer = replace_record_with_retry,
) -> Path:
    """Durably publish bytes by replacing one record in its target directory."""

    if not isinstance(target, Path):
        raise ValueError("target must be Path")
    if not isinstance(payload, bytes):
        raise ValueError("payload must be bytes")
    if not isinstance(temporary_label, str) or _RECORD_LABEL.fullmatch(temporary_label) is None:
        raise ValueError("temporary_label must be a safe record label")
    if not callable(replacer):
        raise ValueError("replacer must be callable")

    directory = target.parent
    temporary = directory / (
        f".{temporary_label}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with temporary.open("xb") as destination:
            destination.write(payload)
            destination.flush()
            os.fsync(destination.fileno())
        replacer(temporary, target)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return target


__all__ = [
    "DEFAULT_ATOMIC_REPLACE_RETRY_DELAYS_SECONDS",
    "publish_atomic_record",
    "replace_record_with_retry",
]
