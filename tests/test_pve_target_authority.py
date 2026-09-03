import unittest

from shadowbane_lab.client_observation import (
    NativeCharacterObservation,
    NativeCharacterPopulationObservation,
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
    NativeTargetHealthObservation,
    NativeTargetIdentityObservation,
    NativeTargetPositionObservation,
)
from shadowbane_lab.pve import (
    PvEController,
    PvEControllerConfig,
    PvEIntent,
    PvEObservation,
    PvEPhase,
    PvETargetRejectionReason,
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
                use_native_population=True,
                require_target_identity=True,
                acquisition_retry_ms=100,
                acquisition_timeout_ms=1_000,
                target_sample_interval_ms=100,
                continuous=continuous,
                camp_radius=50.0 if continuous else None,
            )
        )

    def test_selected_candidate_without_target_snapshot_is_quarantined_after_bound(self) -> None:
        controller = self._controller()
        mob = _character("mob", lt=105.0)

        waiting = controller.step(
            _observation(
                0,
                selected="mob",
                target_token=None,
                characters=(mob,),
            )
        )
        still_waiting = controller.step(
            _observation(
                299,
                selected="mob",
                target_token=None,
                characters=(mob,),
            )
        )
        rejected = controller.step(
            _observation(
                300,
                selected="mob",
                target_token=None,
                characters=(mob,),
            )
        )
        stopped = controller.step(
            _observation(
                1_000,
                selected="mob",
                target_token=None,
                characters=(mob,),
            )
        )

        self.assertEqual(300, controller.candidate_validation_timeout_ms)
        self.assertIsNone(waiting.intent)
        self.assertIsNone(still_waiting.intent)
        self.assertIsNone(rejected.intent)
        self.assertEqual(PvEPhase.SEEKING, rejected.phase)
        self.assertEqual(PvEPhase.STOPPED, stopped.phase)
        self.assertEqual("mob_acquisition_timeout", stopped.terminal_reason)
        self.assertEqual(1, len(controller.target_rejections))
        rejection = controller.target_rejections[0]
        self.assertEqual("mob", rejection.target_token)
        self.assertEqual(
            PvETargetRejectionReason.TARGET_SNAPSHOT_UNAVAILABLE,
            rejection.reason,
        )
        self.assertEqual(300, rejection.validation_wait_ms)

    def test_dead_selected_candidate_is_rejected_and_next_candidate_is_requested(self) -> None:
        controller = self._controller()
        first = _character("first", lt=105.0)
        second = _character("second", lt=110.0)

        decision = controller.step(
            _observation(
                0,
                selected="first",
                target_token="first",
                target_health=0.0,
                characters=(first, second),
            )
        )

        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, decision.intent)
        self.assertEqual("second", decision.acquisition_target_token)
        self.assertEqual(
            PvETargetRejectionReason.TARGET_DEAD,
            controller.target_rejections[-1].reason,
        )

    def test_selected_candidate_with_protected_identity_is_rejected_immediately(self) -> None:
        controller = self._controller()
        first = _character("first", lt=105.0)
        second = _character("second", lt=110.0)

        decision = controller.step(
            _observation(
                0,
                selected="first",
                target_token="first",
                trainer=True,
                characters=(first, second),
            )
        )

        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, decision.intent)
        self.assertEqual("second", decision.acquisition_target_token)
        self.assertEqual(
            PvETargetRejectionReason.TARGET_NOT_ATTACK_ELIGIBLE,
            controller.target_rejections[-1].reason,
        )

    def test_unavailable_identity_is_quarantined_without_attack_input(self) -> None:
        controller = self._controller()
        first = _character("first", lt=105.0)
        second = _character("second", lt=110.0)

        decision = controller.step(
            _observation(
                0,
                selected="first",
                target_token="first",
                identity_available=False,
                characters=(first, second),
            )
        )

        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, decision.intent)
        self.assertEqual("second", decision.acquisition_target_token)
        self.assertNotEqual(PvEIntent.ATTACK_SELECTED_TARGET, decision.intent)
        self.assertEqual(
            PvETargetRejectionReason.TARGET_IDENTITY_UNAVAILABLE,
            controller.target_rejections[-1].reason,
        )

    def test_transient_missing_snapshot_recovers_before_validation_deadline(self) -> None:
        controller = self._controller()
        mob = _character("mob", lt=105.0)

        waiting = controller.step(
            _observation(
                0,
                selected="mob",
                target_token=None,
                characters=(mob,),
            )
        )
        engaged = controller.step(
            _observation(
                200,
                selected="mob",
                target_token="mob",
                characters=(mob,),
            )
        )

        self.assertIsNone(waiting.intent)
        self.assertEqual(PvEPhase.ENGAGED, engaged.phase)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, engaged.intent)
        self.assertEqual((), controller.target_rejections)

    def test_continuous_missing_snapshot_enters_camp_idle_after_quarantine(self) -> None:
        controller = self._controller(continuous=True)
        mob = _character("mob", lt=105.0)

        controller.step(
            _observation(
                0,
                selected="mob",
                target_token=None,
                characters=(mob,),
            )
        )
        decision = controller.step(
            _observation(
                300,
                selected="mob",
                target_token=None,
                characters=(mob,),
            )
        )

        self.assertEqual(PvEPhase.CAMP_IDLE, decision.phase)
        self.assertFalse(decision.terminal)
        self.assertEqual(
            PvETargetRejectionReason.TARGET_SNAPSHOT_UNAVAILABLE,
            controller.target_rejections[-1].reason,
        )

    def test_wrapped_target_cycle_records_reason_and_advances_candidate(self) -> None:
        controller = self._controller()
        first = _character("first", lt=105.0)
        second = _character("second", lt=110.0)
        characters = (first, second)

        controller.step(
            _observation(
                0,
                selected=None,
                target_token=None,
                characters=characters,
            )
        )
        controller.step(
            _observation(
                100,
                selected="second",
                target_token="second",
                characters=characters,
            )
        )
        decision = controller.step(
            _observation(
                200,
                selected=None,
                target_token=None,
                characters=characters,
            )
        )

        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, decision.intent)
        self.assertEqual("second", decision.acquisition_target_token)
        rejection = controller.target_rejections[-1]
        self.assertEqual("first", rejection.target_token)
        self.assertEqual(
            PvETargetRejectionReason.TARGET_CYCLE_WRAPPED,
            rejection.reason,
        )
        self.assertEqual("target_cycle_wrapped", rejection.as_dict()["reason"])


if __name__ == "__main__":
    unittest.main()
