"""Typed explicit-list commands on the existing leased native action transport."""

from dataclasses import dataclass

from . import action_channel as channel
from .combat_wire import Command, Verb


@dataclass(frozen=True, slots=True)
class NativeCombatCommand:
    command_id: int
    kind: Verb
    payload: Command

    def encode_slot(self, *, sequence: int, created_tick: int, deadline_tick: int) -> bytes:
        if type(self.command_id) is not int or not 0 < self.command_id < 2**64:
            raise ValueError("combat command ID must be a positive uint64")
        if not 0 < sequence < 2**63 or not 0 < created_tick <= deadline_tick < 2**64:
            raise ValueError("invalid combat command sequence/deadline")
        return channel._COMMAND.pack(
            0, self.command_id, Verb(self.kind), channel.CLIENT_ACTION_PAYLOAD_VERSION,
            created_tick, deadline_tick, 0, 0, 0, 0, 0, 0, bytes(96), bytes(32),
        ) + self.payload.encode()
