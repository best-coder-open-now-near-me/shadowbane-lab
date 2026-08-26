from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from shadowbane_lab.cli import main
from shadowbane_lab.client_observation import (
    NativeCombatLogEntry,
    NativeRuneAnnouncementParser,
)


class NativeRuneAnnouncementParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = NativeRuneAnnouncementParser()

    def test_parses_exact_esh_spawn_announcement(self) -> None:
        message = (
            "Esh, Terror of the Sands in Sand Troll Dens(Leth'khalivar Desert) "
            "has found the Sun Dancer. Are you tough enough to take it?"
        )

        announcement = self.parser.parse(
            NativeCombatLogEntry(sequence=8, timestamp="7:12:03", message=message)
        )

        assert announcement is not None
        self.assertEqual("Esh, Terror of the Sands", announcement.mob_name)
        self.assertEqual("Sand Troll Dens(Leth'khalivar Desert)", announcement.location_name)
        self.assertEqual("Sun Dancer", announcement.rune_name)
        self.assertTrue(announcement.matches_all(("esh", "sun dancer")))

    def test_parses_system_prefix_and_stat_rune(self) -> None:
        announcement = self.parser.parse(
            NativeCombatLogEntry(
                sequence=9,
                timestamp="7:13:04",
                message=(
                    "[System] Info: Forest Lord in Ancient Grove(Fellgrim Forest) has found "
                    "the Intelligence of the Gods. Are you tough enough to take it?"
                ),
            )
        )

        assert announcement is not None
        self.assertEqual("Intelligence of the Gods", announcement.rune_name)
        self.assertTrue(announcement.matches_all(("forest", "intelligence")))

    def test_unrelated_system_message_is_not_guessed(self) -> None:
        entry = NativeCombatLogEntry(
            sequence=10,
            timestamp="7:14:05",
            message="[System] Info: The hotzone has moved.",
        )

        self.assertIsNone(self.parser.parse(entry))


class NativeRuneAnnouncementCliTests(unittest.TestCase):
    def test_watch_can_match_existing_announcement_without_blocking(self) -> None:
        output = io.StringIO()
        errors = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "shadowbane-system.log.txt"
            path.write_text(
                "(7:12:03) Esh, Terror of the Sands in Sand Troll Dens"
                "(Leth'khalivar Desert) has found the Sun Dancer. "
                "Are you tough enough to take it?\r\n\r\n",
                encoding="cp1252",
            )
            with redirect_stdout(output), redirect_stderr(errors):
                result = main(
                    (
                        "client",
                        "watch-rune-announcement",
                        str(path),
                        "--target",
                        "Esh",
                        "--target",
                        "Sun Dancer",
                        "--from-start",
                        "--timeout-seconds",
                        "0",
                        "--no-bell",
                        "--json",
                    )
                )

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertTrue(payload["matched"])
        self.assertEqual("Esh, Terror of the Sands", payload["announcement"]["mob_name"])
        self.assertEqual("", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
