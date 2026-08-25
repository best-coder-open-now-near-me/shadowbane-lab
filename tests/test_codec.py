import json
import unittest

from shadowbane_lab.protocol import ProtocolDecodeError, decode_message, encode_message

from tests.fixtures import protocol_exchange


class ProtocolCodecTests(unittest.TestCase):
    def test_every_message_round_trips(self) -> None:
        for message in protocol_exchange():
            with self.subTest(message=type(message).__name__):
                self.assertEqual(message, decode_message(encode_message(message)))

    def test_encoding_is_canonical(self) -> None:
        decision = protocol_exchange()[2]

        first = encode_message(decision)
        second = encode_message(decode_message(first))

        self.assertEqual(first, second)
        self.assertEqual(first, json.dumps(json.loads(first), separators=(",", ":"), sort_keys=True))

    def test_unknown_protocol_version_fails_closed(self) -> None:
        decision = protocol_exchange()[2]
        payload = json.loads(encode_message(decision))
        payload["protocol_version"] = 99

        with self.assertRaisesRegex(ProtocolDecodeError, "unsupported protocol version"):
            decode_message(json.dumps(payload))

    def test_missing_protocol_version_fails_closed(self) -> None:
        decision = protocol_exchange()[2]
        payload = json.loads(encode_message(decision))
        del payload["protocol_version"]

        with self.assertRaisesRegex(ProtocolDecodeError, "missing required field"):
            decode_message(json.dumps(payload))

    def test_additive_event_kind_round_trips(self) -> None:
        event_batch = protocol_exchange()[3]
        event = event_batch.events[0]
        custom_event = type(event)(
            event_id="event-custom",
            kind="ruleset.custom_event",
            tick=event.tick,
            sim_time_ms=event.sim_time_ms,
        )
        message = type(event_batch)(
            message_id="message-custom-event",
            tick=event_batch.tick,
            sim_time_ms=event_batch.sim_time_ms,
            events=(custom_event,),
        )

        self.assertEqual(message, decode_message(encode_message(message)))

    def test_boolean_is_not_accepted_as_tick(self) -> None:
        decision = protocol_exchange()[2]
        payload = json.loads(encode_message(decision))
        payload["tick"] = True

        with self.assertRaisesRegex(ProtocolDecodeError, "tick must be an integer"):
            decode_message(json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
