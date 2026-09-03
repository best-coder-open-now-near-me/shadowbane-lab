import struct
import unittest

from shadowbane_lab.client_extension.action_trace import (
    CLIENT_ACTION_TRACE_ACTION_188_CANDIDATE_FLAG,
    CLIENT_ACTION_TRACE_ARGUMENT_PRESENT_FLAG,
    CLIENT_ACTION_TRACE_CAPABILITIES,
    CLIENT_ACTION_TRACE_CAPACITY,
    CLIENT_ACTION_TRACE_CONTEXT_COMPLETE_FLAG,
    CLIENT_ACTION_TRACE_HEADER_SIZE,
    CLIENT_ACTION_TRACE_MAGIC,
    CLIENT_ACTION_TRACE_SCHEMA_VERSION,
    CLIENT_ACTION_TRACE_SIZE,
    CLIENT_ACTION_TRACE_SLOT_SIZE,
    CLIENT_ACTION_TRACE_STACK_COMPLETE_FLAG,
    CLIENT_ACTION_TRACE_TUPLE_COMPLETE_FLAG,
    ClientActionTraceError,
    ClientActionTraceProbeStatus,
    REVIEWED_WONDERBANE_IMAGE_SIZE,
    REVIEWED_WONDERBANE_PE_TIMESTAMP,
    REVIEWED_WONDERBANE_PREFERRED_BASE,
    TARGET_NEXT_MOB_ACTION_CODE,
    client_action_trace_mapping_name,
    parse_client_action_trace,
)
from shadowbane_lab.client_extension.action_trace_reader import (
    ClientActionTraceNotArmed,
    ClientActionTraceReader,
)

_HEADER = struct.Struct("<8s6I6Q12I")
_SLOT = struct.Struct("<QIIQIiII8IIiiII32s8I36s")


class StaticMemory:
    def __init__(self, payloads: list[bytes]) -> None:
        self.payloads = payloads
        self.calls: list[tuple[str, int]] = []

    def read(self, mapping_name: str, size: int) -> bytes:
        self.calls.append((mapping_name, size))
        if len(self.payloads) > 1:
            return self.payloads.pop(0)
        return self.payloads[0]


def _payload(
    *,
    status: ClientActionTraceProbeStatus = ClientActionTraceProbeStatus.UNCONFIGURED,
    target_rva: int = 0,
    callsite_rva: int = 0,
    stack_count: int = 0,
    active_probe_count: int = 0,
    include_record: bool = False,
) -> bytes:
    write_sequence = 1 if include_record else 0
    payload = bytearray(CLIENT_ACTION_TRACE_SIZE)
    _HEADER.pack_into(
        payload,
        0,
        CLIENT_ACTION_TRACE_MAGIC,
        CLIENT_ACTION_TRACE_SCHEMA_VERSION,
        CLIENT_ACTION_TRACE_HEADER_SIZE,
        CLIENT_ACTION_TRACE_SLOT_SIZE,
        CLIENT_ACTION_TRACE_CAPACITY,
        4321,
        CLIENT_ACTION_TRACE_CAPABILITIES,
        133_000_000_000_000_000,
        10_000_000,
        1_000,
        write_sequence,
        0,
        write_sequence,
        0,
        int(status),
        TARGET_NEXT_MOB_ACTION_CODE,
        target_rva,
        callsite_rva,
        stack_count,
        active_probe_count,
        REVIEWED_WONDERBANE_PE_TIMESTAMP,
        REVIEWED_WONDERBANE_IMAGE_SIZE,
        REVIEWED_WONDERBANE_PREFERRED_BASE,
        0,
        0,
    )
    if include_record:
        flags = (
            CLIENT_ACTION_TRACE_CONTEXT_COMPLETE_FLAG
            | CLIENT_ACTION_TRACE_STACK_COMPLETE_FLAG
            | CLIENT_ACTION_TRACE_TUPLE_COMPLETE_FLAG
            | CLIENT_ACTION_TRACE_ACTION_188_CANDIDATE_FLAG
        )
        _SLOT.pack_into(
            payload,
            CLIENT_ACTION_TRACE_HEADER_SIZE,
            1,
            1,
            flags,
            2_000,
            77,
            TARGET_NEXT_MOB_ACTION_CODE,
            0x1234,
            0x2345,
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            0x202,
            0,
            0,
            0,
            4,
            b"\0" * 32,
            0x11111111,
            0x22222222,
            0x33333333,
            0x44444444,
            0,
            0,
            0,
            0,
            b"\0" * 36,
        )
    return bytes(payload)


class ClientActionTraceAbiTests(unittest.TestCase):
    def test_unconfigured_profile_is_explicit_and_process_bound(self) -> None:
        snapshot = parse_client_action_trace(
            _payload(),
            expected_process_id=4321,
            expected_process_creation_filetime_utc=133_000_000_000_000_000,
        )

        self.assertEqual(ClientActionTraceProbeStatus.UNCONFIGURED, snapshot.header.probe_status)
        self.assertFalse(snapshot.header.ready_for_capture)
        self.assertEqual(188, snapshot.header.target_action_code)
        self.assertEqual((), snapshot.records)
        self.assertEqual(
            "Local\\ShadowbaneLab.Extension.ActionTrace."
            "4321.133000000000000000",
            client_action_trace_mapping_name(4321, 133_000_000_000_000_000),
        )

    def test_action_188_call_entry_round_trips_bounded_context(self) -> None:
        snapshot = parse_client_action_trace(
            _payload(
                status=ClientActionTraceProbeStatus.OBSERVING,
                target_rva=0x1234,
                callsite_rva=0x2345,
                stack_count=4,
                active_probe_count=1,
                include_record=True,
            ),
            expected_process_id=4321,
            expected_process_creation_filetime_utc=133_000_000_000_000_000,
        )

        record = snapshot.records[0]
        self.assertTrue(snapshot.header.ready_for_capture)
        self.assertEqual(77, record.thread_id)
        self.assertEqual(3, record.ecx)
        self.assertEqual(
            (0x11111111, 0x22222222, 0x33333333, 0x44444444),
            record.stack_dwords,
        )
        self.assertEqual(
            {
                "action_code": 188,
                "parameter_one": 0,
                "parameter_two": 0,
                "argument": "",
            },
            record.as_dict(snapshot.header)["arcane_tuple"],
        )

    def test_partial_tuple_and_argument_are_rejected(self) -> None:
        payload = bytearray(
            _payload(
                status=ClientActionTraceProbeStatus.OBSERVING,
                target_rva=0x1234,
                callsite_rva=0x2345,
                stack_count=4,
                active_probe_count=1,
                include_record=True,
            )
        )
        flags_offset = CLIENT_ACTION_TRACE_HEADER_SIZE + 12
        flags = struct.unpack_from("<I", payload, flags_offset)[0]
        struct.pack_into(
            "<I",
            payload,
            flags_offset,
            flags & ~CLIENT_ACTION_TRACE_TUPLE_COMPLETE_FLAG
            | CLIENT_ACTION_TRACE_ARGUMENT_PRESENT_FLAG,
        )
        struct.pack_into("<I", payload, CLIENT_ACTION_TRACE_HEADER_SIZE + 84, 1)
        payload[CLIENT_ACTION_TRACE_HEADER_SIZE + 92] = ord("x")

        with self.assertRaisesRegex(ClientActionTraceError, "partial Arcane"):
            parse_client_action_trace(
                payload,
                expected_process_id=4321,
                expected_process_creation_filetime_utc=133_000_000_000_000_000,
            )

    def test_wrong_process_lifetime_is_rejected(self) -> None:
        with self.assertRaisesRegex(ClientActionTraceError, "process lifetime"):
            parse_client_action_trace(
                _payload(),
                expected_process_id=4321,
                expected_process_creation_filetime_utc=1,
            )


class ClientActionTraceReaderTests(unittest.TestCase):
    def test_wait_fails_immediately_while_profile_is_unconfigured(self) -> None:
        memory = StaticMemory([_payload()])
        reader = ClientActionTraceReader(
            4321,
            133_000_000_000_000_000,
            memory,
        )

        with self.assertRaisesRegex(ClientActionTraceNotArmed, "not armed"):
            reader.wait_for_records(timeout_seconds=1)

        self.assertEqual(
            [
                (
                    "Local\\ShadowbaneLab.Extension.ActionTrace."
                    "4321.133000000000000000",
                    CLIENT_ACTION_TRACE_SIZE,
                )
            ],
            memory.calls,
        )


if __name__ == "__main__":
    unittest.main()
