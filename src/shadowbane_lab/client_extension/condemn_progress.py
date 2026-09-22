"""Durable Condemn enable intents and qualified state progress, separate from spending.

The native adapter owns dispatch admission, UI serialization and its exact request
receipt. This journal owns write-ahead intent and prohibits replay after any lost
submission/completion. Its completion means keyed enabled state was observed; the
server supplies no nonce, so it never labels that state as command causality.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from shadowbane_lab.record_store import (
    exclusive_record_lock,
    publish_atomic_record,
    read_record_bytes,
)

from .condemn_evidence import (
    Lifetime,
    Response,
    ResponseWindow,
    Target,
    canonical,
    enabled_row,
    integer,
    row_state,
)
from .condemn_responses import CondemnResponseError

LIMIT = 32 * 1024 * 1024
MAX_ATTEMPTS = 4096


class CondemnProgressStopped(RuntimeError):
    pass


def request_key(value):
    if not isinstance(value, str):
        raise ValueError("a canonical Condemn request is required")
    parsed = uuid.UUID(value)
    if str(parsed) != value or not parsed.int:
        raise ValueError("a canonical nonzero Condemn request is required")
    return value


@dataclass(frozen=True, slots=True)
class Submission:
    """Validated native adapter result at the actual invocation boundary.

    The adapter must compare its typed command/receipt, including request, target,
    native scene, producer and window, before constructing this result. Returning
    from an IPC write or from an unverified callback is not a submitted result.
    response_floor and tick_ms are sampled by the native owner thread before send.
    """

    request: str
    lifetime: Lifetime
    target: Target
    response_floor: int
    tick_ms: int
    submitted: bool

    def __post_init__(self):
        request_key(self.request)
        if type(self.lifetime) is not Lifetime or type(self.target) is not Target:
            raise ValueError("typed Condemn submission ownership is required")
        integer(self.response_floor, 2**63 - 1)
        integer(self.tick_ms)
        if type(self.submitted) is not bool:
            raise ValueError("invalid Condemn submission outcome")


def _context(observation):
    root = integer(observation["root_address"], 2**32 - 1, minimum=1)
    windows = [w for w in observation["windows"] if w["kind"] == "kos"]
    if len(windows) != 1:
        raise CondemnProgressStopped("An exact owned Condemn list is required.")
    hud = integer(windows[0]["address"], 2**32 - 1, minimum=1)
    return [root, hud]


def _submission(value):
    if set(value) != {"request", "lifetime", "target", "response_floor", "tick_ms", "submitted"}:
        raise ValueError("invalid Condemn submission fields")
    return Submission(
        value["request"],
        Lifetime(**value["lifetime"]),
        Target(**value["target"]),
        value["response_floor"],
        value["tick_ms"],
        value["submitted"],
    )


def _validate_attempt(attempt):
    if not isinstance(attempt, dict):
        raise ValueError("invalid Condemn attempt record")
    if attempt.get("kind") == "native":
        from .condemn_transaction import validate_attempt

        return validate_attempt(attempt)
    if set(attempt) != {
        "request",
        "owner",
        "lifetime",
        "target",
        "baseline",
        "context",
        "state",
        "submission",
        "completion",
    }:
        raise ValueError("invalid Condemn attempt record")
    request_key(attempt["request"])
    request_key(attempt["owner"])
    lifetime, target = Lifetime(**attempt["lifetime"]), Target(**attempt["target"])
    if attempt["state"] not in {"intent", "submitted", "uncertain", "state_verified"}:
        raise ValueError("invalid Condemn attempt state")
    baseline = attempt["baseline"]
    if set(baseline) != {"sequence", "rejected", "ticket_drops", "read_errors"}:
        raise ValueError("invalid Condemn baseline")
    for value in baseline.values():
        integer(value, 2**63 - 1)
    if len(attempt["context"]) != 2:
        raise ValueError("invalid Condemn context")
    for value in attempt["context"]:
        integer(value, 2**32 - 1, minimum=1)
    submitted = attempt["submission"]
    if submitted is None:
        if attempt["state"] != "intent" or attempt["completion"] is not None:
            raise ValueError("Condemn progress lacks its submission")
        return
    receipt = _submission(submitted)
    if (
        receipt.request != attempt["request"]
        or receipt.lifetime != lifetime
        or receipt.target != target
        or receipt.response_floor < baseline["sequence"]
        or attempt["state"] == "intent"
        or not receipt.submitted
        and attempt["state"] != "uncertain"
    ):
        raise ValueError("Condemn submission does not match its durable intent")
    completion = attempt["completion"]
    if completion is None:
        if attempt["state"] == "state_verified":
            raise ValueError("Condemn progress lacks completion evidence")
        return
    if attempt["state"] != "state_verified" or not receipt.submitted:
        raise ValueError("ambiguous Condemn attempt cannot be completed")
    if set(completion) != {"response", "response_sha256", "observed_tick", "row"}:
        raise ValueError("invalid Condemn completion evidence")
    response = Response(lifetime, canonical(completion["response"]))
    records = response.records
    if (
        not response.enabled_reply(target)
        or response.digest != completion["response_sha256"]
        or records[0]["sequence"] <= receipt.response_floor
        or records[0]["tick_ms"] < receipt.tick_ms
        or integer(completion["observed_tick"]) < records[-1]["tick_ms"]
        or _context(completion["row"]) != attempt["context"]
        or not enabled_row(target, completion["row"])
    ):
        raise ValueError("Condemn enabled state is not qualified")


class CondemnProgressStore:
    """One atomic journal per client store, with a non-replayable active intent.

    Reopening this store can read confirmed progress, but cannot complete another
    runner's pending attempt. A process/scene change never clears uncertainty.
    The eventual town job must acquire the shared native UI owner before submit;
    this lock only serializes Condemn progress and does not grant UI ownership.
    """

    def __init__(self, root):
        root = Path(root).resolve()
        native = str(root).removeprefix("\\\\?\\")
        if native.startswith("\\\\") or native.upper().startswith("UNC\\"):
            raise ValueError("Condemn progress requires local storage")
        self.root = root / "condemn-progress"
        self.path, self.lock = self.root / "progress.json", self.root / "progress.lock"
        self.initialized = self.root / "initialized.json"
        self.owner = str(uuid.uuid4())
        self._windows = {}

    def _read(self):
        if not self.path.exists():
            if self.initialized.exists():
                raise CondemnProgressStopped("Condemn journal is missing; no replay allowed.")
            return {"schema_version": 1, "active": None, "attempts": []}
        try:
            raw = read_record_bytes(self.path, LIMIT)
            if len(raw) > LIMIT:
                raise ValueError("Condemn progress exceeds its bound")
            record = json.loads(raw)
            if (
                set(record) != {"schema_version", "active", "attempts"}
                or type(record["schema_version"]) is not int
                or record["schema_version"] not in (1, 2)
                or not isinstance(record["attempts"], list)
                or len(record["attempts"]) > MAX_ATTEMPTS
            ):
                raise ValueError("invalid Condemn progress schema")
            seen, pending = set(), []
            for attempt in record["attempts"]:
                if not isinstance(attempt, dict):
                    raise ValueError("invalid Condemn attempt record")
                if attempt.get("kind") == "native" and record["schema_version"] != 2:
                    raise ValueError("native Condemn intent requires schema 2")
                _validate_attempt(attempt)
                if attempt["request"] in seen:
                    raise ValueError("duplicate Condemn request")
                seen.add(attempt["request"])
                if attempt["state"] not in {"state_verified", "already_enabled", "not_submitted"}:
                    pending.append(attempt["request"])
            if pending != ([] if record["active"] is None else [record["active"]]):
                raise ValueError("Condemn active intent does not match its history")
            return record
        except (ValueError, KeyError, TypeError, CondemnResponseError) as exc:
            raise CondemnProgressStopped(
                "Condemn progress needs review; no replay allowed."
            ) from exc

    def _write(self, record):
        data = canonical(record)
        if len(data) > LIMIT:
            raise CondemnProgressStopped("Condemn progress storage limit reached.")
        if not self.initialized.exists():
            publish_atomic_record(
                self.initialized, b'{"schema_version":1}', temporary_label="condemn-progress"
            )
        publish_atomic_record(self.path, data, temporary_label="condemn-progress")

    def read(self):
        with exclusive_record_lock(self.lock):
            return self._read()

    def verified_targets(self, lifetime: Lifetime):
        return frozenset(
            Target(**a["target"])
            for a in self.read()["attempts"]
            if a.get("kind") != "native"
            and a["state"] == "state_verified"
            and Lifetime(**a["lifetime"]) == lifetime
        )

    def assert_idle(self):
        if self.read()["active"] is not None:
            raise CondemnProgressStopped("An earlier Condemn attempt needs completion or review.")

    def submit(self, request, target: Target, window: ResponseWindow, before, dispatch):
        """Persist intent, then call a native adapter exactly once. Never retry failures."""
        request_key(request)
        if window.failure or not row_state(target, before, enabled=False):
            raise CondemnProgressStopped("A fresh disabled scoped row is required.")
        context = _context(before)
        baseline = dict(window.baseline, sequence=window.sequence)
        lifetime = window.lifetime
        with exclusive_record_lock(self.lock):
            record = self._read()
            if (
                record["active"] is not None
                or len(record["attempts"]) >= MAX_ATTEMPTS
                or any(a["request"] == request for a in record["attempts"])
            ):
                raise CondemnProgressStopped(
                    "Condemn attempt is pending, repeated, or at capacity."
                )
            attempt = dict(
                request=request,
                owner=self.owner,
                lifetime=asdict(lifetime),
                target=asdict(target),
                baseline=baseline,
                context=context,
                state="intent",
                submission=None,
                completion=None,
            )
            record["attempts"].append(attempt)
            record["active"] = request
            self._write(record)
            # Exceptions here retain the active write-ahead intent. No catch/retry.
            receipt = dispatch()
            if (
                type(receipt) is not Submission
                or receipt.request != request
                or receipt.lifetime != lifetime
                or receipt.target != target
                or receipt.response_floor < baseline["sequence"]
            ):
                raise CondemnProgressStopped("Native Condemn submission does not match its intent.")
            attempt.update(
                submission=asdict(receipt), state="submitted" if receipt.submitted else "uncertain"
            )
            self._write(record)
            self._windows[request] = window
            return receipt

    def observe(self, request, response: Response, window: ResponseWindow, row, observed_tick):
        """Record qualified enabled state; never infer an exact server request nonce."""
        request_key(request)
        with exclusive_record_lock(self.lock):
            record = self._read()
            if record["active"] != request:
                raise CondemnProgressStopped("No matching active Condemn attempt.")
            attempt = next(a for a in record["attempts"] if a["request"] == request)
            if (
                attempt["owner"] != self.owner
                or attempt["state"] != "submitted"
                or self._windows.get(request) is not window
                or window.failure
                or not window.contains(response)
            ):
                raise CondemnProgressStopped("Condemn attempt lost its original evidence interval.")
            attempt.update(
                state="state_verified",
                completion=dict(
                    response=response.records,
                    response_sha256=response.digest,
                    observed_tick=observed_tick,
                    row=json.loads(canonical(row)),
                ),
            )
            try:
                _validate_attempt(attempt)
            except (ValueError, KeyError, TypeError, CondemnResponseError) as exc:
                raise CondemnProgressStopped(
                    "Condemn state evidence does not match its intent."
                ) from exc
            record["active"] = None
            self._write(record)
            self._windows.pop(request, None)

    def submit_native(self, command, window, dispatch):
        from .condemn_transaction import submit

        return submit(self, command, window, dispatch)

    def continue_native(self, command, window, dispatch):
        from .condemn_transaction import advance

        return advance(self, command, window, dispatch)

    def verified_native_targets(self, lifetime):
        from .condemn_transaction import verified_targets

        return verified_targets(self.read(), lifetime)
