"""Kernel-ticket index sharing AttackListStore's existing record lock.

This sidecar never supplies target membership. A failed durable list replacement
leaves revoked tickets revoked. All methods require the caller's list lock.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from shadowbane_lab.client_extension.combat_fence_v3 import Binding, State
from shadowbane_lab.client_extension.combat_fence_windows import FenceError, Ticket, Windows
from shadowbane_lab.record_store import publish_atomic_record, read_record_bytes

CAPACITY = 128
MAX_BYTES = 128 * 1024


class Registry:
    def __init__(self, path: Path, owner: str) -> None:
        self.path = path.with_suffix(".admissions.json")
        self.owner = bytes.fromhex(owner)
        self.store = hashlib.sha256(os.path.normcase(str(path.resolve())).encode()).digest()

    def _read(self) -> list[Binding]:
        try:
            payload = read_record_bytes(self.path, MAX_BYTES)
        except FileNotFoundError:
            return []
        if len(payload) > MAX_BYTES:
            raise FenceError("admission registry exceeds supported size")
        raw = json.loads(payload)
        if (not isinstance(raw, dict) or set(raw) != {"schema", "store", "tickets"}
                or type(raw["schema"]) is not int or raw["schema"] not in (1, 2)
                or raw["store"] != self.store.hex() or not isinstance(raw["tickets"], list)
                or len(raw["tickets"]) > CAPACITY):
            raise FenceError("invalid admission registry")
        result = []
        for item in raw["tickets"]:
            if not isinstance(item, str) or len(item) != 640:
                raise FenceError("invalid registered ticket")
            if raw["schema"] == 1:
                # Decode only for retirement checks. Never reopen/admit legacy
                # authority through the v3 ticket implementation.
                from shadowbane_lab.client_extension.combat_fence import Binding as LegacyBinding
                from shadowbane_lab.client_extension.combat_fence import State as LegacyState

                legacy, state = LegacyBinding.decode(bytes.fromhex(item))
                if (state != LegacyState.REGISTERING or legacy.owner != self.owner
                        or legacy.store != self.store):
                    raise FenceError("legacy admission owner mismatch")
                api = Windows()
                if (api.mapping_exists(legacy.name)
                        and api.alive(legacy.client_pid, legacy.client_creation)):
                    raise FenceError("live v2 combat authority must retire before v3 migration")
                continue
            binding, state = Binding.decode(bytes.fromhex(item))
            if (state != State.REGISTERING or binding.owner != self.owner
                    or binding.store != self.store):
                raise FenceError("registered admission owner mismatch")
            result.append(binding)
        if len({b.digest for b in result}) != len(result):
            raise FenceError("duplicate admission registration")
        return result

    def _write(self, bindings: list[Binding]) -> None:
        payload = json.dumps({"schema": 2, "store": self.store.hex(),
                              "tickets": [b.encode().hex() for b in bindings]},
                             sort_keys=True).encode()
        publish_atomic_record(self.path, payload, temporary_label="attack-admissions")

    def register(self, binding: Binding) -> Ticket:
        if binding.store != self.store or binding.owner != self.owner:
            raise FenceError("wrong admission store")
        retained = []
        for existing in self._read():
            try:
                ticket = Ticket(existing)
            except FileNotFoundError:
                # Consumers only Open existing objects; binding identity is immutable.
                continue
            try:
                ticket.state()  # corrupted/inaccessible live objects fail closed
                retained.append(existing)
            finally:
                ticket.close(revoke=False)
        if len(retained) >= CAPACITY:
            raise FenceError("admission registry is full; close retired consumers")
        ticket = Ticket(binding, create=True)
        try:
            self._write([*retained, binding])
            ticket.arm()
            return ticket
        except BaseException:
            ticket.close()
            raise

    def revoke(self) -> tuple[str, ...]:
        """Revoke pending tickets before publication; retain entered handles.

        Missing objects retire safely. Other errors abort mutation without undoing
        earlier revocations. Entered-revoked means cancellation is still required.
        """
        entered = []
        for binding in self._read():
            try:
                ticket = Ticket(binding)
            except FileNotFoundError:
                continue
            try:
                if ticket.revoke() == State.ENTERED_REVOKED:
                    entered.append(binding.digest.hex())
            finally:
                ticket.close(revoke=False)
        return tuple(entered)
