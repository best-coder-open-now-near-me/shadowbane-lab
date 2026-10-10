"""Native actor v3/v4 canonical boundaries; fixtures are consumed by x86 C++."""

import hashlib
import struct
from dataclasses import replace
from pathlib import Path

import pytest

from shadowbane_lab.client_extension.actor_action_fence import (
    ActorBinding,
    Authority,
    ContextBinding,
    ContextId,
    OwnerId,
    RequestId,
    State,
)
from shadowbane_lab.client_extension.actor_action_wire import (
    APPLICATION_PENDING,
    CONTEXT_CLEANUP,
    OUTBOUND_QUEUED,
    OWNER_CLEANUP,
    Action,
    Application,
    Closure,
    ClosureScope,
    Command,
    Entry,
    LocalSettlement,
    Outcome,
    Phase,
    Reason,
    Receipt,
    Recipient,
    Verb,
)
from shadowbane_lab.client_extension.movement_wire import Grant, Host, Owner


def fixture():
    grant = Grant(8, 9, Owner.AUTOMATION, "worker", "operation")
    parent = ActorBinding(
        1234,
        5678,
        10001,
        20002,
        7,
        8,
        9,
        OwnerId(1),
        (4050960, 53),
        0x12300000,
        b"n" * 32,
        b"s" * 32,
        b"o" * 32,
        hashlib.sha256(grant.encode()[24:]).digest(),
    )
    context = ContextBinding(
        parent.digest,
        ContextId(1),
        Authority.NPC,
        0x12400000,
        (23885, 37),
        0,
        bytes(32),
        bytes(32),
        bytes(32),
    )
    command = Command(
        Host(5678, 7, 20002),
        123,
        grant,
        RequestId(1),
        parent.owner_id,
        None,
        parent.digest,
        bytes(32),
        Action.USE_ITEM,
        item_key=(5802955, 30),
        template_key=(980066, 0),
        item_hint=0x12500000,
        template_hint=0x12600000,
        recipient=Recipient.ACTOR,
        selector_index=0,
        manifest_digest=b"m" * 32,
        publication_revision=7,
        snapshot_id=(7).to_bytes(16, "big"),
    )
    receipt = Receipt(
        command.request,
        command.host,
        command.window,
        Outcome.CLIENT_OUTBOUND_QUEUED,
        OWNER_CLEANUP | OUTBOUND_QUEUED | APPLICATION_PENDING,
        grant,
        parent.owner_id,
        None,
        command.digest,
        Verb.SUBMIT,
        command.action,
        Entry.ENTERED,
        LocalSettlement.SETTLED,
        Phase.BOUND,
        application=Application.PENDING,
    )
    return parent, context, command, receipt


def target_command(action=Action.ATTACK):
    p, context, c, _ = fixture()
    return (
        p,
        context,
        Command(
            c.host,
            c.window,
            c.grant,
            RequestId(2),
            c.parent_id,
            context.context_id,
            p.digest,
            context.digest,
            action,
            power_id=429545819 if action in (Action.CAST, Action.SELF_POWER) else 0,
            recipient=Recipient.ACTOR if action is Action.SELF_POWER else Recipient.TARGET,
        ),
    )


def test_exact_geometry_and_crosslanguage_goldens():
    p, context, c, r = fixture()
    for name, value in (
        ("actor_owner_v4", p),
        ("actor_context_v4", context),
        ("actor_command_v3", c),
        ("actor_receipt_v3", r),
    ):
        assert (
            value.encode().hex()
            == (Path(__file__).parent / "fixtures" / (name + ".hex")).read_text().strip()
        )
    assert len(p.encode()) == len(context.encode()) == 320
    assert len(c.encode()) == 576 and len(r.encode()) == 384
    assert struct.unpack_from("<I", c.encode(), 448) == (3,)
    assert struct.unpack_from("<I", r.encode(), 328) == (3,)
    assert ActorBinding.decode(p.encode(State.ENTERED)) == (p, State.ENTERED)
    assert ContextBinding.decode(context.encode(State.REVOKED)) == (context, State.REVOKED)
    assert Command.decode(c.encode()) == c and Receipt.decode(r.encode()) == r
    c.require_bindings(p)
    r.require_command(c, Verb.SUBMIT)


def test_full_parent_namespace_and_context_authority():
    p, context, c = target_command()
    c.require_bindings(p, context)
    for altered in (
        replace(p, scene=10),
        replace(p, actor_hint=p.actor_hint + 4),
        replace(p, producer_creation=30003),
        replace(p, owner=b"x" * 32),
    ):
        with pytest.raises(ValueError):
            c.require_bindings(altered, context)
    with pytest.raises(ValueError):
        replace(context, target_hint=p.actor_hint).require_parent(p)
    with pytest.raises(ValueError):
        replace(context, authority=Authority.MANUAL_PLAYER)
    player = replace(
        context,
        authority=Authority.MANUAL_PLAYER,
        target_key=(44, 53),
        revision=2,
        store=b"s" * 32,
        entry=b"e" * 32,
        target_name=b"t" * 32,
    )
    player.require_parent(p)


@pytest.mark.parametrize(
    "change",
    [
        dict(template_key=(980066, 30)),
        dict(item_key=(5802955, 0)),
        dict(item_hint=1),
        dict(template_hint=0),
        dict(template_hint=0x12500000),
        dict(recipient=Recipient.TARGET),
        dict(power_id=429021400),
        dict(selector_index=32),
        dict(publication_revision=0),
        dict(snapshot_id=bytes(16)),
        dict(parent_id=None),
        dict(item_key=(True, 30)),
    ],
)
def test_item_operand_and_preparation_publication_cannot_be_faked(change):
    with pytest.raises(ValueError):
        replace(fixture()[2], **change).encode()


@pytest.mark.parametrize("action", [Action.ATTACK, Action.CAST, Action.SELF_POWER])
def test_target_actions_keep_context_and_explicit_recipient(action):
    p, context, c = target_command(action)
    c.require_bindings(p, context)
    c.require_verb(Verb.SUBMIT)
    with pytest.raises(ValueError):
        c.require_verb(Verb.OPEN_OWNER)
    if action is not Action.SELF_POWER:
        with pytest.raises(ValueError):
            replace(c, context_id=None, context_digest=bytes(32)).encode()


def test_readonly_queries_cannot_serve_as_mutation_authority():
    c = Command(Host(1, 1, 2), 123, None, RequestId(1), None, None, bytes(32), bytes(32))
    c.require_verb(Verb.OBSERVE_ACTOR)
    assert Command.decode(c.encode()) == c
    for verb in (Verb.OPEN_OWNER, Verb.SUBMIT, Verb.ATTACH_CONTEXT, Verb.STOP_OWNER):
        with pytest.raises(ValueError):
            c.require_verb(verb)
    with pytest.raises(ValueError):
        fixture()[2].require_verb(Verb.OBSERVE_ACTOR)


@pytest.mark.parametrize(
    "field,value",
    [
        ("request", RequestId(2)),
        ("item_key", (5802956, 30)),
        ("template_hint", 0x12600004),
        ("manifest_digest", b"x" * 32),
        ("selector_index", 1),
        ("parent_id", OwnerId(2)),
        ("publication_revision", 8),
    ],
)
def test_every_operand_and_publication_byte_is_receipt_correlated(field, value):
    _, _, c, r = fixture()
    with pytest.raises(ValueError, match="immutable command"):
        r.require_command(replace(c, **{field: value}), Verb.SUBMIT)


def test_locally_settled_item_does_not_claim_remote_application_or_owner_release():
    _, _, c, r = fixture()
    r.require_command(c, Verb.SUBMIT)
    assert r.local_settlement is LocalSettlement.SETTLED
    assert r.application is Application.PENDING and r.flags & OWNER_CLEANUP
    unknown = replace(
        r,
        outcome=Outcome.UNCERTAIN,
        entry=Entry.UNKNOWN,
        flags=OWNER_CLEANUP | APPLICATION_PENDING,
        application=Application.UNKNOWN,
    )
    assert Receipt.decode(unknown.encode()) == unknown


def test_reuse_noentry_history_survives_stop_but_never_becomes_queue():
    p, _, c = target_command(Action.SELF_POWER)
    r = Receipt(
        c.request,
        c.host,
        c.window,
        Outcome.POWER_REUSE_BLOCKED,
        OWNER_CLEANUP | CONTEXT_CLEANUP,
        c.grant,
        p.owner_id,
        c.context_id,
        c.digest,
        Verb.SUBMIT,
        c.action,
        Entry.NEVER_ENTERED,
        LocalSettlement.SETTLED,
        Phase.BOUND,
        Phase.BOUND,
        reason=Reason.POWER_REUSE,
    )
    r.require_command(c, Verb.SUBMIT)
    history = replace(
        r,
        verb=Verb.ACTION_STATUS,
        context_phase=Phase.CLOSED,
        flags=OWNER_CLEANUP,
        closure=Closure.NATIVE_STOPPED,
        closure_scope=ClosureScope.CONTEXT,
        mode=1,
    )
    history.require_command(c, Verb.ACTION_STATUS)
    for change in (
        dict(entry=Entry.ENTERED),
        dict(flags=r.flags | OUTBOUND_QUEUED),
        dict(verb=Verb.CANCEL_ACTION),
        dict(owner_phase=Phase.UNKNOWN, flags=0),
    ):
        with pytest.raises(ValueError):
            replace(r, **change).encode()


@pytest.mark.parametrize(
    "change",
    [
        dict(closure=Closure.NONE),
        dict(mode=2),
        dict(combat_target_present=True),
        dict(flags=0),
        dict(closure_scope=ClosureScope.NONE),
    ],
)
def test_context_stop_proof_cannot_release_or_disguise_parent(change):
    p, _, c = target_command()
    control = replace(c, action=Action.NONE, recipient=Recipient.NONE)
    r = Receipt(
        control.request,
        c.host,
        c.window,
        Outcome.ENGAGEMENT_CLOSED,
        OWNER_CLEANUP,
        c.grant,
        p.owner_id,
        c.context_id,
        control.digest,
        Verb.STOP_CONTEXT,
        Action.NONE,
        owner_phase=Phase.BOUND,
        context_phase=Phase.CLOSED,
        closure=Closure.NATIVE_STOPPED,
        closure_scope=ClosureScope.CONTEXT,
        mode=1,
    )
    r.require_command(control, Verb.STOP_CONTEXT)
    with pytest.raises(ValueError):
        replace(r, **change).encode()


@pytest.mark.parametrize("index", [16, 20, 104, 319])
def test_corrupt_fence_rejects_or_changes_full_binding_digest(index):
    p = fixture()[0]
    changed = bytearray(p.encode())
    changed[index] ^= 0x80
    try:
        other, _ = ActorBinding.decode(bytes(changed))
    except ValueError:
        return
    assert other.digest != p.digest


@pytest.mark.parametrize("index", [448, 452, 575])
def test_unknown_command_version_or_reserved_bytes_rejected(index):
    raw = bytearray(fixture()[2].encode())
    raw[index] ^= 1
    with pytest.raises(ValueError):
        Command.decode(bytes(raw))


def test_expired_history_is_unknown_not_cleanup_or_never_entry():
    _, _, c, r = fixture()
    expired = replace(
        r,
        outcome=Outcome.HISTORY_EXPIRED,
        flags=0,
        entry=Entry.UNKNOWN,
        local_settlement=LocalSettlement.UNKNOWN,
        owner_phase=Phase.UNKNOWN,
        application=Application.NONE,
        closure=Closure.HISTORY_EXPIRED,
    )
    expired.require_command(c, Verb.SUBMIT)
    for change in (
        dict(entry=Entry.NEVER_ENTERED),
        dict(closure=Closure.NONE),
        dict(local_settlement=LocalSettlement.SETTLED),
    ):
        with pytest.raises(ValueError):
            replace(expired, **change).encode()


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows named fence ABI")
def test_real_windows_parent_and_child_native_consumer(monkeypatch):
    import os
    import queue
    import subprocess
    import threading

    from shadowbane_lab.client_extension.actor_action_fence import Ticket, Windows

    exe = os.environ.get("WONDERBANE_ACTOR_ACTION_TEST")
    if not exe:
        pytest.skip("WONDERBANE_ACTOR_ACTION_TEST is required for native consumer")
    process = subprocess.Popen(
        [exe, "--consumer"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    def line():
        result = queue.Queue()
        threading.Thread(target=lambda: result.put(process.stdout.readline()), daemon=True).start()
        return result.get(timeout=6).strip()

    def send(text):
        process.stdin.write(text + "\n")
        process.stdin.flush()

    parent_ticket = child_ticket = None
    try:
        client_pid, creation = map(int, line().split())
        api = Windows()
        producer_pid, producer_creation = api.identity()
        p, context, _, _ = fixture()
        p = replace(
            p,
            client_pid=client_pid,
            client_creation=creation,
            producer_pid=producer_pid,
            producer_creation=producer_creation,
        )
        context = replace(context, parent_digest=p.digest)
        parent_ticket = Ticket(p, create=True)
        child_ticket = Ticket(context, parent=p, create=True)
        parent_ticket.arm()
        child_ticket.arm()
        send(p.encode().hex())
        send(context.encode().hex())
        assert line() == "open"
        send("enter")
        assert line() == "admitted"
        assert parent_ticket.state() is State.ENTERED
        assert child_ticket.state() is State.ENTERED
        child_ticket.revoke()
        send("inspect")
        assert line() == "4 2 5 4"  # Parent retained; exact child admission revoked.
        parent_ticket.revoke()
        send("inspect")
        assert line() == "5 4 5 4"
        send("exit")
        assert process.wait(timeout=6) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=6)
        for ticket in (child_ticket, parent_ticket):
            if ticket is not None:
                ticket.close()


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows named fence ABI")
def test_fence_collision_and_failed_revoke_preserve_live_handles():
    import threading

    from shadowbane_lab.client_extension.actor_action_fence import FenceError, Ticket, Windows

    api = Windows()
    pid, creation = api.identity()
    p = replace(
        fixture()[0],
        client_pid=pid,
        client_creation=creation,
        producer_pid=pid,
        producer_creation=creation,
        owner_id=OwnerId(99),
    )
    ticket = Ticket(p, create=True)
    held, release = threading.Event(), threading.Event()

    def holder():
        with ticket.locked():
            held.set()
            assert release.wait(timeout=6)

    worker = None
    try:
        ticket.arm()
        with pytest.raises(FenceError, match="already exists"):
            Ticket(p, create=True)
        worker = threading.Thread(target=holder)
        worker.start()
        assert held.wait(timeout=6)
        with pytest.raises(FenceError, match="busy"):
            ticket.close(timeout_ms=0)
        assert ticket.view and ticket.mapping and ticket.mutex
    finally:
        release.set()
        if worker is not None:
            worker.join(timeout=6)
        ticket.close()


@pytest.mark.parametrize("local", [LocalSettlement.UNKNOWN, LocalSettlement.PENDING])
def test_closed_action_history_requires_independent_local_settlement(local):
    _, _, c, r = fixture()
    closed = replace(
        r,
        owner_phase=Phase.CLOSED,
        closure=Closure.LOCAL_RELEASED,
        closure_scope=ClosureScope.OWNER,
        flags=OUTBOUND_QUEUED | APPLICATION_PENDING,
    )
    closed.require_command(c, Verb.SUBMIT)
    assert closed.application is Application.PENDING
    with pytest.raises(ValueError, match="local action responsibility"):
        replace(closed, local_settlement=local).encode()


@pytest.mark.parametrize(
    "scope,owner,child,closure",
    [
        (ClosureScope.CONTEXT, Phase.CLOSED, Phase.CLOSED, Closure.NATIVE_STOPPED),
        (ClosureScope.CONTEXT, Phase.RETIRED, Phase.RETIRED, Closure.SCENE_RETIRED),
        (ClosureScope.OWNER, Phase.CLOSED, Phase.RETIRED, Closure.NATIVE_STOPPED),
        (ClosureScope.OWNER, Phase.RETIRED, Phase.CLOSED, Closure.SCENE_RETIRED),
    ],
)
def test_one_closure_proof_cannot_discharge_a_different_lifecycle(scope, owner, child, closure):
    p, _, c = target_command()
    r = Receipt(
        c.request,
        c.host,
        c.window,
        Outcome.ENGAGEMENT_CLOSED,
        0,
        c.grant,
        p.owner_id,
        c.context_id,
        c.digest,
        Verb.ACTION_STATUS,
        c.action,
        Entry.ENTERED,
        LocalSettlement.SETTLED,
        owner,
        child,
        closure=closure,
        closure_scope=scope,
        mode=1,
    )
    with pytest.raises(ValueError, match="closure"):
        r.encode()


@pytest.mark.parametrize(
    "reason",
    [
        Reason.TARGET_OCCUPIED,
        Reason.LOCAL_ACTION,
        Reason.NATIVE_USE,
        Reason.CHILD_CLEANUP,
        Reason.ADMISSION_CHANGED,
    ],
)
def test_typed_admission_refusal_requires_no_entry_and_exact_verb(reason):
    _, _, _, queued = fixture()
    refusal = replace(
        queued,
        outcome=Outcome.DEFERRED,
        flags=OWNER_CLEANUP,
        entry=Entry.NEVER_ENTERED,
        application=Application.NONE,
        reason=reason,
    )
    assert Receipt.decode(refusal.encode()) == refusal
    assert Receipt.decode(replace(refusal, verb=Verb.ACTION_STATUS).encode()).reason == reason
    for changes in (
        {"verb": Verb.CANCEL_ACTION},
        {"action": Action.NONE},
        {"outcome": Outcome.UNAVAILABLE},
        {"entry": Entry.ENTERED},
        {"local_settlement": LocalSettlement.PENDING},
        {"application": Application.PENDING},
        {"flags": OWNER_CLEANUP | OUTBOUND_QUEUED},
    ):
        with pytest.raises(ValueError):
            replace(refusal, **changes).encode()


@pytest.mark.parametrize("local", [LocalSettlement.PENDING, LocalSettlement.SETTLED])
def test_interrupted_receipt_keeps_original_queue_and_local_facts(local):
    _, _, command, receipt = fixture()
    interrupted = replace(receipt, application=Application.INTERRUPTED,
                          flags=receipt.flags & ~APPLICATION_PENDING, local_settlement=local)
    decoded = Receipt.decode(interrupted.encode())
    decoded.require_command(command, Verb.SUBMIT)
    assert decoded.application is Application.INTERRUPTED
    assert decoded.entry is Entry.ENTERED and decoded.flags & OUTBOUND_QUEUED
    assert decoded.local_settlement is local
    # UNKNOWN=3 is still distinct from the newly appended action value4.
    assert Application.UNKNOWN.value == 3 and Application.INTERRUPTED.value == 4


@pytest.mark.parametrize("change", ["unentered", "unqueued", "pending_flag"])
def test_interrupted_receipt_cannot_forge_terminal_application(change):
    _, _, _, receipt = fixture()
    changes = dict(application=Application.INTERRUPTED, flags=receipt.flags & ~APPLICATION_PENDING)
    if change == "unentered":
        changes["entry"] = Entry.UNKNOWN
    elif change == "unqueued":
        changes["flags"] &= ~OUTBOUND_QUEUED
    else:
        changes["flags"] |= APPLICATION_PENDING
    with pytest.raises(ValueError):
        replace(receipt, **changes).encode()


def tracking_fixture():
    parent, context, command, receipt = fixture()
    command = replace(command, action=Action.TRACK, power_id=429578587,
                      item_key=(0, 0), template_key=(0, 0), item_hint=0, template_hint=0,
                      selector_index=2**32-1, manifest_digest=bytes(32),
                      publication_revision=0, snapshot_id=bytes(16))
    receipt = replace(receipt, action=Action.TRACK, command_digest=command.digest,
                      application=Application.NONE, flags=OWNER_CLEANUP | OUTBOUND_QUEUED)
    return parent, context, command, receipt


def test_tracking_wire_is_context_free_actor_query_with_no_application():
    parent, _, command, receipt = tracking_fixture()
    command.require_bindings(parent)
    for verb in (Verb.SUBMIT, Verb.ACTION_STATUS):
        command.require_verb(verb)
        replace(receipt, verb=verb).require_command(command, verb)
    assert len(command.encode()) == 576
    assert Command.decode(command.encode()) == command
    with pytest.raises(ValueError, match="cancellation"):
        command.require_verb(Verb.CANCEL_ACTION)
    with pytest.raises(ValueError):
        replace(receipt, application=Application.PENDING,
                flags=receipt.flags | APPLICATION_PENDING).encode()


@pytest.mark.parametrize("change", [
    {"power_id": 0}, {"recipient": Recipient.TARGET},
    {"selector_index": 0, "manifest_digest": b"m"*32},
    {"item_hint": 0x12340000},
])
def test_tracking_command_rejects_other_action_operands(change):
    _, _, command, _ = tracking_fixture()
    with pytest.raises(ValueError):
        replace(command, **change).encode()


def test_tracking_cannot_borrow_context_authority():
    _, context, command, _ = tracking_fixture()
    with pytest.raises(ValueError):
        replace(command, context_id=context.context_id, context_digest=context.digest).encode()


def test_group_chat_wire_is_bounded_group_only_and_immutable():
    _, _, command, receipt = tracking_fixture()
    command = replace(command, action=Action.GROUP_CHAT, power_id=0,
                      group_digest=b"g" * 32, group_text="Hunt Foe: Alice")
    assert Command.decode(command.encode()) == command
    receipt = replace(receipt, action=Action.GROUP_CHAT, command_digest=command.digest)
    receipt.require_command(command, Verb.SUBMIT)
    receipt = replace(receipt, verb=Verb.ACTION_STATUS)
    receipt.require_command(command, Verb.ACTION_STATUS)
    with pytest.raises(ValueError):
        command.require_verb(Verb.CANCEL_ACTION)
    for fields in ({"group_text": "x" * 89}, {"group_text": "/group Alice"},
                   {"group_digest": bytes(32)}, {"power_id": 123},
                   {"action": Action.TRACK, "power_id": 429578587},
                   {"group_text": "Alice\u00c9"}):
        with pytest.raises(ValueError):
            replace(command, **fields).encode()
    poisoned = bytearray(command.encode())
    poisoned[-1] = 1
    with pytest.raises(ValueError):
        Command.decode(bytes(poisoned))


def test_real_native_group_chat_wire_roundtrip(tmp_path):
    import os
    import subprocess

    exe = os.environ.get("WONDERBANE_ACTOR_ACTION_TEST")
    if not exe:
        pytest.skip("WONDERBANE_ACTOR_ACTION_TEST is required for native consumer")
    parent, _, original, receipt = fixture()
    command = Command(
        original.host, original.window, original.grant, RequestId(7),
        parent.owner_id, None, parent.digest, bytes(32), Action.GROUP_CHAT,
        recipient=Recipient.ACTOR, group_digest=b"g" * 32,
        group_text="Hunt Foe: Alice, Bob",
    )
    receipt = replace(receipt, request=command.request, command_digest=command.digest,
                      action=Action.GROUP_CHAT, application=Application.NONE,
                      flags=OWNER_CLEANUP | OUTBOUND_QUEUED)
    paths = [tmp_path / "command.hex", tmp_path / "receipt.hex"]
    for path, value in zip(paths, (command, receipt), strict=True):
        path.write_text(value.encode().hex(), encoding="ascii")
    result = subprocess.run([exe, "--group", *map(str, paths)], capture_output=True,
                            text=True, timeout=15, check=True)
    assert result.stdout.strip() == "group chat queued wire accepted"
