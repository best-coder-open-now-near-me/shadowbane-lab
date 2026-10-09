"""Exact native application history; interruption never proves local cleanup."""

from dataclasses import replace

import pytest
from test_pve_preparation import ACTOR, GROUPS, observe

from shadowbane_lab.pve.preparation import (
    ApplicationEvidence,
    ApplicationState,
    ApplicationSubmission,
    Coverage,
    Disposition,
    EntryState,
    PreparationAcknowledgement,
    PreparationPolicy,
    PreparationPolicyError,
)
from shadowbane_lab.pve.preparation_status import capture_status

GROUP = GROUPS[0].group_id


def submission(number=1, revision=1):
    return ApplicationSubmission(number.to_bytes(32, "big"), revision)


def evidence(original, state=ApplicationState.INTERRUPTED, revision=2):
    return ApplicationEvidence(
        GROUP, original, state, 0 if state is ApplicationState.PENDING else revision
    )


def observation(epoch, *history, complete=True, blocks=0):
    pending = {v.group_id for v in history if v.state is ApplicationState.PENDING}
    return replace(
        observe(epoch, groups=GROUPS[:1], pending=pending, complete=complete, blocks=blocks),
        application_history=tuple(history),
    )


def acknowledge(policy, proposal, original, *, settled=True):
    policy.acknowledge(
        PreparationAcknowledgement(
            proposal, Disposition.QUEUED, EntryState.ENTERED, settled, original
        )
    )


def test_interruption_releases_only_application_after_late_local_ack():
    policy = PreparationPolicy(ACTOR, GROUPS[:1])
    proposal = policy.advance(observation(1)).proposal
    original = submission()
    acknowledge(policy, proposal, original, settled=False)
    update = observation(2, evidence(original))
    decision = policy.advance(update)
    assert decision.proposal is proposal and decision.poll_pending
    assert not policy.application_pending_groups
    status = capture_status(
        GROUPS[:1],
        update,
        decision,
        captured_at=100,
        local_pending=True,
        application_pending_groups=policy.application_pending_groups,
    )
    assert status.local_pending and status.groups[0].coverage is Coverage.MISSING
    assert not status.groups[0].application_pending
    # Terminal history may disappear before the original local receipt arrives.
    policy.advance(observation(3))
    acknowledge(policy, proposal, original)
    assert policy.advance(observation(3)).proposal is None
    renewal = policy.advance(observation(4)).proposal
    assert renewal is not None and renewal.sequence != proposal.sequence
    assert not policy.application_pending_groups


def test_reconstructed_policy_uses_native_submission_not_current_capture_revision():
    policy = PreparationPolicy(ACTOR, GROUPS[:1])
    original = submission(revision=1)
    assert (
        policy.advance(observation(20, evidence(original, ApplicationState.PENDING))).proposal
        is None
    )
    assert policy.application_pending_groups == {GROUP}
    decision = policy.advance(observation(21, evidence(original, revision=21)))
    assert decision.proposal is not None and decision.proposal.publication_epoch == 21


@pytest.mark.parametrize("foreign", [submission(2, 1), submission(1, 2)])
def test_foreign_terminal_does_not_clear_local_or_imported_pending(foreign):
    original = submission()
    local = PreparationPolicy(ACTOR, GROUPS[:1])
    proposal = local.advance(observation(1)).proposal
    acknowledge(local, proposal, original)
    assert local.advance(observation(3, evidence(foreign, revision=3))).proposal is None
    imported = PreparationPolicy(ACTOR, GROUPS[:1])
    imported.advance(observation(2, evidence(original, ApplicationState.PENDING)))
    assert imported.advance(observation(3, evidence(foreign, revision=3))).proposal is None
    assert local.application_pending_groups == imported.application_pending_groups == {GROUP}


def test_old_interruption_cannot_release_newer_same_group_submission():
    policy = PreparationPolicy(ACTOR, GROUPS[:1])
    old = submission()
    proposal = policy.advance(observation(1)).proposal
    acknowledge(policy, proposal, old)
    second = policy.advance(observation(2, evidence(old))).proposal
    new = submission(2, 2)
    acknowledge(policy, second, new)
    assert policy.advance(observation(3, evidence(old))).proposal is None
    assert policy.application_pending_groups == {GROUP}
    third = policy.advance(observation(4, evidence(new, revision=4))).proposal
    assert third is not None and third.sequence == 3


def test_new_native_pending_survives_old_terminal_and_blocks_same_group_only():
    policy = PreparationPolicy(ACTOR, GROUPS)
    old, new = submission(), submission(2, 2)
    pending = replace(
        observe(3, pending={GROUP}),
        application_history=(evidence(old), evidence(new, ApplicationState.PENDING)),
    )
    decision = policy.advance(pending)
    assert decision.proposal.group_id == "precision"
    assert policy.application_pending_groups == {GROUP}


def test_unknown_capture_and_legacy_group_suppression_are_not_terminal_proof():
    original = submission()
    policy = PreparationPolicy(ACTOR, GROUPS[:1])
    policy.advance(observation(1, evidence(original, ApplicationState.PENDING)))
    assert policy.advance(observation(2, complete=False)).proposal is None
    assert policy.advance(observation(3)).proposal is None
    legacy = PreparationPolicy(ACTOR, GROUPS[:1])
    legacy.advance(replace(observation(1), pending_applications=frozenset({GROUP})))
    assert legacy.advance(observation(2, evidence(original))).proposal is None
    present = replace(observe(3, groups=GROUPS[:1], coverage={GROUP: Coverage.PRESENT}))
    legacy.advance(present)
    assert not legacy.application_pending_groups


def test_repeated_interruption_manual_deferral_then_fresh_retry():
    policy = PreparationPolicy(ACTOR, GROUPS[:1])
    for number in range(1, 5):
        epoch = number * 3 - 2
        proposal = policy.advance(observation(epoch)).proposal
        assert proposal is not None
        original = submission(number, epoch)
        acknowledge(policy, proposal, original)
        terminal = evidence(original, revision=epoch + 1)
        assert policy.advance(observation(epoch + 1, terminal, blocks=32)).proposal is None
        assert not policy.application_pending_groups
        # Keep admission blocked until the next iteration's fresh native clear.
        assert policy.advance(observation(epoch + 2, terminal, blocks=32)).proposal is None


def test_terminal_before_first_ack_is_correlated_later_without_releasing_local_pending():
    policy = PreparationPolicy(ACTOR, GROUPS[:1])
    proposal = policy.advance(observation(1)).proposal
    original = submission()
    policy.advance(observation(2, evidence(original)))
    acknowledge(policy, proposal, original, settled=False)
    assert policy.pending_proposal is proposal and not policy.application_pending_groups


def test_identity_change_and_command_replacement_fail_closed():
    policy = PreparationPolicy(ACTOR, GROUPS[:1])
    proposal = policy.advance(observation(1)).proposal
    acknowledge(policy, proposal, submission(), settled=False)
    with pytest.raises(PreparationPolicyError, match="command changed"):
        acknowledge(policy, proposal, submission(2), settled=False)
    policy = PreparationPolicy(ACTOR, GROUPS[:1])
    policy.advance(observation(1, evidence(submission(), ApplicationState.PENDING)))
    with pytest.raises(PreparationPolicyError, match="actor identity"):
        policy.advance(
            replace(
                observation(2, evidence(submission())), actor=replace(ACTOR, scene=ACTOR.scene + 1)
            )
        )


@pytest.mark.parametrize("change", ["unknown", "duplicate", "future", "untyped"])
def test_malformed_terminal_observation_rejected(change):
    terminal = evidence(submission())
    with pytest.raises(ValueError):
        if change == "unknown":
            observation(2, terminal, complete=False)
        elif change == "duplicate":
            observation(2, terminal, terminal)
        elif change == "future":
            observation(1, terminal)
        else:
            replace(terminal, state="interrupted")
