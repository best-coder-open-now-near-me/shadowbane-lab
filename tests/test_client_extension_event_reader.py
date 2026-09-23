import struct
import unittest

from shadowbane_lab.client_extension import (
    EXTENSION_EVENT_CHANNEL_CAPACITY,
    EXTENSION_EVENT_CHANNEL_FLAG_WORLD_MAP_DESTINATION,
    EXTENSION_EVENT_CHANNEL_HEADER_SIZE,
    EXTENSION_EVENT_CHANNEL_MAGIC,
    EXTENSION_EVENT_CHANNEL_SCHEMA_VERSION,
    EXTENSION_EVENT_CHANNEL_SIZE,
    EXTENSION_EVENT_CHANNEL_SLOT_SIZE,
    ExtensionEventChannelReader,
    ExtensionEventChannelReadError,
)


class FakeSharedMemory:
    def __init__(self, payload: bytes | Exception) -> None:
        self.payload = payload
        self.calls: list[tuple[str, int]] = []

    def read(self, name: str, size: int) -> bytes:
        self.calls.append((name, size))
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def _empty_channel(process_id: int = 42, creation: int = 1000) -> bytes:
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
        0,
        0,
        0,
        0,
    )
    return bytes(payload)


class ExtensionEventChannelReaderTests(unittest.TestCase):
    def test_reads_only_the_exact_named_mapping(self) -> None:
        memory = FakeSharedMemory(_empty_channel())
        reader = ExtensionEventChannelReader(42, 1000, memory)

        snapshot = reader.snapshot()

        self.assertEqual((42, 1000), reader.process_identity)
        self.assertEqual(0, snapshot.header.pending_count)
        self.assertEqual(
            [("Local\\ShadowbaneLab.Extension.Events.42.1000", EXTENSION_EVENT_CHANNEL_SIZE)],
            memory.calls,
        )

    def test_wraps_mapping_open_failure_without_leaking_details(self) -> None:
        reader = ExtensionEventChannelReader(42, 1000, FakeSharedMemory(OSError("missing")))

        with self.assertRaisesRegex(
            ExtensionEventChannelReadError,
            "could not read the exact extension event channel: OSError",
        ):
            reader.snapshot()

    def test_rejects_payload_from_another_process(self) -> None:
        reader = ExtensionEventChannelReader(42, 1000, FakeSharedMemory(_empty_channel(43)))

        with self.assertRaisesRegex(ExtensionEventChannelReadError, "another process"):
            reader.snapshot()


if __name__ == "__main__":
    unittest.main()
