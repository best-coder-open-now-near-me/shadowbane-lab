"""Deep-immutable finite JSON values for identity-bearing contracts."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any, TypeAlias


@dataclass(frozen=True, slots=True)
class FrozenJsonObject(Mapping[str, "FrozenJson"]):
    """Canonical immutable JSON object backed by sorted key/value pairs."""

    _items: tuple[tuple[str, Any], ...]

    def __post_init__(self) -> None:
        keys = tuple(key for key, _ in self._items)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise ValueError("frozen JSON object keys must be unique and sorted")
        if any(not isinstance(key, str) for key in keys):
            raise ValueError("frozen JSON object keys must be strings")
        if any(not _is_frozen_json(value) for _, value in self._items):
            raise ValueError("frozen JSON object contains a mutable or non-JSON value")

    def __getitem__(self, key: str) -> FrozenJson:
        for candidate, value in self._items:
            if candidate == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __hash__(self) -> int:
        return hash(self._items)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mapping):
            return False
        return dict(self.items()) == dict(other.items())


FrozenJson: TypeAlias = (
    None | bool | int | float | str | tuple["FrozenJson", ...] | FrozenJsonObject
)


def freeze_json(value: Any) -> FrozenJson:
    """Validate, copy, and recursively freeze one finite JSON value."""

    from .canonical import validate_finite_json

    validate_finite_json(value)
    return _freeze_json(value)


def thaw_json(value: Any) -> Any:
    """Return a detached ordinary dict/list representation of a JSON value."""

    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [thaw_json(item) for item in value]
    return value


def _freeze_json(value: Any) -> FrozenJson:
    if isinstance(value, Mapping):
        return FrozenJsonObject(
            tuple(sorted((key, _freeze_json(item)) for key, item in value.items()))
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze_json(item) for item in value)
    return value


def _is_frozen_json(value: Any) -> bool:
    if value is None or isinstance(value, bool | int | str):
        return True
    if isinstance(value, float):
        return isfinite(value)
    if isinstance(value, tuple):
        return all(_is_frozen_json(item) for item in value)
    return isinstance(value, FrozenJsonObject)


__all__ = ["FrozenJson", "FrozenJsonObject", "freeze_json", "thaw_json"]
