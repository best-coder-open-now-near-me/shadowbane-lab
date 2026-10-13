"""Immutable random recipe and quantity-order intent with owned preparation evidence."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .vendor_wire import uint

RANDOM_SENTINEL = 3362971591


@dataclass(frozen=True, slots=True)
class RandomRecipeSpec:
    template: int
    table: int

    def __post_init__(self):
        if (not uint(self.template, 32, "recipe template")
                or not uint(self.table, 32, "recipe table")):
            raise ValueError("random recipe requires nonzero template and table")

    def as_dict(self) -> dict:
        return dict(template=dict(object_id=self.template, object_type=0), mode=1,
                    table=self.table, sentinel=RANDOM_SENTINEL, prefix=RANDOM_SENTINEL,
                    suffix=RANDOM_SENTINEL, quantity=1, multiple=False)

    @classmethod
    def from_dict(cls, value) -> RandomRecipeSpec:
        try:
            result = cls(value["template"]["object_id"], value["table"])
            if json.dumps(value, sort_keys=True) != json.dumps(result.as_dict(), sort_keys=True):
                raise ValueError("noncanonical random recipe specification")
            return result
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError("expected an exact single-item random recipe specification") from exc

    @property
    def canonical_digest(self) -> str:
        raw = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def matches(self, snapshot) -> bool:
        snapshot.encode()
        return bool(snapshot.recipe and snapshot.item_template == self.template
                    and snapshot.table == self.table and snapshot.mode == 1
                    and snapshot.prefix == snapshot.suffix == RANDOM_SENTINEL
                    and snapshot.quantity == 1 and snapshot.multiple == 0)


@dataclass(frozen=True, slots=True)
class RandomOrderSpec:
    recipe: RandomRecipeSpec
    quantity: int = 10

    def __post_init__(self):
        if (type(self.recipe) is not RandomRecipeSpec or type(self.quantity) is not int
                or not 1 <= self.quantity <= 10):
            raise ValueError("a random recipe and quantity 1–10 per slot are required")

    @property
    def template(self) -> int:
        return self.recipe.template

    @property
    def table(self) -> int:
        return self.recipe.table

    def as_dict(self) -> dict:
        return dict(self.recipe.as_dict(), quantity=self.quantity, multiple=True)

    @classmethod
    def from_dict(cls, value) -> RandomOrderSpec:
        try:
            result = cls(RandomRecipeSpec(value["template"]["object_id"], value["table"]),
                         value["quantity"])
            if json.dumps(value, sort_keys=True) != json.dumps(result.as_dict(), sort_keys=True):
                raise ValueError("noncanonical order recipe specification")
            return result
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError("expected an exact multiple-slot random order specification") from exc

    @property
    def canonical_digest(self) -> str:
        raw = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()

    def matches(self, snapshot) -> bool:
        snapshot.encode()
        return bool(snapshot.recipe and snapshot.item_template == self.template
                    and snapshot.table == self.table and snapshot.mode == 1
                    and snapshot.prefix == snapshot.suffix == RANDOM_SENTINEL
                    and snapshot.quantity == self.quantity and snapshot.multiple == 1)


def validate_recipe_preparation(
    raw: bytes, recipe: RandomRecipeSpec | RandomOrderSpec, initial, *, process_id: int,
    process_creation_filetime_utc: int, window: int,
) -> dict:
    """Bind completed menu proof to the exact recipe, client and current visit.

    Spending and menu snapshot revisions belong to different controllers. All
    their shared identity/recipe fields must match; revisions are not comparable.
    """
    from .vendor_menu import validate_completed_menu

    if type(recipe) not in (RandomRecipeSpec, RandomOrderSpec):
        raise ValueError("an immutable random recipe specification is required")
    record, _, final = validate_completed_menu(raw)
    expected_operation = "prepare_order" if type(recipe) is RandomOrderSpec else "prepare_recipe"
    if (record["operation"] != expected_operation
            or type(recipe).from_dict(record["requested_recipe"]) != recipe
            or record["process_id"] != process_id
            or record["process_creation_filetime_utc"] != process_creation_filetime_utc
            or record["window"] != window or not recipe.matches(initial)
            or not recipe.matches(final)
            or any(getattr(initial, name) != getattr(final, name) for name in (
                "scene", "root", "manager", "menu", "hireling", "building", "vendor",
                "recipe", "inventory", "item_template", "prefix", "suffix", "mode",
                "table", "quantity", "multiple",
            ))):
        raise ValueError("recipe preparation does not belong to this exact batch")
    return record
