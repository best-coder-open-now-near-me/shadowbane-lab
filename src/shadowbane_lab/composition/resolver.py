"""Resolve source packages and blueprints into simulator-facing build views."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import isfinite

from shadowbane_lab.composition.model import (
    BodyValues,
    BuildBlueprint,
    CompositionError,
    GrantSource,
    ResolvedBuildView,
    SourcePackage,
    SourcePackageCatalog,
)


class BuildResolutionError(CompositionError):
    """Raised when a build blueprint cannot be resolved consistently."""


def _validate_available(values: frozenset[str] | None, field_name: str) -> None:
    if values is None:
        return
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise BuildResolutionError(f"{field_name} must contain non-empty strings")


@dataclass(frozen=True, slots=True)
class BuildResolver:
    """Close package requirements and materialize one mechanical build view."""

    catalog: SourcePackageCatalog
    available_action_keys: frozenset[str] | None = None
    available_persistent_trigger_keys: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.catalog, SourcePackageCatalog):
            raise BuildResolutionError("catalog must be a SourcePackageCatalog")
        _validate_available(self.available_action_keys, "available_action_keys")
        _validate_available(
            self.available_persistent_trigger_keys,
            "available_persistent_trigger_keys",
        )

    def resolve(self, blueprint: BuildBlueprint) -> ResolvedBuildView:
        if not isinstance(blueprint, BuildBlueprint):
            raise BuildResolutionError("blueprint must be a BuildBlueprint")
        packages = self.catalog.by_id
        unknown = set(blueprint.requested_package_ids) - set(packages)
        if unknown:
            raise BuildResolutionError(
                "blueprint references unknown packages: " + ", ".join(sorted(unknown))
            )

        selected: set[str] = set()
        resolving: list[str] = []

        def include(package_id: str) -> None:
            if package_id in selected:
                return
            if package_id in resolving:
                cycle = (*resolving[resolving.index(package_id) :], package_id)
                raise BuildResolutionError(
                    "package requirement cycle: " + " -> ".join(cycle)
                )
            resolving.append(package_id)
            for required_id in packages[package_id].requires:
                include(required_id)
            resolving.pop()
            selected.add(package_id)

        for package_id in blueprint.requested_package_ids:
            include(package_id)

        for package_id in sorted(selected):
            conflicts = set(packages[package_id].conflicts) & selected
            if conflicts:
                raise BuildResolutionError(
                    f"{package_id} conflicts with " + ", ".join(sorted(conflicts))
                )

        slot_members: dict[str, list[str]] = defaultdict(list)
        for package_id in sorted(selected):
            slot = packages[package_id].selection_slot
            if slot is not None:
                slot_members[slot].append(package_id)
        for slot, package_ids in sorted(slot_members.items()):
            limit = self.catalog.limits_by_slot[slot]
            if len(package_ids) > limit:
                raise BuildResolutionError(
                    f"selection slot {slot} permits {limit} package(s), got: "
                    + ", ".join(package_ids)
                )

        ordered_packages = tuple(packages[key] for key in sorted(selected))
        body = BodyValues(
            health=blueprint.base_body.health
            + sum(package.body_delta.health for package in ordered_packages),
            mana=blueprint.base_body.mana
            + sum(package.body_delta.mana for package in ordered_packages),
            stamina=blueprint.base_body.stamina
            + sum(package.body_delta.stamina for package in ordered_packages),
            move_speed=blueprint.base_body.move_speed
            + sum(package.body_delta.move_speed for package in ordered_packages),
        )

        scalars = dict(blueprint.base_scalars)
        attributes = dict(blueprint.attributes)
        training = dict(blueprint.training)
        for package in ordered_packages:
            _add_pairs(scalars, package.scalar_deltas)
            _add_pairs(attributes, package.attribute_deltas)

        action_sources: dict[str, set[str]] = defaultdict(set)
        tag_sources: dict[str, set[str]] = defaultdict(set)
        trigger_sources: dict[str, set[str]] = defaultdict(set)
        training_access_sources: dict[str, set[str]] = defaultdict(set)
        blueprint_source = f"blueprint:{blueprint.blueprint_id}"
        for action_key in blueprint.direct_action_keys:
            action_sources[action_key].add(blueprint_source)
        for tag in blueprint.direct_tags:
            tag_sources[tag].add(blueprint_source)
        for trigger_key in blueprint.direct_persistent_trigger_keys:
            trigger_sources[trigger_key].add(blueprint_source)
        for package in ordered_packages:
            for action_key in package.action_keys:
                action_sources[action_key].add(package.package_id)
            for tag in package.tags:
                tag_sources[tag].add(package.package_id)
            for trigger_key in package.persistent_trigger_keys:
                trigger_sources[trigger_key].add(package.package_id)
            for training_key in package.training_access_keys:
                training_access_sources[training_key].add(package.package_id)

        requested_actions = tuple(sorted(action_sources))
        executable_actions, omitted_actions = _partition_available(
            requested_actions,
            self.available_action_keys,
        )
        requested_triggers = tuple(sorted(trigger_sources))
        executable_triggers, omitted_triggers = _partition_available(
            requested_triggers,
            self.available_persistent_trigger_keys,
        )
        unresolved_training = tuple(
            sorted(key for key in training if key not in training_access_sources)
        )

        grant_sources = tuple(
            sorted(
                (
                    *(
                        GrantSource("action", key, tuple(sorted(source_ids)))
                        for key, source_ids in action_sources.items()
                    ),
                    *(
                        GrantSource("tag", key, tuple(sorted(source_ids)))
                        for key, source_ids in tag_sources.items()
                    ),
                    *(
                        GrantSource("persistent_trigger", key, tuple(sorted(source_ids)))
                        for key, source_ids in trigger_sources.items()
                    ),
                    *(
                        GrantSource("training_access", key, tuple(sorted(source_ids)))
                        for key, source_ids in training_access_sources.items()
                    ),
                ),
                key=lambda source: (source.grant_kind, source.grant_key),
            )
        )
        selected_ids = tuple(package.package_id for package in ordered_packages)
        auto_added = tuple(
            sorted(set(selected_ids) - set(blueprint.requested_package_ids))
        )
        notes = tuple(
            dict.fromkeys(
                (
                    *blueprint.notes,
                    (
                        "Requirements added automatically: " + ", ".join(auto_added)
                        if auto_added
                        else "No package requirements were added automatically."
                    ),
                )
            )
        )
        return ResolvedBuildView(
            build_id=blueprint.blueprint_id,
            display_name=blueprint.display_name,
            catalog_id=self.catalog.catalog_id,
            body=body,
            requested_package_ids=tuple(sorted(blueprint.requested_package_ids)),
            selected_package_ids=selected_ids,
            auto_added_requirement_ids=auto_added,
            executable_action_keys=executable_actions,
            omitted_action_keys=omitted_actions,
            tags=tuple(sorted(tag_sources)),
            executable_persistent_trigger_keys=executable_triggers,
            omitted_persistent_trigger_keys=omitted_triggers,
            scalars=tuple(sorted(scalars.items())),
            attributes=tuple(sorted(attributes.items())),
            training=tuple(sorted(training.items())),
            unresolved_training_keys=unresolved_training,
            grant_sources=grant_sources,
            metadata=tuple(sorted(blueprint.metadata)),
            notes=notes,
        )


def resolve_build_blueprint(
    catalog: SourcePackageCatalog,
    blueprint: BuildBlueprint,
    *,
    available_action_keys: frozenset[str] | None = None,
    available_persistent_trigger_keys: frozenset[str] | None = None,
) -> ResolvedBuildView:
    return BuildResolver(
        catalog,
        available_action_keys=available_action_keys,
        available_persistent_trigger_keys=available_persistent_trigger_keys,
    ).resolve(blueprint)


def _add_pairs(
    destination: dict[str, float],
    additions: tuple[tuple[str, float], ...],
) -> None:
    for key, value in additions:
        combined = destination.get(key, 0.0) + value
        if not isfinite(combined):
            raise BuildResolutionError(f"resolved numeric value {key} is not finite")
        destination[key] = combined


def _partition_available(
    requested: tuple[str, ...],
    available: frozenset[str] | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if available is None:
        return requested, ()
    return (
        tuple(key for key in requested if key in available),
        tuple(key for key in requested if key not in available),
    )
