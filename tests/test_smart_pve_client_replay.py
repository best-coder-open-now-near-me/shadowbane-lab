import json
import unittest
from dataclasses import replace

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
    NativeCharacterKind,
    NativeCharacterObservation,
    NativeCharacterPopulationObservation,
    NativeCombatEvent,
    NativeCombatEventKind,
    NativePlayerActionObservation,
    NativePlayerVitalsObservation,
    NativeTargetActionPhase,
    NativeTargetHealthObservation,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.pve import (
    ClientPvEIntentDispatcher,
    PvEController,
    PvEControllerConfig,
    PvEIntent,
    PvEObservation,
)
from shadowbane_lab.pve.model import PvECombatCleanupResult


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


def _character(token: str, health: float = 180.0) -> NativeCharacterObservation:
    return NativeCharacterObservation(
        token=token, object_key=NativeObjectKey(int(token.split("-")[-1]) + 100, 37),
        character_kind=NativeCharacterKind.NPC, current_health=health, maximum_health=180,
        lt=100, lg=200, altitude=10, merchant=False, shopkeeper=False, banker=False,
        trainer=False, minion=False,
    )


def _observation(
    now_ms: int,
    target: NativeTargetHealthObservation,
    *events: NativeCombatEvent,
    characters: tuple[NativeCharacterObservation, ...] | None = None,
    action_target: str | None = None,
) -> PvEObservation:
    if characters is None:
        characters = (() if not target.target_present else
                      (_character(target.target_token, target.current_health),))
    selected = target.target_token
    return PvEObservation(
        now_ms, target, _player(), events,
        player_action=NativePlayerActionObservation(
            phase=NativeTargetActionPhase.WINDUP if action_target else NativeTargetActionPhase.IDLE,
            targeting_selected=selected is not None and selected == action_target,
            motion_id=106 if action_target else 21, action_pending=False, impact_frame=None,
            action_sequence=1 if action_target else 0, motion_sequence=0,
            selected_target_token=selected, action_target_token=action_target,
            mode=2 if action_target else 1, action_state=2 if action_target else 1,
        ),
        population=NativeCharacterPopulationObservation(
            characters=characters, selected_target_token=selected,
            player_action_target_token=action_target, scan_generation=1, rejected_candidates=0,
            local_player_object_key=NativeObjectKey(1, 53),
        ),
    )


class SmartPvEClientReplayTests(unittest.TestCase):
    def test_automatic_engagement_requires_native_action_on_the_exact_selected_object(self) -> None:
        controller = PvEController(PvEControllerConfig(
            accept_automatic_targets=True, automatic_target_requires_active_action=True,
        ))
        poison = tuple(NativeCombatEvent(
            sequence=index, timestamp="now", kind=kind, message=kind.value,
            target_name="mob-1",
        ) for index, kind in enumerate((
            NativeCombatEventKind.PLAYER_HIT_TARGET,
            NativeCombatEventKind.TARGET_KILLED,
            NativeCombatEventKind.PLAYER_KILLED,
        )))
        ignored = controller.step(_observation(0, _target("mob-1"), *poison))
        self.assertIsNone(ignored.tracked_target)
        self.assertIsNone(ignored.intent)
        self.assertFalse(ignored.terminal)
        other_action = controller.step(_observation(100, _target("mob-1"), action_target="mob-2"))
        self.assertIsNone(other_action.tracked_target)
        busy = _observation(200, _target("mob-1"))
        busy = replace(busy, player_action=replace(
            busy.player_action, phase=NativeTargetActionPhase.QUEUED, action_pending=True,
        ))
        self.assertIsNone(controller.step(busy).tracked_target)
        confirmed = controller.step(_observation(300, _target("mob-1"), action_target="mob-1"))
        self.assertEqual("mob-1", confirmed.tracked_target.token)
        self.assertIsNone(confirmed.intent)  # Native autoattack already runs; no duplicated input.

    def test_replays_native_object_kill_cleanup_next_opener_and_stall_through_guard(self) -> None:
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
                automatic_target_requires_active_action=True,
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
            # Delayed text and another selected object do not kill the retained mob.
            _observation(450, _target("mob-2"), kill,
                         characters=(_character("mob-1", 160), _character("mob-2")),
                         action_target="mob-1"),
            _observation(500, _target("mob-1", 0)),
            _observation(1_500, _target("mob-1", 0)),
            _observation(1_600, _absent()),
            _observation(1_700, _absent()),
            _observation(1_800, _target("mob-2"), replacement_hit),
            _observation(2_050, _target("mob-2")),
            _observation(6_800, _target("mob-2")),
        )
        decisions = []
        for observation in observations:
            decision = controller.step(observation)
            decisions.append(decision)
            if decision.cleanup_request is not None:
                self.assertIsNone(decision.intent)
                controller.acknowledge_cleanup(PvECombatCleanupResult(
                    decision.cleanup_request, True,
                    request_key="00000000-0000-0000-0000-000000000001",
                ))
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
                HotkeyInvocation(("ctrl", "a")),
                KeyPressInvocation(";"),
                KeyPressInvocation("2"),
                HotkeyInvocation(("ctrl", "a")),
                HotkeyInvocation(("ctrl", "a")),
            ),
            backend.invocations,
        )
        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, decisions[0].intent)
        self.assertEqual(PvEIntent.CAST_SHADOW_TOUCH, decisions[1].intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, decisions[2].intent)
        self.assertIsNone(decisions[3].intent)
        self.assertIsNone(decisions[4].intent)
        self.assertEqual(0, decisions[4].kills)
        self.assertEqual("mob-1", decisions[4].tracked_target.token)
        self.assertEqual(1, decisions[5].kills)
        self.assertEqual("native_health_zero", decisions[5].kill_confirmation.value)
        self.assertEqual("mob-1", decisions[6].cleanup_request.target_token)
        self.assertIsNone(decisions[7].intent)
        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, decisions[8].intent)
        self.assertEqual(PvEIntent.CAST_SHADOW_TOUCH, decisions[9].intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, decisions[10].intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, decisions[11].intent)



if __name__ == "__main__":
    unittest.main()
