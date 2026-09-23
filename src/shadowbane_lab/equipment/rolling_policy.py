"""Conservative keep decisions; no game input or inventory mutation."""

from __future__ import annotations

from enum import StrEnum


class RollDisposition(StrEnum):
    WAIT = "wait"
    KEEP = "keep"
    EXCLUDE = "exclude"


def evaluate_roll_tiers(
    prefix_tier: int | None, suffix_tier: int | None, *, completed: bool
) -> RollDisposition:
    """Exclude fully identified rolls containing Tier 1/2; preserve unknowns.

    None means unresolved identity/tier. Zero means a confirmed absent affix.
    Positive integers are confirmed tiers. A name-only guess is not confirmation.
    Unknowns override exclusion, including a known low tier paired with an
    unknown affix. Unfinished rolls are never evaluated for disposal.
    """
    if type(completed) is not bool:
        raise ValueError("completed must be a boolean")
    for tier in (prefix_tier, suffix_tier):
        if tier is not None and (type(tier) is not int or tier < 0):
            raise ValueError("tier must be a nonnegative integer or None for unknown")
    if not completed:
        return RollDisposition.WAIT
    if prefix_tier is None or suffix_tier is None:
        return RollDisposition.KEEP
    if prefix_tier in (1, 2) or suffix_tier in (1, 2):
        return RollDisposition.EXCLUDE
    return RollDisposition.KEEP
