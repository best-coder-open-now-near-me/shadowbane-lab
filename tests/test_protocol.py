import unittest
from dataclasses import replace

from shadowbane_lab.protocol import (
    ActionBinding,
    EntityKind,
    EntityObservation,
    ProtocolMismatchError,
    Relation,
    TargetKind,
    Vector2,
    validate_exchange,
)

from tests.fixtures import protocol_exchange


class ProtocolModelTests(unittest.TestCase):
    def test_valid_exchange_returns_selected_affordance(self) -> None:
        observation, affordances, decision, _ = protocol_exchange()

        selected = validate_exchange(observation, affordances, decision)

        self.assertEqual("shadowbane.assassin.shadow_bolt", selected.action_key)

    def test_decision_cannot_change_legal_binding(self) -> None:
        observation, affordances, decision, _ = protocol_exchange()
        altered = replace(
            decision,
            binding=ActionBinding(
                actor_id=decision.agent_id,
                target_kind=TargetKind.ENTITY,
                target_entity_id="different-enemy",
            ),
        )

        with self.assertRaisesRegex(ProtocolMismatchError, "binding"):
            validate_exchange(observation, affordances, altered)

    def test_position_binding_requires_position(self) -> None:
        with self.assertRaisesRegex(ValueError, "position targets require position"):
            ActionBinding(actor_id="bot-12", target_kind=TargetKind.POSITION)

    def test_direction_binding_rejects_unrelated_position(self) -> None:
        with self.assertRaisesRegex(ValueError, "position is valid only"):
            ActionBinding(
                actor_id="bot-12",
                target_kind=TargetKind.DIRECTION,
                direction=Vector2(1.0, 0.0),
                position=Vector2(2.0, 2.0),
            )

    def test_direct_constructor_rejects_untyped_target_kind(self) -> None:
        with self.assertRaisesRegex(ValueError, "TargetKind"):
            ActionBinding(actor_id="bot-12", target_kind="none")  # type: ignore[arg-type]

    def test_observation_agent_must_be_self(self) -> None:
        observation = protocol_exchange()[0]
        entities = (
            EntityObservation(
                entity_id=observation.agent_id,
                kind=EntityKind.ACTOR,
                relation=Relation.ALLY,
                position=Vector2(0.0, 0.0),
            ),
        )

        with self.assertRaisesRegex(ValueError, "self relation"):
            replace(observation, entities=entities)


if __name__ == "__main__":
    unittest.main()
