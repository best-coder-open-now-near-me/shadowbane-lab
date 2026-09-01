"""Create-only durable file placement."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .canonical import pretty_json_text


class CreateOnlyError(RuntimeError):
    """Raised when a create-only write cannot be completed safely."""


def create_only_bytes(path: Path, payload: bytes, *, make_parents: bool = False) -> None:
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    if make_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("write returned no progress")
            offset += written
        os.fsync(descriptor)
    except FileExistsError as exc:
        raise CreateOnlyError(f"destination already exists: {path}") from exc
    except OSError as exc:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
            descriptor = None
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise CreateOnlyError(f"cannot create destination: {path}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def create_only_text(path: Path, payload: str, *, make_parents: bool = False) -> None:
    if not isinstance(payload, str):
        raise TypeError("payload must be text")
    create_only_bytes(path, payload.encode("utf-8"), make_parents=make_parents)


def create_only_json(path: Path, payload: Any, *, make_parents: bool = False) -> None:
    create_only_text(path, pretty_json_text(payload), make_parents=make_parents)


__all__ = ["CreateOnlyError", "create_only_bytes", "create_only_json", "create_only_text"]
