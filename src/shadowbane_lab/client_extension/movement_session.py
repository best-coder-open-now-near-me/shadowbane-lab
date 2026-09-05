"""Exact-client native movement session with immutable grants and retry identities."""

from __future__ import annotations

import ctypes
import itertools
import sys
import threading
from dataclasses import dataclass

from . import action_channel as channel
from .movement_wire import Command, Grant, Host, Outcome, Receipt, Settings, Snapshot, Verb


class NativeMovementError(channel.NativeActionChannelError):
    def __init__(self, outcome: Outcome, receipt: Receipt | None = None):
        super().__init__(f"native movement {outcome.name.lower()}")
        self.outcome, self.receipt = outcome, receipt


@dataclass(frozen=True, slots=True)
class NativeMovementGrant:
    process_identity: channel.NativeClientProcessIdentity
    window: int
    ownership: Grant
    host: Host
    request_key: str


def read_snapshot(identity: channel.NativeClientProcessIdentity, window: int) -> Snapshot:
    """Open read-only views, validate schema before status access, never claim/renew."""
    if sys.platform != "win32":
        raise channel.NativeActionChannelUnavailable("native movement requires Windows")
    kernel = channel._WindowsKernel()
    mapping = header_view = view = None
    try:
        mapping = kernel.open_file_mapping(identity.mapping_name, read_only=True)
        header_view = kernel.map_view(
            mapping, channel.CLIENT_ACTION_CHANNEL_HEADER_SIZE, read_only=True
        )
        header = channel.NativeActionChannelHeader.decode(
            ctypes.string_at(header_view, channel.CLIENT_ACTION_CHANNEL_HEADER_SIZE)
        )
        if header.process_identity != identity:
            raise channel.NativeActionChannelUnavailable("native status belongs to another client")
        view = kernel.map_view(mapping, channel.CLIENT_ACTION_CHANNEL_SIZE, read_only=True)
        address = view + channel.CLIENT_ACTION_STATUS_OFFSET
        for _ in range(16):
            before = kernel.read_i64(address)
            if before <= 0 or before & 1:
                continue
            payload = ctypes.string_at(address, 512)
            if kernel.read_i64(address) != before:
                continue
            snapshot = Snapshot.decode(payload)
            if snapshot.sequence != before:
                continue
            if (
                snapshot.process_id != identity.process_id
                or snapshot.creation_filetime != identity.creation_filetime_utc
                or snapshot.window != window
            ):
                raise channel.NativeActionChannelUnavailable(
                    "native status exact-client binding changed"
                )
            return snapshot
        raise channel.NativeActionChannelUnavailable(
            "native movement status is not consistently published"
        )
    finally:
        if view:
            kernel.unmap_view(view)
        if header_view:
            kernel.unmap_view(header_view)
        if mapping:
            kernel.close_handle(mapping)


class NativeMovementSession:
    def __init__(
        self, identity: channel.NativeClientProcessIdentity, window: int, *, timeout_ms: int = 750
    ):
        if not isinstance(identity, channel.NativeClientProcessIdentity):
            raise ValueError("identity must be an exact native client identity")
        if type(window) is not int or not 0 < window < 2**32:
            raise ValueError("window must be an exact nonzero native HWND")
        if type(timeout_ms) is not int or timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        self.identity, self.window, self.timeout_ms = identity, window, timeout_ms
        self._transport: channel.WindowsNativeActionCommandTransport | None = None
        self._ids = itertools.count(1)
        self._acquisitions: dict[str, Command] = {}
        self._revoked: set[NativeMovementGrant] = set()
        self._stops: dict[NativeMovementGrant, str] = {}
        self._closed = False
        self._session_lock = threading.RLock()

    def snapshot(self) -> Snapshot:
        return read_snapshot(self.identity, self.window)

    def _host(self, *, acquire: bool) -> Host:
        with self._session_lock:
            if self._closed:
                raise channel.NativeActionChannelUnavailable("movement session is closed")
            if self._transport is None:
                if not acquire:
                    raise channel.NativeActionChannelUnavailable(
                        "session does not own an automation lease"
                    )
                self._transport = channel.WindowsNativeActionCommandTransport(self.identity)
            transport = self._transport
            if transport is None or self._closed:
                raise channel.NativeActionChannelUnavailable("movement session is closed")
            identity = transport.host_process_identity
            return Host(
                identity.process_id,
                transport.host_lease_generation,
                identity.creation_filetime_utc,
            )

    def _expected(self, snapshot: Snapshot) -> None:
        if (
            snapshot.process_id != self.identity.process_id
            or snapshot.creation_filetime != self.identity.creation_filetime_utc
            or snapshot.window != self.window
        ):
            raise ValueError("snapshot belongs to another client")

    def _submit(self, verb: Verb, payload: Command) -> Receipt:
        transport = self._transport
        if transport is None or self._closed:
            raise channel.NativeActionChannelUnavailable("session is closed")
        # Validation precedes publication; retries retain the same payload UUID.
        payload.encode(verb)
        result = transport.submit(
            channel.NativeMovementCommand(next(self._ids), verb, payload),
            timeout_ms=self.timeout_ms,
        )
        if not result.movement_payload or not any(result.movement_payload):
            raise NativeMovementError(Outcome.UNAVAILABLE)
        receipt = Receipt.decode(result.movement_payload)
        if (
            receipt.request_key != payload.request_key
            or receipt.host != payload.host
            or receipt.window != self.window
        ):
            raise channel.NativeActionChannelError("movement receipt correlation mismatch")
        if receipt.outcome != Outcome.ACCEPTED:
            raise NativeMovementError(receipt.outcome, receipt)
        if not result.stage.accepted_submission or result.error_code:
            raise channel.NativeActionChannelError("movement receipt contradicts action result")
        return receipt

    def acquire(
        self, expected: Snapshot, worker_id: str, operation_id: str, request_key: str
    ) -> NativeMovementGrant:
        self._expected(expected)
        payload = Command(
            self._host(acquire=True),
            self.window,
            expected.grant,
            request_key,
            settings=expected.settings,
            revision=expected.revision,
            worker_id=worker_id,
            operation_id=operation_id,
        )
        previous = self._acquisitions.setdefault(request_key, payload)
        if previous != payload:
            raise ValueError(
                "acquisition retry must preserve its original snapshot, lease and token"
            )
        receipt = self._submit(Verb.ACQUIRE, previous)
        return NativeMovementGrant(
            self.identity, self.window, receipt.grant, receipt.host, request_key
        )

    def _check_grant(self, grant: NativeMovementGrant) -> None:
        if grant.process_identity != self.identity or grant.window != self.window:
            raise ValueError("movement grant belongs to another client")
        if grant in self._revoked or grant.host != self._host(acquire=False):
            raise NativeMovementError(Outcome.STALE)

    def move(
        self, grant: NativeMovementGrant, destination: tuple[float, float, float], request_key: str
    ) -> Receipt:
        self._check_grant(grant)
        if grant in self._stops:
            raise NativeMovementError(Outcome.INHIBITED)
        try:
            return self._submit(
                Verb.DESTINATION,
                Command(grant.host, grant.window, grant.ownership, request_key, destination),
            )
        except NativeMovementError:
            self._revoked.add(grant)
            raise

    def renew(self, grant: NativeMovementGrant) -> None:
        self._check_grant(grant)
        snapshot = self.snapshot()
        if snapshot.grant != grant.ownership or not snapshot.flags & 2 or snapshot.flags & 8:
            self._revoked.add(grant)
            raise NativeMovementError(Outcome.STALE)
        transport = self._transport
        if transport is None or self._closed:
            raise channel.NativeActionChannelUnavailable("movement session is closed")
        transport.renew_lease()

    def pause(self, grant: NativeMovementGrant, request_key: str) -> Receipt:
        self._check_grant(grant)
        try:
            receipt = self._submit(
                Verb.PAUSE, Command(grant.host, grant.window, grant.ownership, request_key)
            )
        except NativeMovementError:
            self._revoked.add(grant)
            raise
        if receipt.grant != grant.ownership:
            self._revoked.add(grant)
            raise channel.NativeActionChannelError("pause changed operation ownership")
        return receipt

    def stop(self, grant: NativeMovementGrant, request_key: str) -> Receipt:
        self._check_grant(grant)
        previous = self._stops.setdefault(grant, request_key)
        if previous != request_key:
            raise ValueError("ambiguous stop retry must retain its request UUID")
        try:
            receipt = self._submit(
                Verb.STOP, Command(grant.host, grant.window, grant.ownership, request_key)
            )
        except channel.NativeActionChannelTimeout:
            # Movement stays excluded, but the exact cancellation can be retried.
            raise
        except NativeMovementError:
            self._revoked.add(grant)
            raise
        self._revoked.add(grant)
        return receipt

    def configure(self, expected: Snapshot, settings: Settings, request_key: str) -> Receipt:
        self._expected(expected)
        return self._submit(
            Verb.CONFIGURE,
            Command(
                self._host(acquire=False),
                self.window,
                expected.grant,
                request_key,
                settings=settings,
                revision=expected.revision,
            ),
        )

    def close(self) -> None:
        with self._session_lock:
            self._closed = True
            if self._transport is not None:
                self._transport.close()
                self._transport = None
