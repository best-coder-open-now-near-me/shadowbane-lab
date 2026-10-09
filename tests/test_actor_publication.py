import os
import queue
import subprocess
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest

from shadowbane_lab.client_extension import actor_publication as p
from shadowbane_lab.client_extension.actor_selector_manifest import Manifest, Selector


def manifest():
    return Manifest(
        123,
        321,
        456,
        654,
        1,
        bytes([1]) * 32,
        bytes([2]) * 32,
        1,
        (Selector(0, 0, 3, 111, 0, 111, 0),),
    )


def header(m=None, nonce=bytes([3]) * 16):
    m = m or manifest()
    return p._HEADER.pack(
        b"WBAPUB2\0",
        2,
        p.SIZE,
        m.client_pid,
        p.SLOT_SIZE,
        2,
        0,
        m.client_creation,
        nonce,
        m.digest,
        4050960,
        53,
        0x21000000,
        0,
        1,
        0,
        bytes(140),
    )


def frame(*, revision=1, sequence=2, tick=100, ready=1, unknown=0, admission=None, blocks=0):
    value = bytearray(p.SLOT_SIZE)
    value[:256] = p._FRAME.pack(
        sequence,
        revision,
        bytes([revision]) * 16,
        tick,
        1 if not unknown else 0,
        unknown,
        int(not unknown),
        0,
        1 if not unknown else 0,
        0,
        1 if not unknown else 0,
        1 if not unknown else 0,
        int(not unknown),
        revision if admission is None else admission,
        blocks,
        bytes(164),
    )
    if not unknown:
        values = [0, 0, 3, 111, 0, 0, 111, 0, 40, 0, 2, 0, 3, 1, ready, 0, 1] + [0] * 9
        value[10496:10624] = p._READY.pack(*values, bytes(24))
        value[18688:18704] = p._DESCRIPTOR.pack(222, 333, 0, 0, 0, bytes(2))
    return bytes(value)


def decode(payload=None):
    return p.Publication.decode(p.Header.decode(header()), payload or frame(), manifest())


def test_complete_native_descriptor_and_readiness_copy():
    result = decode()
    assert result.complete and result.revision == 1 and result.initiation_clear
    assert result.actions[0].coverage is p.Coverage.MISSING
    assert result.actions[0].readiness is p.Readiness.READY
    assert result.actions[0].descriptors[0].descriptor_id == 222
    assert result.identity.actor_key == (4050960, 53)


def test_unknown_is_explicit_and_has_no_absence_authority():
    result = decode(frame(unknown=6))
    assert not result.complete and result.unknown == 6
    assert not result.actions and not result.effects and not result.applications


@pytest.mark.parametrize(
    "offset,value",
    [
        (0, 3),
        (48, 11),
        (52, 2),
        (60, 33),
        (68, 257),
        (72, 0),
        (76, 2),
        (80, 0),
        (88, 64),
        (92, 1),
        (22784, 1),
        (10496 + 13 * 4, 3),
        (10496 + 15 * 4, 1),
        (10496 + 16 * 4, 65),
        (10496 + 17 * 4, 1),
        (10496 + 26 * 4, 1),
        (18688, 0),
        (18688 + 13, 2),
    ],
)
def test_corrupt_or_unqualified_frame_rejected(offset, value):
    data = bytearray(frame())
    if offset == 18688 + 13:
        data[offset] = value
    else:
        data[offset : offset + 4] = value.to_bytes(4, "little")
    with pytest.raises(p.PublicationError):
        decode(bytes(data))


def test_unknown_cannot_retain_old_coverage():
    data = bytearray(frame(unknown=6))
    data[18688] = 1
    with pytest.raises(p.PublicationError):
        decode(bytes(data))


def test_application_uncertainty_and_local_settlement_are_independent():
    data = bytearray(frame())
    data[64:68] = (1).to_bytes(4, "little")
    data[14592:14720] = p._APPLICATION.pack(
        manifest().group_digest(0), bytes([8]) * 32, 1, 0, 2, 1, 1, 0, bytes(32)
    )
    result = decode(bytes(data))
    assert result.applications[0].entry == 2
    assert result.applications[0].state == 1 and result.applications[0].local_settled
    assert not result.applications[0].queued


@pytest.mark.parametrize(
    "entry,state,local,queued,observed",
    [(0, 1, 1, 0, 0), (2, 1, 1, 1, 0), (1, 2, 1, 1, 1), (1, 1, 2, 1, 0), (1, 1, 1, 1, 5)],
)
def test_false_application_proof_rejected(entry, state, local, queued, observed):
    data = bytearray(frame())
    data[64:68] = (1).to_bytes(4, "little")
    data[14592:14720] = p._APPLICATION.pack(
        manifest().group_digest(0),
        bytes([8]) * 32,
        1,
        observed,
        entry,
        state,
        local,
        queued,
        bytes(32),
    )
    with pytest.raises(p.PublicationError):
        decode(bytes(data))


class Session:
    def __init__(self):
        self.binding = SimpleNamespace(
            process_id=123,
            process_creation_filetime_utc=456,
            executable_sha256="0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d",
            object_key=SimpleNamespace(object_type=4050960, object_uuid=53),
        )
        self.calls = 0
        self.fail_at = None

    def require_current(self):
        self.calls += 1
        if self.calls == self.fail_at:
            raise RuntimeError("session revoked")


def reader(monkeypatch):
    current = [p.Header.decode(header()), frame()]
    monkeypatch.setattr(p, "_copy_mapping", lambda _: tuple(current))
    monkeypatch.setattr(p, "_tick", lambda: 110)
    session = Session()
    return p.Reader(session, manifest()), current, session


def test_reader_preserves_full_content_identity_and_freshness(monkeypatch):
    r, current, session = reader(monkeypatch)
    first = r.read()
    current[1] = frame(sequence=4, tick=105)
    fresh = r.read()
    assert fresh.snapshot_id == first.snapshot_id and session.calls == 4
    current[1] = frame(sequence=6, revision=2, ready=5)
    assert r.read().actions[0].readiness is p.Readiness.POWER_REUSE


def test_same_revision_mutated_facts_rejected(monkeypatch):
    r, current, _ = reader(monkeypatch)
    r.read()
    current[1] = frame(sequence=4, ready=5)
    with pytest.raises(p.PublicationError, match="same native revision"):
        r.read()


def test_lifetime_substitution_permanently_revokes_reader(monkeypatch):
    r, current, _ = reader(monkeypatch)
    r.read()
    old = current[0]
    current[0] = p.Header.decode(header(nonce=bytes([4]) * 16))
    with pytest.raises(p.PublicationError, match="lifetime changed"):
        r.read()
    current[0] = old
    with pytest.raises(p.PublicationError, match="was revoked"):
        r.read()


@pytest.mark.parametrize("tick", [111, 1])
def test_stale_or_future_frame_cannot_be_used(monkeypatch, tick):
    r, current, _ = reader(monkeypatch)
    r.max_age_ms = 50
    current[1] = frame(tick=tick)
    with pytest.raises(p.PublicationError, match="freshness"):
        r.read()


def test_final_session_revocation_propagates(monkeypatch):
    r, _, session = reader(monkeypatch)
    session.fail_at = 2
    with pytest.raises(RuntimeError, match="session revoked"):
        r.read()
    assert r.last is None


def test_manifest_and_actor_binding_rejected(monkeypatch):
    r, current, session = reader(monkeypatch)
    current[0] = replace(
        current[0], identity=replace(current[0].identity, manifest_digest=bytes([9]) * 32)
    )
    with pytest.raises(p.PublicationError, match="manifest/process"):
        r.read()
    current[0] = p.Header.decode(header())
    session.binding.object_key = SimpleNamespace(object_type=999, object_uuid=53)
    with pytest.raises(p.PublicationError, match="actor key"):
        r.read()


def test_real_native_publication_mapping_roundtrip():
    executable = os.environ.get("SHADOWBANE_ACTOR_PUBLICATION_TEST_EXE")
    if os.name != "nt" or not executable:
        pytest.skip("requires reviewed x86 native publication fixture")
    process = subprocess.Popen(
        [executable, "ipc"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    lines = queue.Queue()

    def receive():
        for line in process.stdout:
            lines.put(line.strip())

    thread = threading.Thread(target=receive, daemon=True)
    thread.start()

    def command(value):
        process.stdin.write(value + "\n")
        process.stdin.flush()
        return lines.get(timeout=3)

    try:
        pid, creation = map(int, lines.get(timeout=3).split())
        m = Manifest(
            pid,
            pid,
            creation,
            creation,
            1,
            bytes([1]) * 32,
            bytes([2]) * 32,
            1,
            (Selector(0, 0, 3, 111, 0, 111, 0),),
        )
        session = Session()
        session.binding.process_id = pid
        session.binding.process_creation_filetime_utc = creation
        reader = p.Reader(session, m)
        first = reader.read()
        assert first.complete and first.actions[0].readiness is p.Readiness.READY
        assert command("same") == "published"
        second = reader.read()
        assert second.revision == first.revision and second.snapshot_id == first.snapshot_id
        assert second.sequence > first.sequence
        assert command("journal") == "published"
        journal = reader.read()
        assert journal.revision > second.revision
        assert journal.admission_revision == second.admission_revision
        assert journal.applications and journal.applications[0].entry == 0
        assert command("occupied") == "published"
        occupied = reader.read()
        assert occupied.admission_blocks == p.AdmissionBlock.FOREIGN_TARGET
        assert occupied.admission_revision > journal.admission_revision
        assert command("clear") == "published"
        clear = reader.read()
        assert not clear.admission_blocks
        assert clear.admission_revision > occupied.admission_revision
        assert command("race") == "published"
        race = reader.read()
        assert not race.admission_blocks and race.eligibility_facts() == clear.eligibility_facts()
        assert race.admission_revision > clear.admission_revision
        assert command("reuse") == "published"
        reuse = reader.read()
        assert reuse.revision > second.revision
        assert reuse.actions[0].readiness is p.Readiness.POWER_REUSE
        assert command("unknown") == "published"
        unknown = reader.read()
        assert not unknown.complete and not unknown.actions and unknown.revision > reuse.revision
        assert command("close") == "closed"
        assert process.wait(timeout=3) == 0
        with pytest.raises((FileNotFoundError, p.PublicationError)):
            reader.read()
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()
        thread.join(timeout=1)


def test_v1_publication_is_not_admission_authority():
    old = bytearray(header())
    old[:8] = b"WBAPUB1\0"
    old[8:12] = (1).to_bytes(4, "little")
    with pytest.raises(p.PublicationError):
        p.Header.decode(bytes(old))
    assert "ActorPublication.v2." in p.mapping_name(manifest())


@pytest.mark.parametrize("blocks", [1, 2, 4, 8, 16, 31])
def test_resource_readiness_is_distinct_from_shared_admission(blocks):
    observed = decode(frame(blocks=blocks, admission=17))
    assert observed.actions[0].readiness is p.Readiness.READY
    assert observed.admission_blocks == blocks and observed.admission_revision == 17


def test_unknown_frame_cannot_claim_admission_block():
    with pytest.raises(p.PublicationError):
        decode(frame(unknown=6, blocks=8))


def test_admission_revision_monotonic_independent_of_full_revision(monkeypatch):
    r, current, _ = reader(monkeypatch)
    current[1] = frame(admission=3)
    first = r.read()
    current[1] = frame(sequence=4, revision=2, admission=3)
    assert r.read().admission_revision == first.admission_revision
    current[1] = frame(sequence=6, revision=3, admission=2)
    with pytest.raises(p.PublicationError, match="admission revision regressed"):
        r.read()


def test_same_full_revision_cannot_mutate_admission_facts(monkeypatch):
    r, current, _ = reader(monkeypatch)
    r.read()
    current[1] = frame(sequence=4, blocks=8)
    with pytest.raises(p.PublicationError, match="same native revision"):
        r.read()


@pytest.mark.parametrize("change", ["readiness", "mode", "blocks", "unknown", "rank"])
def test_same_admission_revision_cannot_change_semantic_eligibility(monkeypatch, change):
    r, current, _ = reader(monkeypatch)
    r.read()
    payload = bytearray(
        frame(
            sequence=4,
            revision=2,
            admission=1,
            ready=5 if change == "readiness" else 1,
            blocks=8 if change == "blocks" else 0,
            unknown=6 if change == "unknown" else 0,
        )
    )
    if change == "mode":
        payload[72:76] = (2).to_bytes(4, "little")
    if change == "rank":
        payload[10496 + 32 : 10496 + 36] = (41).to_bytes(4, "little")
    current[1] = bytes(payload)
    with pytest.raises(p.PublicationError, match="admission revision changed eligibility"):
        r.read()


def test_same_admission_revision_allows_descriptor_detail_and_effect_epoch(monkeypatch):
    r, current, _ = reader(monkeypatch)
    first = r.read()
    payload = bytearray(frame(sequence=4, revision=2, admission=1))
    payload[40:48] = (2).to_bytes(8, "little")
    payload[18688:18692] = (223).to_bytes(4, "little")
    current[1] = bytes(payload)
    second = r.read()
    assert second.eligibility_facts() == first.eligibility_facts()
    assert second.actions != first.actions and second.effect_epoch != first.effect_epoch


def item_and_power_frame(readiness=p.Readiness.UNKNOWN, operand=None, *, clear=True, power_ready=1):
    m = replace(
        manifest(),
        group_count=2,
        selectors=(Selector(0, 0, 4, 0, 980066, 429021400, 0), Selector(1, 1, 3, 111, 0, 111, 0)),
    )
    data = bytearray(frame())
    data[76:80] = int(clear).to_bytes(4, "little")
    data[60:64] = (2).to_bytes(4, "little")
    data[68:72] = (2).to_bytes(4, "little")
    power = list(p._READY.unpack_from(data, 10496))
    power[:8] = list(p._READY.unpack(m.selectors[1].encode() + bytes(96)))[:8]
    power[15] = 1
    power[14] = power_ready
    data[10624:10752] = p._READY.pack(*power)
    item = list(power)
    item[:8] = list(p._READY.unpack(m.selectors[0].encode() + bytes(96)))[:8]
    item[8:13] = [0] * 5
    item[14:17] = [readiness, 0, 1]
    item[17:26] = [0] * 9 if operand is None else operand
    data[10496:10624] = p._READY.pack(*item)
    data[18704:18720] = p._DESCRIPTOR.pack(223, 334, 0, 0, 0, bytes(2))
    return p.Publication.decode(p.Header.decode(header(m)), bytes(data), m)


@pytest.mark.parametrize("readiness", [p.Readiness.UNKNOWN, p.Readiness.ITEM_UNAVAILABLE])
def test_empty_item_resource_does_not_discard_independent_power_facts(readiness):
    result = item_and_power_frame(readiness)
    assert result.complete
    assert result.actions[0].readiness is readiness
    assert result.actions[0].item_key == (0, 0) and result.actions[0].item_hint == 0
    assert result.actions[0].coverage is p.Coverage.MISSING
    assert result.actions[1].readiness is p.Readiness.READY


@pytest.mark.parametrize("index", range(9))
def test_unknown_item_cannot_retain_any_partial_operand(index):
    operand = [0] * 9
    operand[index] = 1
    with pytest.raises(p.PublicationError, match="unknown item contains operand"):
        item_and_power_frame(operand=operand)


def test_unknown_item_cannot_retain_even_previously_valid_operand():
    operand = [5802955, 30, 980066, 0, 0x12500000, 0x12600000, 3, 8, 10]
    with pytest.raises(p.PublicationError, match="unknown item contains operand"):
        item_and_power_frame(operand=operand)
    result = item_and_power_frame(p.Readiness.READY, operand)
    assert result.actions[0].item_key == (5802955, 30)


def test_ready_item_requires_full_qualified_operand():
    with pytest.raises(p.PublicationError, match="unavailable item"):
        item_and_power_frame(p.Readiness.READY)
    with pytest.raises(p.PublicationError, match="unqualified retained item"):
        item_and_power_frame(p.Readiness.READY, [5802955, 30, 980066, 0, 0x12500000, 0, 3, 8, 10])


def test_stationary_item_readiness_does_not_make_retained_id_power_ready():
    operand = [5802955, 30, 980066, 0, 0x12500000, 0x12600000, 3, 8, 10]
    result = item_and_power_frame(
        p.Readiness.READY, operand, clear=False, power_ready=p.Readiness.INITIATION_PENDING
    )
    assert not result.initiation_clear
    assert result.actions[0].readiness is p.Readiness.READY
    assert result.actions[1].readiness is p.Readiness.INITIATION_PENDING
    with pytest.raises(p.PublicationError, match="ready power"):
        item_and_power_frame(p.Readiness.READY, operand, clear=False)

@pytest.mark.parametrize("digest,allowed", [
    ("e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437", True),
    ("78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903", True),
    ("381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5", False),
    ("e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e", False),
    ("ff" * 32, False),
])
def test_exact_successor_image_preserves_publication_session_gate(monkeypatch, digest, allowed):
    r, current, session = reader(monkeypatch)
    session.binding.executable_sha256 = digest
    if allowed:
        assert r.read().complete
        current[1] = frame(sequence=4, tick=105)
        assert r.read().identity == r.identity
    else:
        monkeypatch.setattr(p, "_copy_mapping",
                            lambda _: pytest.fail("unqualified image read mapping"))
        with pytest.raises(p.PublicationError, match="unqualified publication session"):
            r.read()
