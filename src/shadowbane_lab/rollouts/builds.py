"""Explicit character-build construction for deterministic rollout brackets."""

from __future__ import annotations

from shadowbane_lab.rulesets import CharacterBuild

_POWER_MAXIMUMS = {
    "assassin": (
        ("shadowbane.assassin.shadow_bolt", 40),
        ("shadowbane.assassin.shadow_touch", 40),
        ("shadowbane.assassin.steal_breath", 40),
        ("shadowbane.assassin.fade", 20),
        ("shadowbane.assassin.backstab", 40),
        ("shadowbane.assassin.invisibility", 20),
        ("shadowbane.assassin.shadow_mantle", 40),
    ),
    "warlock": (
        ("shadowbane.warlock.mind_strike", 40),
        ("shadowbane.warlock.mind_snare", 40),
        ("shadowbane.warlock.psychic_healing", 40),
        ("shadowbane.warlock.psychic_shield", 40),
    ),
}


def progression_build(profession: str, level: int, rank: int) -> CharacterBuild:
    """Build an explicit equal-rank bracket, respecting individual power caps."""

    try:
        power_limits = _POWER_MAXIMUMS[profession]
    except KeyError as exc:
        raise ValueError(f"unsupported duel profession: {profession}") from exc
    if isinstance(level, bool) or not isinstance(level, int) or level < 1:
        raise ValueError("level must be a positive integer")
    if isinstance(rank, bool) or not isinstance(rank, int) or not 0 <= rank <= 40:
        raise ValueError("rank must be an integer between zero and 40")
    if profession == "assassin":
        skills = (("shadowmastery", 200), ("sorcery", 1), ("stalk", 1))
    else:
        skills = (("warlockry", 200),)
    return CharacterBuild(
        profession=profession,
        level=level,
        skill_ranks=skills,
        power_ranks=tuple(
            (action_key, min(rank, maximum_rank))
            for action_key, maximum_rank in power_limits
        ),
    )


__all__ = ["progression_build"]
