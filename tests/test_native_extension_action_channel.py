import inspect
import struct
import unittest

import shadowbane_lab.client_extension.action_channel as action_channel_module
from shadowbane_lab.client_extension import (
    CLIENT_ACTION_ARGUMENT_CAPACITY,
    CLIENT_ACTION_CHANNEL_HEADER_SIZE,
    CLIENT_ACTION_CHANNEL_MAGIC,
    CLIENT_ACTION_CHANNEL_SCHEMA_VERSION,
    CLIENT_ACTION_COMMAND_CAPACITY,
    CLIENT_ACTION_COMMAND_SLOT_SIZE,
    CLIENT_ACTION_PAYLOAD_VERSION,
    CLIENT_ACTION_POWER_IDENTIFIER_CAPACITY,
    CLIENT_ACTION_RESULT_CAPACITY,
    CLIENT_ACTION_RESULT_SLOT_SIZE,
    CLIENT_ACTION_TRANSPORT_CAPABILITY,
    DEFAULT_NATIVE_ACTIONS,
    LearnedPowerDescriptor,
    NativeActionChannelHeader,
    NativeActionCommand,
    NativeActionCommandKind,
    NativeActionDescriptor,
    NativeActionResult,
    NativeActionResultStage,
    NativeClientProcessIdentity,
    NativeExtensionActionDispatcher,
)
from shadowbane_lab.pve.model import PvEIntent
from shadowbane_lab.pve.native_actuator import NativeExtensionPvEIntentDispatcher


class RecordingTransport:
    def __init__(self, result: NativeActionResult) -> None:
        self.result = result
        self.commands: list[NativeActionCommand] = []
        self.timeouts: list[int] = []

    def submit(
        self,
        command: NativeActionCommand,
        *,
        timeout_ms: int,
    ) -> NativeActionResult:
        self.commands.append(command)
        self.timeouts.append(timeout_ms)
        return NativeActionResult(
            result_sequence=self.result.result_sequence,
            command_id=command.command_id,
            command_sequence=self.result.command_sequence,
            stage=self.result.stage,
            error_code=self.result.error_code,
            observed_tick=self.result.observed_tick,
            consumer_thread_id=self.result.consumer_thread_id,
            detail=self.result.detail,
        )


def _result(
    stage: NativeActionResultStage,
    *,
    error_code: int = 0,
    detail: str = "",
) -> NativeActionResult:
    return NativeActionResult(
        result_sequence=1,
        command_id=1,
        command_sequence=1,
        stage=stage,
        error_code=error_code,
        observed_tick=100,
        consumer_thread_id=77,
        detail=detail,
    )


class NativeActionAbiTests(unittest.TestCase):
    def test_header_geometry_and_process_identity_round_trip(self) -> None:
        identity = NativeClientProcessIdentity(4321, 133_000_000_000_000_000)
        header = struct.pack(
            "<8s8IQ6q2iq2i8s",
            CLIENT_ACTION_CHANNEL_MAGIC,
            CLIENT_ACTION_CHANNEL_SCHEMA_VERSION,
            CLIENT_ACTION_CHANNEL_HEADER_SIZE,
            CLIENT_ACTION_COMMAND_SLOT_SIZE,
            CLIENT_ACTION_COMMAND_CAPACITY,
            CLIENT_ACTION_RESULT_SLOT_SIZE,
            CLIENT_ACTION_RESULT_CAPACITY,
            identity.process_id,
            CLIENT_ACTION_TRANSPORT_CAPABILITY,
            identity.creation_filetime_utc,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            b"\0" * 8,
        )

        decoded = NativeActionChannelHeader.decode(header)

        self.assertEqual(identity, decoded.process_identity)
        self.assertEqual(CLIENT_ACTION_TRANSPORT_CAPABILITY, decoded.capability_flags)
        self.assertEqual(
            "Local\\ShadowbaneLab.Extension.Actions."
            "4321.133000000000000000",
            identity.mapping_name,
        )

    def test_native_action_command_encodes_complete_arcane_tuple(self) -> None:
        command = NativeActionCommand(
            9,
            NativeActionDescriptor(
                48,
                parameter_one=7,
                parameter_two=-2,
                argument="WorldMap",
                evidence_source="fixture",
            ),
        )

        payload = command.encode_slot(
            sequence=3,
            created_tick=100,
            deadline_tick=500,
        )
        fields = struct.unpack("<qQIIQQiiiIII96s32s", payload)

        self.assertEqual(CLIENT_ACTION_COMMAND_SLOT_SIZE, len(payload))
        self.assertEqual(0, fields[0])
        self.assertEqual(9, fields[1])
        self.assertEqual(NativeActionCommandKind.NATIVE_ACTION, fields[2])
        self.assertEqual(CLIENT_ACTION_PAYLOAD_VERSION, fields[3])
        self.assertEqual((48, 7, -2), fields[6:9])
        self.assertEqual(len("WorldMap"), fields[9])
        self.assertEqual(b"WorldMap", fields[12][: fields[9]])
        self.assertEqual(0, fields[10])
        self.assertEqual(
            b"\0" * CLIENT_ACTION_POWER_IDENTIFIER_CAPACITY,
            fields[13],
        )

    def test_learned_power_command_is_not_a_hotbar_slot(self) -> None:
        command = NativeActionCommand(
            10,
            LearnedPowerDescriptor("ASS-013", "Arcane hotbar POWERNAME"),
        )

        payload = command.encode_slot(
            sequence=4,
            created_tick=100,
            deadline_tick=500,
        )
        fields = struct.unpack("<qQIIQQiiiIII96s32s", payload)

        self.assertEqual(NativeActionCommandKind.LEARNED_POWER, fields[2])
        self.assertEqual((0, 0, 0), fields[6:9])
        self.assertEqual(0, fields[9])
        self.assertEqual(len("ASS-013"), fields[10])
        self.assertEqual(b"ASS-013", fields[13][: fields[10]])
        self.assertEqual(b"\0" * CLIENT_ACTION_ARGUMENT_CAPACITY, fields[12])


class NativeExtensionActionDispatcherTests(unittest.TestCase):
    def test_known_pve_actions_map_to_native_descriptors(self) -> None:
        next_target = DEFAULT_NATIVE_ACTIONS["client.pve.target_next_mobile"]
        previous_target = DEFAULT_NATIVE_ACTIONS["client.pve.target_previous_mobile"]
        attack = DEFAULT_NATIVE_ACTIONS["shadowbane.basic_attack"]
        shadow_touch = DEFAULT_NATIVE_ACTIONS["shadowbane.assassin.shadow_touch"]

        self.assertIsInstance(next_target, NativeActionDescriptor)
        self.assertEqual(188, next_target.action_code)
        self.assertIsInstance(previous_target, NativeActionDescriptor)
        self.assertEqual(189, previous_target.action_code)
        self.assertIsInstance(attack, NativeActionDescriptor)
        self.assertEqual(1551, attack.action_code)
        self.assertIsInstance(shadow_touch, LearnedPowerDescriptor)
        self.assertEqual("ASS-013", shadow_touch.power_identifier)

    def test_submitted_native_result_is_accepted(self) -> None:
        transport = RecordingTransport(
            _result(NativeActionResultStage.SUBMITTED_TO_CLIENT)
        )
        dispatcher = NativeExtensionActionDispatcher(transport, timeout_ms=750)

        result = dispatcher.dispatch_action(
            "client.pve.target_next_mobile",
            correlation_id="test:next",
        )

        self.assertTrue(result.accepted)
        self.assertEqual([750], transport.timeouts)
        target = transport.commands[0].target
        self.assertIsInstance(target, NativeActionDescriptor)
        self.assertEqual(188, target.action_code)
        self.assertEqual(
            NativeActionResultStage.SUBMITTED_TO_CLIENT,
            dispatcher.audits[0].result_stage,
        )

    def test_dispatcher_unavailable_is_a_rejection_without_fallback(self) -> None:
        transport = RecordingTransport(
            _result(
                NativeActionResultStage.FAILED,
                error_code=50,
                detail="reviewed_client_dispatcher_unavailable",
            )
        )
        dispatcher = NativeExtensionActionDispatcher(transport)

        result = dispatcher.dispatch_action(
            "shadowbane.assassin.shadow_touch",
            correlation_id="test:power",
        )

        self.assertFalse(result.accepted)
        self.assertIn("reviewed_client_dispatcher_unavailable", result.reason)
        self.assertEqual(1, len(transport.commands))
        self.assertIsInstance(transport.commands[0].target, LearnedPowerDescriptor)
        source = inspect.getsource(action_channel_module)
        self.assertNotIn("PyAutoGui", source)
        self.assertNotIn("KeyPressCommand", source)
        self.assertNotIn("HotkeyCommand", source)

    def test_unmapped_action_never_reaches_transport(self) -> None:
        transport = RecordingTransport(
            _result(NativeActionResultStage.SUBMITTED_TO_CLIENT)
        )
        dispatcher = NativeExtensionActionDispatcher(transport)

        result = dispatcher.dispatch_action(
            "shadowbane.unverified.action",
            correlation_id="test:unknown",
        )

        self.assertFalse(result.accepted)
        self.assertEqual("native_extension_action_unmapped", result.reason)
        self.assertEqual([], transport.commands)

    def test_pve_intent_dispatcher_preserves_semantic_correlation(self) -> None:
        transport = RecordingTransport(
            _result(NativeActionResultStage.SUBMITTED_TO_CLIENT)
        )
        action_dispatcher = NativeExtensionActionDispatcher(transport)
        dispatcher = NativeExtensionPvEIntentDispatcher(action_dispatcher)

        result = dispatcher.dispatch(PvEIntent.ACQUIRE_PREVIOUS_MOB, sequence=12)

        self.assertTrue(result.accepted)
        self.assertEqual(
            "pve:12:client.pve.target_previous_mobile",
            result.correlation_id,
        )
        target = transport.commands[0].target
        self.assertIsInstance(target, NativeActionDescriptor)
        self.assertEqual(189, target.action_code)


if __name__ == "__main__":
    unittest.main()
