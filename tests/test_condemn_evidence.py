from copy import deepcopy

import pytest

from shadowbane_lab.client_extension.condemn_evidence import (
    Lifetime,
    Response,
    ResponseWindow,
    Target,
    canonical,
    enabled_row,
)
from shadowbane_lab.client_extension.condemn_responses import CondemnResponseError

LIFE = Lifetime(7, 11, 5, (20, 53))
TARGET = Target((100, 8), "nation", (200, 23), (200, 23))


def triple(start=1, *, operation=17, building=(100, 8), entry=(200, 23), state=1):
    body = {
        "operation": operation, "status_raw": 0, "scope_raw": 0, "serialized_fields": 1,
        "building": building, "entry": entry, "character": (0, 0), "guild": (0, 0),
        "nation": (0, 0), "state_raw": state, "inverted_raw": 0,
        "reported_count_raw": 0, "rows": [],
    }
    return [dict(sequence=start + i, tick_ms=1000 + start + i, thread_id=10 if i else 12,
                 stage=stage, decode_sequence=start, scene_epoch=5, local=(20, 53),
                 flags=3 if i == 0 else 7, caller_rva=0x3625BC if i == 0 else 0x4444,
                 payload=deepcopy(body))
            for i, stage in enumerate(("decoded", "processing", "returned"))]


def snapshot(records=(), *, sequence=None, initial_history=False, **changes):
    sequence = sequence if sequence is not None else records[-1]["sequence"] if records else 0
    return dict(process_id=7, process_creation_filetime_utc=11, sequence=sequence,
                overwritten=max(0, sequence - 32), stopped=False, rejected=0, ticket_drops=0,
                records=list(records), initial_history=initial_history, missed_records=0) | changes


def row_observation(*, scope="nation", building=(100, 8), entry=(200, 23), identity=(200, 23)):
    def key(value):
        return dict(object_id=value[0], object_type=value[1])

    return dict(root_refresh_pending_raw=0, windows=[dict(
        kind="kos", context_key_raw=key(building), flags_raw=[0, 0], entries=[dict(
            row_key_raw=key(entry), identities={s: key(identity if s == scope else (0, 0))
                                              for s in ("character", "guild", "nation")},
            flags_raw=[0, 1, 0] if scope == "guild" else [0, 0, 1],
        )],
    )])


def test_complete_live_reply_is_exact_keyed_state_evidence_not_scope_or_nonce():
    window = ResponseWindow(LIFE, snapshot(initial_history=True))
    records = triple()
    assert window.consume(snapshot(records[:1])) == ()
    assert window.consume(snapshot(records[1:2])) == ()
    reply, = window.consume(snapshot(records[2:]))
    assert reply.enabled_reply(TARGET)
    assert not reply.enabled_reply(Target((101, 8), "nation", (200, 23), (200, 23)))
    assert not reply.enabled_reply(Target((100, 8), "nation", (201, 23), (201, 23)))
    # The native reply does not serialize scope. Matching it cannot supply that scope.
    guild = Target((100, 8), "guild", (200, 23), (200, 23))
    assert reply.enabled_reply(guild)
    assert enabled_row(TARGET, row_observation())
    assert not enabled_row(guild, row_observation())
    assert len(reply.digest) == 64
    original = reply.digest
    records[0]["payload"]["state_raw"] = 0
    reply.records[0]["payload"]["state_raw"] = 0
    assert reply.digest == original
    assert window.consume(snapshot(sequence=3)) == ()


@pytest.mark.parametrize("change", [
    {"operation": 12}, {"operation": 13}, {"building": (0, 0)}, {"state": 0},
])
def test_unkeyed_lists_add_responses_and_disabled_states_never_confirm_enable(change):
    reply = Response(LIFE, canonical(triple(**change)))
    assert not reply.enabled_reply(TARGET)


@pytest.mark.parametrize("field,value", [
    ("status_raw", 1), ("inverted_raw", 1), ("reported_count_raw", 1),
])
def test_other_reply_semantics_never_confirm_enable(field, value):
    records = triple()
    for record in records:
        record["payload"][field] = value
    assert not Response(LIFE, canonical(records)).enabled_reply(TARGET)


def test_interleaved_lineages_survive_drain_boundaries_and_ring_wrap():
    window = ResponseWindow(LIFE, snapshot(sequence=30, initial_history=True))
    a, b = triple(31), triple(32)
    records = [a[0], b[0], a[1], b[1], b[2], a[2]]
    for i, record in enumerate(records, 31):
        record.update(sequence=i, tick_ms=1000 + i)
    completed = []
    for record in records:
        completed.extend(window.consume(snapshot([record])))
    assert [r.records[0]["sequence"] for r in completed] == [32, 31]


def test_baseline_retains_old_losses_but_never_uses_old_response_for_progress():
    records = triple(10)
    window = ResponseWindow(LIFE, snapshot(sequence=10, rejected=3, initial_history=True))
    assert window.baseline["rejected"] == 3
    assert window.consume(snapshot(records[1:], rejected=3)) == ()
    fresh = triple(13)
    response, = window.consume(snapshot(fresh, rejected=3))
    assert response.records[0]["sequence"] == 13


@pytest.mark.parametrize("changes", [
    {"missed_records": 1}, {"rejected": 1}, {"ticket_drops": 1}, {"stopped": True},
    {"initial_history": True}, {"process_id": 8}, {"process_creation_filetime_utc": 12},
    {"sequence": 2}, {"sequence": 2**63 - 1},
])
def test_stream_loss_or_rebind_is_terminal_even_if_later_reads_are_healthy(changes):
    window = ResponseWindow(LIFE, snapshot())
    with pytest.raises(CondemnResponseError):
        window.consume(snapshot(triple(), **changes))
    with pytest.raises(CondemnResponseError):
        window.consume(snapshot(triple()))


def test_explicit_read_exception_invalidates_window_instead_of_hiding_torn_read():
    window = ResponseWindow(LIFE, snapshot())
    with pytest.raises(CondemnResponseError, match="interrupted"):
        window.invalidate()
    with pytest.raises(CondemnResponseError):
        window.consume(snapshot(triple()))


@pytest.mark.parametrize("index,field,value", [
    (0, "flags", 2), (1, "flags", 3), (2, "flags", 3),
    (0, "caller_rva", 0), (2, "caller_rva", 0),
    (1, "scene_epoch", 6), (2, "local", (21, 53)), (2, "thread_id", 99),
    (2, "tick_ms", 999), (2, "decode_sequence", 2), (1, "stage", "returned"),
    (2, "sequence", 2), (0, "scene_epoch", True),
])
def test_corruption_cannot_qualify_individual_or_streamed_response(index, field, value):
    records = triple()
    records[index][field] = value
    with pytest.raises(CondemnResponseError):
        Response(LIFE, canonical(records))
    window = ResponseWindow(LIFE, snapshot())
    with pytest.raises(CondemnResponseError):
        window.consume(snapshot(records))


def test_payload_mutation_between_stages_is_rejected():
    records = triple()
    records[2]["payload"]["state_raw"] = 0
    with pytest.raises(CondemnResponseError):
        ResponseWindow(LIFE, snapshot()).consume(snapshot(records))


def test_no_partial_results_escape_a_batch_with_later_bad_evidence():
    records = triple() + triple(4)
    records[-1]["flags"] = 3
    with pytest.raises(CondemnResponseError):
        ResponseWindow(LIFE, snapshot()).consume(snapshot(records))


def test_decodes_never_retire_silently_when_pending_capacity_is_reached():
    window = ResponseWindow(LIFE, snapshot())
    for i in range(1, 65):
        window.consume(snapshot([triple(i)[0]]))
    with pytest.raises(CondemnResponseError, match="capacity"):
        window.consume(snapshot([triple(65)[0]]))


@pytest.mark.parametrize("mutation", [
    lambda o: o.update(root_refresh_pending_raw=1),
    lambda o: o["windows"][0].update(flags_raw=[0, 1]),
    lambda o: o["windows"][0]["context_key_raw"].update(object_id=101),
    lambda o: o["windows"].append(deepcopy(o["windows"][0])),
    lambda o: o["windows"][0]["entries"].append(deepcopy(o["windows"][0]["entries"][0])),
    lambda o: o["windows"][0]["entries"][0].update(flags_raw=[0, 0, 0]),
    lambda o: o["windows"][0]["entries"][0].update(flags_raw=[0, 0, True]),
    lambda o: o["windows"][0]["entries"][0]["identities"]["guild"].update(
        object_id=200, object_type=23),
])
def test_ambiguous_inverted_or_wrong_rows_never_supply_state_evidence(mutation):
    observation = row_observation()
    mutation(observation)
    assert not enabled_row(TARGET, observation)


def test_same_numeric_guild_and_nation_keys_still_require_separate_rows():
    guild = Target((100, 8), "guild", (200, 23), (200, 23))
    assert enabled_row(guild, row_observation(scope="guild"))
    assert not enabled_row(TARGET, row_observation(scope="guild"))


@pytest.mark.parametrize("args", [
    ((100, 8), "character", (200, 53), (200, 53)),
    ((0, 0), "nation", (200, 23), (200, 23)),
    ((100, 8), "nation", (True, 23), (200, 23)),
])
def test_invalid_scope_or_keys_cannot_be_targets(args):
    with pytest.raises(CondemnResponseError):
        Target(*args)
