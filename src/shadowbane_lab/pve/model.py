"""Typed contracts for the bounded PvE controller and runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import hypot, isfinite

from shadowbane_lab.client_observation import (
    NativeCombatEvent,
    NativePlayerActionObservation,
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
    NativeTargetActionObservation,
    NativeTargetHealthObservation,
    NativeTargetIdentityObservation,
    NativeTargetPositionObservation,
)
from shadowbane_lab.travel.model import TravelDecision, TravelDestination


def _positive_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _non_negative_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


class PvEIntent(StrEnum):
    ACQUIRE_NEXT_MOB = "client.pve.target_next_mobile"
    ACQUIRE_PREVIOUS_MOB = "client.pve.target_previous_mobile"
    CAST_SHADOW_TOUCH = "shadowbane.assassin.shadow_touch"
    ATTACK_SELECTED_TARGET = "shadowbane.basic_attack"


class PvEPhase(StrEnum):
    INITIALIZING = "initializing"
    SEEKING = "seeking"
    OPENING = "opening"
    ENGAGED = "engaged"
    POST_KILL = "post_kill"
    CAMP_IDLE = "camp_idle"
    COMPLETE = "complete"
    STOPPED = "stopped"


class PvEKillConfirmation(StrEnum):
    NATIVE_COMBAT_EVENT = "native_combat_event"
    NATIVE_HEALTH_ZERO = "native_health_zero"


@dataclass(frozen=True, slots=True)
class PvECampLease:
    """The spatial operating boundary captured where a continuous run starts."""

    anchor_lt: float
    anchor_lg: float
    radius: float
    return_radius: float

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.anchor_lt, "anchor_lt"),
            (self.anchor_lg, "anchor_lg"),
            (self.radius, "radius"),
            (self.return_radius, "return_radius"),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError(f"camp {field_name} must be finite")
        if self.radius <= 0:
            raise ValueError("camp radius must be positive")
        if self.return_radius <= 0 or self.return_radius >= self.radius:
            raise ValueError("camp return_radius must be positive and below radius")

    def contains(self, lt: float, lg: float) -> bool:
        return hypot(lt - self.anchor_lt, lg - self.anchor_lg) <= self.radius

    def distance_from_anchor(self, lt: float, lg: float) -> float:
        return hypot(lt - self.anchor_lt, lg - self.anchor_lg)

    @property
    def return_destination(self) -> TravelDestination:
        return TravelDestination(
            lt=self.anchor_lt,
            lg=self.anchor_lg,
            arrival_radius=self.return_radius,
        )


@dataclass(frozen=True, slots=True)
class PvEControllerConfig:
    maximum_kills: int = 1
    maximum_session_ms: int = 120_000
    acquisition_retry_ms: int = 1_000
    acquisition_timeout_ms: int = 15_000
    stale_selection_cycle_delay_ms: int = 1_000
    nearest_target_sample_count: int = 1
    target_sample_interval_ms: int = 350
    engagement_timeout_ms: int = 30_000
    stalled_progress_ms: int = 5_000
    quiet_melee_timeout_ms: int = 2_500
    missing_attack_animation_timeout_ms: int = 1_500
    incoming_reposition_grace_ms: int = 1_500
    incoming_reposition_window_ms: int = 3_000
    selection_loss_grace_ms: int = 750
    post_kill_delay_ms: int = 1_000
    recovery_timeout_ms: int = 30_000
    maximum_reengage_attempts: int = 2
    maximum_stalled_retargets: int = 0
    maximum_combat_repositions: int = 2
    minimum_player_health_fraction: float = 0.5
    minimum_recovery_health_fraction: float = 0.0
    minimum_recovery_mana_fraction: float = 0.0
    minimum_recovery_stamina_fraction: float = 0.0
    accept_automatic_targets: bool = False
    opening_intent: PvEIntent | None = None
    opening_mana_cost: float = 0.0
    opening_followup_delay_ms: int = 250
    interrupt_intent: PvEIntent | None = None
    interrupt_mana_cost: float = 0.0
    interrupt_cooldown_ms: int = 0
    maximum_interrupts_per_target: int = 0
    automatic_attack_expected: bool = False
    automatic_target_requires_combat_event: bool = False
    require_target_identity: bool = False
    melee_approach_radius: float = 20.0
    minimum_approach_progress: float = 8.0
    continuous: bool = False
    camp_radius: float | None = None
    camp_return_radius: float = 12.0
    camp_idle_ms: int = 5_000
    camp_return_retry_ms: int = 5_000
    failed_target_cooldown_ms: int = 30_000

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.maximum_kills, "maximum_kills"),
            (self.maximum_session_ms, "maximum_session_ms"),
            (self.acquisition_retry_ms, "acquisition_retry_ms"),
            (self.acquisition_timeout_ms, "acquisition_timeout_ms"),
            (self.stale_selection_cycle_delay_ms, "stale_selection_cycle_delay_ms"),
            (self.nearest_target_sample_count, "nearest_target_sample_count"),
            (self.target_sample_interval_ms, "target_sample_interval_ms"),
            (self.engagement_timeout_ms, "engagement_timeout_ms"),
            (self.stalled_progress_ms, "stalled_progress_ms"),
            (self.quiet_melee_timeout_ms, "quiet_melee_timeout_ms"),
            (
                self.missing_attack_animation_timeout_ms,
                "missing_attack_animation_timeout_ms",
            ),
            (self.incoming_reposition_grace_ms, "incoming_reposition_grace_ms"),
            (self.incoming_reposition_window_ms, "incoming_reposition_window_ms"),
            (self.selection_loss_grace_ms, "selection_loss_grace_ms"),
            (self.post_kill_delay_ms, "post_kill_delay_ms"),
            (self.recovery_timeout_ms, "recovery_timeout_ms"),
            (self.opening_followup_delay_ms, "opening_followup_delay_ms"),
            (self.camp_idle_ms, "camp_idle_ms"),
            (self.camp_return_retry_ms, "camp_return_retry_ms"),
            (self.failed_target_cooldown_ms, "failed_target_cooldown_ms"),
        ):
            _positive_integer(value, field_name)
        _non_negative_integer(self.maximum_reengage_attempts, "maximum_reengage_attempts")
        _non_negative_integer(self.maximum_stalled_retargets, "maximum_stalled_retargets")
        _non_negative_integer(
            self.maximum_combat_repositions,
            "maximum_combat_repositions",
        )
        _non_negative_integer(self.interrupt_cooldown_ms, "interrupt_cooldown_ms")
        _non_negative_integer(
            self.maximum_interrupts_per_target,
            "maximum_interrupts_per_target",
        )
        if (
            isinstance(self.minimum_player_health_fraction, bool)
            or not isinstance(self.minimum_player_health_fraction, (int, float))
            or not 0.0 < self.minimum_player_health_fraction <= 1.0
        ):
            raise ValueError("minimum_player_health_fraction must be in (0, 1]")
        if self.acquisition_retry_ms > self.acquisition_timeout_ms:
            raise ValueError("acquisition retry cannot exceed acquisition timeout")
        if self.stale_selection_cycle_delay_ms > self.acquisition_timeout_ms:
            raise ValueError("stale selection cycle delay cannot exceed acquisition timeout")
        if self.target_sample_interval_ms > self.acquisition_timeout_ms:
            raise ValueError("target sample interval cannot exceed acquisition timeout")
        if self.stalled_progress_ms > self.engagement_timeout_ms:
            raise ValueError("stalled progress timeout cannot exceed engagement timeout")
        if self.missing_attack_animation_timeout_ms > self.quiet_melee_timeout_ms:
            raise ValueError(
                "missing attack-animation timeout cannot exceed quiet melee timeout"
            )
        if self.selection_loss_grace_ms > self.engagement_timeout_ms:
            raise ValueError("selection loss grace cannot exceed engagement timeout")
        if self.post_kill_delay_ms > self.recovery_timeout_ms:
            raise ValueError("post-kill delay cannot exceed recovery timeout")
        for value, field_name in (
            (self.minimum_recovery_health_fraction, "minimum_recovery_health_fraction"),
            (self.minimum_recovery_mana_fraction, "minimum_recovery_mana_fraction"),
            (
                self.minimum_recovery_stamina_fraction,
                "minimum_recovery_stamina_fraction",
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValueError(f"{field_name} must be in [0, 1]")
        if (
            self.minimum_recovery_health_fraction != 0
            and self.minimum_recovery_health_fraction
            < self.minimum_player_health_fraction
        ):
            raise ValueError(
                "minimum recovery health cannot be below the player safety threshold"
            )
        for value, field_name in (
            (self.accept_automatic_targets, "accept_automatic_targets"),
            (self.automatic_attack_expected, "automatic_attack_expected"),
            (
                self.automatic_target_requires_combat_event,
                "automatic_target_requires_combat_event",
            ),
            (self.require_target_identity, "require_target_identity"),
            (self.continuous, "continuous"),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"{field_name} must be a boolean")
        if self.camp_radius is not None and (
            isinstance(self.camp_radius, bool)
            or not isinstance(self.camp_radius, (int, float))
            or not isfinite(self.camp_radius)
            or self.camp_radius <= 0
        ):
            raise ValueError("camp_radius must be positive when present")
        if (
            isinstance(self.camp_return_radius, bool)
            or not isinstance(self.camp_return_radius, (int, float))
            or not isfinite(self.camp_return_radius)
            or self.camp_return_radius <= 0
        ):
            raise ValueError("camp_return_radius must be positive")
        if self.continuous and self.camp_radius is None:
            raise ValueError("continuous PvE requires a camp_radius")
        if (
            self.camp_radius is not None
            and self.camp_return_radius >= self.camp_radius
        ):
            raise ValueError("camp_return_radius must be below camp_radius")
        if self.opening_intent is not None and not isinstance(self.opening_intent, PvEIntent):
            raise ValueError("opening_intent must be PvEIntent when present")
        if self.opening_intent in (
            PvEIntent.ACQUIRE_NEXT_MOB,
            PvEIntent.ACQUIRE_PREVIOUS_MOB,
            PvEIntent.ATTACK_SELECTED_TARGET,
        ):
            raise ValueError("opening_intent must be a power activation")
        if (
            isinstance(self.opening_mana_cost, bool)
            or not isinstance(self.opening_mana_cost, (int, float))
            or not isfinite(self.opening_mana_cost)
            or self.opening_mana_cost < 0
        ):
            raise ValueError("opening_mana_cost must be a non-negative number")
        if self.opening_intent is None and self.opening_mana_cost != 0:
            raise ValueError("opening_mana_cost requires an opening_intent")
        if self.interrupt_intent is not None and not isinstance(
            self.interrupt_intent, PvEIntent
        ):
            raise ValueError("interrupt_intent must be PvEIntent when present")
        if self.interrupt_intent in (
            PvEIntent.ACQUIRE_NEXT_MOB,
            PvEIntent.ACQUIRE_PREVIOUS_MOB,
            PvEIntent.ATTACK_SELECTED_TARGET,
        ):
            raise ValueError("interrupt_intent must be a power activation")
        if (
            isinstance(self.interrupt_mana_cost, bool)
            or not isinstance(self.interrupt_mana_cost, (int, float))
            or not isfinite(self.interrupt_mana_cost)
            or self.interrupt_mana_cost < 0
        ):
            raise ValueError("interrupt_mana_cost must be a non-negative number")
        if self.interrupt_intent is None and any(
            (
                self.interrupt_mana_cost != 0,
                self.interrupt_cooldown_ms != 0,
                self.maximum_interrupts_per_target != 0,
            )
        ):
            raise ValueError("interrupt limits require an interrupt_intent")
        if self.interrupt_intent is not None and self.maximum_interrupts_per_target == 0:
            raise ValueError("interrupt_intent requires a positive per-target limit")
        for value, field_name in (
            (self.melee_approach_radius, "melee_approach_radius"),
            (self.minimum_approach_progress, "minimum_approach_progress"),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{field_name} must be positive")


@dataclass(frozen=True, slots=True)
class PvEObservation:
    now_ms: int
    target: NativeTargetHealthObservation
    player: NativePlayerVitalsObservation
    combat_events: tuple[NativeCombatEvent, ...] = ()
    player_position: NativePlayerPositionObservation | None = None
    target_position: NativeTargetPositionObservation | None = None
    target_action: NativeTargetActionObservation | None = None
    player_action: NativePlayerActionObservation | None = None
    target_identity: NativeTargetIdentityObservation | None = None

    def __post_init__(self) -> None:
        _non_negative_integer(self.now_ms, "now_ms")
        if not isinstance(self.target, NativeTargetHealthObservation):
            raise ValueError("target must be NativeTargetHealthObservation")
        if not isinstance(self.player, NativePlayerVitalsObservation):
            raise ValueError("player must be NativePlayerVitalsObservation")
        if any(not isinstance(event, NativeCombatEvent) for event in self.combat_events):
            raise ValueError("combat_events must contain NativeCombatEvent values")
        sequences = tuple(event.sequence for event in self.combat_events)
        if sequences != tuple(sorted(sequences)) or len(sequences) != len(set(sequences)):
            raise ValueError("combat events must have unique ascending sequences")
        if self.target_action is not None:
            if not isinstance(self.target_action, NativeTargetActionObservation):
                raise ValueError("target_action must be NativeTargetActionObservation")
            if self.target.target_present != self.target_action.target_present:
                raise ValueError("target health and action disagree about target presence")
            if (
                self.target.target_present
                and self.target.target_token != self.target_action.target_token
            ):
                raise ValueError("target health and action resolved different targets")
        if self.player_action is not None and not isinstance(
            self.player_action,
            NativePlayerActionObservation,
        ):
            raise ValueError("player_action must be NativePlayerActionObservation")
        if self.target_identity is not None:
            if not isinstance(self.target_identity, NativeTargetIdentityObservation):
                raise ValueError("target_identity must be NativeTargetIdentityObservation")
            if self.target.target_present != self.target_identity.target_present:
                raise ValueError("target health and identity disagree about target presence")
            if (
                self.target.target_present
                and self.target.target_token != self.target_identity.target_token
            ):
                raise ValueError("target health and identity resolved different targets")
        if (self.player_position is None) != (self.target_position is None):
            raise ValueError("player and target positions must be observed together")
        if self.player_position is None:
            return
        if not isinstance(self.player_position, NativePlayerPositionObservation):
            raise ValueError("player_position must be NativePlayerPositionObservation")
        if not isinstance(self.target_position, NativeTargetPositionObservation):
            raise ValueError("target_position must be NativeTargetPositionObservation")
        if self.target.target_present != self.target_position.target_present:
            raise ValueError("target health and position disagree about target presence")
        if (
            self.target.target_present
            and self.target.target_token != self.target_position.target_token
        ):
            raise ValueError("target health and position resolved different targets")

    @property
    def target_planar_distance(self) -> float | None:
        if self.player_position is None or self.target_position is None:
            return None
        if not self.target_position.target_present:
            return None
        assert self.target_position.lt is not None
        assert self.target_position.lg is not None
        return hypot(
            self.target_position.lt - self.player_position.lt,
            self.target_position.lg - self.player_position.lg,
        )

    @property
    def target_altitude_delta(self) -> float | None:
        if self.player_position is None or self.target_position is None:
            return None
        if not self.target_position.target_present:
            return None
        assert self.target_position.altitude is not None
        return self.target_position.altitude - self.player_position.altitude

    @property
    def target_spatial_distance(self) -> float | None:
        planar = self.target_planar_distance
        altitude = self.target_altitude_delta
        if planar is None or altitude is None:
            return None
        return hypot(planar, altitude)

    @property
    def target_attack_eligible(self) -> bool | None:
        if self.target_identity is None:
            return None
        return self.target_identity.attack_eligible


@dataclass(frozen=True, slots=True)
class PvEControllerDecision:
    decision_id: int
    now_ms: int
    phase: PvEPhase
    kills: int
    intent: PvEIntent | None = None
    reposition_requested: bool = False
    camp: PvECampLease | None = None
    target_inside_camp: bool | None = None
    return_to_camp: bool = False
    terminal_reason: str | None = None
    kill_confirmation: PvEKillConfirmation | None = None

    def __post_init__(self) -> None:
        _non_negative_integer(self.decision_id, "decision_id")
        _non_negative_integer(self.now_ms, "now_ms")
        _non_negative_integer(self.kills, "kills")
        if not isinstance(self.phase, PvEPhase):
            raise ValueError("phase must be PvEPhase")
        if self.intent is not None and not isinstance(self.intent, PvEIntent):
            raise ValueError("intent must be PvEIntent when present")
        if not isinstance(self.reposition_requested, bool):
            raise ValueError("reposition_requested must be boolean")
        if self.camp is not None and not isinstance(self.camp, PvECampLease):
            raise ValueError("camp must be PvECampLease when present")
        if self.target_inside_camp is not None and not isinstance(
            self.target_inside_camp,
            bool,
        ):
            raise ValueError("target_inside_camp must be boolean when present")
        if self.target_inside_camp is not None and self.camp is None:
            raise ValueError("target_inside_camp requires a camp lease")
        if not isinstance(self.return_to_camp, bool):
            raise ValueError("return_to_camp must be boolean")
        if self.return_to_camp and self.camp is None:
            raise ValueError("return_to_camp requires a camp lease")
        if self.return_to_camp and self.phase is not PvEPhase.CAMP_IDLE:
            raise ValueError("return_to_camp is valid only while camp-idle")
        if self.kill_confirmation is not None and not isinstance(
            self.kill_confirmation, PvEKillConfirmation
        ):
            raise ValueError("kill_confirmation must be PvEKillConfirmation when present")
        if self.kill_confirmation is not None and self.intent is not None:
            raise ValueError("kill-confirmation decisions cannot dispatch input")
        if self.kill_confirmation is not None and self.reposition_requested:
            raise ValueError("kill-confirmation decisions cannot request repositioning")
        terminal = self.phase in (PvEPhase.COMPLETE, PvEPhase.STOPPED)
        if terminal != (self.terminal_reason is not None):
            raise ValueError("terminal phases require exactly one terminal reason")
        if terminal and self.intent is not None:
            raise ValueError("terminal decisions cannot dispatch an intent")
        if terminal and self.reposition_requested:
            raise ValueError("terminal decisions cannot request repositioning")
        if terminal and self.return_to_camp:
            raise ValueError("terminal decisions cannot return to camp")

    @property
    def terminal(self) -> bool:
        return self.phase in (PvEPhase.COMPLETE, PvEPhase.STOPPED)


@dataclass(frozen=True, slots=True)
class PvERunTraceStep:
    decision: PvEControllerDecision
    target_present: bool
    current_health: float | None
    maximum_health: float | None
    player_current_health: float | None = None
    player_maximum_health: float | None = None
    player_current_mana: float | None = None
    player_maximum_mana: float | None = None
    player_current_stamina: float | None = None
    player_maximum_stamina: float | None = None
    target_token: str | None = None
    player_position: NativePlayerPositionObservation | None = None
    target_position: NativeTargetPositionObservation | None = None
    target_action: NativeTargetActionObservation | None = None
    player_action: NativePlayerActionObservation | None = None
    target_identity: NativeTargetIdentityObservation | None = None
    target_planar_distance: float | None = None
    target_altitude_delta: float | None = None
    target_spatial_distance: float | None = None
    combat_events: tuple[NativeCombatEvent, ...] = ()
    input_accepted: bool | None = None
    input_reason: str | None = None
    approach_status: str | None = None
    approach_decision: TravelDecision | None = None
    approach_input_accepted: bool | None = None
    approach_input_reason: str | None = None
    movement_stop_accepted: bool | None = None
    movement_stop_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, PvEControllerDecision):
            raise ValueError("decision must be PvEControllerDecision")
        if not isinstance(self.target_present, bool):
            raise ValueError("target_present must be a boolean")
        if self.input_accepted is not None and not isinstance(self.input_accepted, bool):
            raise ValueError("input_accepted must be a boolean when present")
        if self.decision.intent is None and self.input_accepted is not None:
            raise ValueError("input outcome requires a dispatched intent")
        if self.input_reason is not None and self.input_accepted is not False:
            raise ValueError("input_reason is valid only for rejected input")
        if self.approach_status is not None and (
            not isinstance(self.approach_status, str) or not self.approach_status.strip()
        ):
            raise ValueError("approach_status must be a non-empty string when present")
        if self.approach_decision is not None and not isinstance(
            self.approach_decision, TravelDecision
        ):
            raise ValueError("approach_decision must be TravelDecision when present")
        if self.approach_input_accepted is not None and not isinstance(
            self.approach_input_accepted, bool
        ):
            raise ValueError("approach_input_accepted must be a boolean when present")
        if self.approach_input_accepted is not None and (
            self.approach_decision is None
            or self.approach_decision.minimap_direction is None
        ):
            raise ValueError("approach input outcome requires a movement decision")
        if (
            self.approach_input_reason is not None
            and self.approach_input_accepted is not False
        ):
            raise ValueError("approach_input_reason is valid only for rejected input")
        if self.movement_stop_accepted is not None and not isinstance(
            self.movement_stop_accepted, bool
        ):
            raise ValueError("movement_stop_accepted must be a boolean when present")
        if self.movement_stop_accepted is not None and (
            self.approach_decision is None or not self.approach_decision.terminal
        ):
            raise ValueError("movement stop outcome requires a terminal approach decision")
        if self.movement_stop_reason is not None and self.movement_stop_accepted is not False:
            raise ValueError("movement_stop_reason is valid only for rejected movement stop")
        if self.player_position is not None and not isinstance(
            self.player_position, NativePlayerPositionObservation
        ):
            raise ValueError("player_position must be NativePlayerPositionObservation")
        if self.target_position is not None and not isinstance(
            self.target_position, NativeTargetPositionObservation
        ):
            raise ValueError("target_position must be NativeTargetPositionObservation")
        if self.target_action is not None and not isinstance(
            self.target_action, NativeTargetActionObservation
        ):
            raise ValueError("target_action must be NativeTargetActionObservation")
        if self.player_action is not None and not isinstance(
            self.player_action,
            NativePlayerActionObservation,
        ):
            raise ValueError("player_action must be NativePlayerActionObservation")
        if self.target_identity is not None and not isinstance(
            self.target_identity, NativeTargetIdentityObservation
        ):
            raise ValueError("target_identity must be NativeTargetIdentityObservation")
        if any(not isinstance(event, NativeCombatEvent) for event in self.combat_events):
            raise ValueError("combat_events must contain NativeCombatEvent values")

    def as_dict(self) -> dict[str, object]:
        return {
            "decision_id": self.decision.decision_id,
            "at_ms": self.decision.now_ms,
            "phase": self.decision.phase.value,
            "kills": self.decision.kills,
            "kill_confirmation": (
                None
                if self.decision.kill_confirmation is None
                else self.decision.kill_confirmation.value
            ),
            "intent": None if self.decision.intent is None else self.decision.intent.value,
            "reposition_requested": self.decision.reposition_requested,
            "camp": (
                None
                if self.decision.camp is None
                else {
                    "anchor_lt": self.decision.camp.anchor_lt,
                    "anchor_lg": self.decision.camp.anchor_lg,
                    "radius": self.decision.camp.radius,
                    "return_radius": self.decision.camp.return_radius,
                    "target_inside": self.decision.target_inside_camp,
                    "return_requested": self.decision.return_to_camp,
                }
            ),
            "target": {
                "present": self.target_present,
                "token": self.target_token,
                "current_health": self.current_health,
                "maximum_health": self.maximum_health,
                "lt": None if self.target_position is None else self.target_position.lt,
                "lg": None if self.target_position is None else self.target_position.lg,
                "altitude": (
                    None if self.target_position is None else self.target_position.altitude
                ),
                "planar_distance": self.target_planar_distance,
                "altitude_delta": self.target_altitude_delta,
                "spatial_distance": self.target_spatial_distance,
                "action": (
                    None
                    if self.target_action is None
                    else {
                        "phase": (
                            None
                            if self.target_action.phase is None
                            else self.target_action.phase.value
                        ),
                        "targeting_player": self.target_action.targeting_player,
                        "motion_id": self.target_action.motion_id,
                        "action_pending": self.target_action.action_pending,
                        "impact_frame": self.target_action.impact_frame,
                        "action_sequence": self.target_action.action_sequence,
                        "interrupt_opportunity": (
                            self.target_action.interrupt_opportunity
                        ),
                    }
                ),
                "identity": (
                    None
                    if self.target_identity is None
                    else {
                        "classification_available": (
                            self.target_identity.classification_available
                        ),
                        "classification_error": self.target_identity.classification_error,
                        "merchant": self.target_identity.merchant,
                        "shopkeeper": self.target_identity.shopkeeper,
                        "arc_character": self.target_identity.arc_character,
                        "banker": self.target_identity.banker,
                        "trainer": self.target_identity.trainer,
                        "minion": self.target_identity.minion,
                        "protected_roles": list(self.target_identity.protected_roles),
                        "attack_eligible": self.target_identity.attack_eligible,
                    }
                ),
            },
            "player": {
                "current_health": self.player_current_health,
                "maximum_health": self.player_maximum_health,
                "current_mana": self.player_current_mana,
                "maximum_mana": self.player_maximum_mana,
                "current_stamina": self.player_current_stamina,
                "maximum_stamina": self.player_maximum_stamina,
                "lt": None if self.player_position is None else self.player_position.lt,
                "lg": None if self.player_position is None else self.player_position.lg,
                "altitude": (
                    None if self.player_position is None else self.player_position.altitude
                ),
                "action": (
                    None
                    if self.player_action is None
                    else {
                        "phase": self.player_action.phase.value,
                        "targeting_selected": self.player_action.targeting_selected,
                        "motion_id": self.player_action.motion_id,
                        "action_pending": self.player_action.action_pending,
                        "impact_frame": self.player_action.impact_frame,
                        "action_sequence": self.player_action.action_sequence,
                        "motion_sequence": self.player_action.motion_sequence,
                        "action_active": self.player_action.action_active,
                    }
                ),
            },
            "combat_events": [
                {
                    "sequence": event.sequence,
                    "timestamp": event.timestamp,
                    "kind": event.kind.value,
                    "message": event.message,
                    "target_name": event.target_name,
                    "amount": event.amount,
                }
                for event in self.combat_events
            ],
            "input_accepted": self.input_accepted,
            "input_reason": self.input_reason,
            "approach": (
                None
                if self.approach_status is None
                else {
                    "status": self.approach_status,
                    "phase": (
                        None
                        if self.approach_decision is None
                        else self.approach_decision.phase.value
                    ),
                    "maneuver": (
                        None
                        if self.approach_decision is None
                        or self.approach_decision.maneuver is None
                        else self.approach_decision.maneuver.value
                    ),
                    "direction": (
                        None
                        if self.approach_decision is None
                        or self.approach_decision.minimap_direction is None
                        else {
                            "x": self.approach_decision.minimap_direction.x,
                            "y": self.approach_decision.minimap_direction.y,
                        }
                    ),
                    "distance_remaining": (
                        None
                        if self.approach_decision is None
                        else self.approach_decision.distance_remaining
                    ),
                    "click_count": (
                        None
                        if self.approach_decision is None
                        else self.approach_decision.click_count
                    ),
                    "terminal_reason": (
                        None
                        if self.approach_decision is None
                        else self.approach_decision.terminal_reason
                    ),
                    "input_accepted": self.approach_input_accepted,
                    "input_reason": self.approach_input_reason,
                    "movement_stop_accepted": self.movement_stop_accepted,
                    "movement_stop_reason": self.movement_stop_reason,
                }
            ),
        }


@dataclass(frozen=True, slots=True)
class PvERunResult:
    final_phase: PvEPhase
    terminal_reason: str
    kills: int
    trace: tuple[PvERunTraceStep, ...]

    def __post_init__(self) -> None:
        if self.final_phase not in (PvEPhase.COMPLETE, PvEPhase.STOPPED):
            raise ValueError("PvE run result must be terminal")
        if not isinstance(self.terminal_reason, str) or not self.terminal_reason.strip():
            raise ValueError("terminal_reason must be a non-empty string")
        _non_negative_integer(self.kills, "kills")
        if any(not isinstance(step, PvERunTraceStep) for step in self.trace):
            raise ValueError("trace must contain PvERunTraceStep values")
