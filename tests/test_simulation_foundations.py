import unittest

from shadowbane_lab.protocol import EntityKind, Vector2
from shadowbane_lab.sim import (
    ActiveEffectState,
    DeterministicRandom,
    EntityState,
    SimulationClock,
)


class SimulationClockTests(unittest.TestCase):
    def test_snapshot_restores_virtual_time(self) -> None:
        clock = SimulationClock(tick_duration_ms=200)
        clock.advance(3)
        snapshot = clock.snapshot()
        clock.advance(5)

        clock.restore(snapshot)

        self.assertEqual(3, clock.tick)
        self.assertEqual(600, clock.now_ms)


class DeterministicRandomTests(unittest.TestCase):
    def test_pcg32_matches_the_reference_sequence(self) -> None:
        source = DeterministicRandom(seed=42, stream=54)

        sequence = tuple(source.next_uint32() for _ in range(6))

        self.assertEqual(
            (
                0xA15C02B7,
                0x7B47F409,
                0xBA1D3330,
                0x83D2F293,
                0xBFA4784B,
                0xCBED606E,
            ),
            sequence,
        )

    def test_snapshot_replays_random_values(self) -> None:
        source = DeterministicRandom(seed=817)
        source.next_uint32()
        snapshot = source.snapshot()
        expected = tuple(source.next_uint32() for _ in range(10))

        source.restore(snapshot)

        self.assertEqual(expected, tuple(source.next_uint32() for _ in range(10)))

    def test_randbelow_stays_within_bounds(self) -> None:
        source = DeterministicRandom(seed=12)

        values = tuple(source.randbelow(7) for _ in range(200))

        self.assertTrue(all(0 <= value < 7 for value in values))
        self.assertGreater(len(set(values)), 1)


class EntityStateTests(unittest.TestCase):
    def test_snapshot_is_immutable_and_round_trips_state(self) -> None:
        entity = EntityState(
            entity_id="bot-1",
            life_id="bot-1:4",
            kind=EntityKind.ACTOR,
            team_id="blue",
            position=Vector2(1.0, 2.0),
            scalars={"health": 75.0, "mana": 40.0},
            maximums={"health": 100.0, "mana": 80.0},
            tags={"profession.assassin"},
            action_keys=("generic.move",),
            inventory={"item.potion": 2.0},
            effects={
                "concealment": ActiveEffectState(
                    effect_key="concealed",
                    source_entity_id="bot-1",
                    magnitude=1.0,
                    expires_at_ms=5_000,
                    stacking_key="concealment",
                    tags={"visibility.concealed"},
                )
            },
            cooldowns={"generic.move": 200},
        )
        snapshot = entity.snapshot()

        entity.scalars["health"] = 1.0
        entity.tags.add("mutated")
        restored = EntityState.from_snapshot(snapshot)

        self.assertEqual(75.0, restored.scalars["health"])
        self.assertNotIn("mutated", restored.tags)
        self.assertEqual(snapshot, restored.snapshot())
        self.assertIn("visibility.concealed", restored.effective_tags)


if __name__ == "__main__":
    unittest.main()
