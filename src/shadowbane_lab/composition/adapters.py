"""Compatibility adapters between stable composition views and rollout tools."""

from __future__ import annotations

from shadowbane_lab.composition.model import (
    BodyValues,
    BuildBlueprint,
    ResolvedBuildView,
    SourcePackageCatalog,
)
from shadowbane_lab.composition.resolver import resolve_build_blueprint
from shadowbane_lab.rollouts.open_builds import PrimitiveLoadout


def primitive_loadout_from_build_view(view: ResolvedBuildView) -> PrimitiveLoadout:
    """Expose a resolved build through the existing classless rollout contract."""

    metadata = dict(view.metadata)
    metadata.update(
        {
            "catalog_id": view.catalog_id,
            "mechanical_signature": view.mechanical_signature,
            "construction_signature": view.construction_signature,
        }
    )
    if view.selected_package_ids:
        metadata["source_package_ids"] = ",".join(view.selected_package_ids)
    notes = list(view.notes)
    if view.omitted_action_keys:
        notes.append("Omitted actions: " + ", ".join(view.omitted_action_keys))
    if view.omitted_persistent_trigger_keys:
        notes.append(
            "Omitted persistent triggers: "
            + ", ".join(view.omitted_persistent_trigger_keys)
        )
    if view.unresolved_training_keys:
        notes.append(
            "Training access unresolved: "
            + ", ".join(view.unresolved_training_keys)
        )
    return PrimitiveLoadout(
        loadout_id=view.build_id,
        display_name=view.display_name,
        action_keys=view.executable_action_keys,
        health=view.body.health,
        mana=view.body.mana,
        stamina=view.body.stamina,
        move_speed=view.body.move_speed,
        tags=view.tags,
        scalars=view.scalars,
        persistent_trigger_keys=view.executable_persistent_trigger_keys,
        metadata=tuple(sorted(metadata.items())),
        notes=tuple(dict.fromkeys(notes)),
    )


def build_view_from_primitive_loadout(
    loadout: PrimitiveLoadout,
    *,
    catalog_id: str = "primitive-loadout-adapter",
    available_action_keys: frozenset[str] | None = None,
    available_persistent_trigger_keys: frozenset[str] | None = None,
) -> ResolvedBuildView:
    """Lift an existing primitive bag into the stable resolved-build contract."""

    blueprint = BuildBlueprint(
        blueprint_id=loadout.loadout_id,
        display_name=loadout.display_name,
        base_body=BodyValues(
            health=loadout.health,
            mana=loadout.mana,
            stamina=loadout.stamina,
            move_speed=loadout.move_speed,
        ),
        direct_action_keys=loadout.action_keys,
        direct_tags=loadout.tags,
        direct_persistent_trigger_keys=loadout.persistent_trigger_keys,
        base_scalars=loadout.scalars,
        metadata=loadout.metadata,
        notes=loadout.notes,
    )
    return resolve_build_blueprint(
        SourcePackageCatalog(catalog_id=catalog_id),
        blueprint,
        available_action_keys=available_action_keys,
        available_persistent_trigger_keys=available_persistent_trigger_keys,
    )
