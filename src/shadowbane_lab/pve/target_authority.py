"""Bound target validation and optional positive hostile-NPC authority."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, fields
from enum import StrEnum

from shadowbane_lab.pve.authority import (
    PvETargetAuthorityDecision,
    PvETargetAuthorityEvaluator,
    evaluate_pve_target_authority,
)
from shadowbane_lab.pve.controller import PvEController as _BasePvEController
from shadowbane_lab.pve.model import (
    PvEAbility,
    PvEControllerConfig,
    PvEControllerDecision,
    PvEIntent,
    PvEKillConfirmation,
    PvEObservation,
    PvEPhase,
    PvETrackedTarget,
)


class PvETargetRejectionReason(StrEnum):
    """Stable reasons why a native-population candidate was quarantined."""

    TARGET_CYCLE_WRAPPED = "target_cycle_wrapped"
    TARGET_SNAPSHOT_UNAVAILABLE = "target_snapshot_unavailable"
    TARGET_IDENTITY_UNAVAILABLE = "target_identity_unavailable"
    TARGET_DEAD = "target_dead"
    TARGET_OUTSIDE_CAMP = "target_outside_camp"
    TARGET_NOT_ATTACK_ELIGIBLE = "target_not_attack_eligible"
    TARGET_AUTHORITY_UNAVAILABLE = "target_authority_unavailable"
    TARGET_AUTHORITY_REJECTED = "target_authority_rejected"


@dataclass(frozen=True, slots=True)
class PvETargetRejection:
    """One bounded native-population candidate rejection."""

    target_token: str
    reason: PvETargetRejectionReason
    at_ms: int
    validation_wait_ms: int
    population_generation: int
    selected_target_token: str | None
    authority_exclusions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.target_token, str) or not self.target_token.strip():
            raise ValueError("target rejection requires a non-empty target token")
        if not isinstance(self.reason, PvETargetRejectionReason):
            raise ValueError("target rejection reason must be PvETargetRejectionReason")
        for value, field_name in (
            (self.at_ms, "at_ms"),
            (self.validation_wait_ms, "validation_wait_ms"),
            (self.population_generation, "population_generation"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.selected_target_token is not None and not self.selected_target_token.strip():
            raise ValueError("selected_target_token must be non-empty when present")
        if not isinstance(self.authority_exclusions, tuple):
            raise ValueError("authority_exclusions must be a tuple")
        if len(self.authority_exclusions) != len(set(self.authority_exclusions)):
            raise ValueError("authority_exclusions must not contain duplicates")
        if any(
            not isinstance(value, str) or not value.strip() for value in self.authority_exclusions
        ):
            raise ValueError("authority_exclusions must contain non-empty strings")

    def as_dict(self) -> dict[str, object]:
        return {
            "target_token": self.target_token,
            "reason": self.reason.value,
            "at_ms": self.at_ms,
            "validation_wait_ms": self.validation_wait_ms,
            "population_generation": self.population_generation,
            "selected_target_token": self.selected_target_token,
            "authority_exclusions": list(self.authority_exclusions),
        }


@dataclass(frozen=True, slots=True)
class PvETargetAuthorityControllerDecision(PvEControllerDecision):
    """Controller decision carrying authority evidence from the same observation."""

    target_authority: PvETargetAuthorityDecision | None = None
    target_rejections: tuple[PvETargetRejection, ...] = ()

    def __post_init__(self) -> None:
        PvEControllerDecision.__post_init__(self)
        if self.target_authority is not None:
            if not isinstance(self.target_authority, PvETargetAuthorityDecision):
                raise ValueError("target_authority must be PvETargetAuthorityDecision")
            if self.target_authority.observed_at_ms != self.now_ms:
                raise ValueError("target authority time must match controller decision time")
        if not isinstance(self.target_rejections, tuple):
            raise ValueError("target_rejections must be a tuple")
        if any(not isinstance(value, PvETargetRejection) for value in self.target_rejections):
            raise ValueError("target_rejections must contain PvETargetRejection values")
        if any(value.at_ms != self.now_ms for value in self.target_rejections):
            raise ValueError("target rejection time must match controller decision time")

    @classmethod
    def from_decision(
        cls,
        decision: PvEControllerDecision,
        *,
        target_authority: PvETargetAuthorityDecision | None,
        target_rejections: tuple[PvETargetRejection, ...],
    ) -> PvETargetAuthorityControllerDecision:
        if not isinstance(decision, PvEControllerDecision):
            raise ValueError("decision must be PvEControllerDecision")
        values = {
            field.name: getattr(decision, field.name) for field in fields(PvEControllerDecision)
        }
        return cls(
            **values,
            target_authority=target_authority,
            target_rejections=target_rejections,
        )


class PvEController(_BasePvEController):
    """Bounds candidate validation and can require verified hostile-NPC proof."""

    _MAXIMUM_RETAINED_TARGET_REJECTIONS = 256
    _MAXIMUM_RETAINED_AUTHORITY_DECISIONS = 256

    def __init__(
        self,
        config: PvEControllerConfig,
        *,
        target_authority_evaluator: PvETargetAuthorityEvaluator | None = None,
        require_verified_target_authority: bool = False,
    ) -> None:
        if not isinstance(require_verified_target_authority, bool):
            raise ValueError("require_verified_target_authority must be boolean")
        if target_authority_evaluator is not None and not isinstance(
            target_authority_evaluator,
            PvETargetAuthorityEvaluator,
        ):
            raise ValueError(
                "target_authority_evaluator must implement PvETargetAuthorityEvaluator"
            )
        if require_verified_target_authority and target_authority_evaluator is None:
            raise ValueError("verified target authority requires a target_authority_evaluator")
        super().__init__(config)
        self._population_candidate_selected_at: int | None = None
        self._target_rejections: deque[PvETargetRejection] = deque(
            maxlen=self._MAXIMUM_RETAINED_TARGET_REJECTIONS
        )
        self._target_authority_evaluator = target_authority_evaluator
        self._require_verified_target_authority = require_verified_target_authority
        self._active_target_authority: PvETargetAuthorityDecision | None = None
        self._active_step_target_rejections: list[PvETargetRejection] = []
        self._target_authority_history: deque[PvETargetAuthorityDecision] = deque(
            maxlen=self._MAXIMUM_RETAINED_AUTHORITY_DECISIONS
        )

    @property
    def candidate_validation_timeout_ms(self) -> int:
        """Maximum time a selected population token may lack a usable target snapshot."""

        return min(
            self._config.acquisition_timeout_ms,
            max(
                self._config.acquisition_retry_ms,
                self._config.target_sample_interval_ms * 3,
            ),
        )

    @property
    def target_rejections(self) -> tuple[PvETargetRejection, ...]:
        """Return the bounded ordered tail of candidate rejections."""

        return tuple(self._target_rejections)

    @property
    def require_verified_target_authority(self) -> bool:
        return self._require_verified_target_authority

    @property
    def target_authority_history(self) -> tuple[PvETargetAuthorityDecision, ...]:
        """Return the bounded ordered authority decisions evaluated by this controller."""

        return tuple(self._target_authority_history)

    @property
    def latest_target_authority(self) -> PvETargetAuthorityDecision | None:
        return None if not self._target_authority_history else self._target_authority_history[-1]

    def step(
        self,
        observation: PvEObservation,
        *,
        external_combat: bool = False,
    ) -> PvEControllerDecision:
        if not isinstance(observation, PvEObservation):
            raise ValueError("observation must be PvEObservation")
        self._active_step_target_rejections.clear()
        tracked = self.tracked_target(observation) or self.observed_action_target(observation)
        self._active_target_authority = (
            None if tracked is None else self._evaluate_tracked_authority(observation, tracked)
        )
        try:
            return super().step(observation, external_combat=external_combat)
        finally:
            self._active_target_authority = None
            self._active_step_target_rejections.clear()

    def _enter(self, phase: PvEPhase, now_ms: int) -> None:
        super()._enter(phase, now_ms)
        self._population_candidate_selected_at = None

    def _evaluate_tracked_authority(
        self, observation: PvEObservation, tracked: PvETrackedTarget,
    ) -> PvETargetAuthorityDecision | None:
        evaluator = self._target_authority_evaluator
        if evaluator is None and observation.authority_snapshot is not None:
            from shadowbane_lab.pve.authority_snapshot import SnapshotPvETargetAuthorityEvaluator

            evaluator = SnapshotPvETargetAuthorityEvaluator(observation.authority_snapshot)
        if evaluator is None:
            return None
        evaluate_tracked = getattr(evaluator, "evaluate_tracked", None)
        authority = (
            evaluate_tracked(observation, tracked) if callable(evaluate_tracked)
            else evaluate_pve_target_authority(observation, None, tracked_target=tracked)
        )
        if not isinstance(authority, PvETargetAuthorityDecision):
            raise ValueError("target authority evaluator must return PvETargetAuthorityDecision")
        if (authority.observed_at_ms != observation.now_ms
                or authority.target_token != tracked.token):
            raise ValueError("target authority decision does not match tracked observation")
        if authority.accepted and authority.target_object_key != tracked.object_key:
            raise ValueError("tracked target authority decision object key does not match")
        self._target_authority_history.append(authority)
        return authority

    def _tracked_target_attack_eligible(
        self,
        observation: PvEObservation,
        tracked: PvETrackedTarget,
    ) -> bool:
        if not super()._tracked_target_attack_eligible(observation, tracked):
            return False
        authority = self._active_target_authority
        if authority is None or authority.target_token != tracked.token:
            authority = self._evaluate_tracked_authority(observation, tracked)
            self._active_target_authority = authority
        if not self._require_verified_target_authority:
            return True
        accepted = bool(
            authority is not None and authority.accepted
            and authority.target_token == tracked.token
            and authority.target_object_key == tracked.object_key
        )
        if not accepted and self._engaged_target_token is None:
            self._quarantine_population_candidate(
                observation, tracked,
                PvETargetRejectionReason.TARGET_AUTHORITY_UNAVAILABLE if authority is None
                else PvETargetRejectionReason.TARGET_AUTHORITY_REJECTED,
            )
        return accepted

    def _quarantine_population_candidate(
        self,
        observation: PvEObservation,
        tracked: PvETrackedTarget,
        reason: PvETargetRejectionReason,
    ) -> None:
        target_token = tracked.token
        population = observation.population
        assert population is not None
        selected_at = self._population_candidate_selected_at
        validation_wait_ms = 0 if selected_at is None else max(0, observation.now_ms - selected_at)
        authority = self._active_target_authority
        authority_exclusions = (
            ()
            if authority is None or authority.target_token != target_token
            else tuple(value.value for value in authority.exclusions)
        )
        rejection = PvETargetRejection(
            target_token=target_token,
            reason=reason,
            at_ms=observation.now_ms,
            validation_wait_ms=validation_wait_ms,
            population_generation=population.scan_generation,
            selected_target_token=population.selected_target_token,
            authority_exclusions=authority_exclusions,
        )
        self._target_rejections.append(rejection)
        self._active_step_target_rejections.append(rejection)
        self._failed_targets[(target_token, tracked.object_key)] = observation.now_ms
        self._population_desired_target_token = None
        self._population_cycle_seen.clear()
        self._population_candidate_selected_at = None

    def _emit(
        self,
        now_ms: int,
        intent: PvEIntent | None = None,
        *,
        ability: PvEAbility | None = None,
        terminal_reason: str | None = None,
        kill_confirmation: PvEKillConfirmation | None = None,
        reposition_requested: bool = False,
        return_to_camp: bool = False,
    ) -> PvEControllerDecision:
        decision = super()._emit(
            now_ms,
            intent,
            ability=ability,
            terminal_reason=terminal_reason,
            kill_confirmation=kill_confirmation,
            reposition_requested=reposition_requested,
            return_to_camp=return_to_camp,
        )
        return PvETargetAuthorityControllerDecision.from_decision(
            decision,
            target_authority=self._active_target_authority,
            target_rejections=tuple(self._active_step_target_rejections),
        )
