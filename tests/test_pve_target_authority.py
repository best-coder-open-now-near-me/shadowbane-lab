import unittest
from dataclasses import replace

from shadowbane_lab.client_observation import (
    NativeCharacterObservation,
    NativeCharacterPopulationObservation,
    NativePlayerActionObservation,
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
    NativeTargetActionPhase,
    NativeTargetHealthObservation,
    NativeTargetIdentityObservation,
    NativeTargetPositionObservation,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.client_observation.native_population import NativeCharacterKind
from shadowbane_lab.pve import (
    PvEController,
    PvEControllerConfig,
    PvEIntent,
    PvEObservation,
    PvEPhase,
)


def _player() -> NativePlayerVitalsObservation:
    return NativePlayerVitalsObservation(100.0, 100.0, 50.0, 50.0, 100.0, 100.0)


def _player_position() -> NativePlayerPositionObservation:
    return NativePlayerPositionObservation(100.0, 200.0, 10.0)


def _target(token: str | None, *, health: float = 10.0) -> NativeTargetHealthObservation:
    if token is None:
        return NativeTargetHealthObservation(target_present=False)
    return NativeTargetHealthObservation(
        target_present=True,
        current_health=health,
        maximum_health=10.0,
        target_token=token,
    )


def _target_position(token: str | None, *, lt: float = 105.0) -> NativeTargetPositionObservation:
    if token is None:
        return NativeTargetPositionObservation(target_present=False)
    return NativeTargetPositionObservation(
        target_present=True,
        lt=lt,
        lg=200.0,
        altitude=10.0,
        target_token=token,
    )


def _identity(
    token: str | None,
    *,
    trainer: bool = False,
    available: bool = True,
) -> NativeTargetIdentityObservation:
    if token is None:
        return NativeTargetIdentityObservation(target_present=False)
    if not available:
        return NativeTargetIdentityObservation.unavailable(
            target_token=token,
            error="test identity unavailable",
        )
    return NativeTargetIdentityObservation(
        target_present=True,
        arc_character=True,
        merchant=False,
        shopkeeper=False,
        banker=False,
        trainer=trainer,
        minion=False,
        target_token=token,
    )


def _character(token: str, *, lt: float) -> NativeCharacterObservation:
    return NativeCharacterObservation(
        token=token,
        object_key=NativeObjectKey(20, {"mob": 1, "first": 2, "second": 3}[token]),
        character_kind=NativeCharacterKind.NPC,
        current_health=10.0,
        maximum_health=10.0,
        lt=lt,
        lg=200.0,
        altitude=10.0,
        merchant=False,
        shopkeeper=False,
        banker=False,
        trainer=False,
        minion=False,
    )


def _observation(
    now_ms: int,
    *,
    selected: str | None,
    target_token: str | None,
    characters: tuple[NativeCharacterObservation, ...],
    target_health: float = 10.0,
    trainer: bool = False,
    identity_available: bool = True,
) -> PvEObservation:
    return PvEObservation(
        now_ms=now_ms,
        target=_target(target_token, health=target_health),
        player_action=NativePlayerActionObservation(
            NativeTargetActionPhase.IDLE, False, 21, False, None, 0, 0,
            selected_target_token=selected, action_target_token=None,
            mode=1, action_state=1,
        ),
        player=_player(),
        player_position=_player_position(),
        target_position=_target_position(target_token),
        target_identity=_identity(
            target_token,
            trainer=trainer,
            available=identity_available,
        ),
        population=NativeCharacterPopulationObservation(
            characters=characters,
            selected_target_token=selected,
            player_action_target_token=None,
            scan_generation=7,
            rejected_candidates=0,
        ),
    )


class PvETargetAuthorityTests(unittest.TestCase):
    def _controller(self, *, continuous: bool = False) -> PvEController:
        return PvEController(
            PvEControllerConfig(
                require_target_identity=True,
                acquisition_retry_ms=100,
                acquisition_timeout_ms=1_000,
                target_sample_interval_ms=100,
                continuous=continuous,
                camp_radius=50.0 if continuous else None,
            )
        )

    def test_unselected_current_object_requires_no_selected_snapshot(self):
        controller = self._controller()
        decision = controller.step(_observation(0, selected=None, target_token=None,
            characters=(_character("mob", lt=105),)))
        self.assertEqual("mob", decision.combat_proposal.target_token)
        self.assertEqual(PvEPhase.ENGAGED, decision.phase)

    def test_dead_population_object_is_skipped_for_next_ranked_candidate(self):
        first = replace(_character("first", lt=101), current_health=0)
        second = _character("second", lt=110)
        decision = self._controller().step(_observation(0, selected=None, target_token=None,
            characters=(first, second)))
        self.assertEqual(second.object_key, decision.combat_proposal.target_key)

    def test_current_protected_role_overrides_unprotected_selected_identity(self):
        first = replace(_character("first", lt=101), trainer=True)
        second = _character("second", lt=110)
        decision = self._controller().step(_observation(0, selected="first", target_token="first",
            characters=(first, second)))
        self.assertEqual(second.object_key, decision.combat_proposal.target_key)

    def test_unavailable_selected_identity_does_not_discard_current_object(self):
        decision = self._controller().step(_observation(0, selected="mob", target_token="mob",
            identity_available=False, characters=(_character("mob", lt=105),)))
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, decision.intent)
        self.assertEqual("mob", decision.combat_proposal.target_token)

    def test_missing_population_key_cannot_create_native_authority(self):
        mob = replace(_character("mob", lt=105), object_key=None)
        decision = self._controller().step(_observation(0, selected="mob", target_token="mob",
            characters=(mob,)))
        self.assertIsNone(decision.combat_proposal)
        self.assertEqual(PvEPhase.SEEKING, decision.phase)

    def test_continuous_empty_population_enters_camp_idle_without_input(self):
        decision = self._controller(continuous=True).step(_observation(
            0, selected=None, target_token=None, characters=()))
        self.assertEqual(PvEPhase.CAMP_IDLE, decision.phase)
        self.assertIsNone(decision.combat_proposal)
        self.assertIsNone(decision.intent)

    def test_selected_cycle_cannot_replace_unacknowledged_object_proposal(self):
        first, second = _character("first", lt=101), _character("second", lt=110)
        controller = self._controller()
        original = controller.step(_observation(0, selected="second", target_token="second",
            characters=(first, second))).combat_proposal
        next_frame = controller.step(_observation(100, selected=None, target_token=None,
            characters=(first, second)))
        self.assertIsNone(next_frame.combat_proposal)
        self.assertEqual(original, controller.pending_combat_proposal)
        self.assertEqual(first.object_key, original.target_key)


if __name__ == "__main__":
    unittest.main()
