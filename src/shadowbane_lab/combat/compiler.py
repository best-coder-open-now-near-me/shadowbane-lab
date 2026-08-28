"""Fail-closed compilation from complete combat sheets to executable simulator actions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite

from shadowbane_lab.combat.formulas import (
    defense_rating,
    power_attack_rating,
    spell_amount_bounds,
    weapon_attack_rating,
    weapon_damage_bounds,
)
from shadowbane_lab.combat.model import (
    CombatSheet,
    CompatibilityStatus,
    WeaponDamageInputs,
)
from shadowbane_lab.protocol import EntityKind, NamedScalar, Relation, TargetKind, Vector2
from shadowbane_lab.rulesets.model import (
    CharacterBuild,
    CompilationStatus,
    CompiledRuleset,
)
from shadowbane_lab.sim import (
    ActionCatalog,
    ActionPhase,
    ActionSpec,
    ApplyEffect,
    AttackGate,
    AttackKind,
    ChanceGate,
    DealDamage,
    DirectEffectPrimitive,
    EntityState,
    PhaseKind,
    RestoreResource,
    SubjectRef,
    TargetingSpec,
    TriangularAmount,
    UniformAmount,
    UniformIntegerAmount,
    WeightedAmount,
)

MAGICBANE_COMBAT_FORMULA_REVISION = "3649c629b709c67625a09150a3752107f4b873cc"
REQUIRED_RESISTANCE_TYPES = frozenset(
    {
        "slash",
        "crush",
        "pierce",
        "magic",
        "bleed",
        "poison",
        "mental",
        "holy",
        "unholy",
        "lightning",
        "fire",
        "cold",
        "healing",
    }
)
REQUIRED_PASSIVE_DEFENSES = frozenset({"block", "parry", "dodge"})
_BASIC_ATTACK = "shadowbane.basic_attack"
_MOVEMENT = "shadowbane.move"


class CombatReadinessError(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        if not issues:
            raise ValueError("readiness error requires at least one issue")
        self.issues = tuple(sorted(set(issues)))
        super().__init__("combat inputs are not ready: " + "; ".join(self.issues))


@dataclass(frozen=True, slots=True)
class CombatCompilePolicy:
    accepted_compatibility: tuple[CompatibilityStatus, ...] = (
        CompatibilityStatus.LIVE_VERIFIED,
    )
    allow_ruleset_overrides: bool = False

    def __post_init__(self) -> None:
        if not self.accepted_compatibility:
            raise ValueError("accepted_compatibility must not be empty")
        if len(self.accepted_compatibility) != len(set(self.accepted_compatibility)):
            raise ValueError("accepted_compatibility must not contain duplicates")
        if any(
            not isinstance(status, CompatibilityStatus)
            for status in self.accepted_compatibility
        ):
            raise ValueError("accepted_compatibility must contain CompatibilityStatus values")
        if not isinstance(self.allow_ruleset_overrides, bool):
            raise ValueError("allow_ruleset_overrides must be a boolean")


@dataclass(frozen=True, slots=True)
class CompiledCombatant:
    sheet: CombatSheet
    build: CharacterBuild
    catalog: ActionCatalog
    action_keys: tuple[str, ...]
    canonical_action_keys: tuple[tuple[str, str], ...]
    scalars: tuple[tuple[str, float], ...]
    maximums: tuple[tuple[str, float], ...]
    tags: tuple[str, ...]

    def entity(self, entity_id: str, team_id: str, position: Vector2) -> EntityState:
        return EntityState(
            entity_id=entity_id,
            life_id=f"{entity_id}:1",
            kind=EntityKind.ACTOR,
            team_id=team_id,
            position=position,
            scalars=dict(self.scalars),
            maximums=dict(self.maximums),
            tags=set(self.tags),
            action_keys=self.action_keys,
        )

    def action_key(self, canonical_action_key: str) -> str:
        try:
            return dict(self.canonical_action_keys)[canonical_action_key]
        except KeyError as exc:
            raise KeyError(f"combatant does not expose {canonical_action_key}") from exc


def compile_combatant(
    sheet: CombatSheet,
    build: CharacterBuild,
    ruleset: CompiledRuleset,
    *,
    policy: CombatCompilePolicy | None = None,
) -> CompiledCombatant:
    """Compile one complete sheet and selected ruleset powers without fallback values."""

    policy = policy or CombatCompilePolicy()
    issues = _readiness_issues(sheet, build, ruleset, policy)
    if issues:
        raise CombatReadinessError(tuple(issues))

    scalars = _compile_scalars(sheet)
    actions: list[ActionSpec] = []
    mappings: list[tuple[str, str]] = []
    if sheet.weapon is not None:
        basic = _compile_basic_attack(sheet)
        actions.append(basic)
        mappings.append((_BASIC_ATTACK, basic.action_key))

    selected = ruleset.action_keys_for(build)
    for canonical_key in selected:
        if canonical_key in {_BASIC_ATTACK, _MOVEMENT}:
            continue
        record = ruleset.record(canonical_key)
        if record.action is None:
            continue
        compiled = _compile_power_action(sheet, record.action, record.rank)
        actions.append(compiled)
        mappings.append((canonical_key, compiled.action_key))

    catalog = ActionCatalog(tuple(actions))
    return CompiledCombatant(
        sheet=sheet,
        build=build,
        catalog=catalog,
        action_keys=tuple(action.action_key for action in catalog.actions),
        canonical_action_keys=tuple(sorted(mappings)),
        scalars=tuple(sorted(scalars.items())),
        maximums=(
            ("health", float(sheet.maximum_health)),
            ("mana", float(sheet.maximum_mana)),
            ("stamina", float(sheet.maximum_stamina)),
        ),
        tags=_compile_tags(sheet),
    )


def _readiness_issues(
    sheet: CombatSheet,
    build: CharacterBuild,
    ruleset: CompiledRuleset,
    policy: CombatCompilePolicy,
) -> list[str]:
    issues: list[str] = []
    if sheet.formula_revision != MAGICBANE_COMBAT_FORMULA_REVISION:
        issues.append(
            f"sheet formula revision {sheet.formula_revision} does not match "
            f"{MAGICBANE_COMBAT_FORMULA_REVISION}"
        )
    if sheet.compatibility not in policy.accepted_compatibility:
        issues.append(f"sheet compatibility {sheet.compatibility.value} is not accepted")
    if sheet.profession.casefold() != build.profession.casefold():
        issues.append("sheet and progression build professions differ")
    if sheet.level != build.level:
        issues.append("sheet and progression build levels differ")
    resistance_keys = {key for key, _ in sheet.resistances}
    missing_resists = REQUIRED_RESISTANCE_TYPES - resistance_keys
    if missing_resists:
        issues.append(f"missing resistances: {', '.join(sorted(missing_resists))}")
    passive_keys = {key for key, _ in sheet.passive_defenses}
    missing_passives = REQUIRED_PASSIVE_DEFENSES - passive_keys
    if missing_passives:
        issues.append(f"missing passive defenses: {', '.join(sorted(missing_passives))}")
    if sheet.weapon is None:
        issues.append("weapon profile is required, including explicit unarmed profiles")
    else:
        skill_keys = {key for key, _ in sheet.skill_values}
        for key in (sheet.weapon.skill_key, sheet.weapon.mastery_key):
            if key not in skill_keys:
                issues.append(f"missing weapon skill value {key}")

    try:
        selected = ruleset.action_keys_for(build)
    except ValueError as exc:
        issues.append(str(exc))
        return issues
    explicitly_selected = {key for key, _ in build.power_ranks} | set(
        build.enabled_power_keys or ()
    )
    for action_key in explicitly_selected:
        record = ruleset.record(action_key)
        if record.status is CompilationStatus.UNRESOLVED:
            issues.append(f"selected action {action_key} is unresolved")
    focus_keys = {key for key, _ in sheet.power_focus_values}
    for action_key in selected:
        if action_key in {_BASIC_ATTACK, _MOVEMENT}:
            continue
        record = ruleset.record(action_key)
        if record.status is CompilationStatus.UNRESOLVED:
            issues.append(f"selected action {action_key} is unresolved")
        elif (
            record.status is CompilationStatus.COMPILED_WITH_OVERRIDE
            and not policy.allow_ruleset_overrides
        ):
            issues.append(f"selected action {action_key} requires ruleset-override acceptance")
        if record.action is not None and _action_needs_focus(record.action):
            if action_key not in focus_keys:
                issues.append(f"missing power focus {action_key}")
    return issues


def _compile_scalars(sheet: CombatSheet) -> dict[str, float]:
    modifiers = sheet.modifiers
    result = {
        "health": float(sheet.maximum_health),
        "mana": float(sheet.maximum_mana),
        "stamina": float(sheet.maximum_stamina),
        "move_speed": float(sheet.move_speed),
        "armor_piercing": float(modifiers.armor_piercing),
        "defense": float(
            defense_rating(
                sheet.dexterity,
                sheet.equipment_defense,
                flat_dcv=modifiers.flat_dcv,
                positive_dcv_percent=modifiers.positive_dcv_percent,
                negative_dcv_percent=modifiers.negative_dcv_percent,
            )
        ),
    }
    result.update({f"resist.{key}": float(value) for key, value in sheet.resistances})
    result.update(
        {f"passive.{key}": float(value) for key, value in sheet.passive_defenses}
    )
    if sheet.protection_type is not None:
        result["protection.trains"] = float(sheet.protection_trains)
    if sheet.weapon is not None:
        result["attack.main_hand"] = float(
            weapon_attack_rating(
                sheet.skill_value(sheet.weapon.skill_key),
                sheet.skill_value(sheet.weapon.mastery_key),
                sheet.strength,
                sheet.dexterity,
                flat_ocv=modifiers.flat_ocv,
                positive_ocv_percent=modifiers.positive_ocv_percent,
                negative_ocv_percent=modifiers.negative_ocv_percent,
            )
        )
    for action_key, focus in sheet.power_focus_values:
        result[f"attack.power.{action_key}"] = power_attack_rating(
            focus,
            sheet.dexterity,
            flat_ocv=modifiers.flat_ocv,
            positive_ocv_percent=modifiers.positive_ocv_percent,
            negative_ocv_percent=modifiers.negative_ocv_percent,
        )
    if any(not isfinite(value) for value in result.values()):
        raise CombatReadinessError(("compiled scalar is not finite",))
    return result


def _compile_tags(sheet: CombatSheet) -> tuple[str, ...]:
    tags = {f"profession.{sheet.profession.casefold()}", *sheet.tags}
    if sheet.protection_type is not None:
        tags.add(f"protection.{sheet.protection_type}")
    return tuple(sorted(tags))


def _compile_basic_attack(sheet: CombatSheet) -> ActionSpec:
    weapon = sheet.weapon
    if weapon is None:
        raise CombatReadinessError(("weapon profile is required",))
    primary = sheet.strength if weapon.strength_based else sheet.dexterity
    secondary = sheet.dexterity if weapon.strength_based else sheet.strength
    minimum, maximum = weapon_damage_bounds(
        WeaponDamageInputs(
            base_minimum=weapon.base_minimum,
            base_maximum=weapon.base_maximum,
            primary_attribute=primary,
            secondary_attribute=secondary,
            weapon_skill=sheet.skill_value(weapon.skill_key),
            weapon_mastery=sheet.skill_value(weapon.mastery_key),
            item_minimum_flat=weapon.item_minimum_flat,
            item_maximum_flat=weapon.item_maximum_flat,
            item_damage_flat=weapon.item_damage_flat,
            item_minimum_percent=weapon.item_minimum_percent,
            item_maximum_percent=weapon.item_maximum_percent,
            item_damage_percent=weapon.item_damage_percent,
            character_minimum_flat=weapon.character_minimum_flat,
            character_maximum_flat=weapon.character_maximum_flat,
            character_damage_flat=weapon.character_damage_flat,
            character_minimum_percent=weapon.character_minimum_percent,
            character_maximum_percent=weapon.character_maximum_percent,
            character_damage_percent=weapon.character_damage_percent,
            dual_wielding=weapon.dual_wielding,
        )
    )
    if minimum <= 0 or maximum <= minimum:
        raise CombatReadinessError(("compiled weapon damage bounds are not positive",))
    post_hit: list[DirectEffectPrimitive | ChanceGate] = [
        DealDamage(
            SubjectRef.TARGET,
            TriangularAmount(float(minimum), float(maximum)),
            weapon.damage_type,
            uses_resistance=True,
        )
    ]
    post_hit.extend(
        ChanceGate(
            chance_key=proc.proc_key,
            probability=proc.probability,
            effects=(
                DealDamage(
                    SubjectRef.TARGET,
                    TriangularAmount(proc.minimum, proc.maximum),
                    proc.damage_type,
                    uses_resistance=True,
                    power_trains=proc.trains,
                ),
            ),
        )
        for proc in weapon.procs
    )
    passives = ["passive.block"]
    if not weapon.ranged:
        passives.append("passive.parry")
    passives.append("passive.dodge")
    delay_tenths = weapon.speed_tenths
    delay_tenths *= 1.0 + weapon.weapon_speed_percent
    delay_tenths *= 1.0 + weapon.attack_delay_percent
    cooldown_ms = max(10, int(delay_tenths)) * 100
    expected_damage = (minimum + maximum) / 2.0 + sum(
        proc.probability * (proc.minimum + proc.maximum) / 2.0
        for proc in weapon.procs
    )
    action_key = _compiled_action_key(sheet.sheet_id, _BASIC_ATTACK)
    return ActionSpec(
        action_key=action_key,
        targeting=TargetingSpec(
            kind=TargetKind.ENTITY,
            allowed_relations=(Relation.ENEMY,),
            maximum_range=weapon.range_units,
            requires_line_of_sight=True,
        ),
        phases=(
            ActionPhase(
                kind=PhaseKind.ACTIVE,
                duration_ms=0,
                effects=(
                    AttackGate(
                        attack_key="main_hand",
                        kind=AttackKind.BASIC,
                        attack_rating_key="attack.main_hand",
                        defense_rating_key="defense",
                        effects=tuple(post_hit),
                        passive_defense_keys=tuple(passives),
                    ),
                ),
            ),
        ),
        cooldown_ms=cooldown_ms,
        features=(
            NamedScalar("expected_damage", expected_damage),
            NamedScalar("commitment_ms", float(cooldown_ms)),
        ),
        tags=("combat", "attack", "melee" if not weapon.ranged else "ranged"),
    )


def _compile_power_action(sheet: CombatSheet, action: ActionSpec, rank: int) -> ActionSpec:
    focus = sheet.power_focus(action.action_key) if _action_needs_focus(action) else 0.0
    phases = tuple(_compile_power_phase(sheet, phase, rank, focus) for phase in action.phases)
    compiled_key = _compiled_action_key(sheet.sheet_id, action.action_key)
    if _hostile_action(action):
        phases = tuple(
            replace(
                phase,
                effects=(
                    AttackGate(
                        attack_key=action.action_key,
                        kind=AttackKind.POWER,
                        attack_rating_key=f"attack.power.{action.action_key}",
                        defense_rating_key="defense",
                        effects=phase.effects,
                        passive_defense_keys=("passive.dodge",),
                    ),
                ),
            )
            if phase.effects
            else phase
            for phase in phases
        )
    expected_damage = _expected_effect_amount(phases, DealDamage)
    expected_healing = _expected_effect_amount(phases, RestoreResource)
    feature_values = {feature.name: feature.value for feature in action.features}
    if expected_damage > 0:
        feature_values["expected_damage"] = expected_damage
    if expected_healing > 0:
        feature_values["expected_healing"] = expected_healing
    return replace(
        action,
        action_key=compiled_key,
        phases=phases,
        features=tuple(
            NamedScalar(name, value) for name, value in sorted(feature_values.items())
        ),
    )


def _compile_power_phase(
    sheet: CombatSheet,
    phase: ActionPhase,
    rank: int,
    focus: float,
) -> ActionPhase:
    effects: list[DirectEffectPrimitive | ChanceGate | AttackGate] = []
    for effect in phase.effects:
        if isinstance(effect, ChanceGate):
            effects.append(
                replace(
                    effect,
                    effects=tuple(
                        _compile_direct_power_effect(sheet, item, rank, focus)
                        for item in effect.effects
                    ),
                )
            )
        elif isinstance(effect, AttackGate):
            raise CombatReadinessError(("input ruleset already contains an attack gate",))
        else:
            effects.append(_compile_direct_power_effect(sheet, effect, rank, focus))
    return replace(phase, effects=tuple(effects))


def _compile_direct_power_effect(
    sheet: CombatSheet,
    effect: DirectEffectPrimitive,
    rank: int,
    focus: float,
) -> DirectEffectPrimitive:
    if isinstance(effect, DealDamage):
        minimum, maximum = _amount_bounds(effect.amount)
        scaled = spell_amount_bounds(
            minimum,
            maximum,
            sheet.intelligence,
            sheet.spirit,
            focus,
        )
        return replace(
            effect,
            amount=_compiled_amount(*scaled),
            uses_resistance=True,
            power_trains=rank,
        )
    if isinstance(effect, RestoreResource) and effect.resource_key == "health":
        minimum, maximum = _amount_bounds(effect.amount)
        scaled = spell_amount_bounds(
            minimum,
            maximum,
            sheet.intelligence,
            sheet.spirit,
            focus,
        )
        return replace(
            effect,
            amount=_compiled_amount(*scaled),
            uses_resistance=True,
            power_trains=rank,
            resistance_type="healing",
        )
    if isinstance(effect, ApplyEffect):
        return replace(effect, trains=rank)
    return effect


def _amount_bounds(
    amount: float | UniformAmount | UniformIntegerAmount | WeightedAmount | TriangularAmount,
) -> tuple[float, float]:
    if isinstance(amount, (UniformAmount, UniformIntegerAmount, TriangularAmount)):
        return float(amount.minimum), float(amount.maximum)
    if isinstance(amount, WeightedAmount):
        raise CombatReadinessError(("weighted power amounts cannot be stat-scaled",))
    return float(amount), float(amount)


def _compiled_amount(minimum: int, maximum: int) -> float | TriangularAmount:
    if minimum <= 0 or maximum < minimum:
        raise CombatReadinessError(("compiled power amount is not positive and ordered",))
    if minimum == maximum:
        return float(minimum)
    return TriangularAmount(float(minimum), float(maximum))


def _hostile_action(action: ActionSpec) -> bool:
    return (
        action.targeting.kind is TargetKind.ENTITY
        and Relation.ENEMY in action.targeting.allowed_relations
        and "combat" in action.tags
    )


def _action_needs_focus(action: ActionSpec) -> bool:
    if _hostile_action(action):
        return True
    return any(
        isinstance(effect, (DealDamage, RestoreResource))
        for phase in action.phases
        for effect in phase.effects
    )


def _expected_effect_amount(
    phases: tuple[ActionPhase, ...], effect_type: type[DealDamage] | type[RestoreResource]
) -> float:
    total = 0.0
    for phase in phases:
        for effect in phase.effects:
            candidates = effect.effects if isinstance(effect, AttackGate) else (effect,)
            for candidate in candidates:
                if isinstance(candidate, effect_type):
                    amount = candidate.amount
                    total += amount.expected if not isinstance(amount, (int, float)) else amount
    return total


def _compiled_action_key(sheet_id: str, canonical_key: str) -> str:
    return f"{canonical_key}@{sheet_id}"
