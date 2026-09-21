import json
import uuid
from dataclasses import replace

import pytest

from shadowbane_lab.client_extension.condemn_evidence import (
    Response,
    ResponseWindow,
    Target,
    canonical,
)
from shadowbane_lab.client_extension.condemn_progress import (
    CondemnProgressStopped,
    CondemnProgressStore,
    Submission,
)
from shadowbane_lab.client_extension.condemn_responses import CondemnResponseError
from tests.test_condemn_evidence import LIFE, TARGET, row_observation, snapshot, triple


def row(enabled=True):
    observation = row_observation()
    observation['root_address'] = 0x10000
    observation['windows'][0]['address'] = 0x20000
    if not enabled:
        observation['windows'][0]['entries'][0]['flags_raw'] = [0, 0, 0]
    return observation


def setup(tmp_path):
    store = CondemnProgressStore(tmp_path)
    window = ResponseWindow(LIFE, snapshot())
    request = str(uuid.uuid4())
    receipt = Submission(request, LIFE, TARGET, 0, 1000, True)
    return store, window, request, receipt


def complete(store, window, request):
    response, = window.consume(snapshot(triple()))
    store.observe(request, response, window, row(), 1004)
    return response


def test_intent_is_durable_before_dispatch_and_exact_progress_survives_restart(tmp_path):
    store, window, request, receipt = setup(tmp_path)

    def dispatch():
        saved = json.loads(store.path.read_bytes())
        assert saved['active'] == request
        assert saved['attempts'][0]['state'] == 'intent'
        return receipt

    assert store.submit(request, TARGET, window, row(False), dispatch) == receipt
    complete(store, window, request)
    recovered = CondemnProgressStore(tmp_path)
    recovered.assert_idle()
    assert recovered.verified_targets(LIFE) == {TARGET}
    assert not recovered.verified_targets(replace(LIFE, creation=12))
    assert not recovered.verified_targets(replace(LIFE, scene_epoch=6))
    assert recovered.read()['attempts'][0]['completion']['response'][0]['payload']['scope_raw'] == 0
    with pytest.raises(CondemnProgressStopped):
        recovered.submit(request, TARGET, window, row(False), dispatch)


@pytest.mark.parametrize('when', ['dispatch', 'submission_write', 'intent_write'])
def test_failures_never_replay_and_never_lose_write_ahead_intent(tmp_path, when, monkeypatch):
    store, window, request, receipt = setup(tmp_path)
    calls = []
    original = store._write

    def write(record):
        if (when == 'intent_write' and record['attempts'][0]['state'] == 'intent'
                or when == 'submission_write' and record['attempts'][0]['state'] == 'submitted'):
            raise OSError('simulated storage failure')
        original(record)

    def dispatch():
        calls.append(request)
        if when == 'dispatch':
            raise TimeoutError('lost native reply')
        return receipt

    monkeypatch.setattr(store, '_write', write)
    with pytest.raises(OSError):
        store.submit(request, TARGET, window, row(False), dispatch)
    assert calls == ([] if when == 'intent_write' else [request])
    if when != 'intent_write':
        recovered = CondemnProgressStore(tmp_path)
        with pytest.raises(CondemnProgressStopped):
            recovered.assert_idle()
        with pytest.raises(CondemnProgressStopped):
            recovered.submit(str(uuid.uuid4()), TARGET, window, row(False), dispatch)
        assert calls == [request]


@pytest.mark.parametrize('change', [
    {'request': str(uuid.uuid4())}, {'lifetime': replace(LIFE, creation=12)},
    {'target': Target((101, 8), 'nation', (200, 23), (200, 23))},
])
def test_mismatched_native_receipt_does_not_release_intent(tmp_path, change):
    store, window, request, receipt = setup(tmp_path)
    with pytest.raises(CondemnProgressStopped):
        store.submit(request, TARGET, window, row(False), lambda: replace(receipt, **change))
    assert store.read()['attempts'][0]['state'] == 'intent'
    with pytest.raises(CondemnProgressStopped):
        store.assert_idle()


def test_uncertain_result_or_restarted_host_cannot_complete_with_enabled_row(tmp_path):
    store, window, request, receipt = setup(tmp_path)
    store.submit(request, TARGET, window, row(False), lambda: replace(receipt, submitted=False))
    response, = window.consume(snapshot(triple()))
    with pytest.raises(CondemnProgressStopped):
        store.observe(request, response, window, row(), 1004)
    assert store.read()['attempts'][0]['state'] == 'uncertain'


def test_restart_never_rebinds_a_pending_attempt_even_with_identical_process(tmp_path):
    store, window, request, receipt = setup(tmp_path)
    store.submit(request, TARGET, window, row(False), lambda: receipt)
    response, = window.consume(snapshot(triple()))
    recovered = CondemnProgressStore(tmp_path)
    with pytest.raises(CondemnProgressStopped):
        recovered.observe(request, response, window, row(), 1004)
    assert recovered.read()['active'] == request


@pytest.mark.parametrize('case', ['wrong_building', 'unkeyed', 'disabled', 'old_row',
                                  'changed_hud', 'lost_stream', 'different_window', 'not_drained'])
def test_only_original_healthy_interval_and_post_reply_exact_row_can_finish(tmp_path, case):
    store, window, request, receipt = setup(tmp_path)
    store.submit(request, TARGET, window, row(False), lambda: receipt)
    records = triple(building=(101, 8) if case == 'wrong_building' else
                     (0, 0) if case == 'unkeyed' else (100, 8))
    response = Response(LIFE, canonical(records))
    if case != 'not_drained':
        response, = window.consume(snapshot(records))
    observation = row(enabled=case != 'disabled')
    if case == 'changed_hud':
        observation['windows'][0]['address'] += 4
    if case == 'lost_stream':
        with pytest.raises(CondemnResponseError):
            window.invalidate()
    if case == 'different_window':
        window = ResponseWindow(LIFE, snapshot())
        window.consume(snapshot(records))
    with pytest.raises(CondemnProgressStopped):
        store.observe(request, response, window, observation, 1002 if case == 'old_row' else 1004)
    assert store.read()['active'] == request


def test_response_decoded_before_native_invocation_is_not_new_completion(tmp_path):
    store, window, request, receipt = setup(tmp_path)
    store.submit(request, TARGET, window, row(False), lambda: replace(receipt, response_floor=1))
    response, = window.consume(snapshot(triple()))
    with pytest.raises(CondemnProgressStopped):
        store.observe(request, response, window, row(), 1004)


def test_confirmed_target_scope_is_never_shared_between_guild_and_nation(tmp_path):
    store, window, request, receipt = setup(tmp_path)
    store.submit(request, TARGET, window, row(False), lambda: receipt)
    complete(store, window, request)
    assert Target(TARGET.building, 'guild', TARGET.identity, TARGET.entry) not in (
        store.verified_targets(LIFE))


def test_deleted_or_corrupt_journal_cannot_restart_from_empty(tmp_path):
    store, window, request, receipt = setup(tmp_path)
    store.submit(request, TARGET, window, row(False), lambda: receipt)
    store.path.unlink()
    with pytest.raises(CondemnProgressStopped, match='missing'):
        CondemnProgressStore(tmp_path).assert_idle()


@pytest.mark.parametrize('corrupt', [
    lambda r: r.update(active=None),
    lambda r: r['attempts'][0].update(state='state_verified'),
    lambda r: r['attempts'][0]['submission'].update(response_floor=-1),
    lambda r: r['attempts'].append(r['attempts'][0].copy()),
    lambda r: r['attempts'][0]['lifetime'].update(creation=12),
])
def test_tampered_progress_is_rejected_without_dispatch(tmp_path, corrupt):
    store, window, request, receipt = setup(tmp_path)
    store.submit(request, TARGET, window, row(False), lambda: receipt)
    record = json.loads(store.path.read_bytes())
    corrupt(record)
    store.path.write_bytes(canonical(record))
    with pytest.raises(CondemnProgressStopped):
        CondemnProgressStore(tmp_path).assert_idle()


def test_enabled_or_ambiguous_row_never_reaches_dispatch(tmp_path):
    store, window, request, receipt = setup(tmp_path)
    with pytest.raises(CondemnProgressStopped):
        store.submit(request, TARGET, window, row(), lambda: pytest.fail('would disable row'))
    assert not store.path.exists()


def test_failed_completion_write_keeps_pending_attempt_recoverable_without_toggle(
    tmp_path, monkeypatch,
):
    store, window, request, receipt = setup(tmp_path)
    store.submit(request, TARGET, window, row(False), lambda: receipt)
    original = store._write
    monkeypatch.setattr(store, '_write', lambda _: (_ for _ in ()).throw(OSError('disk')))
    with pytest.raises(OSError):
        complete(store, window, request)
    assert store.read()['active'] == request
    monkeypatch.setattr(store, '_write', original)
    response = Response(LIFE, canonical(triple()))
    store.observe(request, response, window, row(), 1004)
    store.assert_idle()


def test_two_runners_cannot_dispatch_overlapping_attempts(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    store, window, request, receipt = setup(tmp_path)
    other = CondemnProgressStore(tmp_path)
    entered, release = Event(), Event()
    calls = []

    def dispatch():
        calls.append(request)
        entered.set()
        assert release.wait(2)
        return receipt

    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(store.submit, request, TARGET, window, row(False), dispatch)
        assert entered.wait(2)
        second = pool.submit(other.submit, str(uuid.uuid4()), TARGET, window, row(False), dispatch)
        release.set()
        assert first.result() == receipt
        with pytest.raises(CondemnProgressStopped):
            second.result()
    assert calls == [request]


def test_completed_proof_is_revalidated_on_read(tmp_path):
    store, window, request, receipt = setup(tmp_path)
    store.submit(request, TARGET, window, row(False), lambda: receipt)
    complete(store, window, request)
    record = json.loads(store.path.read_bytes())
    record['attempts'][0]['completion']['response'][2]['payload']['building'] = [101, 8]
    store.path.write_bytes(canonical(record))
    with pytest.raises(CondemnProgressStopped):
        CondemnProgressStore(tmp_path).verified_targets(LIFE)
