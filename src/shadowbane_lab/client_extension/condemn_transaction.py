"""Durable composite Condemn transactions in the existing per-client progress store.

Every potentially mutating continuation has its own write-ahead record. A lost
reply retains that record; process/session replacement never resumes it. Phase
boundaries retain full receipts, while idle polls retain UUIDs and the latest
receipt, keeping bounded storage without discarding uncertain dispatches.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from shadowbane_lab.record_store import exclusive_record_lock

from .condemn_evidence import Lifetime, Response, canonical, integer
from .condemn_evidence import Target as EvidenceTarget
from .condemn_progress import MAX_ATTEMPTS, CondemnProgressStopped, request_key
from .condemn_wire import UNRESOLVED, Command, Outcome, Phase, Receipt, Verb

MAX_POLLS = 512
MAX_CANCELLED_POLLS = 3
TERMINAL = {"state_verified", "already_enabled", "not_submitted"}
NO_START = {Outcome.STALE, Outcome.UNAVAILABLE, Outcome.INVALID, Outcome.EXHAUSTED}
NEXT = {
    Phase.IDLE: {Phase.IDLE, Phase.OPENING, Phase.ADDING, Phase.ENABLING, Phase.EXISTING},
    Phase.OPENING: {Phase.OPENING, Phase.ADDING, Phase.ENABLING, Phase.EXISTING},
    Phase.ADDING: {Phase.ADDING, Phase.ENABLING},
    Phase.ENABLING: {Phase.ENABLING, Phase.VERIFIED},
    Phase.VERIFIED: {Phase.VERIFIED},
    Phase.EXISTING: {Phase.EXISTING},
}


@dataclass(frozen=True, slots=True)
class Observation:
    receipt: Receipt
    tick: int
    response: Response | None = None

    def __post_init__(self):
        if type(self.receipt) is not Receipt:
            raise ValueError("typed native Condemn receipt required")
        self.receipt.encode()
        integer(self.tick, minimum=1)
        if self.receipt.action_tick > self.tick:
            raise ValueError("native action is newer than its observation")
        if self.response is not None and type(self.response) is not Response:
            raise ValueError("typed original response required")


def _bytes(value, size):
    if not isinstance(value, str) or len(value) != size * 2:
        raise ValueError("invalid saved Condemn payload size")
    raw = bytes.fromhex(value)
    if raw.hex() != value:
        raise ValueError("noncanonical saved Condemn payload")
    return raw


def _receipt(value):
    if set(value) != {"receipt", "tick"}:
        raise ValueError("invalid saved native observation")
    return Observation(Receipt.decode(_bytes(value["receipt"], 384)), value["tick"])


def queued_expiry(attempt):
    """Prove the queue cancelled an initial Ensure before the owner took it.

    Deliberately excludes snapshot staleness, availability errors, continuations,
    and every receipt carrying controller state. The native queue's atomic take
    barrier makes this empty STALE receipt a positive no-execution result.
    The caller must obtain the attempt through a validated progress-store read.
    """
    if attempt.get("kind") != "native" or attempt.get("state") != "not_submitted":
        return False
    r = _receipt(attempt["last"]).receipt
    return (
        not attempt["polls"]
        and attempt["pending"] is None
        and not attempt["boundaries"]
        and attempt["completion"] is None
        and _empty_queue_expiry(r)
    )


def _empty_queue_expiry(r):
    return (
        r.outcome == Outcome.STALE
        and r.flags == 0
        and r.snapshot.empty
        and r.target is None
        and r.transition_target is None
        and r.transition_request is None
        and r.phase == Phase.IDLE
        and r.action_tick == r.response_floor == r.completion_sequence == 0
    )


def _cancelled_polls(a, original):
    cancelled = a.get("cancelled_polls", [])
    if (
        not isinstance(cancelled, list)
        or len(cancelled) > MAX_CANCELLED_POLLS
        or "cancelled_polls" in a and not cancelled
    ):
        raise ValueError("invalid cancelled Condemn poll history")
    keys, previous = set(), -1
    for saved in cancelled:
        r = _receipt(saved).receipt
        if (
            not _empty_queue_expiry(r)
            or r.request_key not in a["polls"]
            or r.host != original.host
            or r.window != original.window
        ):
            raise ValueError("unproven cancelled Condemn poll")
        index = a["polls"].index(r.request_key)
        if index <= previous:
            raise ValueError("cancelled Condemn poll order changed")
        keys.add(r.request_key)
        previous = index
    return keys


def _saved(observed):
    return {"receipt": observed.receipt.encode().hex(), "tick": observed.tick}


def _original(attempt):
    return Command.decode(_bytes(attempt["command"], 576), Verb.ENSURE)


def _owner(original, receipt, life):
    s, before = receipt.snapshot, original.expected
    if (
        receipt.host != original.host
        or receipt.window != original.window
        or receipt.target != original.target
        or receipt.transition_target != original.target
        or receipt.transition_request != original.request_key
    ):
        raise ValueError("Condemn transition owner changed")
    if not s.empty and (
        s.scene != life.scene_epoch
        or s.local != life.local
        or (s.root, s.manager, s.building_hud, s.building)
        != (before.root, before.manager, before.building_hud, before.building)
    ):
        raise ValueError("Condemn scene or building owner changed")


def _enabled(original, receipt):
    s = receipt.snapshot
    return (
        not s.empty
        and s.owned_list(original.target)
        and s.enabled == 1
        and s.entry != 0
        and s.entry_key[0] != 0
    )


def _progress(previous, current):
    if current.phase == Phase.UNCERTAIN:
        return
    if current.phase not in NEXT.get(previous.phase, set()):
        raise ValueError("Condemn phase regressed or skipped its enable")
    if current.phase == previous.phase:
        if (current.action_tick, current.response_floor) != (
            previous.action_tick,
            previous.response_floor,
        ):
            raise ValueError("Condemn repeated an action within one phase")
    elif (
        current.action_tick < previous.action_tick
        or current.response_floor < previous.response_floor
    ):
        raise ValueError("Condemn action clock or response floor regressed")
    if current.completion_sequence < previous.completion_sequence:
        raise ValueError("Condemn completion evidence regressed")


def validate_attempt(a):
    if (
        set(a) - {"cancelled_polls"}
        != {
            "kind",
            "request",
            "owner",
            "lifetime",
            "baseline",
            "command",
            "state",
            "polls",
            "pending",
            "last",
            "boundaries",
            "completion",
        }
        or a["kind"] != "native"
    ):
        raise ValueError("invalid composite Condemn record")
    request_key(a["owner"])
    original, life = _original(a), Lifetime(**a["lifetime"])
    if (
        original.request_key != request_key(a["request"])
        or original.expected.scene != life.scene_epoch
        or original.expected.local != life.local
    ):
        raise ValueError("Condemn intent lifetime mismatch")
    if a["state"] not in {"intent", "submitted", "uncertain"} | TERMINAL:
        raise ValueError("invalid composite Condemn state")
    if set(a["baseline"]) != {"sequence", "rejected", "ticket_drops", "read_errors"}:
        raise ValueError("invalid composite response baseline")
    for v in a["baseline"].values():
        integer(v, 2**63 - 1)
    polls = a["polls"]
    if not isinstance(polls, list) or len(polls) > MAX_POLLS:
        raise ValueError("Condemn continuation history exceeds its bound")
    seen = {original.request_key}
    for p in polls:
        if request_key(p) in seen:
            raise ValueError("repeated Condemn continuation")
        seen.add(p)
    cancelled = _cancelled_polls(a, original)
    effective = [p for p in polls if p not in cancelled]
    last_request = polls[-1] if polls else original.request_key
    if a["pending"] is not None:
        verb = Verb.INSPECT if polls else Verb.ENSURE
        pending = Command.decode(_bytes(a["pending"], 576), verb)
        if (
            pending.request_key != last_request
            or pending.request_key in cancelled
            or len(cancelled) >= MAX_CANCELLED_POLLS
            or pending.host != original.host
            or pending.window != original.window
            or pending.target != original.target
            or (polls and pending.transition_request != original.request_key)
            or (not polls and pending != original)
            or a["state"] in TERMINAL
        ):
            raise ValueError("pending Condemn dispatch does not match its intent")
        effective = effective[:-1]
        last_request = effective[-1] if effective else original.request_key if polls else None
    else:
        last_request = effective[-1] if effective else original.request_key
    if a["last"] is None:
        if a["state"] != "intent" or last_request is not None or a["boundaries"] or a["completion"]:
            raise ValueError("Condemn intent lacks submission evidence")
        return
    observation = _receipt(a["last"])
    r = observation.receipt
    if r.request_key != last_request or r.host != original.host or r.window != original.window:
        raise ValueError("saved Condemn receipt correlation mismatch")
    if a["state"] == "not_submitted":
        if polls or r.outcome not in NO_START or a["pending"] or a["boundaries"] or a["completion"]:
            raise ValueError("unproven no-action result")
        return
    _owner(original, r, life)
    boundaries = a["boundaries"]
    if not isinstance(boundaries, list) or not 1 <= len(boundaries) <= 7:
        raise ValueError("invalid Condemn action boundaries")
    previous, previous_index, previous_tick = None, -1, 0
    order = [original.request_key, *effective]
    enable = None
    for saved in boundaries:
        b = _receipt(saved)
        _owner(original, b.receipt, life)
        if b.receipt.request_key not in order:
            raise ValueError("Condemn boundary has no dispatch intent")
        index = order.index(b.receipt.request_key)
        if index <= previous_index or b.tick < previous_tick:
            raise ValueError("Condemn boundary order changed")
        if b.receipt.action_tick and b.receipt.response_floor < a["baseline"]["sequence"]:
            raise ValueError("Condemn boundary precedes its response interval")
        if previous is not None:
            _progress(previous, b.receipt)
            if previous.phase == b.receipt.phase:
                raise ValueError("duplicate Condemn phase boundary")
        if b.receipt.phase == Phase.ENABLING:
            enable = b.receipt
            if (
                not enable.snapshot.owned_list(original.target)
                or not enable.snapshot.entry
                or enable.snapshot.enabled
            ):
                raise ValueError("enable boundary lacks its scoped row")
        previous, previous_index, previous_tick = b.receipt, index, b.tick
    if cancelled:
        # Cancelled polls retain transport proof, never phase/completion authority.
        # Compare their clocks with every retained surrounding owner observation.
        all_order = [original.request_key, *polls]
        timed = [*boundaries, a["last"], *a.get("cancelled_polls", [])]
        timed.sort(key=lambda item: all_order.index(_receipt(item).receipt.request_key))
        ticks = [_receipt(item).tick for item in timed]
        if ticks != sorted(ticks):
            raise ValueError("cancelled Condemn poll clock regressed")
    _progress(previous, r)
    if observation.tick < previous_tick:
        raise ValueError("Condemn observation clock regressed")
    if a["state"] == "uncertain":
        if r.phase != Phase.UNCERTAIN or not r.flags & UNRESOLVED or a["completion"]:
            raise ValueError("uncertain Condemn result changed")
        return
    if r.flags & UNRESOLVED or r.outcome not in (
        Outcome.OBSERVED,
        Outcome.SUBMITTED,
        Outcome.PENDING,
    ):
        raise ValueError("invalid active Condemn result")
    if a["state"] == "already_enabled":
        if (
            a["pending"]
            or r.phase != Phase.EXISTING
            or not _enabled(original, r)
            or any(_receipt(b).receipt.phase in (Phase.ADDING, Phase.ENABLING) for b in boundaries)
            or a["completion"]
        ):
            raise ValueError("existing enabled state is not qualified")
        return
    if a["state"] == "submitted":
        if a["completion"] or r.phase == Phase.EXISTING:
            raise ValueError("unfinished Condemn has contradictory completion")
        return
    if a["state"] != "state_verified" or a["pending"] or enable is None:
        raise ValueError("Condemn lacks enable completion")
    proof = a["completion"]
    if set(proof) != {"response", "sha256"}:
        raise ValueError("invalid Condemn completion proof")
    response = Response(life, canonical(proof["response"]))
    first, _, last = response.records
    target = EvidenceTarget(
        original.target.building,
        "guild" if original.target.scope == 4 else "nation",
        original.target.identity,
        enable.snapshot.entry_key,
    )
    if (
        r.phase != Phase.VERIFIED
        or not _enabled(original, r)
        or (r.action_tick, r.response_floor) != (enable.action_tick, enable.response_floor)
        or r.snapshot.entry_key != target.entry
        or response.digest != proof["sha256"]
        or not response.enabled_reply(target)
        or first["sequence"] <= enable.response_floor
        or first["tick_ms"] < enable.action_tick
        or last["tick_ms"] > observation.tick
        or r.completion_sequence != last["sequence"]
    ):
        raise ValueError("Condemn response and later scoped row do not qualify")


def _apply(a, observation, window):
    if (
        type(observation) is not Observation
        or window.failure
        or window.lifetime != Lifetime(**a["lifetime"])
    ):
        raise CondemnProgressStopped("Condemn lost its original response interval.")
    original, r = _original(a), observation.receipt
    expected = a["polls"][-1] if a["polls"] else original.request_key
    if r.request_key != expected or r.host != original.host or r.window != original.window:
        raise CondemnProgressStopped("Native Condemn receipt does not match its dispatch.")
    if a["polls"] and _empty_queue_expiry(r):
        if a["state"] != "submitted" or a["last"] is None:
            raise CondemnProgressStopped("Queue expiry lacks its original active action.")
        a.setdefault("cancelled_polls", []).append(_saved(observation))
        a["pending"] = None
    elif not a["polls"] and r.outcome in NO_START:
        a.update(state="not_submitted", last=_saved(observation), pending=None)
    else:
        _owner(original, r, window.lifetime)
        if a["last"] is not None:
            _progress(_receipt(a["last"]).receipt, r)
        if not a["boundaries"] or _receipt(a["boundaries"][-1]).receipt.phase != r.phase:
            a["boundaries"].append(_saved(observation))
        a.update(last=_saved(observation), pending=None, state="submitted")
        if r.phase == Phase.UNCERTAIN:
            a["state"] = "uncertain"
        elif r.phase == Phase.EXISTING:
            a["state"] = "already_enabled"
        elif r.phase == Phase.VERIFIED and observation.response is not None:
            if not window.contains(observation.response):
                raise CondemnProgressStopped("Completion did not come from the original drain.")
            a.update(
                state="state_verified",
                completion={
                    "response": observation.response.records,
                    "sha256": observation.response.digest,
                },
            )
    validate_attempt(a)


def submit(store, command, window, dispatch):
    raw = command.encode(Verb.ENSURE)
    if window.failure or (command.expected.scene, command.expected.local) != (
        window.lifetime.scene_epoch,
        window.lifetime.local,
    ):
        raise CondemnProgressStopped("A matching healthy Condemn response interval is required.")
    with exclusive_record_lock(store.lock):
        record = store._read()
        if (
            record["active"] is not None
            or len(record["attempts"]) >= MAX_ATTEMPTS
            or any(a["request"] == command.request_key for a in record["attempts"])
        ):
            raise CondemnProgressStopped("Condemn has a pending, repeated or exhausted intent.")
        a = dict(
            kind="native",
            request=command.request_key,
            owner=store.owner,
            lifetime=asdict(window.lifetime),
            baseline=dict(window.baseline, sequence=window.sequence),
            command=raw.hex(),
            state="intent",
            polls=[],
            pending=raw.hex(),
            last=None,
            boundaries=[],
            completion=None,
        )
        validate_attempt(a)
        record["schema_version"] = 2
        record["attempts"].append(a)
        record["active"] = command.request_key
        store._write(record)
        store._windows[command.request_key] = window
        observation = dispatch()
        _apply(a, observation, window)
        if a["state"] in TERMINAL:
            record["active"] = None
        store._write(record)
        if record["active"] is None:
            store._windows.pop(a["request"], None)
        return observation.receipt


def advance(store, command, window, dispatch):
    raw = command.encode(Verb.INSPECT)
    request_key(command.transition_request)
    with exclusive_record_lock(store.lock):
        record = store._read()
        if record["active"] != command.transition_request:
            raise CondemnProgressStopped("No matching active Condemn transaction.")
        a = next(a for a in record["attempts"] if a["request"] == record["active"])
        if (
            a.get("kind") != "native"
            or a["owner"] != store.owner
            or a["state"] != "submitted"
            or a["pending"] is not None
            or store._windows.get(a["request"]) is not window
            or window.failure
            or len(a["polls"]) >= MAX_POLLS
        ):
            raise CondemnProgressStopped(
                "Condemn cannot resume an uncertain or replaced transaction."
            )
        if len(a.get("cancelled_polls", [])) >= MAX_CANCELLED_POLLS:
            raise CondemnProgressStopped(
                "Three confirmation queue expiries; the original action remains pending."
            )
        original = _original(a)
        if (
            command.target != original.target
            or command.host != original.host
            or command.window != original.window
            or command.request_key == original.request_key
            or command.request_key in a["polls"]
        ):
            raise CondemnProgressStopped(
                "Condemn continuation changed owner or repeated a dispatch."
            )
        a["polls"].append(command.request_key)
        a["pending"] = raw.hex()
        validate_attempt(a)
        store._write(record)
        observation = dispatch()
        _apply(a, observation, window)
        if a["state"] in TERMINAL:
            record["active"] = None
        store._write(record)
        if record["active"] is None:
            store._windows.pop(a["request"], None)
        return observation.receipt


def verified_targets(record, lifetime):
    return frozenset(
        _original(a).target
        for a in record["attempts"]
        if a.get("kind") == "native"
        and a["state"] in {"state_verified", "already_enabled"}
        and Lifetime(**a["lifetime"]) == lifetime
    )
