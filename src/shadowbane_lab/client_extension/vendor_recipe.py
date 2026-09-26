"""Immutable single-item random recipe intent and its owned preparation evidence."""
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


def validate_recipe_preparation(
    raw: bytes, recipe: RandomRecipeSpec, initial, *, process_id: int,
    process_creation_filetime_utc: int, window: int,
) -> dict:
    """Bind completed menu proof to the exact recipe, client and current visit.

    Spending and menu snapshot revisions belong to different controllers. All
    their shared identity/recipe fields must match; revisions are not comparable.
    """
    from .vendor_menu import validate_completed_menu

    if type(recipe) is not RandomRecipeSpec:
        raise ValueError("an immutable random recipe specification is required")
    record, _, final = validate_completed_menu(raw)
    if (record["operation"] != "prepare_recipe"
            or RandomRecipeSpec.from_dict(record["requested_recipe"]) != recipe
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
