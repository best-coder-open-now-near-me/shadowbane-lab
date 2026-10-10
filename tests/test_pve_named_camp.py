"""Named native admission stays separate from navigation and target ownership."""
from dataclasses import replace

import pytest
from test_pve_controller import (
    ConfirmedCleanup,
    _absent,
    _accepted_step,
    _character,
    _observation,
    _player_position,
    _population,
    _target_position,
)

from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.client_observation.native_population import NativeCharacterKind
from shadowbane_lab.client_observation.native_zone import NativeZoneGeometry, NativeZoneIdentity
from shadowbane_lab.pve import PvEController, PvEControllerConfig, PvEPhase


def zone(key=578, name="Connauch Henge"):
    return NativeZoneIdentity(0, name, 0, 528, key, 79, NativeZoneGeometry(
        -128, -128, 128, 128, 1, 0, 0, 0, 500, -200, 0, 0, 128, 128))


def npc(token="first", *, lt=500, named_zone=None):
    return replace(_character(token, lt=lt), named_zone=named_zone)


def frame(now, *characters, position=(100, 200)):
    return _observation(now, _absent(), population=_population(None, *characters),
                        player_position=_player_position(*position),
                        target_position=_target_position(None))


def control(**kwargs):
    return PvEController(PvEControllerConfig(named_camp=True, continuous=True,
        camp_idle_ms=1, **kwargs))


def finish(control, character, now):
    dead = replace(character, current_health=0)
    killed = control.step(frame(now, dead))
    assert killed.kills >= 1
    cleanup = control.step(frame(now + 1000, dead)).cleanup_request
    assert cleanup is not None
    control.acknowledge_cleanup(ConfirmedCleanup().cleanup(cleanup))
    control.step(frame(now + 1001, dead))


def test_nearest_named_npc_establishes_camp_from_parent_area_beyond_old_radius():
    first = npc(named_zone=zone())
    controller = control()
    decision = _accepted_step(controller, frame(0, first,
        npc("farther", lt=550, named_zone=zone(579))))
    assert decision.combat_proposal.target_key == first.object_key
    assert controller.camp.native_zone == zone()
    assert controller.camp.anchor_lt == 100
    assert abs(first.lt - controller.camp.anchor_lt) > 120
    assert controller.camp.matches_character(first)
    assert controller.camp.as_dict()["native_zone"]["object_key"] == [578, 79]
    assert controller.camp.as_dict()["radius_role"] == "navigation_envelope"


def test_capture_ignores_protected_unknown_and_dead_candidates():
    good = npc("good", lt=550, named_zone=zone())
    controller = control()
    decision = _accepted_step(controller, frame(0,
        npc("unknown", lt=101),
        replace(npc("trainer", lt=102, named_zone=zone(2)), trainer=True),
        replace(npc("dead", lt=103, named_zone=zone(3)), current_health=0), good))
    assert controller.camp.native_zone == zone()
    assert decision.combat_proposal.target_key == good.object_key


def test_waiting_for_qualified_camp_preserves_start_anchor_without_unbounded_admission():
    controller = control()
    first = controller.step(frame(0, npc(lt=101)))
    assert first.combat_proposal is None and controller.camp is None
    assert not controller.can_start_external_combat(frame(1))
    second = _accepted_step(controller, frame(100,
        npc(named_zone=zone()), position=(300, 200)))
    assert second.return_to_camp and second.combat_proposal is None
    assert controller.camp.anchor_lt == 100
    returned = _accepted_step(controller, frame(101, npc(named_zone=zone())))
    assert returned.combat_proposal is not None


def test_empty_camp_never_switches_to_same_named_other_instance():
    first = npc(named_zone=zone())
    controller = control()
    _accepted_step(controller, frame(0, first))
    original = controller.camp
    finish(controller, first, 100)
    other = npc("other", lt=101, named_zone=zone(579))
    for now in (1200, 1300, 15000):
        decision = controller.step(frame(now, other))
        assert decision.combat_proposal is None
        assert controller.camp == original
    respawn = npc("respawn", lt=700, named_zone=zone())
    admitted = _accepted_step(controller, frame(15002, respawn, other))
    assert admitted.combat_proposal.target_key == respawn.object_key


@pytest.mark.parametrize("new_zone", [None, zone(579)])
def test_exact_admitted_pull_survives_zone_change_but_not_object_replacement(new_zone):
    first = npc(named_zone=zone())
    controller = control()
    _accepted_step(controller, frame(0, first))
    pulled = replace(first, named_zone=new_zone, lt=1000, current_health=9)
    decision = controller.step(frame(100, pulled))
    assert decision.phase is PvEPhase.ENGAGED and decision.cleanup_request is None
    assert controller.input_target.object_key == first.object_key
    replacement = replace(pulled, object_key=NativeObjectKey(999, 37))
    first_missing = controller.step(frame(1000, replacement))
    assert first_missing.combat_proposal is None
    assert controller.input_target.object_key == first.object_key
    assert controller.step(frame(1750, replacement)).cleanup_request is not None


def test_pull_does_not_bypass_new_protected_role():
    first = npc(named_zone=zone())
    controller = control()
    _accepted_step(controller, frame(0, first))
    decision = controller.step(frame(100, replace(first, trainer=True)))
    assert decision.cleanup_request is not None


def test_navigation_envelope_never_grants_listed_player_membership():
    controller = control()
    controller.step(frame(0, npc(named_zone=zone())))
    assert controller.camp.radius > 120
    assert controller.camp.contains(220, 200)
    assert not controller.camp.contains(221, 200)
    assert controller.camp.listed_target_radius == 120
    player = replace(npc(), character_kind=NativeCharacterKind.PLAYER)
    assert not controller.camp.matches_character(player)


def test_finite_named_run_waits_for_zone_without_using_radius_or_acquisition_timeout():
    controller = PvEController(PvEControllerConfig(named_camp=True,
        acquisition_timeout_ms=1000, maximum_session_ms=5000, camp_idle_ms=1))
    for now in (0, 1001, 3000):
        assert controller.step(frame(now, npc())).combat_proposal is None
        assert not controller.terminal
    assert controller.step(frame(5000)).terminal_reason == "maximum_session_elapsed"


def test_manual_radius_still_uses_position_and_original_return_anchor():
    controller = PvEController(PvEControllerConfig(continuous=True, camp_radius=120))
    inside = npc("inside", lt=200)
    result = controller.step(frame(0, npc(named_zone=zone()), inside))
    assert result.combat_proposal.target_key == inside.object_key
    assert controller.camp.native_zone is None
    assert controller.camp.contains(200, 200)
    assert not controller.camp.contains(500, 200)


@pytest.mark.parametrize("kwargs", [{"named_camp": 1},
    {"named_camp": True, "camp_radius": 120}])
def test_config_rejects_ambiguous_or_untyped_camp_mode(kwargs):
    with pytest.raises(ValueError):
        PvEControllerConfig(**kwargs)


@pytest.mark.parametrize("new_zone", [None, zone(579)])
def test_pending_immutable_action_survives_pull_without_fabricated_acknowledgment(new_zone):
    first = npc(named_zone=zone())
    controller = control()
    initial = controller.step(frame(0, first))
    pending = initial.combat_proposal
    assert pending is not None
    later = controller.step(frame(100, replace(first, named_zone=new_zone)))
    assert later.cleanup_request is None
    assert controller.pending_combat_proposal == pending
    assert later.native_action_pending


def test_named_zone_identity_does_not_depend_on_template_or_display_name():
    controller = control()
    first = npc(named_zone=zone())
    controller.step(frame(0, first))
    assert controller.camp.matches_character(npc("same-instance",
        named_zone=replace(zone(), name="Changed label", template_id=999)))
    assert not controller.camp.matches_character(npc("different-instance",
        named_zone=zone(579)))
