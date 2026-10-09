"""Copied tracking responses and request cadence are separate state machines."""
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from shadowbane_lab.client_observation.native_tracking_ability import NativeTrackingAbility
from shadowbane_lab.pve.preparation_status import PreparationStatus, PvEProgress
from shadowbane_lab.pve.tracking import (
    TrackingActor,
    TrackingActorChanged,
    TrackingContact,
    TrackingQueryResult,
    TrackingScheduler,
    TrackingSettings,
    TrackingStatus,
)

ACTOR = TrackingActor(123, 456, 7, (100, 53))
ABILITY = NativeTrackingAbility(429578587, "Hunt Foe", "SCT-fixture", 4, 4, 0, 1)


def batch(*records, initial=False, **kw):
    return dict(process_id=123, process_creation_filetime_utc=456, records=list(records),
                initial_history=initial, stopped=False, capture_incomplete=False,
                missed_records=0, **kw)


def response(generation=2, contacts=None, **kw):
    return dict(stage="returned", flags=7, scene_epoch=7, local=(100, 53),
                processing_generation=generation, tick_ms=1000,
                payload=dict(power_id=ABILITY.power_id, contacts=(contacts if contacts is not None
                    else [dict(object_key=(200, 53), name="A player", flags_raw=1)])), **kw)


@pytest.fixture
def scheduler():
    now = SimpleNamespace(tick=1000, mono=0.0, wall=100.0)
    reader = Mock()
    reader.drain.return_value = batch(initial=True)
    query = Mock(return_value=TrackingQueryResult("queued"))
    value = TrackingScheduler(TrackingSettings(True), ABILITY, ACTOR, reader, query,
        tick_clock=lambda: now.tick, clock=lambda: now.mono, wall_clock=lambda: now.wall)
    return value, reader, query, now


def test_queued_query_does_not_create_contacts_or_response(scheduler):
    value, _, query, now = scheduler
    status = value.step()
    assert status.query_state == "queued" and status.state == "waiting"
    assert not status.current and status.generation is None and not status.contacts
    now.mono = 9.9
    value.step()
    assert query.call_count == 1
    now.mono = 10
    value.step()
    assert query.call_count == 2


def test_initial_history_is_not_a_new_result_and_identical_empty_responses_are(scheduler):
    value, reader, _, _ = scheduler
    reader.drain.return_value = batch(response(), initial=True)
    assert not value.step().current
    for generation, contacts in ((5, None), (8, None), (11, [])):
        reader.drain.return_value = batch(response(generation, contacts))
        status = value.step()
        assert status.current and status.generation == generation
    assert status.contacts == ()  # Only actual fresh native empty list means none observed.


def test_manual_response_is_awareness_without_an_automated_query(scheduler):
    value, reader, query, _ = scheduler
    reader.drain.return_value = batch(response())
    status = value.step(allow_new=False)
    assert status.current and status.contacts[0].name == "A player"
    query.assert_not_called()


@pytest.mark.parametrize("change", [
    {"flags": 3}, {"stage": "processing"},
    {"payload": {"power_id": 5, "contacts": []}},
])
def test_wrong_scene_actor_power_or_incomplete_result_does_not_become_current(scheduler, change):
    value, reader, _, _ = scheduler
    reader.drain.return_value = batch({**response(), **change})
    assert not value.step().current


def test_process_replacement_and_read_error_revoke_current_view(scheduler):
    value, reader, _, _ = scheduler
    reader.drain.return_value = batch(response())
    assert value.step().current
    reader.drain.return_value = {**batch(), "process_creation_filetime_utc": 999}
    assert value.step().state == "unavailable"
    reader.drain.side_effect = OSError("mapping unavailable")
    assert not value.step().current


def test_gap_is_reported_but_later_complete_result_remains_useful(scheduler):
    value, reader, _, _ = scheduler
    reader.drain.return_value = {**batch(response()), "capture_incomplete": True,
                                "missed_records": 10}
    status = value.step()
    assert status.current and status.capture_incomplete


def test_age_only_revokes_freshness_never_invents_new_generation(scheduler):
    value, reader, _, now = scheduler
    reader.drain.return_value = batch(response())
    status = value.step()
    assert status.at(121).state == "stale" and not status.at(121).current
    assert status.at(99).state == "unavailable"
    reader.drain.return_value = batch()
    now.tick = 22001
    now.wall = 121.001
    stale = value.step()
    assert stale.generation == 2 and not stale.current and stale.state == "stale"
    assert stale.contacts == status.contacts


def test_native_refusal_uses_request_spacing_and_unknown_only_polls_original(scheduler):
    value, _, query, now = scheduler
    query.return_value = TrackingQueryResult("not_ready", "native_use")
    assert value.step().query_state == "not_ready"
    now.mono = 1
    value.step()
    assert query.call_count == 1
    now.mono = 10
    query.return_value = TrackingQueryResult("unknown")
    value.step()
    now.mono = 10.1
    value.step(allow_new=False)
    assert query.call_args.kwargs == {"allow_new": False}


def test_unknown_prepublication_error_cannot_create_new_query_during_handoff(scheduler):
    value, _, query, _ = scheduler
    query.side_effect = OSError("preflight")
    value.step()
    query.side_effect = None
    query.return_value = TrackingQueryResult("not_ready")
    value.step(allow_new=False)
    assert query.call_args.kwargs == {"allow_new": False}


def test_awareness_roundtrips_separately_from_disabled_buffs(scheduler):
    value, reader, _, _ = scheduler
    reader.drain.return_value = batch(response())
    status = value.step()
    progress = PvEProgress(100.0, "engaging", "engaging", 0, PreparationStatus.disabled(), status)
    assert PvEProgress.from_dict(json.loads(json.dumps(progress.to_dict()))) == progress
    legacy = progress.to_dict()
    del legacy["tracking"]
    assert PvEProgress.from_dict(legacy).tracking == TrackingStatus()


@pytest.mark.parametrize("changes", [
    {"current": True}, {"contacts": (TrackingContact((1, 2), "name", 0),)},
    {"generation": 1}, {"enabled": True}, {"freshness_seconds": 0},
])
def test_status_rejects_fabricated_current_contacts_and_partial_identity(changes):
    with pytest.raises(ValueError):
        replace(TrackingStatus(), **changes)


def test_out_of_order_nested_returns_keep_greatest_processing_generation(scheduler):
    value, reader, _, _ = scheduler
    reader.drain.return_value = batch(response(8, []), response(5))
    status = value.step()
    assert status.generation == 8 and status.contacts == ()


def test_actual_publication_reader_feeds_identical_and_empty_native_generations():
    from test_tracking_publication import Memory, fixture

    from shadowbane_lab.client_extension.tracking_publication import TrackingResponseReader

    memory = Memory(fixture())
    reader = TrackingResponseReader(7, 11, memory)
    value = TrackingScheduler(TrackingSettings(True), ABILITY,
        TrackingActor(7, 11, 5, (20, 53)), reader,
        lambda *_args, **_kwargs: TrackingQueryResult("queued"),
        tick_clock=lambda: 1010, clock=lambda: 0, wall_clock=lambda: 100)
    assert not value.step().current
    memory.data = fixture(6)
    status = value.step()
    assert status.current and status.generation == 5 and status.contacts[0].name == "Praeda"
    memory.data = fixture(9, count=0)
    status = value.step()
    assert status.current and status.generation == 8 and status.contacts == ()


@pytest.mark.parametrize("changed", [{"scene_epoch": 8}, {"local": (999, 53)}])
def test_new_complete_other_actor_or_scene_revokes_contacts_and_requires_owner_recovery(
        scheduler, changed):
    value, reader, query, _ = scheduler
    reader.drain.return_value = batch(response())
    assert value.step().current
    before = query.call_count
    reader.drain.return_value = batch({**response(5), **changed})
    with pytest.raises(TrackingActorChanged):
        value.step()
    assert not value.status.current and value.status.state == "unavailable"
    assert query.call_count == before


def test_older_nested_other_scene_return_cannot_retire_newer_awareness(scheduler):
    value, reader, _, _ = scheduler
    reader.drain.return_value = batch(response(8), {**response(5), "scene_epoch": 6})
    assert value.step().generation == 8


def test_correlated_terminal_query_owner_reaches_existing_recovery_boundary(scheduler):
    value, reader, query, _ = scheduler
    reader.drain.return_value = batch(response())
    query.side_effect = TrackingActorChanged("retired")
    with pytest.raises(TrackingActorChanged):
        value.step()
    assert not value.status.current and value.status.state == "unavailable"
