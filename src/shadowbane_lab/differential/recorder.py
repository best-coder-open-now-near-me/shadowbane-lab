"""Capture reference-environment transitions at the shared semantic boundary."""

from __future__ import annotations

from shadowbane_lab.differential.model import (
    CapturedEffect,
    CapturedEntity,
    CapturedState,
    TraceMetadata,
    TraceStep,
    TransitionTrace,
)
from shadowbane_lab.protocol import DecisionMessage, NamedScalar
from shadowbane_lab.sim import EntityState, ReferenceEnvironment


class ReferenceTraceRecorder:
    """Incrementally records controlled reference-simulator steps."""

    def __init__(
        self,
        environment: ReferenceEnvironment,
        metadata: TraceMetadata,
        observed_agent_ids: tuple[str, ...],
    ) -> None:
        if len(observed_agent_ids) != len(set(observed_agent_ids)):
            raise ValueError("observed_agent_ids must be unique")
        if not observed_agent_ids:
            raise ValueError("at least one observed agent is required")
        for agent_id in observed_agent_ids:
            environment.entity(agent_id)
        self._environment = environment
        self._metadata = metadata
        self._observed_agent_ids = tuple(sorted(observed_agent_ids))
        self._steps: list[TraceStep] = []

    def step(self, decisions: tuple[DecisionMessage, ...] = ()) -> TraceStep:
        before = _capture_state(self._environment)
        affordances = tuple(
            self._environment.exchange(agent_id).affordances
            for agent_id in self._observed_agent_ids
        )
        events = self._environment.step(decisions)
        step = TraceStep(
            step_index=len(self._steps),
            before=before,
            affordances=affordances,
            decisions=tuple(decisions),
            events=events,
            after=_capture_state(self._environment),
        )
        self._steps.append(step)
        return step

    def trace(self) -> TransitionTrace:
        return TransitionTrace(metadata=self._metadata, steps=tuple(self._steps))


def _capture_state(environment: ReferenceEnvironment) -> CapturedState:
    return CapturedState(
        tick=environment.tick,
        sim_time_ms=environment.now_ms,
        entities=tuple(_capture_entity(entity) for entity in environment.entities),
    )


def _capture_entity(entity: EntityState) -> CapturedEntity:
    return CapturedEntity(
        entity_id=entity.entity_id,
        life_id=entity.life_id,
        position=entity.position,
        velocity=entity.velocity,
        scalars=tuple(
            NamedScalar(name=key, value=float(value))
            for key, value in sorted(entity.scalars.items())
        ),
        tags=tuple(sorted(entity.tags)),
        effects=tuple(
            CapturedEffect(
                effect_key=effect.effect_key,
                source_entity_id=effect.source_entity_id,
                magnitude=float(effect.magnitude),
                expires_at_ms=effect.expires_at_ms,
                stacking_key=effect.stacking_key,
                tags=tuple(sorted(effect.tags)),
            )
            for _, effect in sorted(entity.effects.items())
        ),
        cooldowns=tuple(sorted(entity.cooldowns.items())),
        busy_until_ms=entity.busy_until_ms,
        alive=entity.alive,
    )
