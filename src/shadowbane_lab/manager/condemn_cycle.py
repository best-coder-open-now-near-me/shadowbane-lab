"""One owned building's scoped crest actions, with durable navigation and progress.

The town job supplies a pinned selection and repeats only completed cycles. Each
cycle retains its operation ID, exact target order and native request identities;
an interrupted cycle is never restarted by this runner.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass

from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.condemn_evidence import Lifetime
from shadowbane_lab.client_extension.condemn_progress import CondemnProgressStore
from shadowbane_lab.client_extension.condemn_session import NativeCondemnSession
from shadowbane_lab.client_extension.condemn_wire import (
    IN_FLIGHT,
    READY,
    UNRESOLVED,
    Command,
    Outcome,
    Target,
    Verb,
)
from shadowbane_lab.client_extension.guard_spending_journal import GuardSpendingJournal
from shadowbane_lab.client_extension.vendor_navigation_wire import RESPONSE_WAIT_SECONDS
from shadowbane_lab.client_extension.vendor_wire import uint
from shadowbane_lab.record_store import exclusive_record_lock

from .guard_owner import read_guard_owner, require_owner
from .guard_plan import operation_id
from .vendor_discovery import _memory
from .vendor_job import _write
from .vendor_navigation import open_navigation_session


class CondemnCycleStopped(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CondemnContext:
    lifetime: Lifetime
    root: int

    def __post_init__(self):
        if type(self.lifetime) is not Lifetime or not uint(self.root, 32, "root"):
            raise ValueError("exact Condemn process, character and scene required")


def open_condemn_session(binding, *, progress):
    _memory(binding).close()
    return NativeCondemnSession(
        NativeClientProcessIdentity(binding.game_process_id, binding.game_process_started_at_100ns),
        binding.game_window_handle,
        progress=progress,
    )


class _Cycle:
    def __init__(
        self,
        binding,
        context,
        targets,
        owner,
        record,
        save,
        progress,
        journal,
        cancelled,
        pause_requested,
        owner_reader,
        clock,
        sleep,
    ):
        self.binding, self.context, self.targets = binding, context, targets
        self.owner, self.record, self.save = owner, record, save
        self.progress, self.journal = progress, journal
        self.cancelled, self.pause_requested = cancelled, pause_requested
        self.owner_reader, self.clock, self.sleep = owner_reader, clock, sleep

    def check(self):
        if self.cancelled():
            raise CondemnCycleStopped("Condemn dispatch stopped; saved requests remain retained.")
        require_owner(self.owner, self.owner_reader(self.binding))

    def session_identity(self, session):
        if (
            session.identity
            != NativeClientProcessIdentity(
                self.binding.game_process_id, self.binding.game_process_started_at_100ns
            )
            or session.window != self.binding.game_window_handle
        ):
            raise CondemnCycleStopped("Condemn session belongs to another client.")

    def scene(self, state):
        if not state.empty and (state.scene, state.root) != (
            self.context.lifetime.scene_epoch,
            self.context.root,
        ):
            raise CondemnCycleStopped("The selected building area changed.")

    def navigate(self, factory):
        self.check()
        session = factory(self.binding, journal=self.journal)
        try:
            self.session_identity(session)
            building = self.targets[0].building[0]
            request, deadline = None, self.clock() + 60
            while True:
                self.check()
                session.renew_lease()
                receipt = session.inspect()
                state = receipt.snapshot
                self.scene(state)
                if receipt.outcome != Outcome.OBSERVED or receipt.flags & UNRESOLVED:
                    raise CondemnCycleStopped("Building navigation needs review.")
                if request is not None and receipt.transition_request != request:
                    raise CondemnCycleStopped("The building reply belongs to another request.")
                if not receipt.flags & IN_FLIGHT and (request or receipt.flags & READY):
                    if state.empty:
                        raise CondemnCycleStopped("The building observation is empty.")
                    if state.opened(building):
                        self.journal.assert_idle()
                        self.record["navigation"]["after"] = state.encode().hex()
                        self.save()
                        return
                    if request is not None:
                        raise CondemnCycleStopped("The requested building did not open.")
                    request = str(uuid.uuid4())
                    self.record["navigation"].update(request=request, before=state.encode().hex())
                    self.save()
                    self.check()
                    submitted = session.open_building(state, building, request)
                    self.record["navigation"]["submission"] = submitted.encode().hex()
                    self.save()
                    if (
                        submitted.outcome != Outcome.SUBMITTED
                        or submitted.transition_request != request
                        or submitted.flags & UNRESOLVED
                    ):
                        raise CondemnCycleStopped("Building open was not accepted; no retry sent.")
                    deadline = self.clock() + RESPONSE_WAIT_SECONDS
                if self.clock() >= deadline:
                    raise CondemnCycleStopped("The building window was not confirmed.")
                self.sleep(0.1)
        finally:
            session.close()

    def ready(self, session, target):
        deadline = self.clock() + 60
        while True:
            self.check()
            session.renew_lease()
            receipt = session.inspect(target)
            self.scene(receipt.snapshot)
            if receipt.outcome != Outcome.OBSERVED or receipt.flags & (IN_FLIGHT | UNRESOLVED):
                raise CondemnCycleStopped("Another action owns the Condemn window.")
            if receipt.flags & READY:
                s = receipt.snapshot
                if (
                    receipt.target != target
                    or not s.eligible(target)
                    or s.local != self.context.lifetime.local
                ):
                    raise CondemnCycleStopped("The scoped Condemn window changed owner.")
                return s
            if self.clock() >= deadline:
                raise CondemnCycleStopped("Return to the game to continue Condemn.")
            self.sleep(0.1)

    def condemn(self, factory):
        self.check()
        self.journal.assert_idle()
        session = factory(self.binding, progress=self.progress)
        try:
            self.session_identity(session)
            for target in self.targets:
                self.check()
                if self.pause_requested():
                    return "paused"
                before = self.ready(session, target)
                request = str(uuid.uuid4())
                attempt = dict(target=target.encode().hex(), request=request, state="intent")
                self.record["actions"].append(attempt)
                self.record["phase"] = "condemn"
                self.save()
                self.check()
                receipt = session.ensure(target, before, request)
                deadline = self.clock() + 45
                while True:
                    self.scene(receipt.snapshot)
                    saved = self.progress.read()
                    matching = [a for a in saved["attempts"] if a["request"] == request]
                    if len(matching) != 1:
                        raise CondemnCycleStopped("Condemn has no matching durable receipt.")
                    current = matching[0]
                    if (
                        current.get("kind") != "native"
                        or Lifetime(**current["lifetime"]) != self.context.lifetime
                    ):
                        raise CondemnCycleStopped("Condemn receipt belongs to another lifetime.")
                    command = Command.decode(bytes.fromhex(current["command"]), Verb.ENSURE)
                    if command.target != target or command.expected != before:
                        raise CondemnCycleStopped(
                            "Condemn receipt differs from the selected crest."
                        )
                    if saved["active"] is None:
                        if current["state"] not in {"state_verified", "already_enabled"}:
                            raise CondemnCycleStopped("Condemn was not applied; no retry sent.")
                        attempt.update(state=current["state"])
                        self.save()
                        break
                    if (
                        saved["active"] != request
                        or current["pending"] is not None
                        or current["state"] != "submitted"
                        or receipt.flags & UNRESOLVED
                    ):
                        raise CondemnCycleStopped("Condemn needs review; no request was repeated.")
                    if self.clock() >= deadline:
                        raise CondemnCycleStopped("Condemn response was not confirmed.")
                    self.sleep(0.1)
                    self.check()
                    session.renew_lease()
                    receipt = session.advance()  # Action-capable: journaled once, never retried.
            self.progress.assert_idle()
            return "complete"
        finally:
            session.close()


def run_condemn_cycle(
    store,
    binding,
    operation,
    context,
    targets,
    owner,
    *,
    cancelled,
    pause_requested=lambda: False,
    navigation_factory=open_navigation_session,
    session_factory=open_condemn_session,
    owner_reader=read_guard_owner,
    clock=time.monotonic,
    sleep=time.sleep,
):
    """Process the selected crests on one building under the shared UI execution lock."""
    operation_id(operation.operation_id)
    if type(context) is not CondemnContext:
        raise ValueError("validated Condemn context required")
    targets = tuple(targets)
    if (
        not 0 < len(targets) <= 512
        or any(type(t) is not Target for t in targets)
        or len(set(targets)) != len(targets)
        or len({t.building for t in targets}) != 1
    ):
        raise ValueError("one building and distinct explicitly scoped crests required")
    if (context.lifetime.process_id, context.lifetime.creation) != (
        binding.game_process_id,
        binding.game_process_started_at_100ns,
    ):
        raise CondemnCycleStopped("Condemn selection belongs to another client lifetime.")
    path = store.root / "condemn-cycles" / (operation.operation_id + ".json")
    progress, journal = CondemnProgressStore(store.root), GuardSpendingJournal(store.root)
    with exclusive_record_lock(store.root / "execution.lock", timeout_seconds=0.1):
        if path.exists():
            raise CondemnCycleStopped("This Condemn cycle was already attempted; no replay sent.")
        progress.assert_idle()
        journal.assert_idle()
        require_owner(owner, owner_reader(binding))
        record = dict(
            schema_version=1,
            identity=list(store.identity),
            operation_id=operation.operation_id,
            context=asdict(context),
            owner=owner,
            window=binding.game_window_handle,
            targets=[t.encode().hex() for t in targets],
            state="running",
            phase="navigation",
            navigation={},
            actions=[],
        )

        def save():
            _write(path, record)

        cycle = _Cycle(
            binding,
            context,
            targets,
            owner,
            record,
            save,
            progress,
            journal,
            cancelled,
            pause_requested,
            owner_reader,
            clock,
            sleep,
        )
        save()
        try:
            cycle.check()
            if pause_requested():
                record["state"] = "paused"
            else:
                cycle.navigate(navigation_factory)
                record["state"] = cycle.condemn(session_factory)
            save()
            return record
        except Exception as exc:
            record.update(state="review", detail=str(exc) or type(exc).__name__)
            save()
            raise
