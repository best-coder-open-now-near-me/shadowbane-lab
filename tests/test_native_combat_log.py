import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from shadowbane_lab.cli import main
from shadowbane_lab.client_observation import (
    NativeCombatLogFormatError,
    NativeCombatLogReader,
)


class NativeCombatLogReaderTests(unittest.TestCase):
    def test_reads_timestamped_records_without_rendered_line_wrapping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "combat.log.txt"
            path.write_bytes(
                b"(4:52:46) The Frost Walker misses YOU!\r\n\r\n"
                b"(4:52:48) You hit the Frost Walker for 4 points of damage!\r\n\r\n"
            )

            entries = NativeCombatLogReader(path).read_new_entries(finalize=True)

        self.assertEqual((0, 1), tuple(entry.sequence for entry in entries))
        self.assertEqual("4:52:46", entries[0].timestamp)
        self.assertEqual("The Frost Walker misses YOU!", entries[0].message)
        self.assertEqual(
            "You hit the Frost Walker for 4 points of damage!",
            entries[1].message,
        )

    def test_preserves_continuation_lines_as_one_lossless_message(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "combat.log.txt"
            path.write_text(
                "(1:02:03) first line\nsecond line\n\n",
                encoding="cp1252",
            )

            entries = NativeCombatLogReader(path).read_new_entries(finalize=True)

        self.assertEqual(1, len(entries))
        self.assertEqual("first line\nsecond line", entries[0].message)

    def test_retains_partial_record_until_the_native_separator_arrives(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "combat.log.txt"
            path.write_bytes(b"(9:10:11) You miss the Frost")
            reader = NativeCombatLogReader(path)

            self.assertEqual((), reader.read_new_entries())
            with path.open("ab") as stream:
                stream.write(b" Walker!\r\n\r\n")
            entries = reader.read_new_entries()

        self.assertEqual(1, len(entries))
        self.assertEqual("You miss the Frost Walker!", entries[0].message)

    def test_start_at_end_emits_only_records_appended_after_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "combat.log.txt"
            path.write_bytes(b"(1:00:00) old message\r\n\r\n")
            reader = NativeCombatLogReader(path, start_at_end=True)

            self.assertEqual((), reader.read_new_entries())
            with path.open("ab") as stream:
                stream.write(b"(1:00:01) new message\r\n\r\n")
            entries = reader.read_new_entries()

        self.assertEqual(1, len(entries))
        self.assertEqual("new message", entries[0].message)

    def test_native_ansi_text_is_decoded_without_loss(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "combat.log.txt"
            path.write_bytes("(3:04:05) René hits YOU!\r\n\r\n".encode("cp1252"))

            entries = NativeCombatLogReader(path).read_new_entries(finalize=True)

        self.assertEqual("René hits YOU!", entries[0].message)

    def test_unknown_non_empty_line_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "combat.log.txt"
            path.write_text("not a native record\n", encoding="ascii")

            with self.assertRaisesRegex(NativeCombatLogFormatError, "unrecognized"):
                NativeCombatLogReader(path).read_new_entries(finalize=True)


class NativeCombatLogCliTests(unittest.TestCase):
    def test_read_command_emits_newest_complete_native_records(self) -> None:
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "combat.log.txt"
            path.write_bytes(b"(4:52:46) first\r\n\r\n(4:52:48) second\r\n\r\n")
            with redirect_stdout(output):
                result = main(
                    (
                        "client",
                        "read-combat-log",
                        str(path),
                        "--limit",
                        "1",
                        "--json",
                    )
                )

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual(2, payload["entry_count"])
        self.assertEqual(1, payload["returned_count"])
        self.assertEqual("second", payload["entries"][0]["message"])


if __name__ == "__main__":
    unittest.main()
