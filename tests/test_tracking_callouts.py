from dataclasses import replace

import pytest

from shadowbane_lab.pve.tracking import TrackingActor, TrackingContact, TrackingStatus
from shadowbane_lab.pve.tracking_callouts import TrackingAppearances

ACTOR = TrackingActor(22, 333, 4, (5, 6))


def response(generation, *names, actor=ACTOR):
    return TrackingStatus(
        enabled=True,
        state="current",
        current=True,
        generation=generation,
        observed_at=100,
        response_age_seconds=0,
        actor=actor,
        contacts=tuple(TrackingContact((100 + i, 30), name, 0) for i, name in enumerate(names)),
    )


def test_initial_history_seed_then_grouped_arrivals_once():
    policy = TrackingAppearances()
    assert policy.observe(response(1, "Alice"), group_generation=1) is None
    call = policy.observe(response(2, "Alice", "Bob Smith", "Carol"), group_generation=1)
    assert call.message == "Hunt Foe: Bob, Carol"
    assert call.first_names == ("Bob", "Carol")
    assert call.actor == ACTOR and call.group_generation == 1 and call.response_generation == 2
    assert policy.observe(response(2, "Alice", "Bob", "Carol"), group_generation=1) is None
    assert policy.observe(response(3, "Carol", "Bob", "Alice"), group_generation=1) is None


def test_failed_and_unavailable_scans_do_not_reset_presence():
    policy = TrackingAppearances()
    policy.observe(response(1), group_generation=1)
    assert policy.observe(response(2, "Alice"), group_generation=1)
    for state in ("unavailable", "stale", "waiting"):
        assert (
            policy.observe(replace(response(3), current=False, state=state), group_generation=1)
            is None
        )
    assert policy.observe(response(4), group_generation=None) is None
    assert policy.observe(response(5, "Alice"), group_generation=1) is None
    assert policy.observe(response(6), group_generation=1) is None
    assert policy.observe(response(7, "Alice"), group_generation=1).first_names == ("Alice",)


def test_old_or_duplicate_empty_response_cannot_rearm_presence():
    policy = TrackingAppearances()
    policy.observe(response(10, "Alice"), group_generation=1)
    for generation in (9, 10):
        assert policy.observe(response(generation), group_generation=1) is None
    assert policy.observe(response(11, "Alice"), group_generation=1) is None


@pytest.mark.parametrize("change", ["process", "scene", "character", "group", "reset"])
def test_ownership_change_seeds_without_backlog(change):
    policy = TrackingAppearances()
    policy.observe(response(1, "Alice"), group_generation=1)
    actor, group = ACTOR, 1
    if change == "process":
        actor = replace(ACTOR, process_creation_filetime_utc=334)
    elif change == "scene":
        actor = replace(ACTOR, scene_epoch=5)
    elif change == "character":
        actor = replace(ACTOR, object_key=(7, 8))
    elif change == "group":
        group = 2
    else:
        policy.reset()
    assert policy.observe(response(2, "Bob", actor=actor), group_generation=group) is None
    assert policy.observe(
        response(3, "Bob", "Carol", actor=actor), group_generation=group
    ).first_names == ("Carol",)


def test_first_name_identity_and_self_are_deduplicated():
    policy = TrackingAppearances()
    policy.observe(response(1), group_generation=1)
    status = response(2, "Alice One", "alice Two")
    status = replace(
        status, contacts=status.contacts + (TrackingContact(ACTOR.object_key, "Umbra", 0),)
    )
    assert policy.observe(status, group_generation=1).first_names == ("Alice",)
    assert policy.observe(response(3, "ALICE"), group_generation=1) is None


def test_unsupported_name_preserves_presence_without_stalling_supported_arrivals():
    policy = TrackingAppearances()
    policy.observe(response(1, "Alice"), group_generation=1)
    call = policy.observe(
        response(2, "Alice", "\u00c9lodie", "Bob", "/group"), group_generation=1)
    assert call.first_names == ("Bob",)
    assert policy.observe(response(3, "Alice", "\u00c9lodie", "Bob"), group_generation=1) is None
    assert policy.observe(response(4, "\u00c9lodie", "Bob", "Carol"),
                          group_generation=1).first_names == ("Carol",)


def test_bounded_single_message_counts_overflow_without_backlog():
    policy = TrackingAppearances()
    policy.observe(response(1), group_generation=1)
    names = tuple("Player" + chr(65 + i) * 20 for i in range(26))
    call = policy.observe(response(2, *names), group_generation=1)
    assert len(call.message.encode("ascii")) <= 88
    assert len(call.first_names) == 26
    assert "more)" in call.message
    assert policy.observe(response(3, *names), group_generation=1) is None


def test_history_gap_does_not_invalidate_later_complete_response():
    policy = TrackingAppearances()
    policy.observe(response(1), group_generation=1)
    # capture_incomplete refers to missed history, not truncated current rows.
    call = policy.observe(
        replace(response(7, "Alice"), capture_incomplete=True), group_generation=1
    )
    assert call.first_names == ("Alice",)


def test_stale_age_and_disabled_do_not_change_presence():
    policy = TrackingAppearances()
    policy.observe(response(1, "Alice"), group_generation=1)
    assert policy.observe(replace(response(2), response_age_seconds=21), group_generation=1) is None
    assert policy.observe(TrackingStatus(), group_generation=1) is None
    assert policy.observe(response(3, "Alice"), group_generation=1) is None


@pytest.mark.parametrize("bad", [True, 0, -1, 2**64, "1"])
def test_group_authority_cannot_be_guessed_from_invalid_token(bad):
    with pytest.raises(ValueError):
        TrackingAppearances().observe(response(1), group_generation=bad)
