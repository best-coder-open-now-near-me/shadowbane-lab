import struct
import unittest

from shadowbane_lab.client_extension.events import (
    EXTENSION_EVENT_CHANNEL_CAPACITY,
    EXTENSION_EVENT_CHANNEL_FLAG_WORLD_MAP_DESTINATION,
    EXTENSION_EVENT_CHANNEL_HEADER_SIZE,
    EXTENSION_EVENT_CHANNEL_MAGIC,
    EXTENSION_EVENT_CHANNEL_SCHEMA_VERSION,
    EXTENSION_EVENT_CHANNEL_SIZE,
    EXTENSION_EVENT_CHANNEL_SLOT_SIZE,
    ExtensionEventError,
    ExtensionPointerButton,
    extension_event_mapping_name,
    extension_event_signal_name,
    parse_extension_event_channel,
)


class ExtensionEventContractTests(unittest.TestCase):
    def test_parses_exact_process_world_map_destination(self) -> None:
        payload = self._channel(
            process_id=42,
            creation=1000,
            write_sequence=1,
            read_sequence=0,
        )
        self._slot(
            payload,
            sequence=1,
            captured=1001,
            window_handle=9001,
            button=2,
            lt=106662.5,
            lg=52432.25,
            snapshot_hash=0x0123456789ABCDEF,
            desktop=(400, 300),
            client=(380, 260),
        )

        snapshot = parse_extension_event_channel(
            payload,
            expected_process_id=42,
            expected_process_creation_filetime_utc=1000,
        )

        self.assertEqual(1, snapshot.header.pending_count)
        self.assertEqual(1, snapshot.header.write_sequence)
        self.assertEqual(0, snapshot.header.read_sequence)
        event = snapshot.events[0]
        self.assertEqual((42, 1000), event.process_identity)
        self.assertEqual(ExtensionPointerButton.RIGHT, event.button)
        self.assertEqual(106662.5, event.lt)
        self.assertEqual(52432.25, event.lg)
        self.assertEqual("0123456789abcdef", event.snapshot_token)
        self.assertEqual((400, 300), (event.desktop_screen_x, event.desktop_screen_y))
        self.assertEqual((380, 260), (event.client_x, event.client_y))
        self.assertEqual("world_map_destination", event.to_dict()["kind"])

    def test_wraps_slots_by_monotonic_sequence(self) -> None:
        read_sequence = EXTENSION_EVENT_CHANNEL_CAPACITY
        write_sequence = read_sequence + 2
        payload = self._channel(
            process_id=42,
            creation=1000,
            write_sequence=write_sequence,
            read_sequence=read_sequence,
        )
        self._slot(payload, sequence=read_sequence + 1, button=1)
        self._slot(payload, sequence=read_sequence + 2, button=2)

        snapshot = parse_extension_event_channel(
            payload,
            expected_process_id=42,
            expected_process_creation_filetime_utc=1000,
        )

        self.assertEqual(
            (read_sequence + 1, read_sequence + 2),
            tuple(event.sequence for event in snapshot.events),
        )

    def test_rejects_wrong_exact_process_lifetime(self) -> None:
        payload = self._channel(process_id=42, creation=1000)
        with self.assertRaisesRegex(ExtensionEventError, "another process lifetime"):
            parse_extension_event_channel(
                payload,
                expected_process_id=42,
                expected_process_creation_filetime_utc=1001,
            )

    def test_rejects_uncommitted_slot(self) -> None:
        payload = self._channel(
            process_id=42,
            creation=1000,
            write_sequence=1,
            read_sequence=0,
        )
        with self.assertRaisesRegex(ExtensionEventError, "not coherently committed"):
            parse_extension_event_channel(
                payload,
                expected_process_id=42,
                expected_process_creation_filetime_utc=1000,
            )

    def test_rejects_capacity_overrun(self) -> None:
        payload = self._channel(
            process_id=42,
            creation=1000,
            write_sequence=EXTENSION_EVENT_CHANNEL_CAPACITY + 1,
            read_sequence=0,
        )
        with self.assertRaisesRegex(ExtensionEventError, "bounded capacity"):
            parse_extension_event_channel(
                payload,
                expected_process_id=42,
                expected_process_creation_filetime_utc=1000,
            )

    def test_names_are_derived_only_from_exact_process_identity(self) -> None:
        self.assertEqual(
            "Local\\ShadowbaneLab.Extension.Events.42.1000",
            extension_event_mapping_name(42, 1000),
        )
        self.assertEqual(
            "Local\\ShadowbaneLab.Extension.Signal.42.1000",
            extension_event_signal_name(42, 1000),
        )

    @staticmethod
    def _channel(
        *,
        process_id: int,
        creation: int,
        write_sequence: int = 0,
        read_sequence: int = 0,
    ) -> bytearray:
        payload = bytearray(EXTENSION_EVENT_CHANNEL_SIZE)
        struct.pack_into(
            "<8s6I4QI12x",
            payload,
            0,
            EXTENSION_EVENT_CHANNEL_MAGIC,
            EXTENSION_EVENT_CHANNEL_SCHEMA_VERSION,
            EXTENSION_EVENT_CHANNEL_HEADER_SIZE,
            EXTENSION_EVENT_CHANNEL_SLOT_SIZE,
            EXTENSION_EVENT_CHANNEL_CAPACITY,
            process_id,
            EXTENSION_EVENT_CHANNEL_FLAG_WORLD_MAP_DESTINATION,
            creation,
            write_sequence,
            read_sequence,
            0,
            0,
        )
        return payload

    @staticmethod
    def _slot(
        payload: bytearray,
        *,
        sequence: int,
        captured: int = 1001,
        window_handle: int = 9001,
        button: int = 1,
        lt: float = 120000.0,
        lg: float = 60000.0,
        snapshot_hash: int = 0xAABBCCDDEEFF0011,
        desktop: tuple[int, int] = (100, 200),
        client: tuple[int, int] = (80, 160),
    ) -> None:
        slot_index = (sequence - 1) % EXTENSION_EVENT_CHANNEL_CAPACITY
        offset = EXTENSION_EVENT_CHANNEL_HEADER_SIZE + (
            slot_index * EXTENSION_EVENT_CHANNEL_SLOT_SIZE
        )
        struct.pack_into(
            "<QIIQQddQiiii8x",
            payload,
            offset,
            sequence,
            1,
            button,
            captured,
            window_handle,
            lt,
            lg,
            snapshot_hash,
            desktop[0],
            desktop[1],
            client[0],
            client[1],
        )


if __name__ == "__main__":
    unittest.main()
