"""Typed equipment and affix catalog for build optimization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AffixPosition(StrEnum):
    PREFIX = "prefix"
    SUFFIX = "suffix"


@dataclass(frozen=True, slots=True)
class ItemRequirement:
    kind: int
    required: bool
    token: int


@dataclass(frozen=True, slots=True)
class BaseItem:
    item_id: int
    name: str
    historical_name: str
    item_type: str
    durability: float
    equip_flags: int
    restrict_flags: int
    value: int
    weight: int
    skill_required: str
    skill_percent_required: int
    mastery: str | None
    slash_resist: float
    crush_resist: float
    pierce_resist: float
    block_modifier: float
    defense: int
    dexterity_penalty: float
    damage_type: str | None
    speed: float
    range: float
    minimum_damage: int
    maximum_damage: int
    two_handed: bool
    strength_based: bool
    parry_bonus: float
    modifier_table_id: int
    item_hash_id: int
    current_name_verified: bool
    requirements: tuple[ItemRequirement, ...]


@dataclass(frozen=True, slots=True)
class AffixChoice:
    table_id: int
    action_id: str


@dataclass(frozen=True, slots=True)
class AffixModifier:
    table_id: int
    table_name: str
    minimum_roll: float
    maximum_roll: float
    action_id: str
    level: int
    value: int
    current_prefix_name: str | None
    current_suffix_name: str | None

    @property
    def choice(self) -> AffixChoice:
        return AffixChoice(self.table_id, self.action_id)


@dataclass(frozen=True, slots=True)
class AffixPoolEntry:
    minimum_roll: int
    maximum_roll: int
    modifier_table_id: int
    modifier_table_name: str


@dataclass(frozen=True, slots=True)
class AffixPool:
    pool_id: int
    name: str
    positions: tuple[AffixPosition, ...]
    entries: tuple[AffixPoolEntry, ...]


@dataclass(frozen=True, slots=True)
class AffixRoute:
    generation_table_id: int
    generation_table_name: str
    item_table_id: int
    item_table_name: str
    item_id: int
    prefix_pool_id: int | None
    suffix_pool_id: int | None


@dataclass(frozen=True, slots=True)
class EquipmentCatalog:
    catalog_id: str
    target_variant: str
    status: str
    retrieved_on: str
    sources: tuple[dict[str, object], ...]
    coverage: dict[str, object]
    current_client: dict[str, object]
    base_items: tuple[BaseItem, ...]
    modifiers: tuple[AffixModifier, ...]
    pools: tuple[AffixPool, ...]
    routes: tuple[AffixRoute, ...]

    def __post_init__(self) -> None:
        self._unique((item.item_id for item in self.base_items), "base item")
        self._unique(
            ((item.table_id, item.action_id) for item in self.modifiers),
            "affix modifier",
        )
        self._unique((item.pool_id for item in self.pools), "affix pool")

        item_ids = {item.item_id for item in self.base_items}
        modifier_table_ids = {item.table_id for item in self.modifiers}
        pool_ids = {item.pool_id for item in self.pools}
        for pool in self.pools:
            if not pool.positions:
                raise ValueError(f"affix pool {pool.pool_id} has no position")
            for entry in pool.entries:
                if entry.modifier_table_id not in modifier_table_ids:
                    raise ValueError(
                        f"affix pool {pool.pool_id} references unknown modifier table "
                        f"{entry.modifier_table_id}"
                    )
        for route in self.routes:
            if route.item_id not in item_ids:
                raise ValueError(f"affix route references unknown item {route.item_id}")
            for pool_id in (route.prefix_pool_id, route.suffix_pool_id):
                if pool_id is not None and pool_id not in pool_ids:
                    raise ValueError(f"affix route references unknown pool {pool_id}")

    @staticmethod
    def _unique(values, label: str) -> None:
        materialized = tuple(values)
        if len(materialized) != len(set(materialized)):
            raise ValueError(f"{label} identifiers must be unique")

    def item(self, item_id: int) -> BaseItem:
        for item in self.base_items:
            if item.item_id == item_id:
                return item
        raise KeyError(item_id)

    def choices_for(self, item_id: int, position: AffixPosition) -> tuple[AffixModifier, ...]:
        pool_ids = {
            route.prefix_pool_id if position is AffixPosition.PREFIX else route.suffix_pool_id
            for route in self.routes
            if route.item_id == item_id
        }
        pool_ids.discard(None)
        table_ids = {
            entry.modifier_table_id
            for pool in self.pools
            if pool.pool_id in pool_ids
            for entry in pool.entries
        }
        return tuple(item for item in self.modifiers if item.table_id in table_ids)

    def current_affix_names(self, position: AffixPosition) -> dict[str, str]:
        """Return the complete current-client display dictionary for one affix position."""

        key = "prefixes" if position is AffixPosition.PREFIX else "suffixes"
        dictionary = self.current_client["affix_dictionary"]
        return {item["key"]: item["display_name"] for item in dictionary[key]}

    def is_valid_affix_pair(
        self,
        item_id: int,
        *,
        prefix: AffixChoice | None = None,
        suffix: AffixChoice | None = None,
    ) -> bool:
        """Return whether one historical route permits this exact affix pair.

        This validates item/affix compatibility only. Opaque class and rune requirement
        tokens are preserved on :class:`BaseItem` but deliberately are not guessed here.
        """

        if prefix is None and suffix is None:
            return any(item.item_id == item_id for item in self.base_items)
        pools = {pool.pool_id: pool for pool in self.pools}
        modifiers = {(item.table_id, item.action_id) for item in self.modifiers}
        for route in self.routes:
            if route.item_id != item_id:
                continue
            prefix_allowed = self._route_accepts(
                route.prefix_pool_id, prefix, pools, modifiers
            )
            suffix_allowed = self._route_accepts(
                route.suffix_pool_id, suffix, pools, modifiers
            )
            if prefix_allowed and suffix_allowed:
                return True
        return False

    @staticmethod
    def _route_accepts(pool_id, choice, pools, modifiers) -> bool:
        if choice is None:
            return True
        if pool_id is None or (choice.table_id, choice.action_id) not in modifiers:
            return False
        return any(
            entry.modifier_table_id == choice.table_id for entry in pools[pool_id].entries
        )
