"""Fail-closed legal-build league evaluation over the semantic lifecycle."""

from __future__ import annotations

from dataclasses import replace
from statistics import fmean

from shadowbane_lab.composition.adapters import primitive_loadout_from_build_view
from shadowbane_lab.rollouts.duel import TerminationReason

from .build_model import (
    BuildCompilationStatus,
    CompiledLegalBuild,
    LegalBuildCompileError,
    LegalBuildGenome,
    canonical_digest,
)
from .map_elites import ArchiveAdmission, MapElitesEvaluation
from .policy_rollout import run_open_duel_with_policies
from .static_capabilities import project_static_capabilities
from .training import LegalBuildLeagueEvaluator, genome_mechanical_digest


class StrictLegalBuildLeagueEvaluator(LegalBuildLeagueEvaluator):
    """Evaluate builds without manufacturing static or transient prerequisites.

    The loose open-build harness may synthesize selected requirement tags to explore a
    behavior recipe in isolation. Legal build search must instead retain each action in
    the actor's action set while allowing the authoritative affordance builder to expose
    it only when the compiled build or runtime state actually supplies every requirement.
    """

    EVALUATOR_VERSION = 3

    def __call__(self, genome: LegalBuildGenome) -> MapElitesEvaluation | None:
        try:
            audit = None if self._gate is None else self._gate.validate(genome)
            compilation = self._compiler.compile(genome)
        except (LegalBuildCompileError, KeyError, ValueError):
            return None
        if not compilation.view.executable_action_keys:
            return None

        candidate_projection = project_static_capabilities(compilation)
        candidate = self._strict_loadout(compilation, role="candidate")
        runs: list[dict[str, object]] = []
        scores: list[float] = []
        wins = draws = losses = survivals = 0
        health_fractions: list[float] = []
        opponent_health_fractions: list[float] = []
        ticks: list[float] = []
        rejected_actions: list[float] = []
        unsatisfied_requirements: set[str] = set()

        for opponent in self._opponents:
            opponent_projection = project_static_capabilities(opponent.compilation)
            opponent_loadout = self._strict_loadout(
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
                        run = run_open_duel_with_policies(
                            self._ruleset,
                            left,
                            right,
                            starting_distance=scenario.starting_distance,
                            max_ticks=scenario.max_ticks,
                            seed=seed,
                            auto_satisfy_action_requirements=False,
                        )
                        duel = run.duel
                        candidate_resolved = run.left if candidate_left else run.right
                        unsatisfied_requirements.update(
                            candidate_resolved.unsatisfied_requirement_tags
                        )
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
                            + (
                                tempo * 5.0
                                if outcome > 0
                                else -tempo * 5.0
                                if outcome < 0
                                else 0.0
                            )
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
                                "opponent_static_capabilities": (
                                    opponent_projection.projection_digest
                                ),
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
                                "candidate_unsatisfied_requirement_tags": list(
                                    candidate_resolved.unsatisfied_requirement_tags
                                ),
                                "candidate_auto_added_tags": list(
                                    candidate_resolved.auto_added_tags
                                ),
                            }
                        )

        rollout_count = len(runs)
        if rollout_count == 0:
            return None
        evidence_digest = canonical_digest(
            {
                "evaluator_version": self.EVALUATOR_VERSION,
                "prerequisite_mode": "strict_fail_closed",
                "candidate_compilation": compilation.compilation_digest,
                "candidate_mechanical_digest": genome_mechanical_digest(genome),
                "candidate_static_capabilities": candidate_projection.as_dict(),
                "catalog_legality_audit": None if audit is None else audit.as_dict(),
                "ruleset_id": self._ruleset.ruleset_id,
                "opponents": [
                    {
                        "id": item.opponent_id,
                        "digest": item.opponent_digest,
                        "static_capabilities": project_static_capabilities(
                            item.compilation
                        ).as_dict(),
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
                    *(
                        f"static_capability:{item.tag}:{item.evidence_status}"
                        for item in candidate_projection.grants
                    ),
                    *(
                        f"unresolved_static_capability:{item}"
                        for item in candidate_projection.unresolved
                    ),
                    *(
                        f"unsatisfied_action_requirement:{item}"
                        for item in sorted(unsatisfied_requirements)
                    ),
                    "policy actions execute through the existing semantic lifecycle",
                    "action prerequisites are never synthesized for legal-build search",
                )
            )
        )
        return MapElitesEvaluation(
            candidate_digest=genome_mechanical_digest(genome),
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
                (
                    "unsatisfied_requirement_count",
                    float(len(unsatisfied_requirements)),
                ),
                ("win_rate", wins / rollout_count),
            ),
            evidence_digest=evidence_digest,
            notes=notes,
        )

    def _strict_loadout(
        self,
        compilation: CompiledLegalBuild,
        *,
        role: str,
    ):
        derived = super()._loadout(compilation, role=role)
        proven = primitive_loadout_from_build_view(compilation.view)
        projection = project_static_capabilities(compilation)
        metadata = dict(derived.metadata)
        metadata["action_prerequisite_mode"] = "strict_fail_closed"
        metadata["static_capability_projection"] = projection.projection_digest
        return replace(
            derived,
            tags=projection.tags,
            metadata=tuple(sorted(metadata.items())),
            notes=tuple(
                dict.fromkeys(
                    (
                        *derived.notes,
                        *(
                            f"Static capability {item.tag} from "
                            f"{item.source_kind}:{item.source_key} "
                            f"({item.evidence_status})."
                            for item in projection.grants
                        ),
                        *(
                            f"Unresolved static capability: {item}."
                            for item in projection.unresolved
                        ),
                        "Required actor tags are supplied only by compiled build or runtime state.",
                    )
                )
            ),
        )


__all__ = ["StrictLegalBuildLeagueEvaluator"]
