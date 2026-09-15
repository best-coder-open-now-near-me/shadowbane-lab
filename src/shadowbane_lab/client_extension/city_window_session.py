"""Typed City Command window operations, correlated with the exact client and producer lease."""
from __future__ import annotations

import itertools
import time
import uuid
from dataclasses import dataclass

from . import action_channel as channel
from .city_window_wire import Command, Outcome, Receipt, Snapshot, Verb
from .movement_wire import Host


@dataclass(frozen=True, slots=True)
class NativeCityWindowCommand:
    command_id: int
    kind: Verb
    payload: Command

    def encode_slot(self, *, sequence: int, created_tick: int, deadline_tick: int) -> bytes:
        if type(self.command_id) is not int or not 0 < self.command_id < 2**64:
            raise ValueError("city_window command ID must be a positive uint64")
        if (
            not 0 < sequence < 2**63 or not 0 < created_tick <= deadline_tick < 2**64
            or deadline_tick - created_tick > 5000
        ):
            raise ValueError("invalid city_window command sequence/deadline")
        return channel._COMMAND.pack(
            0, self.command_id, self.kind, channel.CLIENT_ACTION_PAYLOAD_VERSION,
            created_tick, deadline_tick, 0, 0, 0, 0, 0, 0, bytes(96), bytes(32),
        ) + self.payload.encode(self.kind)


class _RetryableInspectionError(channel.NativeActionChannelUnavailable):
    """A rejected read-only observation; never used for opening."""


class NativeCityWindowSession:
    def __init__(self, identity: channel.NativeClientProcessIdentity, window: int):
        if type(window) is not int or not 0 < window < 2**32:
            raise ValueError("an exact client HWND is required")
        self.identity, self.window = identity, window
        self._transport = channel.WindowsNativeActionCommandTransport(identity)
        self._ids = itertools.count(1)
        self._closed = False

    def _submit(
        self, verb: Verb, request_key: str, expected: Snapshot | None = None
    ) -> Receipt:
        if self._closed:
            raise channel.NativeActionChannelUnavailable("city_window session is closed")
        transport = self._transport
        process = transport.host_process_identity
        host = Host(
            process.process_id, transport.host_lease_generation, process.creation_filetime_utc
        )
        command = Command(host, self.window, request_key, expected or Snapshot())
        result = transport.submit(
            NativeCityWindowCommand(next(self._ids), verb, command), timeout_ms=750
        )
        if result.detail != "native_city_window_receipt_v1":
            error = (
                _RetryableInspectionError
                if verb == Verb.INSPECT
                and result.stage == channel.NativeActionResultStage.FAILED
                and result.error_code == 13
                and result.detail == "invalid_or_expired_city_window_lease"
                else channel.NativeActionChannelUnavailable
            )
            raise error(
                f"city_window {verb.name.lower()} failed: {result.detail} "
                f"(stage={result.stage.name}, error={result.error_code})"
            )
        receipt = Receipt.decode(result.movement_payload)
        if (
            receipt.host != host or receipt.window != self.window
            or receipt.request_key != request_key
        ):
            raise channel.NativeActionChannelError("city_window receipt correlation mismatch")
        accepted = receipt.outcome in (Outcome.OBSERVED, Outcome.SUBMITTED)
        if accepted != result.stage.accepted_submission or accepted != (result.error_code == 0):
            raise channel.NativeActionChannelError(
                "city window receipt contradicts transport result"
            )
        return receipt

    def inspect(self) -> Receipt:
        # Only observation can be repeated. Every attempt has a fresh request
        # identity and still passes the native lifetime/lease/receipt checks.
        for attempt in range(3):
            try:
                return self._submit(Verb.INSPECT, str(uuid.uuid4()))
            except (_RetryableInspectionError, channel.NativeActionChannelTimeout):
                if attempt == 2:
                    raise
                time.sleep(0.05)
        raise AssertionError("unreachable inspection retry")

    def open(self, expected: Snapshot, request_key: str) -> Receipt:
        return self._submit(Verb.OPEN, request_key, expected)

    def renew_lease(self) -> None:
        self._transport.renew_lease()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._transport.close()
