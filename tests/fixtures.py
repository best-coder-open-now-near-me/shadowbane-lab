"""Shared valid protocol fixtures."""

from shadowbane_lab.protocol import (
    ActionBinding,
    Affordance,
    AffordanceSetMessage,
    DecisionMessage,
    EntityKind,
    EntityObservation,
    Event,
    EventBatchMessage,
    EventKind,
    NamedScalar,
    ObservationMessage,
    Relation,
    TargetKind,
    Vector2,
)


def protocol_exchange() -> tuple[
    ObservationMessage,
    AffordanceSetMessage,
    DecisionMessage,
    EventBatchMessage,
]:
    observation = ObservationMessage(
        message_id="message-observation-42",
        observation_id="observation-42",
        agent_id="bot-12",
        life_id="bot-12:7",
        tick=42,
        sim_time_ms=8_400,
        entities=(
            EntityObservation(
                entity_id="bot-12",
                kind=EntityKind.ACTOR,
                relation=Relation.SELF,
                position=Vector2(0.0, 0.0),
                scalars=(
                    NamedScalar("health_fraction", 0.63),
                    NamedScalar("mana_fraction", 0.41),
                ),
                tags=("profession.assassin",),
            ),
            EntityObservation(
                entity_id="enemy-7",
                kind=EntityKind.ACTOR,
                relation=Relation.ENEMY,
                position=Vector2(12.0, 5.0),
                velocity=Vector2(-0.25, 0.0),
                scalars=(NamedScalar("health_fraction", 0.28),),
                tags=("casting", "visible"),
            ),
        ),
        global_scalars=(NamedScalar("objective_control", -0.1),),
    )
    binding = ActionBinding(
        actor_id="bot-12",
        target_kind=TargetKind.ENTITY,
        target_entity_id="enemy-7",
    )
    affordances = AffordanceSetMessage(
        message_id="message-affordances-42",
        observation_id=observation.observation_id,
        agent_id=observation.agent_id,
        tick=observation.tick,
        affordances=(
            Affordance(
                affordance_id="affordance-shadow-bolt-enemy-7",
                action_key="shadowbane.assassin.shadow_bolt",
                binding=binding,
                features=(
                    NamedScalar("range", 120.0),
                    NamedScalar("commitment_ms", 2_000.0),
                ),
                tags=("harmful", "ranged", "damage.cold", "control.stun"),
            ),
        ),
    )
    decision = DecisionMessage(
        message_id="message-decision-42",
        correlation_id="decision-42",
        observation_id=observation.observation_id,
        agent_id=observation.agent_id,
        tick=observation.tick,
        affordance_id=affordances.affordances[0].affordance_id,
        action_key=affordances.affordances[0].action_key,
        binding=binding,
    )
    events = EventBatchMessage(
        message_id="message-events-43",
        tick=43,
        sim_time_ms=8_600,
        events=(
            Event(
                event_id="event-action-started-42",
                kind=EventKind.ACTION_STARTED,
                tick=42,
                sim_time_ms=8_400,
                correlation_id=decision.correlation_id,
                source_entity_id="bot-12",
                target_entity_id="enemy-7",
                action_key=decision.action_key,
            ),
        ),
    )
    return observation, affordances, decision, events
