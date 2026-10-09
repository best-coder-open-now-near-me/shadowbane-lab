"""Passive learned Hunt Foe identity, separate from combat recipient routing.

The category-4 player-tracking query is not a self buff or a targeted cast.
This DTO proves only a stable learned definition on the borrowed character
session; native query admission and returned contacts require their own proof.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .native_ability import NativeAbilityDefinition, NativeAbilityError, NativeAbilityResolver

HUNT_FOE = "Hunt Foe"


@dataclass(frozen=True, slots=True)
class NativeTrackingAbility:
    power_id: int
    display_name: str
    internal_name: str
    target_mode: int
    category: int
    delivery: int
    learned_rank: int

    def __post_init__(self) -> None:
        # Reuse strict native scalar/text validation without calling .recipient.
        definition = NativeAbilityDefinition(**asdict(self))
        if (
            definition.display_name.casefold() != HUNT_FOE.casefold()
            or (definition.category, definition.target_mode, definition.delivery) != (4, 4, 0)
        ):
            raise NativeAbilityError(
                "tracking requires learned Hunt Foe category 4/mode 4/delivery 0"
            )

    def as_dict(self) -> dict[str, object]:
        return {"kind": "player_tracking", **asdict(self)}


def resolve_learned_tracking_ability(
    character_session, selector: str = HUNT_FOE,
) -> NativeTrackingAbility:
    """Resolve the explicitly selected Hunt Foe, never Hunt Prey or a numeric shortcut."""
    if not isinstance(selector, str) or selector.strip().casefold() != HUNT_FOE.casefold():
        raise NativeAbilityError("player tracking selector must be Hunt Foe")
    definition = NativeAbilityResolver(character_session).resolve_definition(HUNT_FOE)
    return NativeTrackingAbility(**asdict(definition))
