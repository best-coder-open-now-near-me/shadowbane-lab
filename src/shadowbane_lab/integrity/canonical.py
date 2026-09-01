"""Strict finite JSON decoding and canonical serialization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class IntegrityJsonError(ValueError):
    """Raised when JSON cannot be trusted as a bounded canonical value."""


@dataclass(frozen=True, slots=True)
class JsonBounds:
    maximum_bytes: int = 16 * 1024 * 1024
    maximum_depth: int = 64
    maximum_nodes: int = 1_000_000
    maximum_string_length: int = 4 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in (
            "maximum_bytes",
            "maximum_depth",
            "maximum_nodes",
            "maximum_string_length",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_JSON_BOUNDS = JsonBounds()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IntegrityJsonError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise IntegrityJsonError(f"non-finite JSON number is not permitted: {value}")


def strict_json_loads(
    source: str | bytes | bytearray,
    *,
    bounds: JsonBounds = DEFAULT_JSON_BOUNDS,
) -> Any:
    if isinstance(source, str):
        encoded_size = len(source.encode("utf-8"))
    elif isinstance(source, (bytes, bytearray)):
        encoded_size = len(source)
    else:
        raise TypeError("JSON source must be text or bytes")
    if encoded_size > bounds.maximum_bytes:
        raise IntegrityJsonError("JSON source exceeds the configured byte limit")
    try:
        value = json.loads(
            source,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise IntegrityJsonError(f"invalid JSON: {exc}") from exc
    _validate_bounds(value, bounds)
    return value


def load_strict_json(
    path: Path,
    *,
    bounds: JsonBounds = DEFAULT_JSON_BOUNDS,
) -> Any:
    try:
        with path.open("rb") as stream:
            source = stream.read(bounds.maximum_bytes + 1)
    except OSError as exc:
        raise IntegrityJsonError(f"cannot read JSON file: {path}: {exc}") from exc
    return strict_json_loads(source, bounds=bounds)


def validate_finite_json(value: Any, *, bounds: JsonBounds = DEFAULT_JSON_BOUNDS) -> None:
    _validate_bounds(value, bounds)
    try:
        json.dumps(value, allow_nan=False, ensure_ascii=True, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise IntegrityJsonError(f"value must be finite JSON: {exc}") from exc


def canonical_json_text(value: Any) -> str:
    validate_finite_json(value)
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_json_bytes(value: Any) -> bytes:
    return canonical_json_text(value).encode("ascii")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def pretty_json_text(value: Any) -> str:
    validate_finite_json(value)
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _validate_bounds(value: Any, bounds: JsonBounds) -> None:
    nodes = 0
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > bounds.maximum_nodes:
            raise IntegrityJsonError("JSON value exceeds the configured node limit")
        if depth > bounds.maximum_depth:
            raise IntegrityJsonError("JSON value exceeds the configured depth limit")
        if isinstance(current, str):
            if len(current) > bounds.maximum_string_length:
                raise IntegrityJsonError("JSON string exceeds the configured length limit")
        elif current is None or isinstance(current, bool | int):
            continue
        elif isinstance(current, float):
            if current != current or current in (float("inf"), float("-inf")):
                raise IntegrityJsonError("JSON numbers must be finite")
        elif isinstance(current, list | tuple):
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, dict):
            for key, item in current.items():
                if not isinstance(key, str):
                    raise IntegrityJsonError("JSON object keys must be strings")
                if len(key) > bounds.maximum_string_length:
                    raise IntegrityJsonError("JSON object key exceeds the configured length limit")
                stack.append((item, depth + 1))
        else:
            raise IntegrityJsonError(f"value contains a non-JSON type: {type(current).__name__}")


__all__ = [
    "DEFAULT_JSON_BOUNDS",
    "IntegrityJsonError",
    "JsonBounds",
    "canonical_json_bytes",
    "canonical_json_sha256",
    "canonical_json_text",
    "load_strict_json",
    "pretty_json_text",
    "strict_json_loads",
    "validate_finite_json",
]
