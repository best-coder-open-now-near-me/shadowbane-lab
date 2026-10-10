from types import SimpleNamespace as S
from unittest.mock import Mock

import pytest

from shadowbane_lab.manager.group_commands import GroupCommand
from shadowbane_lab.manager.operation import WorkerOperationKind
from shadowbane_lab.manager.worker_runtime import ExactClientWorkerRuntime


def runtime():
    result = object.__new__(ExactClientWorkerRuntime)
    result._binding = S(client_id="client", instance_id="instance")
    result._process = S(process_id=123, process_started_at_100ns=456)
    result._group_cleanup_confirmed = True
    result._group_operations = {}
    result._preparation_waiting = False
    result._preparation = Mock()
    result._preparation.request_handoff.return_value = False
    result._operation_ledger = Mock()
    result._operation_ledger.inspect_preparation_control.return_value = None
    result._operation_ledger.pending_for.return_value = ()
    result._ledger = Mock()
    publisher = Mock(worker_id="worker-" + "a" * 32)
    publisher.dispatch_gate.return_value.is_set.return_value = False
    command = GroupCommand("b" * 64, 2, 1000, 7, (42, 53), "digest", (123, 53), "Alice", "come")
    result._group_commands = Mock()
    result._group_commands.pending.return_value = command
    result._group_commands.claim.return_value = ((100., 200.), None)
    return result, publisher, command


def test_preemption_only_trips_existing_operation_never_forges_cleanup():
    r, pub, command = runtime()
    active = S(stop_signal=Mock())
    r._poll_group_commands(pub, active)
    active.stop_signal.trip.assert_called_once_with(
        "fresh native group command preemption", requested=True)
    r._operation_ledger.submit.assert_not_called()
    r._group_commands.claim.assert_not_called()
    r._preparation.request_handoff.assert_not_called()


@pytest.mark.parametrize("mode", ["unconfirmed", "preparation_pending", "paused", "permit_revoked"])
def test_no_command_until_real_cleanup_and_current_permission(mode):
    r, pub, command = runtime()
    if mode == "unconfirmed":
        r._group_cleanup_confirmed = False
    elif mode == "paused":
        r._operation_ledger.inspect_preparation_control.return_value = S(enabled=False)
    elif mode == "permit_revoked":
        pub.dispatch_gate.return_value.is_set.return_value = True
    r._poll_group_commands(pub, None)
    r._operation_ledger.submit.assert_not_called()
    r._group_commands.claim.assert_not_called()


def test_positive_handoff_submits_once_to_same_worker(monkeypatch):
    r, pub, command = runtime()
    r._preparation.request_handoff.return_value = True
    permit = S(instance_id="instance", worker_id=pub.worker_id,
               process_id=123, process_started_at_100ns=456)
    r._ledger.inspect_permit.return_value = permit
    created = S(operation_id="operation-" + command.event_id[:32])
    factory = Mock(return_value=created)
    monkeypatch.setattr("shadowbane_lab.manager.operation.new_worker_operation", factory)
    r._poll_group_commands(pub, None)
    r._operation_ledger.submit.assert_called_once_with(created)
    assert factory.call_args.args[1] is WorkerOperationKind.TRAVEL
    assert factory.call_args.kwargs["destination"].lt == 100
    assert r._group_operations[created.operation_id] == command


def test_replacement_permit_never_redirects_group_command():
    r, pub, command = runtime()
    r._preparation.request_handoff.return_value = True
    r._ledger.inspect_permit.return_value = S(instance_id="other", worker_id="replacement",
                                             process_id=999, process_started_at_100ns=999)
    r._poll_group_commands(pub, None)
    r._operation_ledger.submit.assert_not_called()
    assert r._group_commands.note.call_args.args[1] == "withheld"


def test_observer_thread_to_real_operation_consumes_once_and_rechecks_group(tmp_path, monkeypatch):
    import queue
    import time

    from test_group_commands import batch, chat, current

    from shadowbane_lab.manager.group_commands import GroupCommandService
    from shadowbane_lab.manager.operation import WorkerOperationState
    from shadowbane_lab.manager.worker import WorkerDispatchPermit, WorkerHealthState

    inputs, published = queue.Queue(), queue.Queue()
    class Source:
        lifetime = (55, 66)
        def read(self):
            return inputs.get(timeout=2)
        def close(self):
            pass
    service = GroupCommandService(Source(), allowed=lambda: True,
                                  record_path=tmp_path / "consumed.json", interval=.001)
    service._publish_status = lambda: published.put(True)
    monkeypatch.setattr(
        "shadowbane_lab.client_extension.tracking_publication.tick_ms", lambda: 1001)
    c = {**current(), "enabled": True, "positions": {(123, 53): (70000., 50000.)}}
    def feed(messages, state=c):
        inputs.put((messages, batch(), state, 1001))
        assert published.get(timeout=2)
    service.start()
    try:
        feed(batch(initial=True))
        feed(batch([chat()]))
        command = service.pending()
        assert command is not None
        r, pub, _ = runtime()
        r._group_commands = service
        r._preparation.request_handoff.return_value = True
        r._ledger.inspect_permit.return_value = WorkerDispatchPermit(
            node_id="node", client_id="client", health_state=WorkerHealthState.HEALTHY,
            allowed=True, issued_at=time.time(), expires_at=time.time()+30, reason="exact worker",
            instance_id="instance", worker_id=pub.worker_id, process_id=123,
            process_started_at_100ns=456, heartbeat_sequence=1)
        r._poll_group_commands(pub, None)
        operation = r._operation_ledger.submit.call_args.args[0]
        assert operation.destination.lt == 70000
        assert operation.worker_id == pub.worker_id
        assert operation.kind is WorkerOperationKind.TRAVEL
        feed(batch(sequence=3))
        r._poll_group_commands(pub, None)
        assert r._operation_ledger.submit.call_count == 1
        assert service.pending() is None
        # An accepted receive does not authorize a queued command after a group change.
        feed(batch(sequence=3), {**c, "group_digest": "replacement"})
        r._operation_executor = Mock()
        r._operation_ledger.pending_for.return_value = (operation,)
        assert r._start_next_operation(pub) is None
        receipt = r._operation_ledger.publish_receipt.call_args.args[0]
        assert receipt.state is WorkerOperationState.REJECTED
        r._operation_ledger.claim_for_execution.assert_not_called()
        r._operation_executor.assert_not_called()
        assert (tmp_path / "consumed.json").is_file()
        import json
        proof = json.loads((tmp_path / f"admission-{command.event_id}.json").read_text())
        assert proof["command"]["generation"] == command.generation
        assert proof["command"]["sender_key"] == [123, 53]
        assert proof["command"]["group_digest"] == "digest"
        assert proof["operation"]["operation_id"] == operation.operation_id
        assert proof["operation"]["worker_id"] == pub.worker_id
    finally:
        service.stop.set()
        inputs.put((batch(sequence=3), batch(), c, 1001))
        service.close()
        assert not service.thread.is_alive()


def test_missing_attack_target_is_consumed_with_visible_reason(tmp_path, monkeypatch):
    import queue

    from test_group_commands import batch, chat, current

    from shadowbane_lab.manager.group_commands import GroupCommandService

    inputs, published = queue.Queue(), queue.Queue()
    source = Mock(lifetime=(55, 66))
    source.read.side_effect = lambda: inputs.get(timeout=2)
    source.attack_target.side_effect = ValueError("player name is missing or ambiguous")
    service = GroupCommandService(source, allowed=lambda: True,
                                  record_path=tmp_path / "consumed.json", interval=.001)
    service._publish_status = lambda: published.put(True)
    monkeypatch.setattr(
        "shadowbane_lab.client_extension.tracking_publication.tick_ms", lambda: 1001)
    c = {**current(), "enabled": True}
    def feed(messages):
        inputs.put((messages, batch(), c, 1001))
        assert published.get(timeout=2)
    service.start()
    try:
        feed(batch(initial=True))
        feed(batch([chat(text="/attack Typo")]))
        assert service.pending() is None
        assert service.last_request["state"] == "withheld"
        assert "Target: Typo" in service.last_request["detail"]
        assert "missing or ambiguous" in service.last_request["detail"]
        assert service.seeded and service.current is not None
        feed(batch(sequence=3))
        source.attack_target.assert_called_once_with("Typo")
        assert service.pending() is None
    finally:
        service.stop.set()
        inputs.put((batch(sequence=3), batch(), c, 1001))
        service.close()


def test_delayed_handoff_waits_for_fresh_observation_then_submits_once(tmp_path, monkeypatch):
    from test_group_commands import batch, chat, current

    from shadowbane_lab.manager.group_commands import GroupCommandService

    clock = [1001]
    monkeypatch.setattr(
        "shadowbane_lab.client_extension.tracking_publication.tick_ms", lambda: clock[0])
    source = Mock(lifetime=(55, 66))
    service = GroupCommandService(source, allowed=lambda: True,
                                  record_path=tmp_path / "consumed.json")
    c = {**current(), "enabled": True, "positions": {(123, 53): (100., 200.)}}
    service.policy.ingest(batch(initial=True), batch(), c, allowed=True, now_ms=1001)
    service.policy.ingest(batch([chat()]), batch(), c, allowed=True, now_ms=1001)
    command = service.policy.pending
    service.current, service.now_ms = c, 1001
    service.enabled = service.seeded = True
    service.pending_value = command
    r, pub, _ = runtime()
    r._group_commands = service
    r._preparation.request_handoff.return_value = True
    permit = S(instance_id="instance", worker_id=pub.worker_id,
               process_id=123, process_started_at_100ns=456)
    r._ledger.inspect_permit.return_value = permit
    created = S(operation_id="operation-" + command.event_id[:32])
    monkeypatch.setattr("shadowbane_lab.manager.operation.new_worker_operation",
                        Mock(return_value=created))
    service.record_admission = Mock()

    # Ledger work between pending() and claim() outlasts the observation,
    # but not the native receive deadline. Nothing has been submitted yet.
    def delayed_inbox(**kwargs):
        clock[0] = 1602
        return ()
    r._operation_ledger.pending_for.side_effect = delayed_inbox
    r._poll_group_commands(pub, None)
    r._operation_ledger.submit.assert_not_called()
    assert service.taken is None and service.pending_value == command
    assert service.last_request["state"] == "waiting"
    assert service.pending() is None
    assert service.pending_value == command

    # The ordinary observer refresh permits the same intent once. A later poll
    # of that receive event never submits a second operation.
    service.now_ms = clock[0]
    r._poll_group_commands(pub, None)
    r._poll_group_commands(pub, None)
    r._operation_ledger.submit.assert_called_once_with(created)
    assert service.taken == command and service.pending_value is None


@pytest.mark.parametrize("reason", ["deadline", "group", "disabled", "unseeded"])
def test_waiting_claim_never_outlives_deadline_or_permission(tmp_path, monkeypatch, reason):
    from test_group_commands import current

    from shadowbane_lab.manager.group_commands import GroupCommandService

    service = GroupCommandService(Mock(lifetime=(55, 66)), allowed=lambda: True,
                                  record_path=tmp_path / "consumed.json")
    _, _, command = runtime()
    service.current = {**current(), "positions": {(123, 53): (100., 200.)}}
    service.enabled = service.seeded = True
    service.now_ms = 1001
    service.pending_value = command
    clock = [1602]
    monkeypatch.setattr(
        "shadowbane_lab.client_extension.tracking_publication.tick_ms", lambda: clock[0])
    assert service.claim(command) is None
    if reason == "deadline":
        clock[0] = 6001
    elif reason == "group":
        service.current = {**service.current, "group_digest": "replacement"}
    elif reason == "disabled":
        service.enabled = False
    else:
        service.seeded = False
    service.now_ms = clock[0]
    with pytest.raises(ValueError, match="expired or permission changed"):
        service.claim(command)
    assert service.taken == command and service.pending_value is None
    assert service.claim(command) is None


def test_control_io_precedes_native_observation(tmp_path):
    from test_group_commands import batch, current

    from shadowbane_lab.manager.group_commands import GroupCommandService

    order = []
    source = Mock(lifetime=(55, 66))
    def allowed():
        order.append("ledger")
        return True
    def read():
        order.append("native")
        return batch(initial=True), batch(), {**current(), "enabled": True}, 1001
    source.read.side_effect = read
    service = GroupCommandService(source, allowed=allowed,
                                  record_path=tmp_path / "consumed.json")
    service._publish_status = service.stop.set
    service._run()
    assert order == ["ledger", "native"]
