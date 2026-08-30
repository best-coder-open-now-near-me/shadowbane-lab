"""Source-backed WonderBane guide builds and their combat-start state."""

from __future__ import annotations

from dataclasses import dataclass, replace

from shadowbane_lab.combat import (
    CombatSheet,
    CompatibilityStatus,
    DamageType,
    SheetModifiers,
    StanceModifiers,
    StanceProfile,
    WeaponProcProfile,
    WeaponProfile,
)
from shadowbane_lab.combat.compiler import (
    MAGICBANE_COMBAT_FORMULA_REVISION,
    REQUIRED_RESISTANCE_TYPES,
    CombatCompilePolicy,
)
from shadowbane_lab.rollouts.duel import (
    BACKSTAB,
    MIND_SNARE,
    MIND_STRIKE,
    PSYCHIC_HEALING,
    SHADOW_BOLT,
    SHADOW_MANTLE,
    SHADOW_TOUCH,
    CombatantConfig,
    InitialEffectConfig,
    VerifiedCombatantConfig,
    VerifiedDuelBatchResult,
    VerifiedDuelConfig,
    run_verified_duel_batch,
)
from shadowbane_lab.rulesets import CharacterBuild
from shadowbane_lab.sim import (
    CombatStance,
    DamageBreakpoint,
    ResistanceAdjustment,
)


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
    """A named guide build, complete combat sheet, and immutable opening state."""

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
    combat_sheet: CombatSheet
    initial_effects: tuple[InitialEffectConfig, ...] = ()
    initial_stance: CombatStance = CombatStance.NORMAL
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
        if not isinstance(self.combat_sheet, CombatSheet):
            raise ValueError("combat_sheet must be a CombatSheet")
        if self.combat_sheet.profession != self.profession:
            raise ValueError("combat sheet and preset professions must match")
        if self.combat_sheet.level != self.level:
            raise ValueError("combat sheet and preset levels must match")
        if any(not isinstance(effect, InitialEffectConfig) for effect in self.initial_effects):
            raise ValueError("initial_effects must contain InitialEffectConfig values")
        if not isinstance(self.initial_stance, CombatStance):
            raise ValueError("initial_stance must be a CombatStance")

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
            initial_effects=self.initial_effects,
            initial_stance=self.initial_stance,
        )

    def verified_combatant(self, entity_id: str, team_id: str) -> VerifiedCombatantConfig:
        return VerifiedCombatantConfig(
            entity_id=entity_id,
            team_id=team_id,
            sheet=self.combat_sheet,
            build=self.build,
            initial_effects=self.initial_effects,
            initial_stance=self.initial_stance,
        )


@dataclass(frozen=True, slots=True)
class WonderBaneMatchupCell:
    """One range/opener cell from the archived-guide matchup matrix."""

    starting_distance: float
    assassin_starts_stealthed: bool
    batch: VerifiedDuelBatchResult

    def as_dict(self) -> dict[str, object]:
        return {
            "starting_distance": self.starting_distance,
            "assassin_starts_stealthed": self.assassin_starts_stealthed,
            "batch": self.batch.as_dict(),
        }


BLIND = "shadowbane.assassin.blind"
SHADOW_OF_BLINDNESS = "shadowbane.assassin.shadow_of_blindness"
SILENCE = "shadowbane.assassin.silence"
POISON_BLADE = "shadowbane.assassin.poison_blade"
CONSECRATE_WEAPON = "shadowbane.undead_hunter.consecrate_weapon"
PSYCHIC_SHOUT = "shadowbane.warlock.psychic_shout"
SHATTER_WILL = "shadowbane.warlock.shatter_will"
BREAK_ENCHANTMENT = "shadowbane.warlock.break_enchantment"
DULL_THE_MIND = "shadowbane.warlock.dull_the_mind"
DULL_THE_BODY = "shadowbane.warlock.dull_the_body"
SURPASS_LIMITS = "shadowbane.warlock.surpass_limits"
NEEDS_OF_THE_ONE = "shadowbane.warlock.needs_of_the_one"
PSYCHIC_SHIELD = "shadowbane.warlock.psychic_shield"
STEAL_BREATH = "shadowbane.assassin.steal_breath"


def _resistance_vector() -> tuple[tuple[str, float], ...]:
    return tuple((key, 0.0) for key in sorted(REQUIRED_RESISTANCE_TYPES))


def _rogue_assassin_stances() -> tuple[StanceProfile, ...]:
    source = {
        "profile_key": "rogue_assassin",
        "source_id": "morloch-stances-rogue-assassin",
        "source_revision": "retrieved-2026-08-29",
    }
    return (
        StanceProfile(
            **source,
            stance=CombatStance.DEFENSIVE,
            rank=20,
            modifiers=StanceModifiers(
                attack_percent=-0.11,
                defense_percent=0.17,
                damage_dealt_percent=-0.07,
                stamina_recovery_percent=0.24,
            ),
        ),
        StanceProfile(
            **source,
            stance=CombatStance.OFFENSIVE,
            rank=35,
            modifiers=StanceModifiers(
                attack_percent=0.0925,
                defense_percent=-0.23,
                weapon_delay_percent=-0.23,
            ),
        ),
        StanceProfile(
            **source,
            stance=CombatStance.PRECISE,
            rank=25,
            modifiers=StanceModifiers(
                attack_percent=0.36,
                damage_dealt_percent=-0.19,
            ),
        ),
    )


def _fighter_warlock_stances() -> tuple[StanceProfile, ...]:
    source = {
        "profile_key": "fighter_warlock",
        "source_id": "morloch-stances-fighter-warlock",
        "source_revision": "retrieved-2026-08-29",
    }
    return (
        StanceProfile(
            **source,
            stance=CombatStance.DEFENSIVE,
            rank=30,
            modifiers=StanceModifiers(
                attack_percent=-0.13,
                defense_percent=0.21,
                weapon_delay_percent=0.085,
                movement_percent=-0.085,
                stamina_recovery_percent=0.42,
            ),
        ),
        StanceProfile(
            **source,
            stance=CombatStance.OFFENSIVE,
            rank=20,
            modifiers=StanceModifiers(
                defense_percent=-0.34,
                damage_dealt_percent=0.34,
                weapon_delay_percent=-0.17,
                stamina_recovery_percent=-0.14,
            ),
        ),
        StanceProfile(
            **source,
            stance=CombatStance.PRECISE,
            rank=30,
            modifiers=StanceModifiers(
                attack_percent=0.295,
                weapon_delay_percent=0.21,
            ),
        ),
    )


def _assassin_sheet() -> CombatSheet:
    proc = WeaponProcProfile(
        proc_key="tier-three-mental",
        probability=0.05,
        minimum=20.0,
        maximum=46.0,
        damage_type=DamageType.MENTAL,
    )
    main_hand = WeaponProfile(
        weapon_key="rha-khanakar-proc",
        damage_type=DamageType.CRUSH,
        skill_key="unarmed_combat",
        mastery_key="unarmed_mastery",
        base_minimum=4.0,
        base_maximum=16.0,
        speed_tenths=20.0,
        range_units=6.0,
        strength_based=False,
        dual_wielding=True,
        procs=(proc,),
    )
    return CombatSheet(
        sheet_id="wonderbane-sundancer-proc-assassin-guide-v1",
        profession="assassin",
        level=75,
        source_id="wonderbane-sundancer-template+calculator+morloch-v1",
        source_revision="2026-08-29-guide-reconstruction-v1",
        formula_revision=MAGICBANE_COMBAT_FORMULA_REVISION,
        compatibility=CompatibilityStatus.SOURCE_REVISION_ACCEPTED,
        strength=35,
        dexterity=102,
        constitution=85,
        intelligence=165,
        spirit=10,
        maximum_health=1856.0,
        maximum_mana=349.0,
        maximum_stamina=390.0,
        move_speed=31.5,
        equipment_defense=689.42,
        skill_values=(("unarmed_combat", 161.0), ("unarmed_mastery", 70.0)),
        power_focus_values=(
            (SHADOW_BOLT, 97.0),
            (SHADOW_TOUCH, 97.0),
            (STEAL_BREATH, 97.0),
        ),
        resistances=_resistance_vector(),
        passive_defenses=(("block", 0.0), ("dodge", 25.25), ("parry", 5.0)),
        modifiers=SheetModifiers(
            flat_dcv=150.0,
        ),
        stance_profiles=_rogue_assassin_stances(),
        weapon=main_hand,
        off_hand_weapon=replace(
            main_hand,
            weapon_key="khan-xhir-proc",
            speed_tenths=21.5,
        ),
        tags=(
            "base.rogue",
            "build.high_int_proc",
            "discipline.bounty_hunter",
            "discipline.saboteur",
            "discipline.sun_dancer",
            "discipline.undead_hunter",
            "equipment.dual_wield",
            "equipment.melee_weapon",
            "power.stalk",
            "race.irekei",
        ),
    )


def _assassin_initial_effects() -> tuple[InitialEffectConfig, ...]:
    return (
        InitialEffectConfig(
            "cloak_of_shadows",
            tags=("buff", "defense.buff"),
            modifiers=(ResistanceAdjustment(DamageType.COLD, 25.0),),
            trains=40,
        ),
        InitialEffectConfig(
            "poison_blade_proc",
            duration_ms=900_000,
            stacking_key="PoisonBladeProc",
            tags=("buff", "trigger.passive", "proc.poison_blade"),
            trains=40,
        ),
        InitialEffectConfig(
            "consecrate_weapon_proc",
            duration_ms=315_000,
            stacking_key="ConsecrateWeaponProc",
            tags=("buff", "trigger.passive", "proc.consecrate_weapon"),
            trains=1,
        ),
        InitialEffectConfig(
            "slayers_focus",
            duration_ms=122_000,
            tags=("buff", "immunity.stun"),
            trains=1,
        ),
        InitialEffectConfig(
            "embrace_the_phoenix",
            duration_ms=60_000,
            tags=("buff",),
            modifiers=(ResistanceAdjustment(DamageType.FIRE, 11.0),),
            trains=1,
        ),
        InitialEffectConfig(
            "catlike_tread",
            duration_ms=120_000,
            tags=("buff", "visibility.invisible", "detection.untrackable"),
            trains=1,
        ),
    )


def _deflock_sheet() -> CombatSheet:
    return CombatSheet(
        sheet_id="wonderbane-shade-fighter-deflock-guide-v1",
        profession="warlock",
        level=75,
        source_id="morloch-deflock+calculator+formulas-v1",
        source_revision="2026-08-29-guide-reconstruction-v1",
        formula_revision=MAGICBANE_COMBAT_FORMULA_REVISION,
        compatibility=CompatibilityStatus.SOURCE_REVISION_ACCEPTED,
        strength=50,
        dexterity=108,
        constitution=135,
        intelligence=235,
        spirit=60,
        maximum_health=2658.0,
        maximum_mana=496.0,
        maximum_stamina=324.0,
        move_speed=30.0,
        equipment_defense=1311.686,
        skill_values=(("sword", 100.0), ("warlockry", 120.0)),
        power_focus_values=(
            (MIND_STRIKE, 120.0),
            (PSYCHIC_HEALING, 120.0),
            (PSYCHIC_SHOUT, 120.0),
        ),
        resistances=_resistance_vector(),
        passive_defenses=(("block", 24.5), ("dodge", 0.0), ("parry", 0.0)),
        modifiers=SheetModifiers(
            flat_dcv=150.0,
        ),
        stance_profiles=_fighter_warlock_stances(),
        weapon=WeaponProfile(
            weapon_key="legendary-psi-blade-of-the-mentalist",
            damage_type=DamageType.SLASH,
            skill_key="sword",
            mastery_key="warlockry",
            base_minimum=10.0,
            base_maximum=27.0,
            speed_tenths=30.5,
            range_units=6.0,
            strength_based=True,
            weapon_speed_percent=-0.15,
            procs=(
                WeaponProcProfile(
                    proc_key="mentalist",
                    probability=0.05,
                    minimum=20.0,
                    maximum=46.0,
                    damage_type=DamageType.MENTAL,
                ),
            ),
        ),
        tags=(
            "base.fighter",
            "build.deflock",
            "creature.undead",
            "discipline.blade_master",
            "discipline.bounty_hunter",
            "discipline.traveler",
            "equipment.medium_armor",
            "equipment.shield",
            "race.shade",
        ),
    )


def _deflock_initial_effects() -> tuple[InitialEffectConfig, ...]:
    return (
        InitialEffectConfig("danger_sense", tags=("buff", "defense.buff"), trains=40),
        InitialEffectConfig("free_thought", tags=("buff", "attribute.buff"), trains=40),
        InitialEffectConfig(
            "psychic_shield",
            duration_ms=300_000,
            stacking_key="DamageAbsorber",
            tags=("buff", "effect", "damage_absorber"),
            modifiers=(
                ResistanceAdjustment(DamageType.CRUSH, 16.5),
                ResistanceAdjustment(DamageType.PIERCE, 16.5),
                ResistanceAdjustment(DamageType.SLASH, 16.5),
                DamageBreakpoint(
                    "physical",
                    268.75,
                    (DamageType.CRUSH, DamageType.PIERCE, DamageType.SLASH),
                ),
            ),
            trains=1,
        ),
        InitialEffectConfig(
            "ignore_the_old_order",
            duration_ms=60_000,
            tags=("buff",),
            modifiers=(ResistanceAdjustment(DamageType.HOLY, 11.0),),
            trains=1,
        ),
        InitialEffectConfig(
            "detect_hidden",
            duration_ms=30_000,
            tags=("buff", "detection.see_invisible"),
            trains=1,
        ),
    )


def wonderbane_sundancer_proc_assassin() -> CombatantPreset:
    """Return the full archived high-INT Irekei Sun Dancer proc-Assassin guide."""

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
            BLIND,
            SHADOW_OF_BLINDNESS,
            SILENCE,
            STEAL_BREATH,
            POISON_BLADE,
            CONSECRATE_WEAPON,
        ),
        gear=(
            "dual fast Khan'Xhir/Rha'Khanakar-class proc weapons",
            "Sea Dog's Rest-quality light armor baseline",
            "constitution/dexterity jewelry baseline",
        ),
        pre_fight_buffs=(
            "Rogue Assassin defensive stance",
            "Cloak of Shadows",
            "Poison Blade",
            "Undead Hunter Consecrate Weapon versus the Shade target",
            "Slayer's Focus",
            "Embrace the Phoenix",
            "With Catlike Tread when starting hidden",
        ),
        tags=(
            "profile.wonderbane",
            "race.irekei",
            "base.rogue",
            "discipline.sun_dancer",
            "equipment.dual_wield",
            "equipment.khanxhir",
            "gear.sdr_light_armor",
        ),
        unresolved=(
            "Exact crafted weapon affixes are unspecified by the archived guide; both hands "
            "use the sourced tier-three mental proc scenario.",
            "SDR hard-leather defense and health are formula-derived rather than "
            "live-sheet verified.",
            "Greater Concoction is omitted until its current WonderBane values and "
            "stacking are verified.",
        ),
        combat_sheet=_assassin_sheet(),
        initial_effects=_assassin_initial_effects(),
        initial_stance=CombatStance.DEFENSIVE,
        health=1856.0,
        mana=349.0,
        stamina=390.0,
        move_speed=31.5,
    )


def wonderbane_deflock() -> CombatantPreset:
    """Return Rewen's archived Shade Fighter defensive Warlock guide."""

    return CombatantPreset(
        preset_id="wonderbane.shade-fighter-warlock.deflock-guide.v1",
        display_name="Shade Fighter Warlock — Rewen Deflock",
        profession="warlock",
        level=75,
        attribute_targets=(
            ("strength", 50),
            ("dexterity", 98),
            ("constitution", 110),
            ("intelligence", 150),
            ("spirit", 35),
        ),
        disciplines=(
            "blade_master",
            "traveler",
            "bounty_hunter",
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
            (PSYCHIC_SHOUT, 40),
            (SHATTER_WILL, 40),
            ("shadowbane.warlock.danger_sense", 40),
            ("shadowbane.warlock.free_thought", 40),
            (BREAK_ENCHANTMENT, 40),
            (DULL_THE_MIND, 20),
            (DULL_THE_BODY, 20),
            (SURPASS_LIMITS, 5),
            (NEEDS_OF_THE_ONE, 1),
            ("shadowbane.warlock.ignore_the_old_order", 1),
            (PSYCHIC_SHIELD, 1),
            ("shadowbane.bounty_hunter.detect_hidden", 1),
            ("shadowbane.fighter.hide", 1),
            ("shadowbane.recall_to_runegate", 1),
        ),
        executable_power_keys=(
            MIND_STRIKE,
            MIND_SNARE,
            PSYCHIC_HEALING,
            PSYCHIC_SHIELD,
            PSYCHIC_SHOUT,
            SHATTER_WILL,
            BREAK_ENCHANTMENT,
            DULL_THE_MIND,
            DULL_THE_BODY,
            SURPASS_LIMITS,
            NEEDS_OF_THE_ONE,
        ),
        gear=(
            "two Double Intelligence rings and one Double Intelligence amulet "
            "(+60 Intelligence conservative guide option)",
            "8 Defense/40 Health medium armor with 8 Defense/10 Dexterity gloves",
            "Legendary Psiblade of the Mentalist",
            "Impenetrable shield of Defense (+25 Defense, +3 Block)",
        ),
        pre_fight_buffs=(
            "Fighter defensive stance",
            "Danger Sense",
            "Free Thought",
            "Psychic Shield",
            "Ignore the Old Order",
            "Bounty Hunter Detect Hidden",
        ),
        tags=(
            "profile.wonderbane",
            "race.shade",
            "base.fighter",
            "discipline.blade_master",
            "discipline.traveler",
            "discipline.bounty_hunter",
            "equipment.medium_armor",
            "equipment.shield",
            "equipment.psiblade",
            "gear.guide_spec",
        ),
        unresolved=(
            "The level-75 Dexterity target is reconstructed from the calculator point pool, "
            "then the guide's +10 Dexterity gloves are applied to the combat sheet.",
            "The guide's reported 2030 defense is treated as the post-buff target; exact "
            "per-item client rounding awaits a live sheet.",
            "Legendary prefix and Mentalist proc values use archived source-era values "
            "pending WonderBane item inspection.",
            "Dull Mind and Dull Body use explicit output/rating multipliers until attributes "
            "can be recompiled during a running duel.",
        ),
        combat_sheet=_deflock_sheet(),
        initial_effects=_deflock_initial_effects(),
        initial_stance=CombatStance.DEFENSIVE,
        health=2658.0,
        mana=496.0,
        stamina=324.0,
        move_speed=30.0,
    )


def wonderbane_sundancer_vs_deflock(
    *,
    starting_distance: float = 15.0,
    max_ticks: int = 1_200,
    seed: int = 1,
    assassin_starts_stealthed: bool = False,
) -> VerifiedDuelConfig:
    """Build a complete-sheet guide matchup with an explicit source-acceptance policy."""

    assassin = wonderbane_sundancer_proc_assassin()
    warlock = wonderbane_deflock()
    assassin_config = assassin.verified_combatant("assassin", "assassin")
    if not assassin_starts_stealthed:
        assassin_config = replace(
            assassin_config,
            initial_effects=tuple(
                effect
                for effect in assassin_config.initial_effects
                if effect.effect_key != "catlike_tread"
            ),
        )
    return VerifiedDuelConfig(
        left=assassin_config,
        right=warlock.verified_combatant("warlock", "warlock"),
        compile_policy=CombatCompilePolicy(
            accepted_compatibility=(CompatibilityStatus.SOURCE_REVISION_ACCEPTED,),
            allow_ruleset_overrides=True,
        ),
        starting_distance=starting_distance,
        max_ticks=max_ticks,
        seed=seed,
    )


def wonderbane_sundancer_deflock_matrix(
    *,
    starting_distances: tuple[float, ...] = (6.0, 15.0, 40.0, 100.0),
    assassin_stealth_openers: tuple[bool, ...] = (False, True),
    episodes: int = 100,
    max_ticks: int = 2_400,
    seed_start: int = 1,
) -> tuple[WonderBaneMatchupCell, ...]:
    """Run deterministic guide-build batches across distance and opening visibility."""

    if not starting_distances:
        raise ValueError("starting_distances must not be empty")
    if any(
        isinstance(distance, bool) or not isinstance(distance, (int, float)) or distance <= 0
        for distance in starting_distances
    ):
        raise ValueError("starting_distances must contain positive numbers")
    if len(starting_distances) != len(set(starting_distances)):
        raise ValueError("starting_distances must not contain duplicates")
    if not assassin_stealth_openers:
        raise ValueError("assassin_stealth_openers must not be empty")
    if any(not isinstance(value, bool) for value in assassin_stealth_openers):
        raise ValueError("assassin_stealth_openers must contain booleans")
    if len(assassin_stealth_openers) != len(set(assassin_stealth_openers)):
        raise ValueError("assassin_stealth_openers must not contain duplicates")

    cells = []
    for starts_stealthed in assassin_stealth_openers:
        for distance in starting_distances:
            config = wonderbane_sundancer_vs_deflock(
                starting_distance=float(distance),
                max_ticks=max_ticks,
                seed=seed_start,
                assassin_starts_stealthed=starts_stealthed,
            )
            cells.append(
                WonderBaneMatchupCell(
                    starting_distance=float(distance),
                    assassin_starts_stealthed=starts_stealthed,
                    batch=run_verified_duel_batch(
                        config,
                        episodes=episodes,
                        seed_start=seed_start,
                    ),
                )
            )
    return tuple(cells)
