import unittest

from shadowbane_lab.protocol import EntityKind, Vector2
from shadowbane_lab.sim import (
    ActionCatalog,
    EntityState,
    RangeBand,
    RangeRelation,
    ReferenceEnvironment,
    close_range_action,
)


class RangeIntentTests(unittest.TestCase):
    def test_range_band_collapses_rotationally_equivalent_positions(self) -> None:
        band = RangeBand(minimum=2.0, maximum=5.0)

        self.assertEqual(RangeRelation.TOO_CLOSE, band.classify(1.0))
        self.assertEqual(RangeRelation.IN_RANGE, band.classify(2.0))
        self.assertEqual(RangeRelation.IN_RANGE, band.classify(5.0))
        self.assertEqual(RangeRelation.TOO_FAR, band.classify(8.0))

    def test_close_intent_binds_targets_instead_of_compass_directions(self) -> None:
        action = close_range_action(RangeBand(maximum=3.0))
        environment = ReferenceEnvironment(
            ActionCatalog((action,)),
            (
                EntityState(
                    entity_id="player",
                    life_id="player:1",
                    kind=EntityKind.ACTOR,
                    team_id="player",
                    position=Vector2(0.0, 0.0),
                    scalars={"health": 100.0, "move_speed": 10.0},
                    maximums={"health": 100.0},
                    action_keys=(action.action_key,),
                ),
                EntityState(
                    entity_id="north",
                    life_id="north:1",
                    kind=EntityKind.ACTOR,
                    team_id="mob",
                    position=Vector2(0.0, 10.0),
                    scalars={"health": 100.0},
                    maximums={"health": 100.0},
                ),
                EntityState(
                    entity_id="diagonal",
                    life_id="diagonal:1",
                    kind=EntityKind.ACTOR,
                    team_id="mob",
                    position=Vector2(6.0, 8.0),
                    scalars={"health": 100.0},
                    maximums={"health": 100.0},
                ),
            ),
            seed=1,
        )

        exchange = environment.exchange("player")
        close_affordances = tuple(
            item
            for item in exchange.affordances.affordances
            if item.action_key == action.action_key
        )

        self.assertEqual(2, len(close_affordances))
        self.assertEqual(
            {"north", "diagonal"},
            {item.binding.target_entity_id for item in close_affordances},
        )
        self.assertTrue(all(item.binding.direction is None for item in close_affordances))
        diagonal = next(
            item for item in close_affordances if item.binding.target_entity_id == "diagonal"
        )
        environment.step((exchange.decision(diagonal.affordance_id, "close:1"),))

        self.assertEqual(Vector2(1.2, 1.6), environment.entity("player").position)


if __name__ == "__main__":
    unittest.main()
