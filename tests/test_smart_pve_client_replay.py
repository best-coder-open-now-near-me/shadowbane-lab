import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

from test_combat_wire_v2 import command as wire_command
from test_native_combat_coordinator import answer

from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.cleanup_settlement import CleanupSettlement
from shadowbane_lab.client_extension.combat_fence_v3 import Authority, Ordinals
from shadowbane_lab.client_extension.combat_wire_v2 import (
    Action,
    ClosureProof,
    Outcome,
    Phase,
    Verb,
)
from shadowbane_lab.client_extension.movement_session import NativeMovementGrant
from shadowbane_lab.client_observation import (
    NativeCharacterKind,
    NativeCharacterObservation,
    NativeCharacterPopulationObservation,
    NativeCombatEvent,
    NativeCombatEventKind,
    NativePlayerActionObservation,
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
    NativeTargetHealthObservation,
    NativeTargetPositionObservation,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.pve import (
    PvEController,
    PvEControllerConfig,
    PvEIntent,
    PvEObservation,
)
from shadowbane_lab.pve.attack_list import AttackListOwner
from shadowbane_lab.pve.model import PvECombatKind
from shadowbane_lab.pve.native_combat import NativeCombatCoordinator


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
        player_position=NativePlayerPositionObservation(100, 200, 10),
        target_position=(NativeTargetPositionObservation(True, 100, 200, 10, selected)
                         if selected else NativeTargetPositionObservation(False)),
        player_action=NativePlayerActionObservation(
            targeting_selected=selected is not None and selected == action_target,
            motion_id=106 if action_target else 21,
            animation_event_index=1 if action_target else 0,
            animation_frame=None,
            selected_target_token=selected,
            action_target_token=action_target,
            initiation_state=5,
            power_protocol_ids=(),
            mode=2 if action_target else 1,
            action_state=2 if action_target else 1,
        ),
        population=NativeCharacterPopulationObservation(
            characters=characters, selected_target_token=selected,
            player_action_target_token=action_target, scan_generation=1, rejected_candidates=0,
            local_player_object_key=NativeObjectKey(1, 53),
        ),
    )


class SmartPvEClientReplayTests(unittest.TestCase):
    def test_action_adoption_uses_native_object_not_selection(self) -> None:
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
        busy_unknown = _observation(0, _target("mob-1"), *poison)
        busy_unknown = replace(busy_unknown, player_action=replace(
            busy_unknown.player_action, initiation_state=None, power_protocol_ids=None))
        ignored = controller.step(busy_unknown)
        self.assertIsNone(ignored.tracked_target)
        self.assertIsNone(ignored.intent)
        self.assertFalse(ignored.terminal)
        other_action = controller.step(_observation(100, _target("mob-1"), action_target="mob-2"))
        self.assertIsNone(other_action.tracked_target)
        busy = _observation(200, _target("mob-1"))
        busy = replace(busy, player_action=replace(
            busy.player_action, initiation_state=6, power_protocol_ids=(),
        ))
        self.assertIsNone(controller.step(busy).tracked_target)
        confirmed = controller.step(_observation(300, _target("mob-2"),
            characters=(_character("mob-1"), _character("mob-2")), action_target="mob-1"))
        self.assertEqual("mob-1", confirmed.tracked_target.token)
        self.assertIsNone(confirmed.intent)
        self.assertIs(confirmed.combat_proposal.kind, PvECombatKind.BIND)
        self.assertTrue(confirmed.combat_proposal.adopted_existing_action)

    def test_replays_native_kill_cleanup_next_opener_and_stall_through_coordinator(self) -> None:
        command = wire_command(Authority.NPC)
        session = Mock()
        session.cleanup = CleanupSettlement()
        session.combat_ordinals.return_value = Ordinals()
        grant = NativeMovementGrant(NativeClientProcessIdentity(
            command.binding.client_pid, command.binding.client_creation),
            command.window, command.grant, command.host, "replay")
        population = Mock()
        population.resolve_combat_addresses.side_effect = lambda **kw: (
            0x12300000, 0x12400000 + kw["target_key"].object_type * 256)
        identity = Mock()
        identity.binding = SimpleNamespace(object_key=NativeObjectKey(1, 53),
            identity=SimpleNamespace(character_name="Local", server_name="Server"))
        commands = []

        def respond(owned, verb, submitted):
            self.assertIs(owned, grant)
            submitted.require_verb(verb)
            submitted.encode()
            commands.append((verb, submitted))
            receipt = answer(submitted, verb, **({
                "outcome": Outcome.ENGAGEMENT_CLOSED, "phase": Phase.CLOSED,
                "closure": ClosureProof.NATIVE_STOPPED, "queued": False,
            } if verb is Verb.STOP_ENGAGEMENT else {}))
            return SimpleNamespace(receipt=receipt, native_detail="replay:correlated")

        session.combat.side_effect = respond
        coordinator = NativeCombatCoordinator(session=session, grant=grant, population=population,
            character_session=identity,
            store=SimpleNamespace(owner=AttackListOwner("Server", "Local")))
        # Only the OS ticket is replaced. The real coordinator builds complete
        # bindings/commands and verifies correlated receipts and cleanup proof.
        ticket_factory = patch("shadowbane_lab.client_extension.combat_fence_windows.Ticket")
        tickets = ticket_factory.start()
        self.addCleanup(ticket_factory.stop)
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
                self.assertIsNone(decision.combat_proposal)
                cleanup = coordinator.cleanup(decision.cleanup_request)
                self.assertTrue(cleanup.confirmed)
                controller.acknowledge_cleanup(cleanup)
            if decision.combat_proposal is not None:
                update = coordinator.advance(decision.combat_proposal, observation)
                controller.acknowledge_combat(decision.combat_proposal,
                    update.acknowledgement, now_ms=observation.now_ms)
                self.assertTrue(update.receipt.flags & 2)

        submitted = [command for verb, command in commands if verb is Verb.SUBMIT]
        self.assertEqual([Action.CAST, Action.ATTACK, Action.CAST, Action.ATTACK],
                         [command.action for command in submitted])
        self.assertEqual(submitted[0].binding, submitted[1].binding)
        self.assertEqual(submitted[2].binding, submitted[3].binding)
        self.assertNotEqual(submitted[0].binding.engagement, submitted[2].binding.engagement)
        self.assertEqual([101, 101, 102, 102],
                         [command.binding.target_key[0] for command in submitted])
        self.assertEqual(2, tickets.call_count)
        self.assertEqual([Verb.SUBMIT, Verb.SUBMIT, Verb.STOP_ENGAGEMENT,
                          Verb.SUBMIT, Verb.SUBMIT, Verb.STOP_ENGAGEMENT], [v for v, _ in commands])
        session.pause.assert_not_called()
        self.assertIsNone(decisions[0].combat_proposal)
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
        self.assertIsNone(decisions[8].combat_proposal)
        self.assertEqual(PvEIntent.CAST_SHADOW_TOUCH, decisions[9].intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, decisions[10].intent)
        self.assertIsNone(decisions[11].combat_proposal)
        self.assertEqual("mob-2", decisions[11].cleanup_request.target_token)



if __name__ == "__main__":
    unittest.main()
