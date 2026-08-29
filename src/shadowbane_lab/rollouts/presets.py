"""Concrete, deliberately provisional WonderBane duel presets.

These presets translate two recognizable player builds into the subset currently
represented by the reference simulator.  Descriptive build choices that the
engine cannot yet execute remain attached to the preset rather than being
silently discarded or approximated as unrelated actions.
"""

from __future__ import annotations

from dataclasses import dataclass

from shadowbane_lab.rollouts.duel import (
    BACKSTAB,
    MIND_SNARE,
    MIND_STRIKE,
    PSYCHIC_HEALING,
    SHADOW_BOLT,
    SHADOW_MANTLE,
    SHADOW_TOUCH,
    CombatantConfig,
    DuelConfig,
)
from shadowbane_lab.rulesets import CharacterBuild


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _positive_number(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{field_name} must be a positive number")


def _unique_pairs(values: tuple[tuple[str, int], ...], field_name: str) -> None:
    keys = tuple(key for key, _ in values)
    if len(keys) != len(set(keys)):
        raise ValueError(f"{field_name} must not contain duplicate keys")
    for key, value in values:
        _identifier(key, f"{field_name} key")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{field_name} values must be non-negative integers")


def _unique_strings(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    for value in values:
        _identifier(value, field_name)


@dataclass(frozen=True, slots=True)
class CombatantPreset:
    """A named build shell plus the executable subset currently in the harness."""

    preset_id: str
    display_name: str
    profession: str
    level: int
    attribute_targets: tuple[tuple[str, int], ...]
    disciplines: tuple[str, ...]
    skill_ranks: tuple[tuple[str, int], ...]
    intended_power_ranks: tuple[tuple[str, int], ...]
    executable_power_keys: tuple[str, ...]
    gear: tuple[str, ...]
    pre_fight_buffs: tuple[str, ...]
    tags: tuple[str, ...]
    unresolved: tuple[str, ...]
    health: float = 500.0
    mana: float = 300.0
    stamina: float = 200.0
    move_speed: float = 15.0

    def __post_init__(self) -> None:
        for value, name in (
            (self.preset_id, "preset_id"),
            (self.display_name, "display_name"),
            (self.profession, "profession"),
        ):
            _identifier(value, name)
        if isinstance(self.level, bool) or not isinstance(self.level, int) or self.level < 1:
            raise ValueError("level must be a positive integer")
        _unique_pairs(self.attribute_targets, "attribute_targets")
        _unique_pairs(self.skill_ranks, "skill_ranks")
        _unique_pairs(self.intended_power_ranks, "intended_power_ranks")
        for values, name in (
            (self.disciplines, "disciplines"),
            (self.executable_power_keys, "executable_power_keys"),
            (self.gear, "gear"),
            (self.pre_fight_buffs, "pre_fight_buffs"),
            (self.tags, "tags"),
            (self.unresolved, "unresolved"),
        ):
            _unique_strings(values, name)
        intended = dict(self.intended_power_ranks)
        missing = tuple(
            action_key for action_key in self.executable_power_keys if action_key not in intended
        )
        if missing:
            raise ValueError(
                "executable powers require intended ranks: " + ", ".join(sorted(missing))
            )
        for value, name in (
            (self.health, "health"),
            (self.mana, "mana"),
            (self.stamina, "stamina"),
            (self.move_speed, "move_speed"),
        ):
            _positive_number(value, name)

    @property
    def build(self) -> CharacterBuild:
        intended = dict(self.intended_power_ranks)
        return CharacterBuild(
            profession=self.profession,
            level=self.level,
            skill_ranks=self.skill_ranks,
            power_ranks=tuple(
                (action_key, intended[action_key]) for action_key in self.executable_power_keys
            ),
            enabled_power_keys=self.executable_power_keys,
        )

    def combatant(
        self,
        entity_id: str,
        team_id: str,
        *,
        extra_tags: tuple[str, ...] = (),
    ) -> CombatantConfig:
        _unique_strings(extra_tags, "extra_tags")
        combined_tags = tuple(dict.fromkeys((*self.tags, *extra_tags)))
        return CombatantConfig(
            entity_id=entity_id,
            team_id=team_id,
            build=self.build,
            health=self.health,
            mana=self.mana,
            stamina=self.stamina,
            move_speed=self.move_speed,
            tags=combined_tags,
        )


def wonderbane_sundancer_proc_assassin() -> CombatantPreset:
    """Return the provisional high-INT Irekei Sun Dancer proc-Assassin shell."""

    return CombatantPreset(
        preset_id="wonderbane.irekei-rogue-assassin.sundancer-proc.v1",
        display_name="Irekei Rogue Assassin — high-INT Sun Dancer proc",
        profession="assassin",
        level=75,
        attribute_targets=(
            ("strength", 35),
            ("dexterity", 102),
            ("constitution", 85),
            ("intelligence", 165),
            ("spirit", 10),
        ),
        disciplines=(
            "sun_dancer",
            "bounty_hunter",
            "saboteur",
            "undead_hunter",
        ),
        skill_ranks=(
            ("light_armor", 161),
            ("unarmed_combat", 161),
            ("unarmed_mastery", 70),
            ("dodge", 101),
            ("shadowmastery", 97),
            ("stalk", 21),
        ),
        intended_power_ranks=(
            (SHADOW_BOLT, 5),
            (SHADOW_TOUCH, 40),
            (BACKSTAB, 1),
            (SHADOW_MANTLE, 40),
            ("shadowbane.assassin.hide", 40),
            ("shadowbane.assassin.cloak_of_shadows", 40),
            ("shadowbane.assassin.poison_blade", 40),
            ("shadowbane.assassin.blind", 12),
            ("shadowbane.assassin.shadow_of_blindness", 30),
            ("shadowbane.assassin.slayers_focus", 1),
            ("shadowbane.assassin.silence", 1),
            ("shadowbane.assassin.steal_breath", 1),
            ("shadowbane.sundancer.embrace_the_phoenix", 1),
            ("shadowbane.sundancer.catlike_tread", 1),
            ("shadowbane.undead_hunter.consecrate_weapon", 1),
            ("shadowbane.bounty_hunter.detect_hidden", 1),
        ),
        executable_power_keys=(
            SHADOW_BOLT,
            SHADOW_TOUCH,
            BACKSTAB,
            SHADOW_MANTLE,
        ),
        gear=(
            "dual fast Khan'Xhir/Rha'Khanakar-class proc weapons",
            "Sea Dog's Rest-quality light armor baseline",
            "constitution/dexterity jewelry baseline",
        ),
        pre_fight_buffs=(
            "Greater Concoction",
            "Poison Blade",
            "Undead Hunter Consecrate Weapon when applicable",
        ),
        tags=(
            "profile.wonderbane",
            "race.irekei",
            "base.rogue",
            "discipline.sun_dancer",
            "equipment.dual_wield",
            "equipment.khanxhir",
            "gear.sdr_baseline",
            "buff.greater_concoction",
        ),
        unresolved=(
            (
                "Proc chance, proc spell damage, weapon delay and dual-wield cadence "
                "are not represented."
            ),
            (
                "Light Armor, Dodge, Dexterity, resistance and defense do not yet "
                "affect hit resolution."
            ),
            (
                "Poison Blade, blinds, Silence, Steal Breath, detection and Sun Dancer "
                "powers are descriptive only."
            ),
            (
                "Backstab is still the current immediate-hit approximation rather "
                "than a true next-swing modifier."
            ),
            "Normalized health, mana, stamina and movement await the live character sheet.",
        ),
    )


def wonderbane_deflock() -> CombatantPreset:
    """Return the provisional Shade Fighter high-defense Warlock shell."""

    return CombatantPreset(
        preset_id="wonderbane.shade-fighter-warlock.deflock-sdr.v1",
        display_name="Shade Fighter Warlock — SDR Deflock",
        profession="warlock",
        level=75,
        attribute_targets=(
            ("intelligence", 150),
            ("constitution", 110),
        ),
        disciplines=(
            "blade_master",
            "bounty_hunter",
            "commander",
        ),
        skill_ranks=(
            ("warlockry", 120),
            ("medium_armor", 140),
            ("sword", 100),
            ("block", 95),
        ),
        intended_power_ranks=(
            (MIND_STRIKE, 40),
            (MIND_SNARE, 1),
            (PSYCHIC_HEALING, 40),
            ("shadowbane.warlock.psychic_shout", 40),
            ("shadowbane.warlock.shatter_will", 40),
            ("shadowbane.warlock.danger_sense", 40),
            ("shadowbane.warlock.free_thought", 40),
            ("shadowbane.warlock.break_enchantment", 40),
            ("shadowbane.warlock.dull_the_mind", 20),
            ("shadowbane.warlock.dull_the_body", 20),
            ("shadowbane.warlock.surpass_limits", 5),
            ("shadowbane.warlock.needs_of_the_one", 1),
            ("shadowbane.warlock.ignore_the_old_order", 1),
            ("shadowbane.warlock.psychic_shield", 1),
            ("shadowbane.warlock.battlemind", 40),
            ("shadowbane.bounty_hunter.detect_hidden", 1),
            ("shadowbane.bounty_hunter.trip", 1),
            ("shadowbane.commander.take_no_prisoners", 20),
            ("shadowbane.commander.cry_havoc", 20),
        ),
        executable_power_keys=(
            MIND_STRIKE,
            MIND_SNARE,
            PSYCHIC_HEALING,
        ),
        gear=(
            "Sea Dog's Rest Alloyed Imperial medium armor set",
            "Sea Dog's Rest Alloyed Desert Shield of Blocking",
            "Sea Dog's Rest Commander's Psiblade of the Mind",
            "intelligence/mana-recovery jewelry baseline",
        ),
        pre_fight_buffs=(
            "Greater Concoction",
            "Fighter defensive stance",
            "Danger Sense",
            "Free Thought",
            "Psychic Shield",
        ),
        tags=(
            "profile.wonderbane",
            "race.shade",
            "base.fighter",
            "discipline.blade_master",
            "discipline.bounty_hunter",
            "discipline.commander",
            "equipment.medium_armor",
            "equipment.shield",
            "equipment.psiblade",
            "gear.sdr_baseline",
            "buff.greater_concoction",
        ),
        unresolved=(
            (
                "All remaining attribute points are intended for Dexterity; the exact "
                "total awaits calculator/live-sheet reconstruction."
            ),
            (
                "Defense, Block, armor, stance and shield values are descriptive "
                "until hit/passive-defense mechanics exist."
            ),
            (
                "Danger Sense, Free Thought, Psychic Shield, debuffs, dispels and "
                "Detect Hidden are not executable yet."
            ),
            (
                "Commander is provisional; no chant bonus is assumed while "
                "Concoction/Battlemind stacking remains unverified."
            ),
            "Normalized health, mana, stamina and movement await the live character sheet.",
        ),
    )


def wonderbane_sundancer_vs_deflock(
    *,
    starting_distance: float = 15.0,
    max_ticks: int = 1_200,
    seed: int = 1,
    assassin_starts_stealthed: bool = False,
) -> DuelConfig:
    """Build the first concrete matchup using only currently executable powers."""

    assassin = wonderbane_sundancer_proc_assassin()
    warlock = wonderbane_deflock()
    assassin_tags = ("visibility.invisible",) if assassin_starts_stealthed else ()
    return DuelConfig(
        left=assassin.combatant("assassin", "assassin", extra_tags=assassin_tags),
        right=warlock.combatant("warlock", "warlock"),
        starting_distance=starting_distance,
        max_ticks=max_ticks,
        seed=seed,
    )
