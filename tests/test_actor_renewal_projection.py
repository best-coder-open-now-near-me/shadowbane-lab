"""Native timing stays distinct from coverage and application settlement."""
from dataclasses import replace

import pytest
from test_native_actor_coordinator import setup as actor_fixture
from test_native_actor_preparation import configure

from shadowbane_lab.client_extension import actor_publication as native
from shadowbane_lab.pve.buff_intent import BuffAction, BuffGroup, BuffSettings
from shadowbane_lab.pve.preparation import ApplicationState, Coverage, PreparationAction

setup = actor_fixture


@pytest.mark.parametrize("coverage,remaining,stamp,due", [
    (native.Coverage.PRESENT, 15000, 123, True),
    (native.Coverage.PRESENT, 0, 123, True),
    (native.Coverage.PRESENT, 15001, 123, False),
    (native.Coverage.PRESENT, None, None, False),
    (native.Coverage.PARTIAL, 0, 123, False),
    (native.Coverage.UNKNOWN, None, None, False),
    (native.Coverage.MISSING, None, None, False),
])
def test_projection_preserves_coverage_and_limits_renewal(setup, monkeypatch,
                                                        coverage, remaining, stamp, due):
    owner, session, *_ = setup
    pub, _ = configure(owner, session, monkeypatch)
    owner.publication_reader.read.return_value = replace(pub, actions=(
        replace(pub.actions[0], coverage=coverage, remaining_ms=remaining, deadline_stamp=stamp),
        replace(pub.actions[1], coverage=native.Coverage.PRESENT,
                remaining_ms=0, deadline_stamp=123),
    ))
    observed = owner.observe_preparation()
    assert observed.coverage[0].state is Coverage[coverage.name]
    assert observed.coverage[0].renewal_due is due
    assert observed.coverage[1].state is Coverage.PRESENT
    assert not observed.coverage[1].renewal_due


@pytest.mark.parametrize("other", [native.Coverage.PRESENT, native.Coverage.PARTIAL,
                                  native.Coverage.UNKNOWN, native.Coverage.MISSING])
def test_other_alternative_must_be_known_missing_for_conc_renewal(setup, monkeypatch, other):
    owner, session, *_ = setup
    settings = BuffSettings(True, (BuffGroup("mixture", (
        BuffAction(PreparationAction("conc", item_template=(980066, 0)), 429021400),
        BuffAction(PreparationAction("other", power_id=429545819), 429545819),
    )),))
    pub, _ = configure(owner, session, monkeypatch, settings)
    owner.publication_reader.read.return_value = replace(pub, actions=(
        replace(pub.actions[0], coverage=native.Coverage.PRESENT,
                remaining_ms=10000, deadline_stamp=123),
        replace(pub.actions[1], coverage=other, remaining_ms=0, deadline_stamp=123),
    ))
    observed = owner.observe_preparation()
    assert observed.coverage[0].state is Coverage.PRESENT
    assert observed.coverage[0].renewal_due is (other is native.Coverage.MISSING)


def test_old_present_coverage_never_erases_native_pending_renewal(setup, monkeypatch):
    owner, session, *_ = setup
    pub, _ = configure(owner, session, monkeypatch)
    app = native.Application(owner.manifest.group_digest(0), b"c" * 32,
                             1, 0, 1, native.ApplicationState.PENDING, True, True)
    owner.publication_reader.read.return_value = replace(pub, applications=(app,), actions=(
        replace(pub.actions[0], coverage=native.Coverage.PRESENT,
                remaining_ms=14000, deadline_stamp=123),
        pub.actions[1],
    ))
    observed = owner.observe_preparation()
    assert observed.coverage[0].state is Coverage.PRESENT
    assert observed.coverage[0].renewal_due
    assert observed.pending_applications == frozenset({"concoction"})
    evidence = observed.application_history[0]
    assert evidence.state is ApplicationState.PENDING
    assert evidence.submission.command_digest == app.command_digest
    assert evidence.submission.submitted_revision == app.submitted_revision


def test_mixed_group_never_selects_other_ready_power_before_due_conc(setup, monkeypatch):
    owner, session, *_ = setup
    settings = BuffSettings(True, (BuffGroup("mixture", (
        BuffAction(PreparationAction("other", power_id=429545819), 429545819),
        BuffAction(PreparationAction("conc", item_template=(980066, 0)), 429021400),
    )),))
    pub, _ = configure(owner, session, monkeypatch, settings)
    owner.publication_reader.read.return_value = replace(pub, actions=(
        pub.actions[0],
        replace(pub.actions[1], coverage=native.Coverage.PRESENT,
                remaining_ms=10000, deadline_stamp=123),
    ))
    update = owner.preparation_step()
    assert update.acknowledgement.proposal.action.action_id == "conc"
    assert update.decision.groups[0].coverage is Coverage.PRESENT
