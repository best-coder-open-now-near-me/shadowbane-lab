import struct
import unittest

from shadowbane_lab.client_extension.event_consumer import (
    ExtensionEventConsumer,
    ExtensionEventConsumerError,
)
from shadowbane_lab.client_extension.events import (
    EXTENSION_EVENT_CHANNEL_CAPACITY,
    EXTENSION_EVENT_CHANNEL_FLAG_WORLD_MAP_DESTINATION,
    EXTENSION_EVENT_CHANNEL_HEADER_SIZE,
    EXTENSION_EVENT_CHANNEL_MAGIC,
    EXTENSION_EVENT_CHANNEL_SCHEMA_VERSION,
    EXTENSION_EVENT_CHANNEL_SIZE,
    EXTENSION_EVENT_CHANNEL_SLOT_SIZE,
)


class FakeTransport:
    def __init__(self, payload: bytearray, *, claim: bool = True) -> None:
        self.payload = payload
        self.claim_result = claim
        self.claimed = False
        self.closed = False

    def claim(self) -> bool:
        if not self.claim_result:
            return False
        self.claimed = True
        struct.pack_into("<IQ", self.payload, 68, 500, 10_000)
        return True

    def renew(self) -> bool:
        return self.claimed and not self.closed

    def read(self) -> bytes:
        return bytes(self.payload)

    def advance(self, expected_sequence: int, sequence: int) -> bool:
        current = struct.unpack_from("<Q", self.payload, 48)[0]
        if current != expected_sequence:
            return False
        struct.pack_into("<Q", self.payload, 48, sequence)
        return True

    def wait(self, timeout_seconds: float) -> None:
        return None

    def close(self) -> None:
        self.closed = True
        self.claimed = False


class ExtensionEventConsumerTests(unittest.TestCase):
    def test_reads_and_acknowledges_only_the_next_exact_event(self) -> None:
        payload = self._channel(write_sequence=1)
        self._slot(payload, sequence=1)
        consumer = ExtensionEventConsumer(42, 1000, FakeTransport(payload))

        events = consumer.pending()
        self.assertEqual((1,), tuple(event.sequence for event in events))
        consumer.acknowledge(events[0])
        self.assertEqual(1, struct.unpack_from("<Q", payload, 48)[0])
        self.assertEqual((), consumer.pending())

    def test_refuses_a_second_consumer(self) -> None:
        transport = FakeTransport(self._channel(), claim=False)
        with self.assertRaisesRegex(ExtensionEventConsumerError, "active consumer"):
            ExtensionEventConsumer(42, 1000, transport)
        self.assertTrue(transport.closed)

    def test_refuses_to_skip_an_event(self) -> None:
        payload = self._channel(write_sequence=2)
        self._slot(payload, sequence=1)
        self._slot(payload, sequence=2)
        consumer = ExtensionEventConsumer(42, 1000, FakeTransport(payload))

        events = consumer.pending()
        with self.assertRaisesRegex(ExtensionEventConsumerError, "contiguously"):
            consumer.acknowledge(events[1])

    def test_can_claim_a_channel_after_a_prior_consumer_closed(self) -> None:
        payload = self._channel(write_sequence=2, read_sequence=1)
        self._slot(payload, sequence=2)
        consumer = ExtensionEventConsumer(42, 1000, FakeTransport(payload))

        events = consumer.pending()
        self.assertEqual((2,), tuple(event.sequence for event in events))
        consumer.acknowledge(events[0])

    @staticmethod
    def _channel(
        *,
        write_sequence: int = 0,
        read_sequence: int = 0,
    ) -> bytearray:
        payload = bytearray(EXTENSION_EVENT_CHANNEL_SIZE)
        struct.pack_into(
            "<8s6I4QIIQ",
            payload,
            0,
            EXTENSION_EVENT_CHANNEL_MAGIC,
            EXTENSION_EVENT_CHANNEL_SCHEMA_VERSION,
            EXTENSION_EVENT_CHANNEL_HEADER_SIZE,
            EXTENSION_EVENT_CHANNEL_SLOT_SIZE,
            EXTENSION_EVENT_CHANNEL_CAPACITY,
            42,
            EXTENSION_EVENT_CHANNEL_FLAG_WORLD_MAP_DESTINATION,
            1000,
            write_sequence,
            read_sequence,
            0,
            0,
            0,
            0,
        )
        return payload

    @staticmethod
    def _slot(payload: bytearray, *, sequence: int) -> None:
        offset = (
            EXTENSION_EVENT_CHANNEL_HEADER_SIZE
            + ((sequence - 1) % EXTENSION_EVENT_CHANNEL_CAPACITY)
            * EXTENSION_EVENT_CHANNEL_SLOT_SIZE
        )
        struct.pack_into(
            "<QIIQQddQiiii8x",
            payload,
            offset,
            sequence,
            1,
            2,
            1001,
            9001,
            106662.5,
            52432.25,
            0x0123456789ABCDEF,
            400,
            300,
            380,
            260,
        )


if __name__ == "__main__":
    unittest.main()
