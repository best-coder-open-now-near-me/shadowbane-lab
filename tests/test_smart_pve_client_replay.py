import json
import unittest

from shadowbane_lab.client_input import (
    ClientInputAdapter,
    DecisionInputCompiler,
    EventEmergencyStop,
    ForegroundWindowGuard,
    GuardedInputExecutor,
    HotkeyInvocation,
    KeyPressInvocation,
    RecordingInputBackend,
    StaticBindingPointResolver,
    StaticWindowInspector,
    WindowBounds,
    WindowSnapshot,
    load_calibration_text,
)
from shadowbane_lab.client_observation import (
    NativeCombatEvent,
    NativeCombatEventKind,
    NativePlayerVitalsObservation,
    NativeTargetHealthObservation,
)
from shadowbane_lab.pve import (
    ClientPvEIntentDispatcher,
    PvEController,
    PvEControllerConfig,
    PvEIntent,
    PvEObservation,
)


def _profile():
    return load_calibration_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile_id": "smart-pve-dry-run",
                "live_input_enabled": False,
                "target": {
                    "executable_names": ["sb.exe"],
                    "title_pattern": "^Shadowbane$",
                    "reference_width": 1920,
                    "reference_height": 955,
                    "dpi_scale": 1.0,
                    "size_tolerance_px": 0,
                    "dpi_tolerance": 0.01,
                },
                "actions": [
                    {
                        "action_key": PvEIntent.ACQUIRE_NEXT_MOB.value,
                        "activation": {"type": "key", "key": ";"},
                        "target_order": "none",
                        "post_activation_delay_ms": 0,
                    },
                    {
                        "action_key": PvEIntent.CAST_SHADOW_TOUCH.value,
                        "activation": {"type": "key", "key": "2"},
                        "target_order": "none",
                        "post_activation_delay_ms": 0,
                    },
                    {
                        "action_key": PvEIntent.ATTACK_SELECTED_TARGET.value,
                        "activation": {"type": "hotkey", "keys": ["ctrl", "a"]},
                        "target_order": "none",
                        "post_activation_delay_ms": 0,
                    },
                ],
                "movement": {
                    "action_key": "shadowbane.move",
                    "center": {"x": 0.5, "y": 0.5},
                    "horizontal_radius": 0.25,
                    "vertical_radius": 0.2,
                    "button": "left",
                },
                "camera": {
                    "anchor": {"x": 0.5, "y": 0.5},
                    "maximum_horizontal_delta": 0.2,
                    "maximum_vertical_delta": 0.15,
                    "duration_ms": 1000,
                    "button": "left",
                },
            }
        )
    )


def _target(token: str, health: float = 180.0) -> NativeTargetHealthObservation:
    return NativeTargetHealthObservation(True, health, 180.0, token)


def _absent() -> NativeTargetHealthObservation:
    return NativeTargetHealthObservation(False)


def _player() -> NativePlayerVitalsObservation:
    return NativePlayerVitalsObservation(500.0, 500.0, 220.0, 220.0, 100.0, 100.0)


def _observation(
    now_ms: int,
    target: NativeTargetHealthObservation,
    *events: NativeCombatEvent,
) -> PvEObservation:
    return PvEObservation(now_ms, target, _player(), events)


class SmartPvEClientReplayTests(unittest.TestCase):
    def test_replays_cycle_auto_target_opener_and_stall_fallback_through_guard(self) -> None:
        profile = _profile()
        snapshot = WindowSnapshot(
            executable_name="sb.exe",
            title="Shadowbane",
            client_bounds=WindowBounds(0, 0, 1920, 955),
            dpi_scale=1.0,
            is_foreground=True,
            is_visible=True,
        )
        backend = RecordingInputBackend()
        adapter = ClientInputAdapter(
            DecisionInputCompiler(profile, StaticBindingPointResolver()),
            GuardedInputExecutor(
                guard=ForegroundWindowGuard(profile, StaticWindowInspector(snapshot)),
                backend=backend,
                stop_signal=EventEmergencyStop(),
                minimum_input_interval_ms=0,
            ),
        )
        dispatcher = ClientPvEIntentDispatcher(adapter)
        controller = PvEController(
            PvEControllerConfig(
                maximum_kills=2,
                accept_automatic_targets=True,
                opening_intent=PvEIntent.CAST_SHADOW_TOUCH,
                opening_mana_cost=55.0,
                opening_followup_delay_ms=250,
                automatic_attack_expected=True,
                automatic_target_requires_combat_event=True,
                post_kill_delay_ms=1_000,
                stalled_progress_ms=5_000,
            )
        )
        kill = NativeCombatEvent(
            sequence=0,
            timestamp="500ms",
            kind=NativeCombatEventKind.TARGET_KILLED,
            message="[Combat] Info: You have killed Camp Mob One!",
            target_name="Camp Mob One",
        )
        replacement_hit = NativeCombatEvent(
            sequence=1,
            timestamp="1500ms",
            kind=NativeCombatEventKind.PLAYER_HIT_TARGET,
            message="You hit Camp Mob Two for 8 points of damage!",
            target_name="Camp Mob Two",
            amount=8.0,
        )
        observations = (
            _observation(0, _absent()),
            _observation(100, _target("mob-1")),
            _observation(350, _target("mob-1")),
            _observation(400, _target("mob-1", 160.0)),
            _observation(500, _target("mob-2"), kill),
            _observation(1_500, _target("mob-2"), replacement_hit),
            _observation(1_750, _target("mob-2")),
            _observation(6_500, _target("mob-2")),
        )
        decisions = []
        for observation in observations:
            decision = controller.step(observation)
            decisions.append(decision)
            if decision.intent is not None:
                result = dispatcher.dispatch(
                    decision.intent,
                    sequence=decision.decision_id,
                )
                self.assertTrue(result.accepted)

        self.assertEqual(
            (
                KeyPressInvocation(";"),
                KeyPressInvocation("2"),
                KeyPressInvocation("2"),
                HotkeyInvocation(("ctrl", "a")),
            ),
            backend.invocations,
        )
        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, decisions[0].intent)
        self.assertEqual(PvEIntent.CAST_SHADOW_TOUCH, decisions[1].intent)
        self.assertIsNone(decisions[2].intent)
        self.assertIsNone(decisions[3].intent)
        self.assertEqual(PvEIntent.CAST_SHADOW_TOUCH, decisions[5].intent)
        self.assertIsNone(decisions[6].intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, decisions[7].intent)


if __name__ == "__main__":
    unittest.main()
