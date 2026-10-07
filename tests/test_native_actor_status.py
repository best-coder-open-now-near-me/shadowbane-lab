"""Production shared coordinator -> passive status -> runner/worker projection."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_native_actor_coordinator import setup as actor_fixture
from test_native_actor_preparation import configure

from shadowbane_lab.client_extension.actor_action_wire import LocalSettlement, Outcome, Verb
from shadowbane_lab.pve.preparation import Coverage

setup = actor_fixture


def test_status_initial_disabled_enabled_unknown_and_positive_queue_is_not_presence(
    setup, monkeypatch
):
    owner, session, _, _, _ = setup
    assert not owner.preparation_status.enabled
    configure(owner, session, monkeypatch)
    status = owner.preparation_status
    assert status.enabled and not status.complete and status.captured_at is None
    assert all(g.coverage is Coverage.UNKNOWN for g in status.groups)
    first = owner.preparation_step()
    assert first.acknowledgement.local_settled
    status = owner.preparation_status
    assert status.complete and not status.local_pending
    assert status.groups[0].coverage is Coverage.MISSING
    assert status.groups[0].application_pending
    count = session.actor_action.call_count
    reads = owner.publication_reader.read.call_count
    assert owner.preparation_status == status
    assert (
        session.actor_action.call_count == count
        and owner.publication_reader.read.call_count == reads
    )


def test_capture_age_not_renewed_by_same_native_capture_or_property_access(setup, monkeypatch):
    owner, session, _, _, _ = setup
    pub, _ = configure(owner, session, monkeypatch)
    owner.publication_reader.read.side_effect = None
    now = SimpleNamespace(value=100)
    monkeypatch.setattr("shadowbane_lab.pve.native_actor.time.time", lambda: now.value)
    owner.observe_preparation()
    assert owner.preparation_status.captured_at == 100
    now.value = 150
    owner.observe_preparation()
    assert owner.preparation_status.captured_at == 100
    owner.publication_reader.read.return_value = replace(pub, sequence=4)
    owner.observe_preparation()
    assert owner.preparation_status.captured_at == 150


@pytest.mark.parametrize("failure", ["unavailable", "exception"])
def test_failed_refresh_hides_coverage_but_preserves_real_local_pending(
    setup, monkeypatch, failure
):
    owner, session, _, _, _ = setup
    _, send = configure(owner, session, monkeypatch)
    fail = False

    def response(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if verb in (Verb.SUBMIT, Verb.ACTION_STATUS):
            result.receipt = replace(result.receipt, local_settlement=LocalSettlement.PENDING)
        if fail and verb is Verb.OBSERVE_ACTOR:
            if failure == "exception":
                raise RuntimeError("unavailable reader")
            result.receipt = replace(result.receipt, outcome=Outcome.UNAVAILABLE)
        return result

    session.actor_action.side_effect = response
    owner.preparation_step()
    assert owner.preparation_status.local_pending
    fail = True
    if failure == "exception":
        with pytest.raises(RuntimeError):
            owner.observe_preparation()
    else:
        assert owner.observe_preparation() is None
    status = owner.preparation_status
    assert status.local_pending and not status.complete and status.captured_at is None
    assert all(g.coverage is Coverage.UNKNOWN for g in status.groups)


def test_crosslane_settlement_updates_local_status_without_fabricating_new_capture(
    setup, monkeypatch
):
    owner, session, _, _, _ = setup
    _, send = configure(owner, session, monkeypatch)

    def response(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if verb is Verb.SUBMIT:
            result.receipt = replace(result.receipt, local_settlement=LocalSettlement.PENDING)
        return result

    session.actor_action.side_effect = response
    owner.preparation_step()
    before = owner.preparation_status
    assert before.local_pending
    assert owner._local_ready()  # Existing shared arbiter, not the status accessor.
    after = owner.preparation_status
    assert not after.local_pending and after.groups[0].application_pending
    assert (
        after.captured_at == before.captured_at
        and after.capture_sequence == before.capture_sequence
    )
    assert owner.finish("done")[0]
    assert not owner.preparation_status.complete and not owner.preparation_status.local_pending


def test_real_production_runner_projects_to_exact_worker_ledger_and_dashboard(
    setup, monkeypatch, tmp_path
):
    from test_manager_operation import _manifest
    from test_native_actor_preparation import (
        test_public_runner_shared_owner_item_combat_power_death_and_exact_cleanup as run_fixture,
    )
    from test_pve_status import health, operation, snapshot

    from shadowbane_lab.manager.operation import WorkerOperationLedger
    from shadowbane_lab.manager.pve_status import WorkerPvEProgress, project_status
    from shadowbane_lab.pve import PvERunner

    owner, session, _, _, _ = setup
    op = operation()
    ledger = WorkerOperationLedger(_manifest(), tmp_path, clock=lambda: 100)
    ledger.submit(op)
    ledger.claim_for_execution(op, now=100)
    samples = []
    original = PvERunner.__init__

    def sink(value):
        samples.append(value)
        ledger.publish_pve_progress(WorkerPvEProgress(op, value))

    def init(self, **kwargs):
        kwargs["progress_sink"] = sink
        original(self, **kwargs)

    monkeypatch.setattr(PvERunner, "__init__", init)
    run_fixture(
        setup, monkeypatch
    )  # Existing real runner/shared actor policy and native typed receipts.
    assert samples and any(s.preparation.complete for s in samples)
    assert any(any(g.application_pending for g in s.preparation.groups) for s in samples)
    record = ledger.inspect_pve_progress(op.client_id)
    result = project_status(
        record, snapshot(op), health(op), op.instance_id, now=record.progress.observed_at
    )
    assert result["state"] == "current"
    assert len([c for c in session.actor_action.call_args_list if c.args[1] is Verb.SUBMIT]) == 3


def test_presentation_failure_does_not_change_real_runner_actions_or_cleanup(setup, monkeypatch):
    from test_native_actor_preparation import (
        test_public_runner_shared_owner_item_combat_power_death_and_exact_cleanup as run_fixture,
    )

    from shadowbane_lab.pve import PvERunner

    original = PvERunner.__init__

    def fail(_):
        raise OSError("status volume unavailable")

    def init(self, **kwargs):
        kwargs["progress_sink"] = fail
        original(self, **kwargs)

    monkeypatch.setattr(PvERunner, "__init__", init)
    run_fixture(setup, monkeypatch)
