"""Non-spending vendor menu protocol; template keys have native-validated type zero."""
from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass, fields
from enum import IntEnum

from .movement_wire import Host, request_bytes
from .vendor_wire import Outcome, uint

MAGIC, READY, IN_FLIGHT, UNRESOLVED = 0x57424D31, 1, 2, 4
RANDOM_SENTINEL = 3362971591
RESPONSE_WAIT_SECONDS = 6
_SNAPSHOT = struct.Struct("<QQ20I")
_COMMAND = struct.Struct("<16sQ16s96sI436s")
_RECEIPT = struct.Struct("<16s16sQII96s16sI220s")


class Verb(IntEnum):
    INSPECT = 25
    OPEN_RECIPE = 26
    SELECT_RECIPE = 27
    RANDOM_MODE = 28
    CLOSE_RECIPE = 29
    OPEN_INVENTORY = 30
    CLOSE_INVENTORY = 31


@dataclass(frozen=True, slots=True)
class Snapshot:
    scene: int = 0
    revision: int = 0
    root: int = 0
    manager: int = 0
    front_hud: int = 0
    menu: int = 0
    hireling: int = 0
    building: int = 0
    vendor: int = 0
    recipe: int = 0
    inventory: int = 0
    item_template: int = 0
    prefix: int = 0
    suffix: int = 0
    mode: int = 0
    table: int = 0
    quantity: int = 0
    multiple: int = 0
    selected_template: int = 0
    activated_template: int = 0
    sentinel: int = 0
    recipe_list: int = 0

    @property
    def empty(self) -> bool:
        return self == Snapshot()

    @property
    def owner(self) -> tuple[int, ...]:
        return (self.scene, self.root, self.manager, self.menu,
                self.hireling, self.building, self.vendor)

    def selected(self, template: int) -> bool:
        return bool(self.recipe and self.front_hud == self.recipe and template
                    and self.item_template == self.selected_template
                    == self.activated_template == template)

    def random_recipe(self, template: int, table: int | None = None) -> bool:
        return bool(self.selected(template) and self.mode == 1 and self.table
                    and (table is None or self.table == table)
                    and self.prefix == self.suffix == self.sentinel == RANDOM_SENTINEL
                    and self.quantity == 1 and self.multiple == 0)

    def encode(self) -> bytes:
        values = [getattr(self, f.name) for f in fields(self)]
        for index, value in enumerate(values):
            uint(value, 64 if index < 2 else 32, "vendor menu field")
        if not self.empty:
            if not all((*self.owner, self.revision)) or self.mode > 2 or self.multiple > 1:
                raise ValueError("invalid vendor menu snapshot")
            if not self.recipe and any(values[11:]):
                raise ValueError("absent recipe has nonzero fields")
            if self.recipe and (not self.recipe_list or self.sentinel != RANDOM_SENTINEL):
                raise ValueError("invalid recipe list or sentinel")
        return _SNAPSHOT.pack(*values)

    @classmethod
    def decode(cls, data: bytes) -> Snapshot:
        if len(data) != _SNAPSHOT.size:
            raise ValueError("invalid vendor menu snapshot size")
        result = cls(*_SNAPSHOT.unpack(data))
        result.encode()
        return result


@dataclass(frozen=True, slots=True)
class Command:
    host: Host
    window: int
    request_key: str
    expected: Snapshot = Snapshot()
    template: int = 0

    def encode(self, verb: Verb) -> bytes:
        verb = Verb(verb)
        if not uint(self.window, 32, "window"):
            raise ValueError("window is required")
        uint(self.template, 32, "template")
        if verb == Verb.INSPECT:
            if not self.expected.empty or self.template:
                raise ValueError("inspect cannot carry action arguments")
        elif self.expected.empty or bool(self.template) != (verb == Verb.SELECT_RECIPE):
            raise ValueError("invalid vendor menu action arguments")
        if verb != Verb.INSPECT:
            s = self.expected
            recipe_front = bool(s.recipe and s.front_hud == s.recipe)
            inventory_front = bool(s.inventory and s.front_hud == s.inventory)
            allowed = {
                Verb.OPEN_RECIPE: not s.inventory and (
                    s.front_hud == s.menu or recipe_front and not s.multiple),
                Verb.SELECT_RECIPE: recipe_front and not s.multiple,
                Verb.RANDOM_MODE: s.selected(s.item_template) and not s.multiple,
                Verb.CLOSE_RECIPE: not s.inventory and (s.front_hud == s.menu or recipe_front),
                Verb.OPEN_INVENTORY: not s.recipe and (
                    s.front_hud == s.menu or inventory_front),
                Verb.CLOSE_INVENTORY: not s.recipe and (
                    s.front_hud == s.menu or inventory_front),
            }
            if not allowed[verb]:
                raise ValueError("vendor menu action is not owned or ready")
        return _COMMAND.pack(self.host.encode(), self.window, request_bytes(self.request_key),
                             self.expected.encode(), self.template, bytes(436))


@dataclass(frozen=True, slots=True)
class Receipt:
    request_key: str
    host: Host
    window: int
    outcome: Outcome
    flags: int
    snapshot: Snapshot
    transition_request: str | None = None

    @classmethod
    def decode(cls, data: bytes) -> Receipt:
        if len(data) != _RECEIPT.size:
            raise ValueError("invalid vendor menu receipt size")
        request, host, window, outcome, flags, snapshot, transition, magic, pad = (
            _RECEIPT.unpack(data)
        )
        if magic != MAGIC or flags & ~7 or any(pad) or not 0 < window < 2**32:
            raise ValueError("invalid vendor menu receipt")
        key = str(uuid.UUID(bytes=request))
        request_bytes(key)
        state = Snapshot.decode(snapshot)
        if flags & READY and (state.empty or flags & (IN_FLIGHT | UNRESOLVED)):
            raise ValueError("contradictory vendor menu readiness")
        transition_key = str(uuid.UUID(bytes=transition)) if any(transition) else None
        return cls(key, Host.decode(host), window, Outcome(outcome), flags, state, transition_key)
