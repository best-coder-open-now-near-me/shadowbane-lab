"""Project only source-backed static action prerequisites from compiled builds."""

from __future__ import annotations

from dataclasses import dataclass

from .build_model import CompiledLegalBuild, LegalBuildCompileError, canonical_digest

_MELEE_RANGE_MAXIMUM = 6.0
_STATIC_TRAINING_TAGS = (
    ("stalk", 1, "power.stalk"),
)


@dataclass(frozen=True, slots=True)
class StaticCapabilityGrant:
    tag: str
    source_kind: str
    source_key: str
    evidence_status: str

    def __post_init__(self) -> None:
        for field_name in ("tag", "source_kind", "source_key", "evidence_status"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise LegalBuildCompileError(f"{field_name} must be non-empty text")

    def as_dict(self) -> dict[str, str]:
        return {
            "tag": self.tag,
            "source_kind": self.source_kind,
            "source_key": self.source_key,
            "evidence_status": self.evidence_status,
        }


@dataclass(frozen=True, slots=True)
class StaticCapabilityProjection:
    base_tags: tuple[str, ...]
    grants: tuple[StaticCapabilityGrant, ...]
    unresolved: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for values, field_name in (
            (self.base_tags, "base_tags"),
            (self.unresolved, "unresolved"),
        ):
            if len(values) != len(set(values)) or any(
                not isinstance(item, str) or not item.strip() for item in values
            ):
                raise LegalBuildCompileError(
                    f"{field_name} must contain unique non-empty strings"
                )
        if any(not isinstance(item, StaticCapabilityGrant) for item in self.grants):
            raise LegalBuildCompileError(
                "grants must contain StaticCapabilityGrant values"
            )
        tags = tuple(item.tag for item in self.grants)
        if len(tags) != len(set(tags)):
            raise LegalBuildCompileError("static capability grants must have unique tags")

    @property
    def tags(self) -> tuple[str, ...]:
        return tuple(sorted({*self.base_tags, *(item.tag for item in self.grants)}))

    @property
    def projection_digest(self) -> str:
        return canonical_digest(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "base_tags": list(self.base_tags),
            "grants": [item.as_dict() for item in self.grants],
            "tags": list(self.tags),
            "unresolved": list(self.unresolved),
        }


def project_static_capabilities(
    compilation: CompiledLegalBuild,
) -> StaticCapabilityProjection:
    """Translate explicit equipment/training evidence into required actor tags."""

    if not isinstance(compilation, CompiledLegalBuild):
        raise LegalBuildCompileError("compilation must be CompiledLegalBuild")
    grants: dict[str, StaticCapabilityGrant] = {}
    unresolved: set[str] = set()
    skills = dict(compilation.genome.skill_ranks)
    for skill_key, minimum_rank, tag in _STATIC_TRAINING_TAGS:
        if skills.get(skill_key, 0) >= minimum_rank:
            grants[tag] = StaticCapabilityGrant(
                tag=tag,
                source_kind="selected_training",
                source_key=f"skill.{skill_key}",
                evidence_status="selected_rank",
            )

    scalars = dict(compilation.view.scalars)
    melee_slots: list[str] = []
    for slot in ("main_hand", "off_hand"):
        prefix = f"weapon.{slot}"
        minimum = scalars.get(f"{prefix}.damage_min")
        maximum = scalars.get(f"{prefix}.damage_max")
        weapon_range = scalars.get(f"{prefix}.range")
        selected = next(
            (
                item
                for item in compilation.genome.equipment
                if item.slot_key == slot
            ),
            None,
        )
        if selected is None:
            continue
        grants[f"equipment.slot.{slot}"] = StaticCapabilityGrant(
            tag=f"equipment.slot.{slot}",
            source_kind="equipment_selection",
            source_key=f"item.{selected.item_id}",
            evidence_status="selected_item",
        )
        if minimum is None or maximum is None or weapon_range is None:
            unresolved.add(f"equipment.{slot}.weapon_capability_unresolved")
            continue
        if maximum <= minimum or weapon_range > _MELEE_RANGE_MAXIMUM:
            continue
        melee_slots.append(slot)
        grants["equipment.melee_weapon"] = StaticCapabilityGrant(
            tag="equipment.melee_weapon",
            source_kind="compiled_equipment_scalars",
            source_key=f"item.{selected.item_id}",
            evidence_status=(
                "candidate_base_item_values"
                if compilation.coverage.candidate_equipment_values_applied
                else "verified_base_item_values"
            ),
        )

    if len(melee_slots) == 2:
        grants["equipment.dual_wield"] = StaticCapabilityGrant(
            tag="equipment.dual_wield",
            source_kind="equipment_selection",
            source_key="main_hand+off_hand",
            evidence_status="selected_items",
        )
    return StaticCapabilityProjection(
        base_tags=tuple(sorted(compilation.view.tags)),
        grants=tuple(grants[key] for key in sorted(grants)),
        unresolved=tuple(sorted(unresolved)),
    )


__all__ = [
    "StaticCapabilityGrant",
    "StaticCapabilityProjection",
    "project_static_capabilities",
]
