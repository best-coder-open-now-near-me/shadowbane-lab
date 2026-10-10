
import pytest

from shadowbane_lab.manager.group_commands import GroupCommandPolicy, parse_command


def current():
    return {"scene": 7, "local": (42, 53), "group_digest": "digest",
            "members": {(123, 53): "Alice"}, "positions": {}}


def batch(records=(), *, initial=False, gap=False, sequence=None):
    return {"sequence": sequence if sequence is not None else max(
        (r["sequence"] for r in records), default=0), "initial_history": initial,
        "gap": gap, "stopped": False, "records": list(records)}


def chat(generation=2, *, text="/come", tick=1000):
    return {"sequence": generation + 1, "processing_generation": generation,
            "decode_sequence": generation - 1, "tick_ms": tick, "stage": 3,
            "flags": 15, "scene_epoch": 7, "local": (42, 53),
            "payload": {"sender": "Alice", "sender_key": (123, 53),
                        "text": text, "group_digest": "digest"}}


def ready(persist=lambda value: None):
    policy = GroupCommandPolicy((55, 66), persist=persist)
    policy.ingest(batch(initial=True), batch(initial=True), current(), allowed=True, now_ms=1000)
    return policy


@pytest.mark.parametrize("text,result", [("/come", ("come", None)),
    ("/attack Alice", ("attack", "Alice")), ("come", None),
    ("/attack[Alice]", None), ("/attack Alice]", None), ("/attack Alice Bob", None)])
def test_only_exact_commands(text, result):
    assert parse_command(text) == result


def test_disabled_history_and_inflight_decode_are_never_replayed():
    p = ready()
    p.ingest(batch([chat()]), batch(), current(), allowed=False, now_ms=1000)
    p.ingest(batch([chat(3)]), batch(), current(), allowed=True, now_ms=1001)
    assert p.pending is None
    p.ingest(batch([chat(7)]), batch(), current(), allowed=True, now_ms=1002)
    assert p.pending is not None


def test_fresh_exact_member_and_latest_generation_only():
    p = ready()
    old = chat(2)
    old["scene_epoch"] = 6
    p.ingest(batch([chat(5), old]), batch(), current(), allowed=True, now_ms=1001)
    assert p.pending.generation == 5


def test_same_name_different_key_or_ambiguous_member_rejected():
    for members in ({(99, 53): "Alice"}, {(123, 53): "Alice", (99, 53): "ALICE"}):
        c = current()
        c["members"] = members
        p = ready()
        p.ingest(batch([chat()]), batch(), c, allowed=True, now_ms=1001)
        assert p.pending is None


def test_stale_unknown_gap_and_group_change_do_not_mint_commands():
    p = ready()
    p.ingest(batch([chat()], gap=True), batch(), current(), allowed=True, now_ms=1001)
    assert p.pending is None
    p.ingest(batch([chat(7)]), batch(), current(), allowed=True, now_ms=8000)
    assert p.pending is None
    c = current()
    c["group_digest"] = "replacement"
    p.ingest(batch([chat(10)]), batch(), c, allowed=True, now_ms=1001)
    assert p.pending is None


def test_consumption_write_failure_prevents_effect():
    p = ready()
    def fail(_):
        raise OSError("full")
    p.persist = fail
    with pytest.raises(OSError):
        p.ingest(batch([chat()]), batch(), current(), allowed=True, now_ms=1001)
    assert p.pending is None


def test_positions_require_same_roster_and_per_member_fresh_native_update():
    p = ready()
    u = chat()
    u["payload"] = {"kind": 5, "group_digest": "digest",
        "positions": [{"key": (123, 53), "xyz": (70000., 100., -50000.)}]}
    p.ingest(batch([chat()]), batch([u]), current(), allowed=True, now_ms=1001)
    command = p.pending
    assert p.destination(command, current(), 1001) == (70000., 50000.)
    with pytest.raises(ValueError):
        p.destination(command, current(), 7000)
    c = current()
    c["positions"] = {(123, 53): (70001., 50001.)}
    assert p.destination(command, c, 1002) == (70001., 50001.)
    invalidate = chat(5)
    invalidate["payload"] = {
        "kind": 8, "group_digest": "digest", "positions": []}
    p.ingest(batch(sequence=3), batch([invalidate]), current(), allowed=True, now_ms=1003)
    with pytest.raises(ValueError):
        p.destination(command, current(), 1003)


def test_decoded_self_member_is_not_excluded_from_any_member_policy():
    p = ready()
    c = current()
    c["members"] = {(42, 53): "Alice"}
    r = chat()
    r["payload"]["sender_key"] = (42, 53)
    p.ingest(batch([r]), batch(), c, allowed=True, now_ms=1001)
    assert p.pending.sender_key == (42, 53)
