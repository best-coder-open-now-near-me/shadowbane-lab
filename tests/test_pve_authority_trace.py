import unittest

from shadowbane_lab.client_input import EventEmergencyStop
from shadowbane_lab.client_observation import (
    NativeCharacterObservation,
    NativeCharacterPopulationObservation,
    NativeCombatLogEntry,
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
    NativeTargetHealthObservation,
    NativeTargetIdentityObservation,
    NativeTargetPositionObservation,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.protocol import DispatchResult, Relation
from shadowbane_lab.pve import (
    PvEAuthorityRunTraceStep,
    PvEController,
    PvEControllerConfig,
    PvEIntent,
    PvEPhase,
    PvERunner,
    PvETargetAuthorityEvidence,
    PvETargetCharacterKind,
    StaticPvETargetAuthorityEvaluator,
)
from shadowbane_lab.pve.runtime import PvERunner as CanonicalPvERunner


def _absent_target() -> NativeTargetHealthObservation:
    return NativeTargetHealthObservation(target_present=False)


def _target(
    token: str,
    current_health: float = 10.0,
) -> NativeTargetHealthObservation:
    return NativeTargetHealthObservation(
        target_present=True,
        current_health=current_health,
        maximum_health=10.0,
        target_token=token,
    )


def _absent_identity() -> NativeTargetIdentityObservation:
    return NativeTargetIdentityObservation(target_present=False)


def _identity(token: str) -> NativeTargetIdentityObservation:
    return NativeTargetIdentityObservation(
        target_present=True,
        arc_character=True,
        merchant=False,
        shopkeeper=False,
        banker=False,
        trainer=False,
        minion=False,
        target_token=token,
    )


def _player() -> NativePlayerVitalsObservation:
    return NativePlayerVitalsObservation(
        current_health=100.0,
        maximum_health=100.0,
        current_mana=50.0,
        maximum_mana=50.0,
        current_stamina=100.0,
        maximum_stamina=100.0,
    )


def _player_position() -> NativePlayerPositionObservation:
    return NativePlayerPositionObservation(100.0, 200.0, 10.0)


def _target_position(token: str | None) -> NativeTargetPositionObservation:
    if token is None:
        return NativeTargetPositionObservation(target_present=False)
    return NativeTargetPositionObservation(
        target_present=True,
        lt=105.0,
        lg=200.0,
        altitude=10.0,
        target_token=token,
    )


def _character(token: str) -> NativeCharacterObservation:
    return NativeCharacterObservation(
        token=token,
        current_health=10.0,
        maximum_health=10.0,
        lt=105.0,
        lg=200.0,
        altitude=10.0,
        merchant=False,
        shopkeeper=False,
        banker=False,
        trainer=False,
        minion=False,
    )


def _authority(
    token: str,
    *,
    relation: Relation = Relation.ENEMY,
) -> PvETargetAuthorityEvidence:
    return PvETargetAuthorityEvidence(
        target_token=token,
        source_revision=7,
        target_object_key=NativeObjectKey(20, 7001),
        local_player_object_key=NativeObjectKey(10, 42),
        character_kind=PvETargetCharacterKind.NPC,
        relation=relation,
        same_party=False,
        friendly_owned=False,
        attackable=True,
        evidence_sources=(
            "native_object_identity",
            "native_character_kind",
            "native_relation_snapshot",
            "native_party_projection",
            "native_ownership_projection",
            "native_attackability",
        ),
    )


class SequenceHealthSource:
    def __init__(self, values: tuple[NativeTargetHealthObservation, ...]) -> None:
        self.values = list(values)

    def observe(self) -> NativeTargetHealthObservation:
        return self.values.pop(0)


class SequenceIdentitySource:
    def __init__(self, values: tuple[NativeTargetIdentityObservation, ...]) -> None:
        self.values = list(values)

    def observe(self) -> NativeTargetIdentityObservation:
        return self.values.pop(0)


class SequencePlayerPositionSource:
    def __init__(self, values: tuple[NativePlayerPositionObservation, ...]) -> None:
        self.values = list(values)

    def observe(self) -> NativePlayerPositionObservation:
        return self.values.pop(0)


class SequenceTargetPositionSource:
    def __init__(self, values: tuple[NativeTargetPositionObservation, ...]) -> None:
        self.values = list(values)

    def observe(self) -> NativeTargetPositionObservation:
        return self.values.pop(0)


class SequencePopulationSource:
    def __init__(self, values: tuple[NativeCharacterPopulationObservation, ...]) -> None:
        self.values = list(values)

    def observe(self) -> NativeCharacterPopulationObservation:
        return self.values.pop(0)


class ConstantVitalsSource:
    def observe(self) -> NativePlayerVitalsObservation:
        return _player()


class EmptyCombatLogSource:
    def read_new_entries(self) -> tuple[NativeCombatLogEntry, ...]:
        return ()


class RecordingDispatcher:
    def __init__(self) -> None:
        self.intents: list[PvEIntent] = []

    def dispatch(self, intent: PvEIntent, *, sequence: int) -> DispatchResult:
        self.intents.append(intent)
        return DispatchResult(
            adapter_name="authority-trace-test",
            correlation_id=f"authority-trace:{sequence}",
            accepted=True,
        )


class AdvancingClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class PvETargetAuthorityTraceTests(unittest.TestCase):
    def test_verified_authority_is_persisted_on_the_attack_trace_step(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                maximum_kills=1,
                require_target_identity=True,
                acquisition_retry_ms=100,
                target_sample_interval_ms=100,
                acquisition_timeout_ms=1_000,
            ),
            target_authority_evaluator=StaticPvETargetAuthorityEvaluator(
                (_authority("mob"),)
            ),
            require_verified_target_authority=True,
        )
        dispatcher = RecordingDispatcher()
        clock = AdvancingClock()
        runner = PvERunner(
            controller=controller,
            health_reader=SequenceHealthSource(
                (_absent_target(), _target("mob"), _target("mob", 0.0))
            ),
            player_vitals_reader=ConstantVitalsSource(),
            target_identity_reader=SequenceIdentitySource(
                (_absent_identity(), _identity("mob"), _identity("mob"))
            ),
            combat_log_reader=EmptyCombatLogSource(),
            dispatcher=dispatcher,
            stop_signal=EventEmergencyStop(),
            poll_interval_ms=100,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertIs(CanonicalPvERunner.run, PvERunner.run)
        self.assertEqual(PvEPhase.COMPLETE, result.final_phase)
        self.assertEqual(1, result.kills)
        self.assertEqual(
            [PvEIntent.ACQUIRE_NEXT_MOB, PvEIntent.ATTACK_SELECTED_TARGET],
            dispatcher.intents,
        )
        attack_step = result.trace[1]
        self.assertIsInstance(attack_step, PvEAuthorityRunTraceStep)
        payload = attack_step.as_dict()
        authority = payload["target_authority"]
        assert isinstance(authority, dict)
        self.assertTrue(authority["accepted"])
        self.assertEqual("verified_hostile_npc", authority["summary_reason"])
        self.assertEqual("enemy", authority["relation"])
        self.assertEqual([], authority["exclusions"])
        self.assertEqual([], payload["target_rejections"])

    def test_population_quarantine_persists_authority_exclusions(self) -> None:
        selected_population = NativeCharacterPopulationObservation(
            characters=(_character("mob"),),
            selected_target_token="mob",
            player_action_target_token=None,
            scan_generation=9,
            rejected_candidates=0,
        )
        empty_population = NativeCharacterPopulationObservation(
            characters=(),
            selected_target_token=None,
            player_action_target_token=None,
            scan_generation=9,
            rejected_candidates=0,
        )
        controller = PvEController(
            PvEControllerConfig(
                require_target_identity=True,
                use_native_population=True,
                acquisition_retry_ms=100,
                stale_selection_cycle_delay_ms=100,
                target_sample_interval_ms=100,
                acquisition_timeout_ms=100,
            ),
            target_authority_evaluator=StaticPvETargetAuthorityEvaluator(
                (_authority("mob", relation=Relation.NEUTRAL),)
            ),
            require_verified_target_authority=True,
        )
        dispatcher = RecordingDispatcher()
        clock = AdvancingClock()
        runner = PvERunner(
            controller=controller,
            health_reader=SequenceHealthSource((_target("mob"), _absent_target())),
            player_vitals_reader=ConstantVitalsSource(),
            player_position_reader=SequencePlayerPositionSource(
                (_player_position(), _player_position())
            ),
            target_position_reader=SequenceTargetPositionSource(
                (_target_position("mob"), _target_position(None))
            ),
            target_identity_reader=SequenceIdentitySource(
                (_identity("mob"), _absent_identity())
            ),
            population_reader=SequencePopulationSource(
                (selected_population, empty_population)
            ),
            combat_log_reader=EmptyCombatLogSource(),
            dispatcher=dispatcher,
            stop_signal=EventEmergencyStop(),
            poll_interval_ms=100,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual(PvEPhase.STOPPED, result.final_phase)
        self.assertEqual("mob_acquisition_timeout", result.terminal_reason)
        self.assertEqual([], dispatcher.intents)
        rejection_step = result.trace[0]
        self.assertIsInstance(rejection_step, PvEAuthorityRunTraceStep)
        payload = rejection_step.as_dict()
        authority = payload["target_authority"]
        assert isinstance(authority, dict)
        self.assertFalse(authority["accepted"])
        self.assertIn("relation_not_enemy", authority["exclusions"])
        rejections = payload["target_rejections"]
        assert isinstance(rejections, list)
        self.assertEqual(1, len(rejections))
        self.assertEqual("target_authority_rejected", rejections[0]["reason"])
        self.assertIn(
            "relation_not_enemy",
            rejections[0]["authority_exclusions"],
        )


if __name__ == "__main__":
    unittest.main()
