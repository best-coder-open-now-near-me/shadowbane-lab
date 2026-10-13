"""Typed vendor commands, correlated with the exact client and producer lease."""
from __future__ import annotations

import itertools
import time
import uuid
from dataclasses import dataclass

from . import action_channel as channel
from .movement_wire import Host
from .vendor_wire import UNRESOLVED, Command, NativeOrderBudget, Outcome, Receipt, Snapshot, Verb


@dataclass(frozen=True, slots=True)
class NativeVendorCommand:
    command_id: int
    kind: Verb
    payload: Command

    def encode_slot(self, *, sequence: int, created_tick: int, deadline_tick: int) -> bytes:
        if type(self.command_id) is not int or not 0 < self.command_id < 2**64:
            raise ValueError("vendor command ID must be a positive uint64")
        if (
            not 0 < sequence < 2**63 or not 0 < created_tick <= deadline_tick < 2**64
            or deadline_tick - created_tick > 5000
        ):
            raise ValueError("invalid vendor command sequence/deadline")
        return channel._COMMAND.pack(
            0, self.command_id, self.kind, channel.CLIENT_ACTION_PAYLOAD_VERSION,
            created_tick, deadline_tick, 0, 0, 0, 0, 0, 0, bytes(96), bytes(32),
        ) + self.payload.encode(self.kind)


class _RetryableInspectionError(channel.NativeActionChannelUnavailable):
    """A rejected read-only observation; never used for Create or Keep."""


class NativeVendorSession:
    def __init__(self, identity: channel.NativeClientProcessIdentity, window: int):
        if type(window) is not int or not 0 < window < 2**32:
            raise ValueError("an exact client HWND is required")
        self.identity, self.window = identity, window
        self._transport = channel.WindowsNativeActionCommandTransport(identity)
        self._ids = itertools.count(1)
        self._closed = False

    def _submit(
        self, verb: Verb, request_key: str, expected: Snapshot | None = None, item: int = 0,
        *, batch_key: str | None = None,
        order_budget: NativeOrderBudget | None = None,
    ) -> Receipt:
        if self._closed:
            raise channel.NativeActionChannelUnavailable("vendor session is closed")
        transport = self._transport
        process = transport.host_process_identity
        host = Host(
            process.process_id, transport.host_lease_generation, process.creation_filetime_utc
        )
        command = Command(host, self.window, request_key, expected or Snapshot(), item,
                          batch_key, order_budget)
        result = transport.submit(
            NativeVendorCommand(next(self._ids), verb, command), timeout_ms=750
        )
        orders = verb in (Verb.INSPECT_ORDERS, Verb.CREATE_ORDERS)
        expected_detail = ("native_vendor_orders_receipt_v2" if orders
                           else "native_vendor_receipt_v1")
        if result.detail != expected_detail:
            error = (
                _RetryableInspectionError
                if verb in (Verb.INSPECT, Verb.INSPECT_RANDOM, Verb.INSPECT_ORDERS)
                and result.stage == channel.NativeActionResultStage.FAILED
                and result.error_code == 13
                and result.detail == "invalid_or_expired_vendor_lease"
                else channel.NativeActionChannelUnavailable
            )
            raise error(
                f"vendor {verb.name.lower()} failed: {result.detail} "
                f"(stage={result.stage.name}, error={result.error_code})"
            )
        receipt = Receipt.decode(result.movement_payload)
        if (receipt.remaining_counts is not None) != orders:
            raise channel.NativeActionChannelError("vendor receipt profile mismatch")
        if (
            receipt.host != host or receipt.window != self.window
            or receipt.request_key != request_key
        ):
            raise channel.NativeActionChannelError("vendor receipt correlation mismatch")
        accepted = receipt.outcome in (Outcome.OBSERVED, Outcome.SUBMITTED)
        if accepted != result.stage.accepted_submission or accepted != (result.error_code == 0):
            raise channel.NativeActionChannelError("vendor receipt contradicts transport result")
        return receipt

    def _inspect(self, verb: Verb) -> Receipt:
        # Only observation can be repeated. Every attempt has a fresh request
        # identity and still passes the native lifetime/lease/receipt checks.
        for attempt in range(3):
            try:
                receipt = self._submit(verb, str(uuid.uuid4()))
                if receipt.outcome != Outcome.STALE or receipt.flags & UNRESOLVED or attempt == 2:
                    return receipt
            except (_RetryableInspectionError, channel.NativeActionChannelTimeout):
                if attempt == 2:
                    raise
            time.sleep(0.05)
        raise AssertionError("unreachable inspection retry")

    def inspect(self) -> Receipt:
        return self._inspect(Verb.INSPECT)

    def inspect_random(self) -> Receipt:
        """Prove generalized single-recipe support without spending."""
        return self._inspect(Verb.INSPECT_RANDOM)

    def inspect_orders(self) -> Receipt:
        """Read raw per-slot order counts; this grants no quantity-ten dispatch."""
        return self._inspect(Verb.INSPECT_ORDERS)

    def create_orders(self, expected: Snapshot, request_key: str, *, batch_key: str,
                      budget: NativeOrderBudget) -> Receipt:
        return self._submit(Verb.CREATE_ORDERS, request_key, expected, batch_key=batch_key,
                            order_budget=budget)

    def create_random(self, expected: Snapshot, request_key: str) -> Receipt:
        return self._submit(Verb.CREATE_RANDOM, request_key, expected)

    def create(self, expected: Snapshot, request_key: str) -> Receipt:
        return self._submit(Verb.CREATE, request_key, expected)

    def keep(self, expected: Snapshot, item: int, request_key: str) -> Receipt:
        return self._submit(Verb.KEEP, request_key, expected or Snapshot(), item)

    def menu_session(self):
        """Borrow this producer lease and command sequence for owned menu transitions."""
        from .vendor_menu_session import NativeVendorMenuSession

        return NativeVendorMenuSession._borrow(self)

    def renew_lease(self) -> None:
        self._transport.renew_lease()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._transport.close()
