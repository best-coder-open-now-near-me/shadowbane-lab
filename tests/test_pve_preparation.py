"""Preparation policy tests use explicit boundary evidence, never a fake live observer."""

from dataclasses import FrozenInstanceError, replace

import pytest

from shadowbane_lab.pve.preparation import (
    ActorIdentity,
    Coverage,
    CoverageEvidence,
    Disposition,
    EntryState,
    ItemOperand,
    PowerOperand,
    PreparationAcknowledgement,
    PreparationAction,
    PreparationGroup,
    PreparationObservation,
    PreparationPolicy,
    PreparationPolicyError,
    Readiness,
    ReadinessEvidence,
)

ACTOR = ActorIdentity(100, 200, 1, (4050960, 53), "native-actor-a")
POTION = PreparationAction("potion", item_template=(980066, 0))
PRECISION = PreparationAction("precision", power_id=429545819)
BEORC = PreparationAction("beorc", power_id=429590426)
STANCE = PreparationAction("stance", power_id=676005819)
RAT = PreparationAction("rat", power_id=429513599)
SKREE = PreparationAction("skree", power_id=429415295)
GROUPS = (
    PreparationGroup("concentration", (POTION,)),
    PreparationGroup("precision", (PRECISION,)),
    PreparationGroup("beorc", (BEORC,)),
    PreparationGroup("transform", (RAT, SKREE)),
    PreparationGroup("stance", (STANCE,)),
)


def observe(
    epoch=1,
    *,
    groups=GROUPS,
    coverage=None,
    ready=None,
    pending=(),
    complete=True,
    admission=None,
    blocks=0,
    capture=None,
):
    coverage = coverage or {}
    ready = ready or {}
    evidence = []
    for group in groups:
        for action in group.alternatives:
            operand = (
                PowerOperand(action.power_id)
                if action.power_id
                else ItemOperand((88, 40), "native-item-a", action.item_template)
            )
            evidence.append(
                ReadinessEvidence(
                    action.action_id, ready.get(action.action_id, Readiness.READY), operand
                )
            )
    return PreparationObservation(
        ACTOR,
        epoch,
        complete,
        tuple(
            CoverageEvidence(g.group_id, coverage.get(g.group_id, Coverage.MISSING)) for g in groups
        ),
        tuple(evidence),
        epoch if admission is None else admission,
        blocks,
        frozenset(pending),
        capture_sequence=epoch * 2 if capture is None else capture,
    )


def acknowledge(policy, proposal, disposition=Disposition.QUEUED, *, settled=True, entry=None):
    if entry is None:
        entry = (
            EntryState.ENTERED if disposition is Disposition.QUEUED else EntryState.NEVER_ENTERED
        )
    policy.acknowledge(PreparationAcknowledgement(proposal, disposition, entry, settled))


def test_delayed_potion_does_not_block_other_ready_buffs_or_duplicate_it():
    policy = PreparationPolicy(ACTOR, GROUPS)
    first = policy.advance(observe()).proposal
    assert first.action is POTION
    acknowledge(policy, first)
    assert policy.advance(observe()).reason == "fresh_publication_required"
    for epoch, expected in enumerate((PRECISION, BEORC, RAT, STANCE), 2):
        proposal = policy.advance(observe(epoch)).proposal
        assert proposal.action is expected
        acknowledge(policy, proposal)
    decision = policy.advance(observe(10**12))
    assert decision.proposal is None
    assert all(s.application_pending and s.coverage is Coverage.MISSING for s in decision.groups)
    assert decision.reason == "waiting"  # Arbitrary time-like epoch growth proves nothing.


def test_all_five_groups_renew_after_sequential_local_settlement_and_native_presence():
    policy = PreparationPolicy(ACTOR, GROUPS)
    epoch = 1
    previous_sequence = 0
    for _ in range(3):
        for expected in (POTION, PRECISION, BEORC, RAT, STANCE):
            proposal = policy.advance(observe(epoch)).proposal
            assert proposal.action is expected and proposal.sequence > previous_sequence
            previous_sequence = proposal.sequence
            acknowledge(policy, proposal)
            epoch += 1
        missing = policy.advance(observe(epoch))
        assert missing.proposal is None and all(g.application_pending for g in missing.groups)
        epoch += 1
        present = policy.advance(observe(
            epoch, coverage={g.group_id: Coverage.PRESENT for g in GROUPS}
        ))
        assert present.proposal is None and not any(g.application_pending for g in present.groups)
        epoch += 1


@pytest.mark.parametrize("active_form", [RAT, SKREE])
def test_either_form_coverage_never_replaces_the_active_form(active_form):
    groups = (GROUPS[3],)
    policy = PreparationPolicy(ACTOR, groups)
    # The canonical adapter qualifies either active_form as the same coverage group.
    decision = policy.advance(
        observe(
            groups=groups,
            coverage={"transform": Coverage.PRESENT},
            ready={active_form.action_id: Readiness.NOT_READY},
        )
    )
    assert decision.proposal is None and decision.reason == "covered"


@pytest.mark.parametrize("state", [Readiness.NOT_READY, Readiness.UNKNOWN])
def test_form_alternative_uses_positive_native_readiness_only(state):
    policy = PreparationPolicy(ACTOR, (GROUPS[3],))
    p = policy.advance(observe(groups=(GROUPS[3],), ready={"rat": state})).proposal
    assert p.action is SKREE


def test_all_alternatives_unknown_or_blocked_wait_without_submission():
    policy = PreparationPolicy(ACTOR, (GROUPS[3],))
    assert (
        policy.advance(
            observe(
                groups=(GROUPS[3],), ready={"rat": Readiness.UNKNOWN, "skree": Readiness.NOT_READY}
            )
        ).proposal
        is None
    )


def test_partial_potion_effects_suppress_reapplication_through_staggered_expiry():
    policy = PreparationPolicy(ACTOR, (GROUPS[0],))
    for epoch, state in enumerate((Coverage.PRESENT, Coverage.PARTIAL, Coverage.PARTIAL), 1):
        assert (
            policy.advance(
                observe(epoch, groups=(GROUPS[0],), coverage={"concentration": state})
            ).proposal
            is None
        )
    assert policy.advance(observe(4, groups=(GROUPS[0],))).proposal.action is POTION


def test_imported_application_history_survives_policy_reconstruction_and_missing_projection():
    observation = observe(pending=("concentration",))
    for policy in (PreparationPolicy(ACTOR, GROUPS), PreparationPolicy(ACTOR, GROUPS)):
        p = policy.advance(observation).proposal
        assert p.action is PRECISION
        acknowledge(policy, p, Disposition.NOT_READY)
        later = policy.advance(observe(2, ready={"precision": Readiness.NOT_READY}))
        assert later.proposal.action is BEORC
        assert later.groups[0].application_pending


def test_positive_fresh_effect_then_later_qualified_missing_allows_refresh():
    policy = PreparationPolicy(ACTOR, (GROUPS[0],))
    p = policy.advance(observe(groups=(GROUPS[0],))).proposal
    acknowledge(policy, p)
    d = policy.advance(
        observe(2, groups=(GROUPS[0],), coverage={"concentration": Coverage.PRESENT})
    )
    assert not d.groups[0].application_pending and d.proposal is None
    new = policy.advance(observe(3, groups=(GROUPS[0],))).proposal
    assert new.sequence > p.sequence and new.operand == p.operand


def test_native_pending_history_is_not_cleared_by_effect_presence():
    policy = PreparationPolicy(ACTOR, (GROUPS[0],))
    policy.advance(observe(groups=(GROUPS[0],), pending=("concentration",)))
    d = policy.advance(
        observe(
            2,
            groups=(GROUPS[0],),
            pending=("concentration",),
            coverage={"concentration": Coverage.PRESENT},
        )
    )
    assert d.groups[0].application_pending
    assert policy.advance(observe(3, groups=(GROUPS[0],))).proposal is None


@pytest.mark.parametrize("complete,coverage", [(False, Coverage.MISSING), (True, Coverage.UNKNOWN)])
def test_incomplete_or_unknown_coverage_never_means_missing(complete, coverage):
    p = PreparationPolicy(ACTOR, (GROUPS[0],))
    d = p.advance(
        observe(groups=(GROUPS[0],), complete=complete, coverage={"concentration": coverage})
    )
    assert d.proposal is None and d.groups[0].coverage is Coverage.UNKNOWN


def test_missing_coverage_entry_is_unknown():
    policy = PreparationPolicy(ACTOR, (GROUPS[0],))
    assert policy.advance(replace(observe(groups=(GROUPS[0],)), coverage=())).proposal is None


def test_queued_local_continuation_requires_receipt_not_effect_to_settle():
    policy = PreparationPolicy(ACTOR, GROUPS)
    p = policy.advance(observe()).proposal
    acknowledge(policy, p, settled=False)
    d = policy.advance(observe(2, coverage={"concentration": Coverage.PRESENT}))
    assert d.proposal is p and d.poll_pending
    acknowledge(policy, p, settled=True)
    next_action = policy.advance(observe(3, coverage={"concentration": Coverage.PRESENT}))
    assert next_action.proposal.action is PRECISION


@pytest.mark.parametrize("entry", [EntryState.UNKNOWN, EntryState.ENTERED])
def test_uncertainty_only_polls_exact_proposal_despite_new_item_or_epoch(entry):
    policy = PreparationPolicy(ACTOR, GROUPS)
    p = policy.advance(observe()).proposal
    acknowledge(policy, p, Disposition.UNCERTAIN, settled=False, entry=entry)
    obs = observe(1000)
    obs = replace(
        obs,
        readiness=(
            replace(obs.readiness[0], operand=ItemOperand((99, 40), "another-item", (980066, 0))),
            *obs.readiness[1:],
        ),
    )
    d = policy.advance(obs)
    assert d.proposal is p and d.proposal.operand.item_key == (88, 40) and d.poll_pending


@pytest.mark.parametrize(
    "disposition", [Disposition.NOT_READY, Disposition.DEFERRED, Disposition.REJECTED]
)
def test_definitive_no_entry_waits_for_fresh_publication_then_qualified_alternative(disposition):
    policy = PreparationPolicy(ACTOR, (GROUPS[3],))
    obs = observe(groups=(GROUPS[3],))
    p = policy.advance(obs).proposal
    acknowledge(policy, p, disposition)
    assert policy.advance(obs).proposal is None
    new = policy.advance(
        observe(2, groups=(GROUPS[3],), ready={"rat": Readiness.NOT_READY})
    ).proposal
    assert new.action is SKREE and new.sequence != p.sequence


@pytest.mark.parametrize(
    "actor",
    [
        replace(ACTOR, actor_key=(9, 53)),
        replace(ACTOR, actor_token="replacement"),
        replace(ACTOR, process_creation=201),
        replace(ACTOR, scene=2),
    ],
)
def test_actor_replacement_latches_fault_and_retains_pending_for_owner_cleanup(actor):
    policy = PreparationPolicy(ACTOR, GROUPS)
    pending = policy.advance(observe()).proposal
    with pytest.raises(PreparationPolicyError, match="identity changed"):
        policy.advance(replace(observe(2), actor=actor))
    assert policy.pending_proposal is pending
    with pytest.raises(PreparationPolicyError):
        policy.advance(observe(3))


@pytest.mark.parametrize("changed", [observe(1), replace(observe(2), complete=False)])
def test_epoch_regression_or_same_epoch_changed_snapshot_is_rejected(changed):
    policy = PreparationPolicy(ACTOR, GROUPS)
    policy.advance(observe(2))
    with pytest.raises(PreparationPolicyError, match="publication"):
        policy.advance(changed)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: replace(p, sequence=p.sequence + 1),
        lambda p: replace(p, actor=replace(ACTOR, scene=2)),
        lambda p: replace(p, action=PRECISION),
        lambda p: replace(p, operand=ItemOperand((99, 40), "wrong-instance", (980066, 0))),
    ],
)
def test_mismatched_receipt_cannot_release_or_transfer_pending_proposal(mutation):
    policy = PreparationPolicy(ACTOR, GROUPS)
    p = policy.advance(observe()).proposal
    with pytest.raises(PreparationPolicyError, match="receipt"):
        acknowledge(policy, mutation(p))
    assert policy.pending_proposal is p


def test_known_queue_cannot_be_downgraded_to_no_entry():
    policy = PreparationPolicy(ACTOR, GROUPS)
    p = policy.advance(observe()).proposal
    acknowledge(policy, p, settled=False)
    with pytest.raises(PreparationPolicyError, match="queue history"):
        acknowledge(policy, p, Disposition.NOT_READY)


def test_resolved_operand_cannot_change_configured_power_or_template():
    policy = PreparationPolicy(ACTOR, GROUPS)
    obs = observe()
    obs = replace(
        obs,
        readiness=(
            replace(obs.readiness[0], operand=ItemOperand((88, 40), "item", (980067, 0))),
            *obs.readiness[1:],
        ),
    )
    with pytest.raises(PreparationPolicyError, match="operand"):
        policy.advance(obs)


def test_no_installed_default_groups_or_actions_and_immutable_inputs():
    policy = PreparationPolicy(ACTOR)
    assert (
        policy.advance(
            PreparationObservation(ACTOR, 1, True, (), (), 1, 0, capture_sequence=2)
        ).proposal
        is None
    )
    with pytest.raises(FrozenInstanceError):
        ACTOR.scene = 2
    with pytest.raises(ValueError):
        PreparationGroup("mutable", [POTION])
    with pytest.raises(ValueError):
        replace(observe(), pending_applications={"concentration"})
    with pytest.raises(ValueError):
        replace(observe(), publication_epoch=True)


def test_invalid_receipt_claims_are_rejected_before_policy():
    p = PreparationPolicy(ACTOR, GROUPS).advance(observe()).proposal
    for disposition, entry, settled in (
        (Disposition.QUEUED, EntryState.UNKNOWN, True),
        (Disposition.NOT_READY, EntryState.ENTERED, True),
        (Disposition.DEFERRED, EntryState.NEVER_ENTERED, False),
    ):
        with pytest.raises(ValueError):
            PreparationAcknowledgement(p, disposition, entry, settled)


def test_entered_uncertainty_never_downgrades_to_fresh_action_permission():
    policy = PreparationPolicy(ACTOR, GROUPS)
    p = policy.advance(observe()).proposal
    acknowledge(policy, p, Disposition.UNCERTAIN, settled=False, entry=EntryState.ENTERED)
    with pytest.raises(PreparationPolicyError, match="entry history"):
        acknowledge(policy, p, Disposition.DEFERRED)
    assert policy.pending_proposal is p


def test_definitive_rejection_is_not_retried_each_publication():
    groups = (GROUPS[3],)
    policy = PreparationPolicy(ACTOR, groups)
    rat = policy.advance(observe(groups=groups)).proposal
    acknowledge(policy, rat, Disposition.REJECTED)
    skree = policy.advance(observe(2, groups=groups)).proposal
    assert skree.action is SKREE
    acknowledge(policy, skree, Disposition.REJECTED)
    assert policy.advance(observe(3, groups=groups)).proposal is None


def test_late_ack_cannot_clear_the_next_groups_pending_action():
    policy = PreparationPolicy(ACTOR, GROUPS)
    first = policy.advance(observe()).proposal
    acknowledge(policy, first)
    second = policy.advance(observe(2)).proposal
    with pytest.raises(PreparationPolicyError, match="receipt"):
        acknowledge(policy, first)
    assert policy.pending_proposal is second


def test_captured_concoction_template_zero_word_is_distinct_from_instance_key():
    # Exact passive inventory metadata: template 980066/0, concrete item key type40.
    action = PreparationAction("captured-concoction", item_template=(980066, 0))
    item = ItemOperand((88, 40), "native-instance", (980066, 0))
    assert action.matches(item)
    for invalid in ((980066, 40), (980066, 1), (0, 0), (980066, False)):
        with pytest.raises(ValueError):
            PreparationAction("bad-template", item_template=invalid)
        with pytest.raises(ValueError):
            ItemOperand((88, 40), "native-instance", invalid)
    with pytest.raises(ValueError):
        ItemOperand((88, 0), "not-an-instance", (980066, 0))


def test_same_epoch_changed_item_or_pending_history_is_never_fresh_evidence():
    for changed in (
        replace(observe(), pending_applications=frozenset({"concentration"})),
        replace(
            observe(),
            readiness=(
                replace(
                    observe().readiness[0],
                    operand=ItemOperand((99, 40), "replacement-item", (980066, 0)),
                ),
                *observe().readiness[1:],
            ),
        ),
    ):
        policy = PreparationPolicy(ACTOR, GROUPS)
        pending = policy.advance(observe()).proposal
        with pytest.raises(PreparationPolicyError, match="without an epoch"):
            policy.advance(changed)
        assert policy.pending_proposal is pending


@pytest.mark.parametrize("entry", [EntryState.UNKNOWN, EntryState.ENTERED])
def test_remote_uncertainty_with_proven_local_completion_allows_other_groups(entry):
    policy = PreparationPolicy(ACTOR, GROUPS)
    potion = policy.advance(observe()).proposal
    acknowledge(policy, potion, Disposition.UNCERTAIN, settled=True, entry=entry)
    assert policy.pending_proposal is None
    assert policy.advance(observe()).reason == "fresh_publication_required"
    for epoch, action in enumerate((PRECISION, BEORC, RAT, STANCE), 2):
        decision = policy.advance(observe(epoch))
        assert decision.groups[0].application_pending
        assert decision.proposal.action is action
        acknowledge(policy, decision.proposal)
    decision = policy.advance(observe(10**12))
    assert decision.proposal is None and decision.groups[0].application_pending
    # The owning coordinator projects this unresolved application on reconstruction.
    recreated = PreparationPolicy(ACTOR, GROUPS)
    restored = recreated.advance(observe(10**12, pending=("concentration",)))
    assert restored.proposal.action is PRECISION


@pytest.mark.parametrize("entry", [EntryState.UNKNOWN, EntryState.ENTERED])
def test_effect_presence_never_settles_uncertain_local_responsibility(entry):
    policy = PreparationPolicy(ACTOR, GROUPS)
    potion = policy.advance(observe()).proposal
    acknowledge(policy, potion, Disposition.UNCERTAIN, settled=False, entry=entry)
    decision = policy.advance(observe(2, coverage={"concentration": Coverage.PRESENT}))
    assert decision.proposal is potion and decision.poll_pending
    acknowledge(policy, potion, Disposition.UNCERTAIN, settled=True, entry=entry)
    decision = policy.advance(observe(3))
    # Coverage proved the remote application, but only the explicit settled
    # receipt released local responsibility. Its later loss can now renew.
    assert decision.proposal.action is POTION and not decision.groups[0].application_pending


def test_positive_queue_history_survives_remotely_uncertain_local_completion():
    policy = PreparationPolicy(ACTOR, GROUPS)
    potion = policy.advance(observe()).proposal
    acknowledge(policy, potion, settled=False)
    acknowledge(policy, potion, Disposition.UNCERTAIN, settled=True, entry=EntryState.ENTERED)
    decision = policy.advance(observe(2))
    assert decision.proposal.action is PRECISION and decision.groups[0].application_pending


@pytest.mark.parametrize("disposition", [Disposition.DEFERRED, Disposition.NOT_READY])
def test_no_entry_refusal_ignores_journal_only_publication_revisions(disposition):
    groups = (GROUPS[2],)
    policy = PreparationPolicy(ACTOR, groups)
    proposal = policy.advance(observe(groups=groups, admission=7)).proposal
    acknowledge(policy, proposal, disposition)
    for revision in range(2, 102):
        decision = policy.advance(observe(revision, groups=groups, admission=7))
        assert decision.proposal is None and not decision.poll_pending
    # A newly captured refusal/clear race advances native eligibility, not time.
    next_proposal = policy.advance(observe(102, groups=groups, admission=9)).proposal
    assert next_proposal.action is BEORC and next_proposal.sequence == proposal.sequence + 1
    assert next_proposal.admission_revision == 9


@pytest.mark.parametrize("block", [1, 2, 4, 8, 16, 31])
def test_actual_native_block_to_clear_transition_resumes(block):
    policy = PreparationPolicy(ACTOR, (GROUPS[2],))
    for revision in range(1, 5):
        result = policy.advance(observe(revision, groups=(GROUPS[2],), admission=2, blocks=block))
        assert result.proposal is None and result.reason == "native_admission_blocked"
    assert policy.advance(observe(5, groups=(GROUPS[2],), admission=3)).proposal.action is BEORC


def test_refused_action_does_not_block_other_ready_group_same_admission_revision():
    groups = (GROUPS[2], GROUPS[1])
    policy = PreparationPolicy(ACTOR, groups)
    beorc = policy.advance(observe(groups=groups, admission=7)).proposal
    acknowledge(policy, beorc, Disposition.DEFERRED)
    precision = policy.advance(observe(2, groups=groups, admission=7)).proposal
    assert precision.action is PRECISION
    acknowledge(policy, precision)
    assert policy.advance(observe(3, groups=groups, admission=7)).proposal is None


def test_entered_local_pending_keeps_polling_despite_block_or_unknown_capture():
    policy = PreparationPolicy(ACTOR, (GROUPS[1],))
    proposal = policy.advance(observe(groups=(GROUPS[1],))).proposal
    acknowledge(policy, proposal, settled=False)
    blocked = policy.advance(observe(2, groups=(GROUPS[1],), blocks=4))
    assert blocked.proposal is proposal and blocked.poll_pending
    unknown = policy.advance(observe(3, groups=(GROUPS[1],), complete=False))
    assert unknown.proposal is proposal and unknown.poll_pending


def test_admission_revision_regression_latches_fault():
    policy = PreparationPolicy(ACTOR, (GROUPS[2],))
    first = policy.advance(observe(groups=(GROUPS[2],), admission=4)).proposal
    acknowledge(policy, first, Disposition.DEFERRED)
    with pytest.raises(PreparationPolicyError, match="regressed"):
        policy.advance(observe(2, groups=(GROUPS[2],), admission=3))


def test_admission_unknown_never_claims_block_and_requires_positive_revision():
    for changes in (
        {"admission_revision": 0},
        {"admission_revision": True},
        {"admission_blocks": 64},
        {"admission_blocks": True},
        {"complete": False, "admission_blocks": 1},
    ):
        with pytest.raises(ValueError):
            replace(observe(), **changes)


def test_settlement_requires_new_capture_not_changed_semantic_revision():
    policy = PreparationPolicy(ACTOR, GROUPS)
    covered = {"concentration": Coverage.PRESENT, "precision": Coverage.PRESENT}
    beorc = policy.advance(observe(13, coverage=covered, admission=9, capture=100)).proposal
    assert beorc.action is BEORC
    acknowledge(policy, beorc, settled=False)
    settled = observe(
        17, coverage={**covered, "beorc": Coverage.PRESENT}, admission=12, capture=176
    )
    assert policy.advance(settled).proposal == beorc
    acknowledge(policy, beorc, settled=True)
    assert policy.advance(settled).reason == "fresh_publication_required"
    rat = policy.advance(replace(settled, capture_sequence=178)).proposal
    assert rat.action is RAT and rat.publication_epoch == 17 and rat.admission_revision == 12
    acknowledge(policy, rat)
    assert policy.advance(replace(settled, capture_sequence=178)).proposal is None
    stance = policy.advance(replace(settled, capture_sequence=180)).proposal
    assert stance.action is STANCE and stance.publication_epoch == 17
    acknowledge(policy, stance)
    # Possible remote application still suppresses duplicate entries even though
    # complete captures continue and neither effect has appeared yet.
    assert policy.advance(replace(settled, capture_sequence=182)).proposal is None


@pytest.mark.parametrize("capture", [0, -2, 1, True, 2**63])
def test_invalid_native_capture_sequence_rejected(capture):
    with pytest.raises(ValueError, match="capture"):
        observe(capture=capture)


def test_capture_regression_and_same_capture_changed_semantics_revoke_policy():
    for changed in (observe(2, capture=2), observe(1, capture=2)):
        policy = PreparationPolicy(ACTOR, GROUPS)
        policy.advance(observe(1, capture=4))
        with pytest.raises(PreparationPolicyError):
            policy.advance(changed)
        with pytest.raises(PreparationPolicyError):
            policy.advance(observe(3, capture=6))
    policy = PreparationPolicy(ACTOR, GROUPS)
    policy.advance(observe(1, capture=4))
    with pytest.raises(PreparationPolicyError):
        policy.advance(observe(2, capture=4))


def test_new_capture_does_not_make_unknown_or_changed_same_epoch_facts_authoritative():
    policy = PreparationPolicy(ACTOR, GROUPS)
    first = policy.advance(observe()).proposal
    acknowledge(policy, first)
    unknown = observe(2, capture=4, complete=False)
    assert policy.advance(unknown).reason == "observation_unknown"
    with pytest.raises(PreparationPolicyError):
        policy.advance(replace(unknown, capture_sequence=6, complete=True))


@pytest.mark.parametrize(
    "disposition,entry",
    [
        (Disposition.QUEUED, EntryState.ENTERED),
        (Disposition.UNCERTAIN, EntryState.ENTERED),
        (Disposition.UNCERTAIN, EntryState.UNKNOWN),
    ],
)
@pytest.mark.parametrize("missing_before_settlement", [False, True])
def test_observed_application_is_not_recreated_by_late_settlement(
    disposition, entry, missing_before_settlement
):
    groups = (GROUPS[2],)
    policy = PreparationPolicy(ACTOR, groups)
    original = policy.advance(observe(13, groups=groups, capture=100)).proposal
    acknowledge(policy, original, disposition, settled=False, entry=entry)
    present = observe(17, groups=groups, coverage={"beorc": Coverage.PRESENT}, capture=176)
    decision = policy.advance(present)
    assert decision.proposal is original and decision.poll_pending
    assert not decision.groups[0].application_pending
    if missing_before_settlement:
        decision = policy.advance(observe(18, groups=groups, capture=178))
        assert decision.proposal is original and decision.poll_pending
    acknowledge(policy, original, disposition, settled=True, entry=entry)
    renewed = policy.advance(observe(19, groups=groups, capture=180)).proposal
    assert renewed.action is BEORC and renewed.sequence == original.sequence + 1
    # The previous application evidence cannot satisfy this new submission.
    acknowledge(policy, renewed, disposition, settled=True, entry=entry)
    assert policy.advance(observe(20, groups=groups, capture=182)).proposal is None


@pytest.mark.parametrize(
    "complete,coverage,native_pending",
    [
        (False, Coverage.PRESENT, ()),
        (True, Coverage.UNKNOWN, ()),
        (True, Coverage.PARTIAL, ()),
        (True, Coverage.MISSING, ()),
        (True, Coverage.PRESENT, ("beorc",)),
    ],
)
@pytest.mark.parametrize(
    "disposition,entry",
    [
        (Disposition.QUEUED, EntryState.ENTERED),
        (Disposition.UNCERTAIN, EntryState.UNKNOWN),
    ],
)
def test_unproven_application_remains_suppressed_after_local_settlement(
    complete, coverage, native_pending, disposition, entry
):
    groups = (GROUPS[2],)
    policy = PreparationPolicy(ACTOR, groups)
    original = policy.advance(observe(13, groups=groups)).proposal
    acknowledge(policy, original, disposition, settled=False, entry=entry)
    policy.advance(
        observe(
            17,
            groups=groups,
            coverage={"beorc": coverage},
            complete=complete,
            pending=native_pending,
        )
    )
    acknowledge(policy, original, disposition, settled=True, entry=entry)
    for epoch in (18, 19, 10**12):
        decision = policy.advance(observe(epoch, groups=groups))
        assert decision.proposal is None and decision.groups[0].application_pending


def test_new_native_pending_after_observed_application_requires_new_positive_evidence():
    groups = (GROUPS[2],)
    policy = PreparationPolicy(ACTOR, groups)
    original = policy.advance(observe(13, groups=groups)).proposal
    acknowledge(policy, original, settled=False)
    policy.advance(observe(17, groups=groups, coverage={"beorc": Coverage.PRESENT}))
    policy.advance(observe(18, groups=groups, pending=("beorc",)))
    acknowledge(policy, original)
    assert policy.advance(observe(19, groups=groups)).proposal is None
    policy.advance(observe(20, groups=groups, coverage={"beorc": Coverage.PRESENT}))
    assert policy.advance(observe(21, groups=groups)).proposal.action is BEORC


def test_alternative_group_renews_across_repeated_observed_expiry_cycles():
    groups = (GROUPS[3],)
    policy = PreparationPolicy(ACTOR, groups)
    for cycle in range(4):
        epoch = 1 + cycle * 3
        action = RAT if cycle % 2 == 0 else SKREE
        unavailable = SKREE if action is RAT else RAT
        first = policy.advance(
            observe(epoch, groups=groups, ready={unavailable.action_id: Readiness.NOT_READY})
        ).proposal
        assert first.action is action
        acknowledge(policy, first, settled=False)
        policy.advance(observe(epoch + 1, groups=groups, coverage={"transform": Coverage.PRESENT}))
        acknowledge(policy, first)
        assert (
            policy.advance(
                observe(epoch + 2, groups=groups, coverage={"transform": Coverage.PRESENT})
            ).proposal
            is None
        )
