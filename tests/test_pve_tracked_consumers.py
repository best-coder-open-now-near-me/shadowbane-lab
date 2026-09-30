"""Selection-independent approach and authority use the current bound object."""

from dataclasses import replace

import pytest

from shadowbane_lab.client_observation import (
    NativePlayerActionObservation,
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
    NativeTargetActionPhase,
    NativeTargetHealthObservation,
    NativeTargetPositionObservation,
)
from shadowbane_lab.client_observation.native_object import (
    NativeEntityBinding,
    NativeEntityIdentityMap,
    NativeObjectKey,
)
from shadowbane_lab.client_observation.native_population import (
    NativeCharacterKind,
    NativeCharacterObservation,
    NativeCharacterPopulationObservation,
)
from shadowbane_lab.protocol import Relation
from shadowbane_lab.pve.approach import PvEApproachConfig, PvEApproachController
from shadowbane_lab.pve.authority import (
    PvETargetAuthorityEvidence,
    PvETargetAuthorityExclusion,
    PvETargetCharacterKind,
    StaticPvETargetAuthorityEvaluator,
)
from shadowbane_lab.pve.authority_snapshot import (
    PvEAuthorityCharacterRecord,
    PvETargetAuthoritySnapshot,
    SnapshotPvETargetAuthorityEvaluator,
)
from shadowbane_lab.pve.model import PvEControllerConfig, PvEObservation, PvEPhase, PvETrackedTarget
from shadowbane_lab.pve.target_authority import PvEController
from shadowbane_lab.sim.affiliations import (
    AffiliationSnapshot,
    GroupKey,
    GroupKind,
    GroupMembership,
    legacy_team_affiliations,
)

ACTOR = NativeObjectKey(10, 1)
BOUND = NativeObjectKey(20, 2)


def character(**changes):
    value = NativeCharacterObservation(
        token="bound",
        object_key=BOUND,
        character_kind=NativeCharacterKind.NPC,
        current_health=10,
        maximum_health=10,
        lt=200,
        lg=200,
        altitude=10,
        merchant=False,
        shopkeeper=False,
        banker=False,
        trainer=False,
        minion=False,
    )
    return replace(value, **changes)


def observation(now=0, selected=None, characters=None):
    chars = (character(),) if characters is None else characters
    return PvEObservation(
        now_ms=now,
        target=NativeTargetHealthObservation(target_present=False)
        if selected is None
        else NativeTargetHealthObservation(True, 10, 10, selected),
        player=NativePlayerVitalsObservation(100, 100, 100, 100, 100, 100),
        player_action=NativePlayerActionObservation(
            NativeTargetActionPhase.IDLE,
            False,
            0,
            False,
            None,
            0,
            0,
            selected,
            None,
            mode=1,
            action_state=1,
        ),
        player_position=NativePlayerPositionObservation(100, 200, 10),
        target_position=NativeTargetPositionObservation(target_present=False)
        if selected is None
        else NativeTargetPositionObservation(True, 0, 200, 10, selected),
        population=NativeCharacterPopulationObservation(
            characters=chars,
            selected_target_token=selected,
            player_action_target_token=None,
            scan_generation=1,
            rejected_candidates=0,
            local_player_object_key=ACTOR,
        ),
    )


def tracked(value=None):
    return PvETrackedTarget("bound", BOUND, character() if value is None else value)


def evidence(**changes):
    return replace(
        PvETargetAuthorityEvidence(
            target_token="bound",
            source_revision=1,
            target_object_key=BOUND,
            local_player_object_key=ACTOR,
            character_kind=PvETargetCharacterKind.NPC,
            relation=Relation.ENEMY,
            same_party=False,
            friendly_owned=False,
            attackable=True,
            evidence_sources=("native_keyed_character",),
        ),
        **changes,
    )


def snapshot(*, key=BOUND, party=False):
    affiliations = legacy_team_affiliations({"actor": "players", "target": "monsters"}, revision=1)
    if party:
        group = GroupKey(GroupKind.PARTY, "party")
        affiliations = AffiliationSnapshot(
            revision=1,
            memberships=(
                *affiliations.memberships,
                GroupMembership("actor", group),
                GroupMembership("target", group),
            ),
            relation_overrides=affiliations.relation_overrides,
        )
    return PvETargetAuthoritySnapshot(
        revision=1,
        local_player_object_key=ACTOR,
        identities=NativeEntityIdentityMap(
            (NativeEntityBinding(ACTOR, "actor"), NativeEntityBinding(key, "target"))
        ),
        affiliations=affiliations,
        characters=(
            PvEAuthorityCharacterRecord(
                "bound", key, PvETargetCharacterKind.NPC, True, ("native_object",)
            ),
        ),
        party_complete=True,
        ownership_complete=True,
        relation_complete=True,
        evidence_sources=("native_snapshot",),
    )


@pytest.mark.parametrize("selected", [None, "other"])
def test_approach_tracks_bound_object_when_selection_changes(selected):
    control = PvEApproachController(PvEApproachConfig(native_progress_grace_ms=100))
    first = control.step(
        observation(selected=selected), phase=PvEPhase.ENGAGED, tracked_target=tracked()
    )
    moving = control.step(
        observation(100, selected), phase=PvEPhase.ENGAGED, tracked_target=tracked()
    )
    assert first.status.value == "idle"
    assert moving.status.value == "moving"
    assert moving.decision.distance_remaining == 100
    assert moving.decision.minimap_direction.x > 0  # Other selection is to the left.


def test_approach_selection_change_preserves_route_but_replacement_does_not():
    control = PvEApproachController(PvEApproachConfig(native_progress_grace_ms=100))
    control.step(observation(), phase=PvEPhase.ENGAGED, tracked_target=tracked())
    control.step(observation(100), phase=PvEPhase.ENGAGED, tracked_target=tracked())
    continued = control.step(
        observation(200, "other"), phase=PvEPhase.ENGAGED, tracked_target=tracked()
    )
    assert continued.status.value == "moving"
    new_key = NativeObjectKey(20, 3)
    replacement = character(object_key=new_key)
    changed = control.step(
        observation(300, "other", (replacement,)),
        phase=PvEPhase.ENGAGED,
        tracked_target=PvETrackedTarget("bound", new_key, replacement),
    )
    assert changed.status.value == "cancelled"
    assert changed.decision.terminal_reason == "approach_target_changed"


@pytest.mark.parametrize("case", ["absent", "dead", "stale"])
def test_approach_never_falls_back_to_selection_when_bound_object_unavailable(case):
    control = PvEApproachController(PvEApproachConfig(native_progress_grace_ms=100))
    control.step(observation(), phase=PvEPhase.ENGAGED, tracked_target=tracked())
    control.step(observation(100), phase=PvEPhase.ENGAGED, tracked_target=tracked())
    view = (
        PvETrackedTarget("bound", BOUND, None)
        if case == "absent"
        else tracked(character(current_health=0) if case == "dead" else character())
    )
    chars = () if case != "dead" else (character(current_health=0),)
    result = control.step(
        observation(200, "other", chars), phase=PvEPhase.ENGAGED, tracked_target=view
    )
    assert result.status.value == "cancelled"
    assert result.decision.terminal_reason == "tracked_target_position_unavailable"


@pytest.mark.parametrize("selected", [None, "other"])
def test_authority_uses_bound_object_without_relabeling_selection(selected):
    obs = observation(selected=selected)
    before = (obs.target, obs.target_position, obs.population.selected_target_token)
    for evaluator in (
        StaticPvETargetAuthorityEvaluator((evidence(),)),
        SnapshotPvETargetAuthorityEvaluator(snapshot()),
    ):
        decision = evaluator.evaluate_tracked(obs, tracked())
        assert decision.accepted
        assert decision.target_token == "bound"
        assert decision.target_object_key == BOUND
    assert before == (obs.target, obs.target_position, obs.population.selected_target_token)


@pytest.mark.parametrize("case", ["replacement", "party", "role", "missing", "stale", "dead"])
def test_tracked_authority_fails_closed_on_changed_native_evidence(case):
    char = character(merchant=case == "role", current_health=0 if case == "dead" else 10)
    view = PvETrackedTarget("bound", BOUND, None) if case == "missing" else tracked(char)
    obs = observation(selected="other", characters=() if case == "stale" else (char,))
    evaluator = SnapshotPvETargetAuthorityEvaluator(
        snapshot(
            key=NativeObjectKey(20, 3) if case == "replacement" else BOUND, party=case == "party"
        )
    )
    assert not evaluator.evaluate_tracked(obs, view).accepted


def test_static_authority_rejects_evidence_for_reused_pointer_key():
    evaluator = StaticPvETargetAuthorityEvaluator(
        (evidence(target_object_key=NativeObjectKey(20, 3)),)
    )
    decision = evaluator.evaluate_tracked(observation(), tracked())
    assert not decision.accepted
    assert PvETargetAuthorityExclusion.TARGET_OBJECT_IDENTITY_UNAVAILABLE in decision.exclusions


@pytest.mark.parametrize(
    "kind", [NativeCharacterKind.PET, NativeCharacterKind.PLAYER, NativeCharacterKind.UNKNOWN]
)
def test_current_non_npc_never_inherits_stale_static_npc_authority(kind):
    char = character(character_kind=kind)
    evaluator = StaticPvETargetAuthorityEvaluator((evidence(),))
    decision = evaluator.evaluate_tracked(observation(characters=(char,)), tracked(char))
    assert not decision.accepted
    if kind is NativeCharacterKind.PET:
        assert PvETargetAuthorityExclusion.PROTECTED_SERVICE_ROLE in decision.exclusions


@pytest.mark.parametrize("tracked_capability", [True, False])
def test_guarded_controller_rechecks_bound_authority_after_deselection(tracked_capability):
    static = StaticPvETargetAuthorityEvaluator((evidence(),))

    class SelectedOnlyEvaluator:
        def evaluate(self, obs):
            return static.evaluate(obs)

    controller = PvEController(
        PvEControllerConfig(require_target_identity=False),
        target_authority_evaluator=static if tracked_capability else SelectedOnlyEvaluator(),
        require_verified_target_authority=True,
    )
    # Pin through the controller's real admission path with native role evidence.
    from shadowbane_lab.client_observation import NativeTargetIdentityObservation

    obs = observation(selected="bound")
    obs = replace(
        obs,
        target_identity=NativeTargetIdentityObservation(
            target_present=True,
            arc_character=True,
            target_token="bound",
            merchant=False,
            shopkeeper=False,
            banker=False,
            trainer=False,
            minion=False,
        ),
    )
    controller.step(observation(0))
    admitted = controller.step(replace(obs, now_ms=500))
    assert admitted.phase is PvEPhase.ENGAGED
    result = controller.step(observation(600))
    assert result.target_authority.target_token == "bound"
    assert result.target_authority.accepted is tracked_capability
    assert result.phase is (PvEPhase.ENGAGED if tracked_capability else PvEPhase.DISENGAGING)
    assert result.intent is None


@pytest.mark.parametrize(
    "kind", [NativeCharacterKind.PLAYER, NativeCharacterKind.PET, NativeCharacterKind.UNKNOWN]
)
def test_ordinary_population_ranking_never_selects_non_npc(kind):
    controller = PvEController(PvEControllerConfig(use_native_population=True))
    decision = controller.step(observation(characters=(character(character_kind=kind),)))
    assert decision.intent is None
    assert decision.acquisition_target_token is None
    assert decision.phase is PvEPhase.SEEKING


def test_strict_startup_adopts_actual_combat_object_independent_of_ui_selection():
    controller = PvEController(
        PvEControllerConfig(use_native_population=True),
        target_authority_evaluator=StaticPvETargetAuthorityEvaluator((evidence(),)),
        require_verified_target_authority=True,
    )
    obs = observation(selected="other")
    obs = replace(
        obs,
        population=replace(obs.population, player_action_target_token="bound"),
        player_action=NativePlayerActionObservation(
            phase=NativeTargetActionPhase.WINDUP,
            targeting_selected=False,
            motion_id=4,
            action_pending=True,
            impact_frame=None,
            action_sequence=1,
            motion_sequence=1,
            selected_target_token="other",
            action_target_token="bound",
            mode=2,
            action_state=3,
        ),
    )
    result = controller.step(obs)
    assert result.phase is PvEPhase.ENGAGED
    assert result.intent is None
    assert result.tracked_target.object_key == BOUND
    assert result.target_authority.accepted
    assert result.target_authority.target_token == "bound"
    assert obs.target.target_token == "other"


def test_failed_adoption_cannot_lend_its_authority_to_a_selected_target():
    controller = PvEController(
        PvEControllerConfig(
            use_native_population=True, continuous=True, camp_radius=50, camp_return_radius=12
        ),
        target_authority_evaluator=StaticPvETargetAuthorityEvaluator((evidence(),)),
        require_verified_target_authority=True,
    )
    selected = character(token="other", object_key=NativeObjectKey(20, 9), lt=105)
    obs = observation(selected="other", characters=(character(), selected))
    from shadowbane_lab.client_observation import NativeTargetIdentityObservation

    obs = replace(
        obs,
        target_position=NativeTargetPositionObservation(True, 105, 200, 10, "other"),
        target_identity=NativeTargetIdentityObservation(
            target_present=True,
            arc_character=True,
            target_token="other",
            merchant=False,
            shopkeeper=False,
            banker=False,
            trainer=False,
            minion=False,
        ),
        population=replace(obs.population, player_action_target_token="bound"),
        player_action=NativePlayerActionObservation(
            phase=NativeTargetActionPhase.WINDUP,
            targeting_selected=False,
            motion_id=4,
            action_pending=True,
            impact_frame=None,
            action_sequence=1,
            motion_sequence=1,
            selected_target_token="other",
            action_target_token="bound",
            mode=2,
            action_state=3,
        ),
    )
    result = controller.step(obs)
    assert result.intent is None
    assert result.phase is not PvEPhase.ENGAGED
    assert result.tracked_target is None
