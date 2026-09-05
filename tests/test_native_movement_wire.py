import struct
import unittest
from dataclasses import replace
from pathlib import Path

from shadowbane_lab.client_extension.movement_wire import (
    Command,
    Grant,
    Host,
    Outcome,
    Owner,
    Receipt,
    Settings,
    Snapshot,
    Verb,
)

FIXTURE = Path(__file__).parent / "fixtures" / "native_movement_wire_v2.hex"
KEY = "12345678-1234-5678-9abc-def0123456f0"


def values():
    grant = Grant(0x1020304050607080, 0x2030405060708090, Owner.AUTOMATION, "w" * 95, "o" * 95)
    settings = Settings(
        enabled=True,
        controller=True,
        keys=(0x49, 0x4B, 0x4A, 0x4C),
        controller_slot=3,
        movement_dead_zone=0.25,
        camera_dead_zone=0.125,
        invert_camera_y=True,
    )
    command = Command(
        Host(1234, 27, 0x1122334455667788),
        0xF1234567,
        grant,
        KEY,
        (1.25, -20.5, 4096.0),
        settings,
        0x3456789012345678,
        "n" * 95,
        "p" * 95,
    )
    receipt = Receipt(
        grant, KEY, command.host, command.window, command.revision, settings, Outcome.STALE, 7
    )
    snapshot = Snapshot(
        12,
        4321,
        7,
        0x2233445566778899,
        command.window,
        grant,
        settings,
        command.revision,
        987654321,
    )
    return command, receipt, snapshot


class MovementWireTest(unittest.TestCase):
    def test_shared_fixture_exact_bytes_and_round_trip(self):
        command, receipt, snapshot = values()
        actual = [command.encode(Verb.ACQUIRE), receipt.encode(), snapshot.encode()]
        expected = [bytes.fromhex(line) for line in FIXTURE.read_text().splitlines()]
        self.assertEqual([len(x) for x in actual], [576, 384, 512])
        self.assertEqual(actual, expected)
        self.assertEqual(Command.decode(actual[0], Verb.ACQUIRE), command)
        self.assertEqual(Receipt.decode(actual[1]), receipt)
        self.assertEqual(Snapshot.decode(actual[2]), snapshot)
        self.assertEqual(actual[0][240:256].hex(), KEY.replace("-", ""))
        self.assertEqual(struct.unpack_from("<Q", actual[0], 16)[0], command.window)
        self.assertEqual(struct.unpack_from("<Q", actual[2], 300)[0], command.revision)

    def test_lossless_identity_validation(self):
        command, _, _ = values()
        for invalid in (
            replace(command, worker_id="a" * 96),
            replace(command, operation_id="é"),
            replace(command, host=Host(1, 0, 3)),
            replace(command, window=2**32),
            replace(command, request_key=KEY.upper()),
            replace(command, request_key="00000000-0000-0000-0000-000000000000"),
            replace(command, expected=replace(command.expected, owner=Owner.MANUAL)),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                invalid.encode(Verb.ACQUIRE)

    def test_reserved_padding_and_truncation_rejected(self):
        command, receipt, snapshot = values()
        for encoded, decode in (
            (command.encode(Verb.ACQUIRE), lambda b: Command.decode(b, Verb.ACQUIRE)),
            (receipt.encode(), Receipt.decode),
            (snapshot.encode(), Snapshot.decode),
        ):
            changed = bytearray(encoded)
            changed[-1] = 1
            with self.assertRaises(ValueError):
                decode(changed)
            with self.assertRaises((ValueError, struct.error)):
                decode(encoded[:-1])
        encoded = bytearray(command.encode(Verb.ACQUIRE))
        encoded[24 + 24 + 95] = 65
        with self.assertRaises(ValueError):
            Command.decode(encoded, Verb.ACQUIRE)

    def test_native_settings_limits_and_precision(self):
        settings = Settings()
        for invalid in (
            replace(settings, enabled=1),
            replace(settings, keys=(87, 87, 65, 68)),
            replace(settings, controller_slot=4),
            replace(settings, drag_button=2),
            replace(settings, movement_dead_zone=0.95),
            replace(settings, camera_dead_zone=float("nan")),
            replace(settings, drag_threshold_pixels=1),
            replace(settings, camera_radians_per_second=11),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                invalid.encode()
        self.assertEqual(Settings.decode(settings.encode()).encode(), settings.encode())

    def test_verb_ownership_and_snapshot_publication(self):
        command, _, snapshot = values()
        move = replace(command, worker_id="", operation_id="")
        self.assertEqual(Command.decode(move.encode(Verb.DESTINATION), Verb.DESTINATION), move)
        for invalid in (
            replace(move, destination=(float("inf"), 1, 2)),
            replace(move, expected=Grant(1, 2, Owner.NONE)),
        ):
            with self.assertRaises(ValueError):
                invalid.encode(Verb.DESTINATION)
        for invalid in (
            replace(snapshot, sequence=0),
            replace(snapshot, sequence=13),
            replace(snapshot, flags=64),
        ):
            with self.assertRaises(ValueError):
                invalid.encode()


if __name__ == "__main__":
    unittest.main()
