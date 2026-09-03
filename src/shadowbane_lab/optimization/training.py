"""Catalog-backed legal-build evaluation and mutation for deterministic MAP-Elites."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from math import isfinite
from statistics import fmean

from shadowbane_lab.combat import power_attack_rating, weapon_attack_rating
from shadowbane_lab.composition.adapters import primitive_loadout_from_build_view
from shadowbane_lab.equipment import EquipmentCatalog
from shadowbane_lab.progression import (
    WonderbaneCalculatorCatalog,
    rogue_training_points_for_level,
)
from shadowbane_lab.rollouts.duel import TerminationReason
from shadowbane_lab.rollouts.open_builds import PrimitiveLoadout, run_open_duel
from shadowbane_lab.rulesets import CompiledRuleset
from shadowbane_lab.sim import DeterministicRandom

from .build_compiler import LegalBuildCompiler
from .build_model import (
    BuildCompilationStatus,
    CompiledLegalBuild,
    EquipmentSelection,
    LegalBuildCompileError,
    LegalBuildGenome,
    canonical_digest,
)
from .map_elites import ArchiveAdmission, MapElitesEvaluation


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LegalBuildCompileError(f"{field_name} must be non-empty text")
    return value


def _positive(value: float, field_name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value <= 0
    ):
        raise LegalBuildCompileError(f"{field_name} must be a positive finite number")
    return float(value)


def _non_negative_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LegalBuildCompileError(f"{field_name} must be a non-negative integer")
    return value


def _semantic_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


@dataclass(frozen=True, slots=True)
class EquipmentSkillRequirement:
    slot_key: str
    item_id: int
    skill_name: str
    semantic_skill_key: str
    required_rank: int
    observed_rank: int

    @property
    def satisfied(self) -> bool:
        return self.observed_rank >= self.required_rank

    def as_dict(self) -> dict[str, object]:
        return {
            "slot_key": self.slot_key,
            "item_id": self.item_id,
            "skill_name": self.skill_name,
            "semantic_skill_key": self.semantic_skill_key,
            "required_rank": self.required_rank,
            "observed_rank": self.observed_rank,
            "satisfied": self.satisfied,
        }


@dataclass(frozen=True, slots=True)
class CatalogLegalityAudit:
    base_class_name: str
    power_rank_points: int
    known_power_training_budget: int | None
    equipment_skill_requirements: tuple[EquipmentSkillRequirement, ...]
    opaque_item_requirement_count: int
    unresolved_skill_cost_keys: tuple[str, ...]

    @property
    def power_training_remaining(self) -> int | None:
        if self.known_power_training_budget is None:
            return None
        return self.known_power_training_budget - self.power_rank_points

    def as_dict(self) -> dict[str, object]:
        return {
            "base_class_name": self.base_class_name,
            "power_rank_points": self.power_rank_points,
            "known_power_training_budget": self.known_power_training_budget,
            "power_training_remaining": self.power_training_remaining,
            "equipment_skill_requirements": [
                item.as_dict() for item in self.equipment_skill_requirements
            ],
            "opaque_item_requirement_count": self.opaque_item_requirement_count,
            "unresolved_skill_cost_keys": list(self.unresolved_skill_cost_keys),
            "power_budget_scope": (
                "necessary lower bound only; skill training costs remain unresolved"
            ),
        }


class CatalogBackedLegalityGate:
    """Apply safe necessary conditions not yet owned by the general compiler.

    The gate does not promote a candidate to strict evidence. It rejects only conditions
    that are provably impossible from existing catalog fields: insufficient named item
    skill, weapon placement outside a hand slot, incompatible two-handed use, and a
    selected-power rank sum larger than a sourced Rogue training pool.
    """

    def __init__(
        self,
        calculator: WonderbaneCalculatorCatalog,
        equipment: EquipmentCatalog,
        *,
        skill_aliases: tuple[tuple[str, str], ...] = (
            ("unarmed", "unarmed_combat"),
            ("unarmed_combat", "unarmed"),
        ),
    ) -> None:
        if not isinstance(calculator, WonderbaneCalculatorCatalog):
            raise LegalBuildCompileError("calculator has the wrong type")
        if not isinstance(equipment, EquipmentCatalog):
            raise LegalBuildCompileError("equipment has the wrong type")
        alias_keys = tuple(key for key, _ in skill_aliases)
        if len(alias_keys) != len(set(alias_keys)):
            raise LegalBuildCompileError("skill_aliases keys must be unique")
        for key, value in skill_aliases:
            _identifier(key, "skill alias key")
            _identifier(value, "skill alias value")
        self._calculator = calculator
        self._equipment = equipment
        self._skill_aliases = dict(skill_aliases)

    def audit(self, genome: LegalBuildGenome) -> CatalogLegalityAudit:
        if not isinstance(genome, LegalBuildGenome):
            raise LegalBuildCompileError("genome must be LegalBuildGenome")
        base = self._calculator.base_class(genome.base_class_id)
        skill_ranks = dict(genome.skill_ranks)
        requirements: list[EquipmentSkillRequirement] = []
        opaque_count = 0
        hand_items = {}
        for selection in genome.equipment:
            try:
                item = self._equipment.item(selection.item_id)
            except KeyError as exc:
                raise LegalBuildCompileError(
                    f"unknown equipment item {selection.item_id}"
                ) from exc
            if selection.slot_key in {"main_hand", "off_hand"}:
                hand_items[selection.slot_key] = item
            weapon_like = (
                item.damage_type is not None
                and item.maximum_damage > item.minimum_damage
                and item.speed > 0
                and item.range > 0
            )
            if weapon_like and selection.slot_key not in {"main_hand", "off_hand"}:
                raise LegalBuildCompileError(
                    f"weapon item {selection.item_id} cannot occupy "
                    f"{selection.slot_key}; hand-slot semantics are proven by its "
                    "damage, speed, and range fields"
                )
            opaque_count += len(item.requirements)
            if item.skill_required and item.skill_percent_required > 0:
                semantic = _semantic_key(item.skill_required)
                aliases = {semantic, self._skill_aliases.get(semantic, semantic)}
                observed = max((skill_ranks.get(key, 0) for key in aliases), default=0)
                requirement = EquipmentSkillRequirement(
                    slot_key=selection.slot_key,
                    item_id=selection.item_id,
                    skill_name=item.skill_required,
                    semantic_skill_key=semantic,
                    required_rank=item.skill_percent_required,
                    observed_rank=observed,
                )
                requirements.append(requirement)
                if not requirement.satisfied:
                    raise LegalBuildCompileError(
                        f"item {selection.item_id} requires {item.skill_required} "
                        f"{item.skill_percent_required}, got {observed}"
                    )

        if any(item.two_handed for item in hand_items.values()) and len(hand_items) > 1:
            raise LegalBuildCompileError(
                "a two-handed weapon cannot be combined with another occupied hand slot"
            )

        power_points = sum(rank for _, rank in genome.power_ranks)
        budget = (
            rogue_training_points_for_level(genome.level)
            if base.name.casefold() == "rogue" and genome.level <= 75
            else None
        )
        if budget is not None and power_points > budget:
            raise LegalBuildCompileError(
                f"selected power ranks require at least {power_points} Rogue training "
                f"points, but level {genome.level} supplies only {budget}"
            )
        return CatalogLegalityAudit(
            base_class_name=base.name,
            power_rank_points=power_points,
            known_power_training_budget=budget,
            equipment_skill_requirements=tuple(requirements),
            opaque_item_requirement_count=opaque_count,
            unresolved_skill_cost_keys=tuple(sorted(skill_ranks)),
        )

    def validate(self, genome: LegalBuildGenome) -> CatalogLegalityAudit:
        return self.audit(genome)


@dataclass(frozen=True, slots=True)
class DuelScenario:
    scenario_id: str
    starting_distance: float
    max_ticks: int = 1_200
    mirrored: bool = True

    def __post_init__(self) -> None:
        _identifier(self.scenario_id, "scenario_id")
        _positive(self.starting_distance, "starting_distance")
        if (
            isinstance(self.max_ticks, bool)
            or not isinstance(self.max_ticks, int)
            or self.max_ticks < 1
        ):
            raise LegalBuildCompileError("max_ticks must be a positive integer")
        if not isinstance(self.mirrored, bool):
            raise LegalBuildCompileError("mirrored must be a boolean")

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "starting_distance": self.starting_distance,
            "max_ticks": self.max_ticks,
            "mirrored": self.mirrored,
        }


@dataclass(frozen=True, slots=True)
class CompiledOpponent:
    opponent_id: str
    compilation: CompiledLegalBuild

    def __post_init__(self) -> None:
        _identifier(self.opponent_id, "opponent_id")
        if not isinstance(self.compilation, CompiledLegalBuild):
            raise LegalBuildCompileError("compilation must be CompiledLegalBuild")

    @property
    def opponent_digest(self) -> str:
        return canonical_digest(
            {
                "opponent_id": self.opponent_id,
                "compilation_digest": self.compilation.compilation_digest,
            }
        )


class LegalBuildLeagueEvaluator:
    """Evaluate compiler-admitted builds with common seeds and mirrored starts."""

    EVALUATOR_VERSION = 1

    def __init__(
        self,
        compiler: LegalBuildCompiler,
        ruleset: CompiledRuleset,
        opponents: tuple[LegalBuildGenome, ...],
        scenarios: tuple[DuelScenario, ...],
        seeds: tuple[int, ...],
        *,
        gate: CatalogBackedLegalityGate | None = None,
    ) -> None:
        if not isinstance(compiler, LegalBuildCompiler):
            raise LegalBuildCompileError("compiler has the wrong type")
        if not isinstance(ruleset, CompiledRuleset):
            raise LegalBuildCompileError("ruleset has the wrong type")
        if not opponents:
            raise LegalBuildCompileError("opponents must not be empty")
        if not scenarios or any(not isinstance(item, DuelScenario) for item in scenarios):
            raise LegalBuildCompileError("scenarios must contain DuelScenario values")
        if not seeds:
            raise LegalBuildCompileError("seeds must not be empty")
        for seed in seeds:
            _non_negative_integer(seed, "seed")
        if len(seeds) != len(set(seeds)):
            raise LegalBuildCompileError("seeds must not contain duplicates")
        if gate is not None and not isinstance(gate, CatalogBackedLegalityGate):
            raise LegalBuildCompileError("gate has the wrong type")
        compiled_opponents: list[CompiledOpponent] = []
        for index, genome in enumerate(opponents):
            if gate is not None:
                gate.validate(genome)
            compilation = compiler.compile(genome)
            if not compilation.view.executable_action_keys:
                raise LegalBuildCompileError(
                    f"opponent {genome.genome_id} has no executable actions"
                )
            compiled_opponents.append(
                CompiledOpponent(f"opponent-{index:03d}", compilation)
            )
        digests = tuple(item.opponent_digest for item in compiled_opponents)
        if len(digests) != len(set(digests)):
            raise LegalBuildCompileError("opponents must compile to distinct identities")
        self._compiler = compiler
        self._ruleset = ruleset
        self._opponents = tuple(compiled_opponents)
        self._scenarios = scenarios
        self._seeds = tuple(sorted(seeds))
        self._gate = gate

    @property
    def opponents(self) -> tuple[CompiledOpponent, ...]:
        return self._opponents

    @property
    def scenarios(self) -> tuple[DuelScenario, ...]:
        return self._scenarios

    @property
    def seeds(self) -> tuple[int, ...]:
        return self._seeds

    def __call__(self, genome: LegalBuildGenome) -> MapElitesEvaluation | None:
        try:
            audit = None if self._gate is None else self._gate.validate(genome)
            compilation = self._compiler.compile(genome)
        except (LegalBuildCompileError, KeyError, ValueError):
            return None
        if not compilation.view.executable_action_keys:
            return None

        candidate = self._loadout(compilation, role="candidate")
        runs: list[dict[str, object]] = []
        scores: list[float] = []
        wins = draws = losses = survivals = 0
        health_fractions: list[float] = []
        opponent_health_fractions: list[float] = []
        ticks: list[float] = []
        rejected_actions: list[float] = []

        for opponent in self._opponents:
            opponent_loadout = self._loadout(
                opponent.compilation,
                role=opponent.opponent_id,
            )
            for scenario in self._scenarios:
                for seed in self._seeds:
                    orientations = (True, False) if scenario.mirrored else (True,)
                    for candidate_left in orientations:
                        left, right = (
                            (candidate, opponent_loadout)
                            if candidate_left
                            else (opponent_loadout, candidate)
                        )
                        run = run_open_duel(
                            self._ruleset,
                            left,
                            right,
                            starting_distance=scenario.starting_distance,
                            max_ticks=scenario.max_ticks,
                            seed=seed,
                        )
                        duel = run.duel
                        candidate_result = next(
                            item
                            for item in duel.combatants
                            if item.entity_id == candidate.loadout_id
                        )
                        opponent_result = next(
                            item
                            for item in duel.combatants
                            if item.entity_id == opponent_loadout.loadout_id
                        )
                        candidate_health = max(candidate.health, 1.0)
                        opponent_health = max(opponent_loadout.health, 1.0)
                        candidate_fraction = max(
                            0.0, candidate_result.final_health / candidate_health
                        )
                        opponent_fraction = max(
                            0.0, opponent_result.final_health / opponent_health
                        )
                        health_fractions.append(candidate_fraction)
                        opponent_health_fractions.append(opponent_fraction)
                        ticks.append(float(duel.ticks))
                        rejected_actions.append(float(candidate_result.rejected_actions))
                        survivals += int(candidate_result.alive)
                        if duel.winner_entity_id == candidate.loadout_id:
                            outcome = 1.0
                            wins += 1
                        elif duel.winner_entity_id is None:
                            outcome = 0.0
                            draws += 1
                        else:
                            outcome = -1.0
                            losses += 1
                        margin = candidate_fraction - opponent_fraction
                        tempo = 1.0 - min(1.0, duel.ticks / scenario.max_ticks)
                        score = (
                            outcome * 100.0
                            + margin * 10.0
                            + (tempo * 5.0 if outcome > 0 else -tempo * 5.0 if outcome < 0 else 0.0)
                            - candidate_result.rejected_actions * 0.25
                            - (
                                1.0
                                if duel.reason is TerminationReason.TIME_LIMIT
                                else 0.0
                            )
                        )
                        scores.append(score)
                        runs.append(
                            {
                                "opponent_digest": opponent.opponent_digest,
                                "scenario": scenario.as_dict(),
                                "seed": seed,
                                "candidate_left": candidate_left,
                                "winner": duel.winner_entity_id,
                                "termination_reason": duel.reason.value,
                                "ticks": duel.ticks,
                                "trace_digest": duel.trace_digest,
                                "candidate_final_health": candidate_result.final_health,
                                "opponent_final_health": opponent_result.final_health,
                                "candidate_rejected_actions": (
                                    candidate_result.rejected_actions
                                ),
                            }
                        )

        rollout_count = len(runs)
        if rollout_count == 0:
            return None
        evidence_digest = canonical_digest(
            {
                "evaluator_version": self.EVALUATOR_VERSION,
                "candidate_compilation": compilation.compilation_digest,
                "catalog_legality_audit": None if audit is None else audit.as_dict(),
                "ruleset_id": self._ruleset.ruleset_id,
                "opponents": [
                    {
                        "id": item.opponent_id,
                        "digest": item.opponent_digest,
                    }
                    for item in self._opponents
                ],
                "scenarios": [item.as_dict() for item in self._scenarios],
                "seeds": list(self._seeds),
                "runs": runs,
            }
        )
        action_count = float(len(compilation.view.executable_action_keys))
        resource_depth = float(
            compilation.view.body.health
            + compilation.view.body.mana
            + compilation.view.body.stamina
        )
        notes = tuple(
            dict.fromkeys(
                (
                    *(
                        f"unresolved:{item}"
                        for item in compilation.coverage.unresolved
                    ),
                    *(
                        f"accepted_assumption:{item}"
                        for item in compilation.coverage.accepted_assumptions
                    ),
                    "policy actions execute through the existing semantic lifecycle",
                    "runtime action requirement tags are derived from compiled "
                    "action specifications",
                )
            )
        )
        return MapElitesEvaluation(
            candidate_digest=genome.genome_digest,
            quality=fmean(scores),
            admission=(
                ArchiveAdmission.STRICT
                if compilation.status is BuildCompilationStatus.SIMULATION_READY
                else ArchiveAdmission.CANDIDATE
            ),
            features=(
                ("action_count", action_count),
                ("resource_depth", resource_depth),
                ("survival_rate", survivals / rollout_count),
            ),
            metrics=(
                ("draw_rate", draws / rollout_count),
                ("loss_rate", losses / rollout_count),
                ("mean_candidate_health_fraction", fmean(health_fractions)),
                (
                    "mean_opponent_health_fraction",
                    fmean(opponent_health_fractions),
                ),
                ("mean_rejected_actions", fmean(rejected_actions)),
                ("mean_ticks", fmean(ticks)),
                ("rollout_count", float(rollout_count)),
                ("win_rate", wins / rollout_count),
            ),
            evidence_digest=evidence_digest,
            notes=notes,
        )

    def _loadout(self, compilation: CompiledLegalBuild, *, role: str) -> PrimitiveLoadout:
        loadout = primitive_loadout_from_build_view(compilation.view)
        attributes = compilation.calculator_output.attributes
        skills = dict(compilation.genome.skill_ranks)
        scalars = dict(loadout.scalars)

        weapon_skill = max(
            (
                rank
                for key, rank in skills.items()
                if key in {"unarmed", "unarmed_combat", "sword", "axe", "dagger"}
            ),
            default=0,
        )
        weapon_mastery = max(
            (
                rank
                for key, rank in skills.items()
                if key.endswith("_mastery") or key == "unarmed_mastery"
            ),
            default=weapon_skill,
        )
        if weapon_skill > 0:
            rating = float(
                weapon_attack_rating(
                    weapon_skill,
                    weapon_mastery,
                    attributes.strength,
                    attributes.dexterity,
                )
            )
            scalars["attack.main_hand"] = rating
            scalars["attack_rating"] = rating
            if "weapon.off_hand.damage_min" in scalars:
                scalars["attack.off_hand"] = rating

        required_tags = set(loadout.tags)
        for action_key in compilation.view.executable_action_keys:
            record = self._ruleset.record(action_key)
            if record.action is None:
                continue
            required_tags.update(record.action.required_actor_tags)
            if record.progression is None:
                continue
            focus = max(
                (
                    skills.get(requirement.training_key, 0)
                    for requirement in record.progression.skill_requirements
                ),
                default=0,
            )
            if focus > 0:
                scalars[f"attack.power.{action_key}"] = float(
                    power_attack_rating(focus, attributes.dexterity)
                )

        metadata = dict(loadout.metadata)
        metadata.update(
            {
                "compilation_digest": compilation.compilation_digest,
                "evaluation_role": role,
            }
        )
        return replace(
            loadout,
            loadout_id=(
                f"{role}.{compilation.genome.genome_digest[:20]}"
            ),
            tags=tuple(sorted(required_tags)),
            scalars=tuple(sorted(scalars.items())),
            metadata=tuple(sorted(metadata.items())),
        )


class CompilerBackedGenomeMutator:
    """Mutate declared choices and return only compiler- and gate-admitted children."""

    def __init__(
        self,
        compiler: LegalBuildCompiler,
        *,
        gate: CatalogBackedLegalityGate | None = None,
        rune_ids: tuple[int, ...] = (),
        equipment_options: tuple[tuple[str, tuple[int, ...]], ...] = (),
        power_options: tuple[tuple[str, int], ...] = (),
        maximum_attempts: int = 64,
    ) -> None:
        if not isinstance(compiler, LegalBuildCompiler):
            raise LegalBuildCompileError("compiler has the wrong type")
        if gate is not None and not isinstance(gate, CatalogBackedLegalityGate):
            raise LegalBuildCompileError("gate has the wrong type")
        if len(rune_ids) != len(set(rune_ids)):
            raise LegalBuildCompileError("rune_ids must not contain duplicates")
        slot_keys = tuple(slot for slot, _ in equipment_options)
        if len(slot_keys) != len(set(slot_keys)):
            raise LegalBuildCompileError("equipment option slots must be unique")
        power_keys = tuple(key for key, _ in power_options)
        if len(power_keys) != len(set(power_keys)):
            raise LegalBuildCompileError("power option keys must be unique")
        for slot, item_ids in equipment_options:
            _identifier(slot, "equipment option slot")
            if not item_ids or len(item_ids) != len(set(item_ids)):
                raise LegalBuildCompileError(
                    "equipment option item ids must be non-empty and unique"
                )
            for item_id in item_ids:
                if isinstance(item_id, bool) or not isinstance(item_id, int) or item_id <= 0:
                    raise LegalBuildCompileError(
                        "equipment option item ids must be positive integers"
                    )
        for key, rank in power_options:
            _identifier(key, "power option key")
            _non_negative_integer(rank, f"power option {key}")
        if (
            isinstance(maximum_attempts, bool)
            or not isinstance(maximum_attempts, int)
            or not 1 <= maximum_attempts <= 10_000
        ):
            raise LegalBuildCompileError("maximum_attempts must be in [1, 10000]")
        self._compiler = compiler
        self._gate = gate
        self._rune_ids = tuple(sorted(rune_ids))
        self._equipment_options = tuple(
            (slot, tuple(sorted(item_ids))) for slot, item_ids in sorted(equipment_options)
        )
        self._power_options = tuple(sorted(power_options))
        self._maximum_attempts = maximum_attempts

    def __call__(
        self,
        parent: LegalBuildGenome,
        random: DeterministicRandom,
    ) -> LegalBuildGenome | None:
        if not isinstance(parent, LegalBuildGenome):
            raise LegalBuildCompileError("parent must be LegalBuildGenome")
        if not isinstance(random, DeterministicRandom):
            raise LegalBuildCompileError("random must be DeterministicRandom")
        operations = ["attributes"]
        if self._rune_ids:
            operations.append("rune")
        if self._equipment_options:
            operations.append("equipment")
        if self._power_options:
            operations.append("power")

        for _ in range(self._maximum_attempts):
            operation = operations[random.randbelow(len(operations))]
            candidate = (
                self._mutate_attributes(parent, random)
                if operation == "attributes"
                else self._mutate_rune(parent, random)
                if operation == "rune"
                else self._mutate_equipment(parent, random)
                if operation == "equipment"
                else self._mutate_power(parent, random)
            )
            if candidate is None or candidate.genome_digest == parent.genome_digest:
                continue
            try:
                if self._gate is not None:
                    self._gate.validate(candidate)
                compilation = self._compiler.compile(candidate)
            except (LegalBuildCompileError, KeyError, ValueError):
                continue
            if not compilation.view.executable_action_keys:
                continue
            return candidate
        return None

    def _mutate_attributes(
        self,
        parent: LegalBuildGenome,
        random: DeterministicRandom,
    ) -> LegalBuildGenome | None:
        candidate = self._compiler.mutate_attributes(
            parent,
            random,
            maximum_attempts=8,
        )
        return None if candidate.genome_digest == parent.genome_digest else candidate

    def _mutate_rune(
        self,
        parent: LegalBuildGenome,
        random: DeterministicRandom,
    ) -> LegalBuildGenome | None:
        selected = set(parent.rune_ids)
        available = tuple(item for item in self._rune_ids if item not in selected)
        can_remove = bool(selected)
        can_add = bool(available)
        if not can_remove and not can_add:
            return None
        remove = can_remove and (not can_add or random.randbelow(2) == 0)
        if remove:
            ordered = tuple(sorted(selected))
            selected.remove(ordered[random.randbelow(len(ordered))])
        else:
            selected.add(available[random.randbelow(len(available))])
        return self._replace(parent, rune_ids=tuple(sorted(selected)))

    def _mutate_equipment(
        self,
        parent: LegalBuildGenome,
        random: DeterministicRandom,
    ) -> LegalBuildGenome | None:
        slot, item_ids = self._equipment_options[
            random.randbelow(len(self._equipment_options))
        ]
        current = {item.slot_key: item for item in parent.equipment}
        choices: tuple[int | None, ...] = (None, *item_ids)
        current_id = current.get(slot).item_id if slot in current else None
        alternatives = tuple(item for item in choices if item != current_id)
        if not alternatives:
            return None
        selected_id = alternatives[random.randbelow(len(alternatives))]
        if selected_id is None:
            current.pop(slot, None)
        else:
            current[slot] = EquipmentSelection(slot, selected_id)
        return self._replace(
            parent,
            equipment=tuple(current[key] for key in sorted(current)),
        )

    def _mutate_power(
        self,
        parent: LegalBuildGenome,
        random: DeterministicRandom,
    ) -> LegalBuildGenome | None:
        key, rank = self._power_options[random.randbelow(len(self._power_options))]
        powers = dict(parent.power_ranks)
        if key in powers:
            del powers[key]
        else:
            powers[key] = rank
        return self._replace(parent, power_ranks=tuple(sorted(powers.items())))

    @staticmethod
    def _replace(parent: LegalBuildGenome, **changes) -> LegalBuildGenome:
        payload = {
            "parent": parent.genome_digest,
            "changes": _json_safe(changes),
        }
        suffix = canonical_digest(payload)[:16]
        return replace(
            parent,
            genome_id=f"{parent.genome_id}.m.{suffix}",
            display_name=f"{parent.display_name} mutation {suffix[:8]}",
            **changes,
        )


def _json_safe(value):
    if isinstance(value, EquipmentSelection):
        return value.as_dict()
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in sorted(value.items())}
    return value


def evaluation_digest(evaluation: MapElitesEvaluation) -> str:
    """Return a stable digest for regression tests and experiment receipts."""

    return hashlib.sha256(
        json.dumps(
            evaluation.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    "CatalogBackedLegalityGate",
    "CatalogLegalityAudit",
    "CompiledOpponent",
    "CompilerBackedGenomeMutator",
    "DuelScenario",
    "EquipmentSkillRequirement",
    "LegalBuildLeagueEvaluator",
    "evaluation_digest",
]
