import unittest

from shadowbane_lab.client_observation import (
    NativeCombatEventKind,
    NativeCombatEventParser,
    NativeCombatLogEntry,
)


def _entry(message: str, *, sequence: int = 0) -> NativeCombatLogEntry:
    return NativeCombatLogEntry(sequence=sequence, timestamp="5:02:20", message=message)


class NativeCombatEventParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = NativeCombatEventParser()

    def test_parses_observed_player_damage_record(self) -> None:
        event = self.parser.parse(_entry("You hit the Frost Walker for 4 points of damage!"))

        self.assertEqual(NativeCombatEventKind.PLAYER_HIT_TARGET, event.kind)
        self.assertEqual("the Frost Walker", event.target_name)
        self.assertEqual(4.0, event.amount)

    def test_parses_observed_target_miss_record(self) -> None:
        event = self.parser.parse(_entry("The Frost Walker misses YOU!"))

        self.assertEqual(NativeCombatEventKind.TARGET_MISSED_PLAYER, event.kind)
        self.assertEqual("The Frost Walker", event.target_name)

    def test_parses_observed_kill_record_with_native_prefix(self) -> None:
        event = self.parser.parse(
            _entry("[Combat] Info: You have killed the Frost Walker!", sequence=188)
        )

        self.assertEqual(188, event.sequence)
        self.assertEqual(NativeCombatEventKind.TARGET_KILLED, event.kind)
        self.assertEqual("the Frost Walker", event.target_name)

    def test_parses_observed_experience_record(self) -> None:
        event = self.parser.parse(_entry("[Combat] Info: You have received 744 Experience Points!"))

        self.assertEqual(NativeCombatEventKind.EXPERIENCE_GAINED, event.kind)
        self.assertEqual(744.0, event.amount)

    def test_player_death_patterns_are_fail_safe_semantics(self) -> None:
        for message in (
            "[Combat] Info: You have been killed by the Frost Walker!",
            "The Frost Walker has killed YOU!",
        ):
            with self.subTest(message=message):
                event = self.parser.parse(_entry(message))
                self.assertEqual(NativeCombatEventKind.PLAYER_KILLED, event.kind)

    def test_unrecognized_native_message_is_preserved_as_other(self) -> None:
        entry = _entry("[Combat] Info: You have gained a level!")

        event = self.parser.parse(entry)

        self.assertEqual(NativeCombatEventKind.OTHER, event.kind)
        self.assertEqual(entry.message, event.message)


if __name__ == "__main__":
    unittest.main()
