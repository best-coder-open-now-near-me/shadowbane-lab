"""One producer-owned Condemn session; mutating continuations never retry."""

from __future__ import annotations

import itertools
import threading
import uuid
from dataclasses import dataclass
from functools import wraps

from . import action_channel as channel
from .condemn_evidence import Lifetime, ResponseWindow
from .condemn_progress import CondemnProgressStopped, CondemnProgressStore
from .condemn_responses import CondemnResponseReader
from .condemn_transaction import Observation
from .condemn_wire import READY, Command, Outcome, Receipt, Snapshot, Target, Verb
from .event_reader import WindowsSharedMemorySnapshotReader
from .movement_wire import Host
from .vendor_wire import uint


@dataclass(frozen=True, slots=True)
class NativeCondemnCommand:
    command_id: int
    kind: Verb
    payload: Command

    def encode_slot(self, *, sequence: int, created_tick: int, deadline_tick: int):
        if (
            not uint(self.command_id, 64, "command ID")
            or not 0 < uint(sequence, 63, "sequence")
            or not 0 < uint(created_tick, 64, "created tick") <= deadline_tick
            or uint(deadline_tick, 64, "deadline") - created_tick > 5000
        ):
            raise ValueError("invalid Condemn command envelope")
        return channel._COMMAND.pack(
            0,
            self.command_id,
            self.kind,
            channel.CLIENT_ACTION_PAYLOAD_VERSION,
            created_tick,
            deadline_tick,
            0,
            0,
            0,
            0,
            0,
            0,
            bytes(96),
            bytes(32),
        ) + self.payload.encode(self.kind)


def _serialized(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return call


class NativeCondemnSession:
    def __init__(
        self,
        identity: channel.NativeClientProcessIdentity,
        window: int,
        *,
        progress: CondemnProgressStore | None = None,
    ):
        if not isinstance(identity, channel.NativeClientProcessIdentity) or not uint(
            window, 32, "window"
        ):
            raise ValueError("an exact client process and HWND are required")
        self.identity, self.window = identity, window
        self._progress = progress
        self._transport = channel.WindowsNativeActionCommandTransport(identity)
        self._ids = itertools.count(1)
        self._closed = False
        self._lock = threading.RLock()
        self._active = None
        self._reader = None
        self._interval = None
        self._responses = {}
        # Journal validation and atomic disk writes may outlast the transport lease.
        # Renew ownership independently; this thread never submits game commands.
        self._lease_lock = threading.RLock()
        self._lease_error = None
        self._lease_stop = threading.Event()
        self._lease_thread = threading.Thread(
            target=self._maintain_lease, name="condemn-lease", daemon=True
        )
        try:
            self._lease_thread.start()
        except BaseException:
            self._transport.close()
            raise

    def _require_lease(self):
        if self._closed:
            raise channel.NativeActionChannelUnavailable("Condemn session is closed")
        if self._lease_error is not None:
            raise channel.NativeActionChannelUnavailable(
                f"Condemn host lease maintenance failed: {self._lease_error}"
            ) from self._lease_error

    def _renew_lease(self):
        with self._lease_lock:
            self._require_lease()
            try:
                self._transport.renew_lease()
            except Exception as exc:
                self._lease_error = exc
                self._lease_stop.set()
                raise

    def _maintain_lease(self):
        while not self._lease_stop.wait(0.2):
            try:
                self._renew_lease()
            except Exception:
                return  # Latched; foreground work must stop without reacquisition.

    def _command(self, target, request, expected=None, transition=None):
        if self._closed:
            raise channel.NativeActionChannelUnavailable("Condemn session is closed")
        process = self._transport.host_process_identity
        host = Host(
            process.process_id, self._transport.host_lease_generation, process.creation_filetime_utc
        )
        return Command(host, self.window, request, target, expected or Snapshot(), transition)

    def _send(self, verb, command):
        encoded = NativeCondemnCommand(next(self._ids), verb, command)
        with self._lease_lock:
            self._require_lease()
            result = self._transport.submit(encoded, timeout_ms=750)
        if result.detail != "native_condemn_receipt_v1":
            raise channel.NativeActionChannelUnavailable(f"Condemn command failed: {result.detail}")
        receipt = Receipt.decode(result.movement_payload)
        if (
            receipt.host != command.host
            or receipt.window != command.window
            or receipt.request_key != command.request_key
            or receipt.flags & READY
            and receipt.target != command.target
            or result.command_id != encoded.command_id
            or not 0 < result.consumer_thread_id < 2**32
        ):
            raise channel.NativeActionChannelError("Condemn receipt correlation mismatch")
        accepted = receipt.outcome in (Outcome.OBSERVED, Outcome.SUBMITTED) or (
            receipt.outcome == Outcome.PENDING and receipt.transition_request == command.request_key
        )
        stage = (
            channel.NativeActionResultStage.SUBMITTED_TO_CLIENT
            if accepted
            else channel.NativeActionResultStage.REJECTED_BY_CLIENT
        )
        if result.stage != stage or accepted != (result.error_code == 0):
            raise channel.NativeActionChannelError(
                "Condemn receipt contradicts its transport result"
            )
        return Observation(receipt, result.observed_tick)

    def _drain(self):
        try:
            for response in self._interval.consume(self._reader.drain()):
                self._responses[response.records[-1]["sequence"]] = response
            while len(self._responses) > 64:
                del self._responses[next(iter(self._responses))]
        except Exception as exc:
            self._interval.invalidate(
                f"Condemn response observation interrupted: {type(exc).__name__}: {exc}"
            )

    def _dispatch(self, verb, command):
        self._drain()
        observed = self._send(verb, command)
        self._drain()
        return Observation(
            observed.receipt,
            observed.tick,
            self._responses.get(observed.receipt.completion_sequence),
        )

    @_serialized
    def inspect(self, target: Target):
        if self._active is not None:
            raise CondemnProgressStopped(
                "Use the original Condemn continuation while its job is active."
            )
        # This has no continuation UUID, so it cannot advance a native action.
        # Keep even read-only retries explicit to avoid masking producer changes.
        return self._send(Verb.INSPECT, self._command(target, str(uuid.uuid4()))).receipt

    @_serialized
    def ensure(self, target: Target, expected: Snapshot, request_key: str):
        if self._progress is None or self._active is not None:
            raise CondemnProgressStopped("Condemn requires an idle durable progress store.")
        self._progress.assert_idle()
        command = self._command(target, request_key, expected)
        command.encode(Verb.ENSURE)
        self._reader = CondemnResponseReader(
            self.identity.process_id,
            self.identity.creation_filetime_utc,
            WindowsSharedMemorySnapshotReader(),
        )
        lifetime = Lifetime(
            self.identity.process_id,
            self.identity.creation_filetime_utc,
            expected.scene,
            expected.local,
        )
        self._interval = ResponseWindow(lifetime, self._reader.drain())
        self._responses = {}
        self._active = (target, request_key)
        receipt = self._progress.submit_native(
            command, self._interval, lambda: self._dispatch(Verb.ENSURE, command)
        )
        self._retire_completed()
        return receipt

    @_serialized
    def advance(self):
        if self._progress is None or self._active is None:
            raise CondemnProgressStopped("No original Condemn transaction is active.")
        target, request = self._active
        command = self._command(target, str(uuid.uuid4()), transition=request)
        receipt = self._progress.continue_native(
            command, self._interval, lambda: self._dispatch(Verb.INSPECT, command)
        )
        self._retire_completed()
        return receipt

    def _retire_completed(self):
        if self._progress.read()["active"] is None:
            self._active = self._interval = self._reader = None
            self._responses.clear()

    @_serialized
    def renew_lease(self):
        self._renew_lease()

    @_serialized
    def close(self):
        if not self._closed:
            self._lease_stop.set()
            self._lease_thread.join()
            with self._lease_lock:
                self._closed = True
                self._transport.close()
            # Any saved active intent remains; another session may not take it over.
