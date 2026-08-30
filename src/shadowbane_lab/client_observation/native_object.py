"""Reusable native object identity values with no reader dependencies."""

from __future__ import annotations

from dataclasses import dataclass


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _native_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"{field_name} must be an unsigned 32-bit integer")


@dataclass(frozen=True, slots=True, order=True)
class NativeObjectKey:
    """Shadowbane's lossless object type plus runtime UUID identity."""

    object_type: int
    object_uuid: int

    def __post_init__(self) -> None:
        _native_integer(self.object_type, "object_type")
        _native_integer(self.object_uuid, "object_uuid")

    @property
    def is_null(self) -> bool:
        return self.object_type == 0 and self.object_uuid == 0

    @property
    def canonical_token(self) -> str:
        return f"{self.object_type:08x}:{self.object_uuid:08x}"

    def as_dict(self) -> dict[str, int]:
        return {
            "object_type": self.object_type,
            "object_uuid": self.object_uuid,
        }

    @classmethod
    def from_dict(cls, raw: object) -> NativeObjectKey:
        if not isinstance(raw, dict):
            raise ValueError("native object key must be an object")
        expected = {"object_type", "object_uuid"}
        unknown = set(raw) - expected
        missing = expected - set(raw)
        if unknown:
            raise ValueError("native object key has unknown fields: " + ", ".join(sorted(unknown)))
        if missing:
            raise ValueError("native object key is missing fields: " + ", ".join(sorted(missing)))
        return cls(
            object_type=raw["object_type"],
            object_uuid=raw["object_uuid"],
        )


@dataclass(frozen=True, slots=True)
class NativeEntityBinding:
    """One explicit native-key to simulator-entity binding."""

    object_key: NativeObjectKey
    entity_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.object_key, NativeObjectKey):
            raise ValueError("object_key must be a NativeObjectKey")
        if self.object_key.is_null:
            raise ValueError("a null native object key cannot bind an entity")
        _identifier(self.entity_id, "entity_id")


@dataclass(frozen=True, slots=True)
class NativeEntityIdentityMap:
    """Snapshot-scoped one-to-one mapping that keeps pointers out of simulator IDs."""

    bindings: tuple[NativeEntityBinding, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.bindings, tuple):
            raise ValueError("bindings must be a tuple")
        if any(not isinstance(binding, NativeEntityBinding) for binding in self.bindings):
            raise ValueError("bindings must contain NativeEntityBinding values")
        object_keys = tuple(binding.object_key for binding in self.bindings)
        entity_ids = tuple(binding.entity_id for binding in self.bindings)
        if len(object_keys) != len(set(object_keys)):
            raise ValueError("native object keys must be unique")
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("simulator entity ids must be unique")

    @property
    def canonical_bindings(self) -> tuple[NativeEntityBinding, ...]:
        return tuple(
            sorted(
                self.bindings,
                key=lambda binding: (
                    binding.object_key.object_type,
                    binding.object_key.object_uuid,
                    binding.entity_id,
                ),
            )
        )

    def entity_id_for(self, object_key: NativeObjectKey) -> str | None:
        if not isinstance(object_key, NativeObjectKey):
            raise ValueError("object_key must be a NativeObjectKey")
        return next(
            (binding.entity_id for binding in self.bindings if binding.object_key == object_key),
            None,
        )

    def object_key_for(self, entity_id: str) -> NativeObjectKey | None:
        _identifier(entity_id, "entity_id")
        return next(
            (binding.object_key for binding in self.bindings if binding.entity_id == entity_id),
            None,
        )

    def require_entity_id(self, object_key: NativeObjectKey) -> str:
        entity_id = self.entity_id_for(object_key)
        if entity_id is None:
            raise KeyError(f"native object key {object_key.canonical_token} is unbound")
        return entity_id

    def with_binding(
        self,
        object_key: NativeObjectKey,
        entity_id: str,
    ) -> NativeEntityIdentityMap:
        binding = NativeEntityBinding(object_key, entity_id)
        return NativeEntityIdentityMap((*self.bindings, binding))
