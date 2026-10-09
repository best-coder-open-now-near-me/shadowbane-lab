"""Coherent PvE observation assembly over the canonical runtime dispatch loop."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Protocol, runtime_checkable

from shadowbane_lab.client_input import StopSignal
from shadowbane_lab.client_observation import (
    NativeTargetActionObservation,
    NativeTargetActionReadError,
    NativeTargetHealthObservation,
    NativeTargetHealthReadError,
    NativeTargetIdentityObservation,
    NativeTargetIdentityReadError,
    NativeTargetPositionObservation,
    NativeTargetPositionReadError,
)
from shadowbane_lab.pve.approach import (
    PvEApproachController,
    PvEApproachStatus,
    PvEApproachUpdate,
)
from shadowbane_lab.pve.authority_snapshot import (
    NativeGroupSource,
    build_native_party_authority_snapshot,
    native_party_identity_signature,
)
from shadowbane_lab.pve.controller import PvEController as _BasePvEController
from shadowbane_lab.pve.model import PvEObservation, PvETrackedTarget, PvETrackedTargetAction
from shadowbane_lab.pve.runtime import (
    CharacterPopulationSource,
    PlayerActionSource,
    PlayerPositionSource,
    PlayerVitalsSource,
    PvEIntentDispatcher,
    TargetActionSource,
    TargetHealthSource,
    TargetIdentitySource,
    TargetPositionSource,
)
from shadowbane_lab.pve.runtime import (
    PvERunner as _BasePvERunner,
)
from shadowbane_lab.travel import TravelDecision, TravelPhase
from shadowbane_lab.travel.runtime import TravelDecisionDispatcher


class PvEObservationCoherenceError(RuntimeError):
    """Raised when native channels disagree on actor, object or party ownership."""


@runtime_checkable
class PvEObservationSource(Protocol):
    """Build one controller-ready observation from an explicit channel request."""

    def observe(
        self,
        *,
        now_ms: int,
        target_action_active: bool,
        player_action_active: bool,
    ) -> PvEObservation: ...


class NativePvEObservationSource:
    """Assemble actor and exact-object state independently of UI selection.

    Selection is optional diagnostic data: a churned or unreadable selected
    snapshot is withheld without discarding valid actor and population state.
    """

    def __init__(
        self,
        *,
        health_reader: TargetHealthSource,
        player_vitals_reader: PlayerVitalsSource,
        player_position_reader: PlayerPositionSource | None = None,
        target_position_reader: TargetPositionSource | None = None,
        target_action_reader: TargetActionSource | None = None,
        player_action_reader: PlayerActionSource | None = None,
        target_identity_reader: TargetIdentitySource | None = None,
        population_reader: CharacterPopulationSource | None = None,
        group_reader: NativeGroupSource | None = None,
        party_group_id: str | None = None,
        tracked_target: Callable[[], PvETrackedTarget | None] | None = None,
    ) -> None:
        if not isinstance(health_reader, TargetHealthSource):
            raise ValueError("health_reader must implement TargetHealthSource")
        if not isinstance(player_vitals_reader, PlayerVitalsSource):
            raise ValueError("player_vitals_reader must implement PlayerVitalsSource")
        if (player_position_reader is None) != (target_position_reader is None):
            raise ValueError("player and target position readers must be provided together")
        if player_position_reader is not None and not isinstance(
            player_position_reader, PlayerPositionSource
        ):
            raise ValueError("player_position_reader must implement PlayerPositionSource")
        if target_position_reader is not None and not isinstance(
            target_position_reader, TargetPositionSource
        ):
            raise ValueError("target_position_reader must implement TargetPositionSource")
        if target_action_reader is not None and not isinstance(
            target_action_reader, TargetActionSource
        ):
            raise ValueError("target_action_reader must implement TargetActionSource")
        if player_action_reader is not None and not isinstance(
            player_action_reader, PlayerActionSource
        ):
            raise ValueError("player_action_reader must implement PlayerActionSource")
        if target_identity_reader is not None and not isinstance(
            target_identity_reader, TargetIdentitySource
        ):
            raise ValueError("target_identity_reader must implement TargetIdentitySource")
        if population_reader is not None and not isinstance(
            population_reader, CharacterPopulationSource
        ):
            raise ValueError("population_reader must implement CharacterPopulationSource")
        if group_reader is not None:
            if not isinstance(group_reader, NativeGroupSource):
                raise ValueError("group_reader must implement NativeGroupSource")
            if not isinstance(party_group_id, str) or not party_group_id.strip():
                raise ValueError("group_reader requires a non-empty party_group_id")
            ids = tuple(
                self._process_id(r) for r in (health_reader, population_reader, group_reader)
            )
            if any(value is None for value in ids) or len(set(ids)) != 1:
                raise ValueError(
                    "party authority requires same-process health, population and group"
                )
        elif party_group_id is not None:
            raise ValueError("party_group_id requires group_reader")

        process_ids = {
            process_id
            for reader in (
                health_reader,
                player_vitals_reader,
                player_position_reader,
                target_position_reader,
                target_action_reader,
                player_action_reader,
                target_identity_reader,
                population_reader,
            )
            if (process_id := self._process_id(reader)) is not None
        }
        if len(process_ids) > 1:
            raise ValueError("native PvE observation readers resolved different processes")

        self._tracked_target = tracked_target
        self._actor_identity = getattr(population_reader, "observe_actor_identity", None)
        self._bound_action = getattr(population_reader, "observe_character_detail", None)
        self._health_reader = health_reader
        self._player_vitals_reader = player_vitals_reader
        self._player_position_reader = player_position_reader
        self._target_position_reader = target_position_reader
        self._target_action_reader = target_action_reader
        self._player_action_reader = player_action_reader
        self._target_identity_reader = target_identity_reader
        self._population_reader = population_reader
        self._group_reader = group_reader
        self._party_group_id = party_group_id
        self._authority_revision = 0
        self._authority_process_id = self._process_id(group_reader)
        self._selection_boundary_enabled = self._process_id(health_reader) is not None

    @property
    def selection_boundary_enabled(self) -> bool:
        """Whether the source performs the second process-backed target sample."""

        return self._selection_boundary_enabled

    def observe(
        self,
        *,
        now_ms: int,
        target_action_active: bool,
        player_action_active: bool,
    ) -> PvEObservation:
        if isinstance(now_ms, bool) or not isinstance(now_ms, int) or now_ms < 0:
            raise ValueError("now_ms must be a non-negative integer")
        if not isinstance(target_action_active, bool):
            raise ValueError("target_action_active must be boolean")
        if not isinstance(player_action_active, bool):
            raise ValueError("player_action_active must be boolean")

        binding = None if self._tracked_target is None else self._tracked_target()
        actor_before = None if self._actor_identity is None else self._actor_identity()
        selection_observed = True
        try:
            target = self._health_reader.observe()
        except NativeTargetHealthReadError:
            target = NativeTargetHealthObservation(target_present=False)
            selection_observed = False
        group_before = None if self._group_reader is None else self._group_reader.observe()
        population = (
            None if self._population_reader is None else self._population_reader.observe()
        )
        target_action = (
            None
            if (self._target_action_reader is None or not target_action_active
                or (binding is not None and self._bound_action is not None))
            else self._selection_detail(self._target_action_reader, NativeTargetActionReadError)
        )
        player_action = (
            None
            if self._player_action_reader is None or not player_action_active
            else self._player_action_reader.observe_player()
        )
        target_identity = self._observe_target_identity(target)
        target_position = (
            None
            if self._target_position_reader is None
            else self._selection_detail(self._target_position_reader, NativeTargetPositionReadError)
        )
        player_position = (
            None
            if self._player_position_reader is None
            else self._player_position_reader.observe()
        )
        player = self._player_vitals_reader.observe()

        if self._selection_boundary_enabled:
            try:
                boundary = self._health_reader.observe()
                selection_observed &= self._same_selection(target, boundary)
                target = boundary
            except NativeTargetHealthReadError:
                selection_observed = False
        if population is not None:
            selection_observed &= population.selection_observed
            if target.target_present and target.target_token != population.selected_target_token:
                selection_observed = False
        for detail in (target_action, target_identity, target_position):
            if detail is not None and (detail.target_present != target.target_present
                                      or detail.target_token != target.target_token):
                selection_observed = False
        if not selection_observed:
            target = NativeTargetHealthObservation(target_present=False)
        # Missing optional detail is diagnostic unavailability, not target loss.
        if self._target_position_reader is not None and target_position is None:
            selection_observed = False
            target = NativeTargetHealthObservation(target_present=False)
            target_position = NativeTargetPositionObservation(target_present=False)
        tracked_action = None
        if (binding is not None and population is not None and self._bound_action is not None
                and self._target_action_reader is not None and target_action_active
                and any(c.token == binding.token and c.object_key == binding.object_key
                        for c in population.characters)):
            detail = self._bound_action(
                binding.token, binding.object_key, self._target_action_reader,
            )
            # The canonical reader owns addresses and refreshes the retained
            # object. Do not keep stale health if that exact object disappeared.
            others = tuple(c for c in population.characters if c.token != binding.token)
            characters = others if detail is None else (*others, detail.character)
            population = replace(
                population, characters=tuple(sorted(characters, key=lambda c: c.token)),
            )
            if detail is not None and detail.action is not None:
                tracked_action = PvETrackedTargetAction(
                    binding.token, binding.object_key, detail.action,
                )
        if actor_before is not None:
            if (self._actor_identity() != actor_before or population is None
                    or population.local_player_object_key != actor_before[1]
                    or population.player_action_target_token != actor_before[2]):
                raise PvEObservationCoherenceError("local actor changed during native PvE frame")

        authority_snapshot = None
        if self._group_reader is not None:
            group_after = self._group_reader.observe()
            assert group_before is not None
            if native_party_identity_signature(group_before) != native_party_identity_signature(
                group_after
            ):
                raise PvEObservationCoherenceError("party roster changed during native PvE frame")
            if any(
                self._process_id(reader) != self._authority_process_id
                for reader in (self._health_reader, self._population_reader, self._group_reader)
            ):
                raise PvEObservationCoherenceError("party authority process changed during frame")
            assert population is not None
            assert self._party_group_id is not None
            authority_snapshot = build_native_party_authority_snapshot(
                population, group_after, revision=self._authority_revision + 1,
                party_group_id=self._party_group_id,
            )

        if not target.target_present:
            target_position = self._absent_target_position(target_position)
            target_action = self._absent_target_action(target_action)
            target_identity = self._absent_target_identity(target_identity)

        try:
            observation = PvEObservation(
                now_ms=now_ms,
                target=target,
                player=player,
                player_position=player_position,
                target_position=target_position,
                target_action=target_action,
                tracked_target_action=tracked_action,
                selection_observed=selection_observed,
                player_action=player_action,
                target_identity=target_identity,
                population=population,
                authority_snapshot=authority_snapshot,
            )
        except ValueError as exc:
            message = str(exc)
            if "disagree" in message or "resolved different" in message:
                raise PvEObservationCoherenceError(message) from exc
            raise

        if authority_snapshot is not None:
            self._authority_revision = authority_snapshot.revision
        return observation

    @staticmethod
    def _selection_detail(reader, error_type):
        try:
            return reader.observe()
        except error_type:
            return None

    def _observe_target_identity(
        self,
        target: NativeTargetHealthObservation,
    ) -> NativeTargetIdentityObservation | None:
        if self._target_identity_reader is None:
            return None
        try:
            return self._target_identity_reader.observe()
        except NativeTargetIdentityReadError as exc:
            if not target.target_present:
                return NativeTargetIdentityObservation(target_present=False)
            assert target.target_token is not None
            message = " ".join(str(exc).split())
            return NativeTargetIdentityObservation.unavailable(
                target_token=target.target_token,
                error=f"{type(exc).__name__}:{message[:160]}",
            )

    @staticmethod
    def _same_selection(
        first: NativeTargetHealthObservation,
        second: NativeTargetHealthObservation,
    ) -> bool:
        return (
            first.target_present == second.target_present
            and first.target_token == second.target_token
        )

    @staticmethod
    def _absent_target_position(
        value: NativeTargetPositionObservation | None,
    ) -> NativeTargetPositionObservation | None:
        if value is None or not value.target_present:
            return value
        return NativeTargetPositionObservation(target_present=False)

    @staticmethod
    def _absent_target_action(
        value: NativeTargetActionObservation | None,
    ) -> NativeTargetActionObservation | None:
        if value is None or not value.target_present:
            return value
        return NativeTargetActionObservation(target_present=False)

    @staticmethod
    def _absent_target_identity(
        value: NativeTargetIdentityObservation | None,
    ) -> NativeTargetIdentityObservation | None:
        if value is None or not value.target_present:
            return value
        return NativeTargetIdentityObservation(target_present=False)

    @staticmethod
    def _process_id(reader: object | None) -> int | None:
        if reader is None:
            return None
        value = getattr(reader, "process_id", None)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return None
        return value


class _ObservationFrameBridge:
    """Present one fully validated observation through the legacy reader protocols."""

    def __init__(
        self,
        source: NativePvEObservationSource,
        controller: _BasePvEController,
    ) -> None:
        self._source = source
        self._controller = controller
        self._frame: PvEObservation | None = None
        self._completed_frame: PvEObservation | None = None

    def begin_frame(self) -> PvEObservation:
        self._frame = None
        self._completed_frame = None
        self._frame = self._source.observe(
            now_ms=0,
            target_action_active=self._controller.target_action_observation_active,
            player_action_active=self._controller.player_action_observation_active,
        )
        return self._frame

    def require_frame(self) -> PvEObservation:
        if self._frame is None:
            raise RuntimeError("PvE observation frame was requested before target health")
        return self._frame

    def complete_observation(self, **values) -> PvEObservation:
        frame = self.require_frame()
        self._frame = None
        assembled = PvEObservation(
            **values, tracked_target_action=frame.tracked_target_action,
            selection_observed=frame.selection_observed,
        )
        expected = replace(frame, now_ms=assembled.now_ms, authority_snapshot=None)
        if assembled != expected:
            raise PvEObservationCoherenceError("runtime channels disagree with completed frame")
        return replace(frame, now_ms=assembled.now_ms)


class _FrameTargetHealthSource:
    def __init__(self, bridge: _ObservationFrameBridge) -> None:
        self._bridge = bridge

    def observe(self):
        return self._bridge.begin_frame().target


class _FramePlayerVitalsSource:
    def __init__(self, bridge: _ObservationFrameBridge) -> None:
        self._bridge = bridge

    def observe(self):
        return self._bridge.require_frame().player


class _FramePlayerPositionSource:
    def __init__(self, bridge: _ObservationFrameBridge) -> None:
        self._bridge = bridge

    def observe(self):
        value = self._bridge.require_frame().player_position
        if value is None:
            raise RuntimeError("coherent PvE frame is missing player position")
        return value


class _FrameTargetPositionSource:
    def __init__(self, bridge: _ObservationFrameBridge) -> None:
        self._bridge = bridge

    def observe(self):
        value = self._bridge.require_frame().target_position
        if value is None:
            raise RuntimeError("coherent PvE frame is missing target position")
        return value


class _FrameTargetActionSource:
    def __init__(self, bridge: _ObservationFrameBridge) -> None:
        self._bridge = bridge

    def observe(self):
        return self._bridge.require_frame().target_action


class _FramePlayerActionSource:
    def __init__(self, bridge: _ObservationFrameBridge) -> None:
        self._bridge = bridge

    def observe_player(self):
        value = self._bridge.require_frame().player_action
        if value is None:
            raise RuntimeError("coherent PvE frame is missing player action")
        return value


class _FrameTargetIdentitySource:
    def __init__(self, bridge: _ObservationFrameBridge) -> None:
        self._bridge = bridge

    def observe(self):
        value = self._bridge.require_frame().target_identity
        if value is None:
            raise RuntimeError("coherent PvE frame is missing target identity")
        return value


class _FrameCharacterPopulationSource:
    def __init__(self, bridge: _ObservationFrameBridge) -> None:
        self._bridge = bridge

    def observe(self):
        value = self._bridge.require_frame().population
        if value is None:
            raise RuntimeError("coherent PvE frame is missing character population")
        return value


def _failure_reason(prefix: str, exc: Exception) -> str:
    message = " ".join(str(exc).split())
    detail = f":{message[:160]}" if message else ""
    return f"{prefix}:{type(exc).__name__}{detail}"


class _FailClosedController(_BasePvEController):
    """Translate decision/approach exceptions into terminal controller decisions."""

    def __init__(self, delegate: _BasePvEController) -> None:
        self._delegate = delegate

    @property
    def requires_target_action(self) -> bool:
        return self._delegate.requires_target_action

    @property
    def requires_target_identity(self) -> bool:
        return self._delegate.requires_target_identity

    @property
    def requires_population(self) -> bool:
        return self._delegate.requires_population

    @property
    def continuous(self) -> bool:
        return self._delegate.continuous

    @property
    def terminal(self) -> bool:
        return self._delegate.terminal

    @property
    def target_action_observation_active(self) -> bool:
        return self._delegate.target_action_observation_active

    @property
    def player_action_observation_active(self) -> bool:
        return self._delegate.player_action_observation_active

    def tracked_target(self, observation: PvEObservation):
        return self._delegate.tracked_target(observation)

    def request_final_cleanup(self):
        return self._delegate.request_final_cleanup()

    def acknowledge_cleanup(self, result):
        return self._delegate.acknowledge_cleanup(result)

    @property
    def pending_combat_proposal(self):
        return self._delegate.pending_combat_proposal

    def acknowledge_combat(self, proposal, result, *, now_ms: int) -> None:
        self._delegate.acknowledge_combat(proposal, result, now_ms=now_ms)

    def candidate_camp(self, observation: PvEObservation):
        return self._delegate.candidate_camp(observation)

    def resume_after_external_combat(self, observation: PvEObservation) -> None:
        self._delegate.resume_after_external_combat(observation)

    def can_start_external_combat(self, observation: PvEObservation) -> bool:
        return self._delegate.can_start_external_combat(observation)

    def step(self, observation: PvEObservation, *, external_combat: bool = False):
        try:
            if external_combat:
                return self._delegate.step(observation, external_combat=True)
            return self._delegate.step(observation)
        except Exception as exc:
            return self._delegate.stop(
                _failure_reason("decision_failure", exc),
                now_ms=observation.now_ms,
            )

    def stop(self, reason: str, *, now_ms: int | None = None):
        coherence_prefix = "observation_failure:PvEObservationCoherenceError"
        if reason.startswith(coherence_prefix):
            reason = reason.replace(
                "observation_failure:",
                "observation_coherence_failure:",
                1,
            )
        return self._delegate.stop(reason, now_ms=now_ms)

    def recover_from_approach_failure(
        self,
        observation: PvEObservation,
        reason: str,
    ):
        if reason.startswith("runtime_exception:"):
            return self._delegate.stop(
                f"approach_failure:{reason.removeprefix('runtime_exception:')}",
                now_ms=observation.now_ms,
            )
        return self._delegate.recover_from_approach_failure(observation, reason)

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)


class _FailClosedApproach(PvEApproachController):
    """Represent an unexpected approach exception as a non-dispatchable failure."""

    def __init__(self, delegate: PvEApproachController) -> None:
        self._delegate = delegate

    @property
    def config(self):
        return self._delegate.config

    def step(self, observation: PvEObservation, **kwargs) -> PvEApproachUpdate:
        try:
            return self._delegate.step(observation, **kwargs)
        except Exception as exc:
            distance = observation.target_planar_distance or 0.0
            return PvEApproachUpdate(
                PvEApproachStatus.FAILED,
                TravelDecision(
                    decision_id=0,
                    now_ms=observation.now_ms,
                    phase=TravelPhase.STOPPED,
                    waypoint_index=0,
                    distance_remaining=distance,
                    click_count=0,
                    terminal_reason=_failure_reason("runtime_exception", exc),
                ),
            )

    def cancel(self, reason: str) -> PvEApproachUpdate:
        return self._delegate.cancel(reason)

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)


class PvERunner(_BasePvERunner):
    """Use coherent frames and fail-closed stage proxies with one dispatch loop."""

    def __init__(
        self,
        *,
        controller: _BasePvEController,
        health_reader: TargetHealthSource,
        player_vitals_reader: PlayerVitalsSource,
        player_position_reader: PlayerPositionSource | None = None,
        target_position_reader: TargetPositionSource | None = None,
        target_action_reader: TargetActionSource | None = None,
        player_action_reader: PlayerActionSource | None = None,
        target_identity_reader: TargetIdentitySource | None = None,
        population_reader: CharacterPopulationSource | None = None,
        group_reader: NativeGroupSource | None = None,
        party_group_id: str | None = None,
        dispatcher: PvEIntentDispatcher,
        approach_controller: PvEApproachController | None = None,
        movement_dispatcher: TravelDecisionDispatcher | None = None,
        listed_combat=None,
        combat_cleanup=None,
        actor_preparation=None,
        actor_tracking=None,
        stop_signal: StopSignal,
        poll_interval_ms: int = 100,
        maximum_consecutive_observation_failures: int = 3,
        maximum_retained_trace_steps: int | None = None,
        trace_sink=None,
        progress_sink=None,
        clock=time.monotonic,
        sleeper=time.sleep,
    ) -> None:
        if not isinstance(controller, _BasePvEController):
            raise ValueError("controller must be PvEController")
        source = NativePvEObservationSource(
            health_reader=health_reader,
            player_vitals_reader=player_vitals_reader,
            player_position_reader=player_position_reader,
            target_position_reader=target_position_reader,
            target_action_reader=target_action_reader,
            player_action_reader=player_action_reader,
            target_identity_reader=target_identity_reader,
            population_reader=population_reader,
            group_reader=group_reader,
            party_group_id=party_group_id,
            tracked_target=lambda: controller.input_target,
        )
        bridge = _ObservationFrameBridge(source, controller)
        self._frame_bridge = bridge
        guarded_controller = _FailClosedController(controller)
        guarded_approach = (
            None
            if approach_controller is None
            else _FailClosedApproach(approach_controller)
        )
        super().__init__(
            controller=guarded_controller,
            health_reader=_FrameTargetHealthSource(bridge),
            player_vitals_reader=_FramePlayerVitalsSource(bridge),
            player_position_reader=(
                None
                if player_position_reader is None
                else _FramePlayerPositionSource(bridge)
            ),
            target_position_reader=(
                None
                if target_position_reader is None
                else _FrameTargetPositionSource(bridge)
            ),
            target_action_reader=(
                None
                if target_action_reader is None
                else _FrameTargetActionSource(bridge)
            ),
            player_action_reader=(
                None
                if player_action_reader is None
                else _FramePlayerActionSource(bridge)
            ),
            target_identity_reader=(
                None
                if target_identity_reader is None
                else _FrameTargetIdentitySource(bridge)
            ),
            population_reader=(
                None
                if population_reader is None
                else _FrameCharacterPopulationSource(bridge)
            ),
            dispatcher=dispatcher,
            approach_controller=guarded_approach,
            movement_dispatcher=movement_dispatcher,
            listed_combat=listed_combat,
            combat_cleanup=combat_cleanup,
            actor_preparation=actor_preparation,
            actor_tracking=actor_tracking,
            stop_signal=stop_signal,
            poll_interval_ms=poll_interval_ms,
            maximum_consecutive_observation_failures=(
                maximum_consecutive_observation_failures
            ),
            maximum_retained_trace_steps=maximum_retained_trace_steps,
            trace_sink=trace_sink,
            progress_sink=progress_sink,
            clock=clock,
            sleeper=sleeper,
        )
        self._native_observation_source = source

    @property
    def observation_source(self) -> NativePvEObservationSource:
        return self._native_observation_source

    def _build_observation(self, **values) -> PvEObservation:
        return self._frame_bridge.complete_observation(**values)
