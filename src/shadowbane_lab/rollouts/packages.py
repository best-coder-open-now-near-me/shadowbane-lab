"""Assemble open simulation loadouts from a finite package inventory.

Packages describe grants and constraints only. Their labels may correspond to
runes, bodies, promotions, equipment, consumables, or invented search pieces;
the simulator receives only the resulting numbers, tags, and ability recipes.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any

from shadowbane_lab.rollouts.open_builds import PrimitiveLoadout
from shadowbane_lab.sim import DeterministicRandom


class PackageAssemblyError(ValueError):
    """Raised when an inventory or selected package set is malformed."""


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise PackageAssemblyError(f"{field_name} must be a non-empty string")


def _unique_strings(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise PackageAssemblyError(f"{field_name} must not contain duplicates")
    for value in values:
        _identifier(value, field_name)


def _finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise PackageAssemblyError(f"{field_name} must be a finite number")


def _positive(value: float, field_name: str) -> None:
    _finite(value, field_name)
    if value <= 0:
        raise PackageAssemblyError(f"{field_name} must be positive")


@dataclass(frozen=True, slots=True)
class PackagePiece:
    """One selectable source of body modifiers, state tags, and recipes."""

    package_id: str
    display_name: str
    action_keys: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    health_delta: float = 0.0
    mana_delta: float = 0.0
    stamina_delta: float = 0.0
    move_speed_delta: float = 0.0
    requires: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.package_id, "package_id")
        _identifier(self.display_name, "display_name")
        for values, name in (
            (self.action_keys, "action_keys"),
            (self.tags, "tags"),
            (self.requires, "requires"),
            (self.conflicts, "conflicts"),
        ):
            _unique_strings(values, name)
        if self.package_id in self.requires:
            raise PackageAssemblyError("a package cannot require itself")
        if self.package_id in self.conflicts:
            raise PackageAssemblyError("a package cannot conflict with itself")
        for value, name in (
            (self.health_delta, "health_delta"),
            (self.mana_delta, "mana_delta"),
            (self.stamina_delta, "stamina_delta"),
            (self.move_speed_delta, "move_speed_delta"),
        ):
            _finite(value, name)
        metadata_keys = tuple(key for key, _ in self.metadata)
        _unique_strings(metadata_keys, "metadata keys")
        for key, value in self.metadata:
            _identifier(key, "metadata key")
            _identifier(value, f"metadata.{key}")


@dataclass(frozen=True, slots=True)
class PackageInventory:
    """Finite toolbox from which candidate loadouts may be assembled."""

    inventory_id: str
    packages: tuple[PackagePiece, ...]
    base_health: float = 500.0
    base_mana: float = 300.0
    base_stamina: float = 200.0
    base_move_speed: float = 15.0
    base_tags: tuple[str, ...] = ()
    selection_minimum: int = 1
    selection_maximum: int | None = None

    def __post_init__(self) -> None:
        _identifier(self.inventory_id, "inventory_id")
        if not self.packages:
            raise PackageAssemblyError("an inventory requires at least one package")
        package_ids = tuple(item.package_id for item in self.packages)
        _unique_strings(package_ids, "package ids")
        _unique_strings(self.base_tags, "base_tags")
        for value, name in (
            (self.base_health, "base_health"),
            (self.base_mana, "base_mana"),
            (self.base_stamina, "base_stamina"),
            (self.base_move_speed, "base_move_speed"),
        ):
            _positive(value, name)
        if (
            isinstance(self.selection_minimum, bool)
            or not isinstance(self.selection_minimum, int)
            or self.selection_minimum < 1
        ):
            raise PackageAssemblyError("selection_minimum must be positive")
        maximum = self.selection_maximum
        if maximum is None:
            maximum = len(self.packages)
            object.__setattr__(self, "selection_maximum", maximum)
        if (
            isinstance(maximum, bool)
            or not isinstance(maximum, int)
            or maximum < self.selection_minimum
            or maximum > len(self.packages)
        ):
            raise PackageAssemblyError(
                "selection_maximum must be between selection_minimum and package count"
            )
        known = set(package_ids)
        for package in self.packages:
            unknown = (set(package.requires) | set(package.conflicts)) - known
            if unknown:
                raise PackageAssemblyError(
                    f"{package.package_id} references unknown packages: "
                    + ", ".join(sorted(unknown))
                )

    @property
    def by_id(self) -> dict[str, PackagePiece]:
        return {item.package_id: item for item in self.packages}


@dataclass(frozen=True, slots=True)
class PackageAssembly:
    inventory_id: str
    requested_package_ids: tuple[str, ...]
    selected_package_ids: tuple[str, ...]
    auto_added_requirement_ids: tuple[str, ...]
    loadout: PrimitiveLoadout

    def as_dict(self) -> dict[str, object]:
        return {
            "inventory_id": self.inventory_id,
            "requested_package_ids": list(self.requested_package_ids),
            "selected_package_ids": list(self.selected_package_ids),
            "auto_added_requirement_ids": list(self.auto_added_requirement_ids),
            "loadout": self.loadout.as_dict(),
        }


def assemble_package_loadout(
    inventory: PackageInventory,
    package_ids: tuple[str, ...],
    *,
    loadout_id: str,
    display_name: str,
) -> PackageAssembly:
    """Close requirements, reject conflicts, and cookie-cut one loadout."""

    _identifier(loadout_id, "loadout_id")
    _identifier(display_name, "display_name")
    if not package_ids:
        raise PackageAssemblyError("at least one package must be requested")
    _unique_strings(package_ids, "requested package ids")
    packages = inventory.by_id
    unknown = set(package_ids) - set(packages)
    if unknown:
        raise PackageAssemblyError(
            "selection contains unknown packages: " + ", ".join(sorted(unknown))
        )

    selected: set[str] = set()
    resolving: set[str] = set()

    def include(package_id: str) -> None:
        if package_id in selected:
            return
        if package_id in resolving:
            raise PackageAssemblyError(
                f"package requirements contain a cycle involving {package_id}"
            )
        resolving.add(package_id)
        for required_id in packages[package_id].requires:
            include(required_id)
        resolving.remove(package_id)
        selected.add(package_id)

    for package_id in package_ids:
        include(package_id)

    for package_id in sorted(selected):
        conflicts = set(packages[package_id].conflicts) & selected
        if conflicts:
            raise PackageAssemblyError(
                f"{package_id} conflicts with " + ", ".join(sorted(conflicts))
            )

    ordered = tuple(sorted(selected))
    health = inventory.base_health + sum(packages[key].health_delta for key in ordered)
    mana = inventory.base_mana + sum(packages[key].mana_delta for key in ordered)
    stamina = inventory.base_stamina + sum(packages[key].stamina_delta for key in ordered)
    move_speed = inventory.base_move_speed + sum(packages[key].move_speed_delta for key in ordered)
    for value, name in (
        (health, "assembled health"),
        (mana, "assembled mana"),
        (stamina, "assembled stamina"),
        (move_speed, "assembled move speed"),
    ):
        _positive(value, name)

    action_keys = tuple(
        sorted(
            {
                action_key
                for package_id in ordered
                for action_key in packages[package_id].action_keys
            }
        )
    )
    tags = tuple(
        sorted(
            set(inventory.base_tags)
            | {tag for package_id in ordered for tag in packages[package_id].tags}
        )
    )
    auto_added = tuple(sorted(selected - set(package_ids)))
    loadout = PrimitiveLoadout(
        loadout_id=loadout_id,
        display_name=display_name,
        action_keys=action_keys,
        health=health,
        mana=mana,
        stamina=stamina,
        move_speed=move_speed,
        tags=tags,
        metadata=(
            ("inventory_id", inventory.inventory_id),
            ("package_ids", ",".join(ordered)),
        ),
        notes=(
            "Assembled from a finite package inventory.",
            (
                "Requirements added automatically: " + ", ".join(auto_added)
                if auto_added
                else "No package requirements were added automatically."
            ),
        ),
    )
    return PackageAssembly(
        inventory_id=inventory.inventory_id,
        requested_package_ids=package_ids,
        selected_package_ids=ordered,
        auto_added_requirement_ids=auto_added,
        loadout=loadout,
    )


def generate_inventory_loadouts(
    inventory: PackageInventory,
    *,
    count: int,
    seed: int,
    minimum_packages: int | None = None,
    maximum_packages: int | None = None,
) -> tuple[PackageAssembly, ...]:
    """Generate reproducible legal package combinations from one toolbox."""

    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise PackageAssemblyError("count must be a positive integer")
    minimum = minimum_packages or inventory.selection_minimum
    maximum = maximum_packages or inventory.selection_maximum
    if (
        isinstance(minimum, bool)
        or not isinstance(minimum, int)
        or minimum < inventory.selection_minimum
    ):
        raise PackageAssemblyError("minimum_packages is below the inventory minimum")
    if (
        isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or maximum > inventory.selection_maximum
        or maximum < minimum
    ):
        raise PackageAssemblyError("maximum_packages is outside inventory bounds")

    rng = DeterministicRandom(seed)
    package_ids = tuple(sorted(inventory.by_id))
    signatures: set[tuple[str, ...]] = set()
    assemblies: list[PackageAssembly] = []
    attempts = 0
    while len(assemblies) < count and attempts < max(200, count * 300):
        attempts += 1
        desired = minimum + rng.randbelow(maximum - minimum + 1)
        remaining = list(package_ids)
        requested: list[str] = []
        while len(requested) < desired and remaining:
            index = rng.randbelow(len(remaining))
            requested.append(remaining.pop(index))
        try:
            assembly = assemble_package_loadout(
                inventory,
                tuple(sorted(requested)),
                loadout_id=f"{inventory.inventory_id}.{seed}.{len(assemblies):03d}",
                display_name=f"{inventory.inventory_id} candidate {len(assemblies):03d}",
            )
        except PackageAssemblyError:
            continue
        signature = assembly.selected_package_ids
        if signature in signatures or not assembly.loadout.action_keys:
            continue
        signatures.add(signature)
        assemblies.append(assembly)
    if len(assemblies) != count:
        raise PackageAssemblyError(
            f"could generate only {len(assemblies)} unique package assemblies"
        )
    return tuple(assemblies)


def load_package_inventory(path: str | Path) -> PackageInventory:
    return load_package_inventory_text(Path(path).read_text(encoding="utf-8"))


def load_package_inventory_text(text: str) -> PackageInventory:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PackageAssemblyError("inventory is not valid JSON") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise PackageAssemblyError("inventory must be a schema-version-1 object")
    package_values = raw.get("packages")
    if not isinstance(package_values, list) or not package_values:
        raise PackageAssemblyError("inventory packages must be a non-empty array")

    body = raw.get("body", {})
    if not isinstance(body, dict):
        raise PackageAssemblyError("body must be an object")
    packages = tuple(_parse_package(value, index) for index, value in enumerate(package_values))
    return PackageInventory(
        inventory_id=raw.get("inventory_id", ""),
        packages=packages,
        base_health=body.get("health", 500.0),
        base_mana=body.get("mana", 300.0),
        base_stamina=body.get("stamina", 200.0),
        base_move_speed=body.get("move_speed", 15.0),
        base_tags=_strings(body, "tags", "body"),
        selection_minimum=raw.get("selection_minimum", 1),
        selection_maximum=raw.get("selection_maximum"),
    )


def _parse_package(raw: Any, index: int) -> PackagePiece:
    if not isinstance(raw, dict):
        raise PackageAssemblyError(f"packages[{index}] must be an object")
    modifiers = raw.get("modifiers", {})
    if not isinstance(modifiers, dict):
        raise PackageAssemblyError(f"packages[{index}].modifiers must be an object")
    metadata = raw.get("metadata", {})
    if not isinstance(metadata, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in metadata.items()
    ):
        raise PackageAssemblyError(f"packages[{index}].metadata must map strings to strings")
    return PackagePiece(
        package_id=raw.get("package_id", ""),
        display_name=raw.get("display_name", ""),
        action_keys=_strings(raw, "action_keys", f"packages[{index}]"),
        tags=_strings(raw, "tags", f"packages[{index}]"),
        health_delta=modifiers.get("health", 0.0),
        mana_delta=modifiers.get("mana", 0.0),
        stamina_delta=modifiers.get("stamina", 0.0),
        move_speed_delta=modifiers.get("move_speed", 0.0),
        requires=_strings(raw, "requires", f"packages[{index}]"),
        conflicts=_strings(raw, "conflicts", f"packages[{index}]"),
        metadata=tuple(sorted(metadata.items())),
    )


def _strings(raw: dict[str, Any], key: str, context: str) -> tuple[str, ...]:
    values = raw.get(key, [])
    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
        raise PackageAssemblyError(f"{context}.{key} must contain strings")
    return tuple(values)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m shadowbane_lab.rollouts.packages",
        description="Generate open-loadout rosters from a finite package inventory.",
    )
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--generate", type=int, default=24)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--min-packages", type=int)
    parser.add_argument("--max-packages", type=int)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    inventory = load_package_inventory(arguments.inventory)
    assemblies = generate_inventory_loadouts(
        inventory,
        count=arguments.generate,
        seed=arguments.seed,
        minimum_packages=arguments.min_packages,
        maximum_packages=arguments.max_packages,
    )
    payload = {
        "schema_version": 1,
        "inventory_id": inventory.inventory_id,
        "assemblies": [item.as_dict() for item in assemblies],
        "loadouts": [item.loadout.as_dict() for item in assemblies],
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(assemblies)} package assemblies to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
