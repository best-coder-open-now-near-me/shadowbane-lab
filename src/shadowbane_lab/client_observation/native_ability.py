"""Passive learned ability resolution for the exact reviewed WonderBane 1.3.38.13/.14.

Reviewed native manager lookup uses RVA 0x138757c and its bounded ordered map.
Native name lookup 0x16d910 compares core::String fields +0x13c/+0x154; learned
rank lookup 0x9b400 returns the training record's +0xc value. The unchanged
common power path 0x9c710 uses actor recipient for target mode 2. These are
observation facts, not evidence of server acceptance or skill consumption.
No native function, input, producer lease or second process handle is used.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass

from .native_training import NativePlayerTrainingReader, load_bundled_native_training_profile

_REVIEWED_IMAGES = frozenset(
    {
        "e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8",
        "e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e",
        "381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5",
        "0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d",
        "78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903",
        "e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437",
    }
)
_MANAGER_RVA = 0x138757C


class NativeAbilityError(RuntimeError):
    """Ability identity or eligibility could not be established."""


class NativeAbilityCompatibilityError(NativeAbilityError):
    """The process is outside the exact reviewed observation scope."""


class NativeAbilityReadError(NativeAbilityError):
    """Native data was unavailable, corrupt or changed during observation."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NativeAbilityReadError(message)


@dataclass(frozen=True, slots=True)
class NativeAbilityDefinition:
    power_id: int
    display_name: str
    internal_name: str
    target_mode: int
    category: int
    delivery: int
    learned_rank: int

    def __post_init__(self) -> None:
        for field in ("power_id", "target_mode", "category", "delivery", "learned_rank"):
            value = getattr(self, field)
            if type(value) is not int or not 0 <= value < 2**32:
                raise ValueError(f"{field} must be uint32")
        if not self.power_id or not self.learned_rank:
            raise ValueError("ability requires positive native power ID and learned rank")
        for field in ("display_name", "internal_name"):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or not value.strip()
                or any(ord(char) < 32 for char in value)
            ):
                raise ValueError(
                    f"{field} requires nonempty native text without control characters"
                )

    @property
    def recipient(self) -> str:
        """Supported native recipient; the engagement target remains independently bound."""
        if self.category not in (0, 1) or self.target_mode == 3 or self.delivery == 2:
            raise NativeAbilityError("ability category, target mode or delivery is unsupported")
        if self.target_mode == 2:
            if self.delivery != 0:
                raise NativeAbilityError("self-directed ability requires delivery 0")
            return "actor"
        return "engagement_target"

    def as_dict(self) -> dict[str, object]:
        return {
            "power_id": self.power_id,
            "display_name": self.display_name,
            "internal_name": self.internal_name,
            "target_mode": self.target_mode,
            "category": self.category,
            "delivery": self.delivery,
            "learned_rank": self.learned_rank,
            "recipient": self.recipient,
        }


class NativeAbilityResolver:
    """Borrow the caller's exact character handle; ownership/close stays with that session."""

    def __init__(self, character_session) -> None:
        self._session = character_session
        self._binding = character_session.binding
        self._process = character_session.reader.process
        binding, process = self._binding, self._process
        if (
            binding.executable_sha256 not in _REVIEWED_IMAGES
            or process.executable_sha256 != binding.executable_sha256
            or process.pid != binding.process_id
            or binding.process_creation_filetime_utc <= 0
            or character_session.reader.process_creation_filetime_utc
            != binding.process_creation_filetime_utc
            or process.pointer_size != 4
            or process.executable_name.casefold() != "sb.exe"
        ):
            raise NativeAbilityCompatibilityError(
                "ability resolver requires exact reviewed .13 image"
            )
        self._current()
        self._training = NativePlayerTrainingReader(
            load_bundled_native_training_profile(),
            process,
        )

    def _current(self) -> None:
        if (
            self._session.binding != self._binding
            or self._session.reader.process is not self._process
        ):
            raise NativeAbilityReadError("ability session binding or handle changed")
        self._session.require_current()

    def _read(self, address: int, size: int) -> bytes:
        _require(
            type(address) is int and 0 < size <= 0x300 and 0x10000 <= address <= 0x7FFF0000 - size,
            "ability address outside bounded user range",
        )
        try:
            value = self._process.read_block(address, size)
        except Exception as exc:
            raise NativeAbilityReadError("native ability read failed") from exc
        _require(len(value) == size, "short native ability read")
        return value

    def _u32(self, address: int) -> int:
        return struct.unpack("<I", self._read(address, 4))[0]

    def _definition(self, power_id: int, rank: int) -> NativeAbilityDefinition:
        self._current()
        slot = self._process.base_address + _MANAGER_RVA
        manager = self._u32(slot)
        manager_head = self._read(manager, 8)
        sentinel, count = struct.unpack("<II", manager_head)
        _require(0 < count <= 4096, "ability manager count outside bound")
        sentinel_head = self._read(sentinel, 16)
        node = struct.unpack_from("<I", sentinel_head, 4)[0]
        visited = {}
        matched = None
        for _ in range(64):
            if not node or node == sentinel:
                break
            _require(node not in visited, "ability map cycle")
            raw = self._read(node, 24)
            visited[node] = raw
            key, definition = struct.unpack_from("<II", raw, 16)
            if key == power_id:
                matched = definition
                break
            node = struct.unpack_from("<I", raw, 8 if power_id < key else 12)[0]
        _require(matched is not None, "learned ability definition missing within bounded lookup")
        data = self._read(matched, 0x28C)
        strings = []
        for offset in (0x13C, 0x154):
            begin, end, capacity = struct.unpack_from("<III", data, offset + 4)
            _require(
                begin >= 0x10000
                and begin <= end < capacity
                and not (begin | end | capacity) & 1
                and capacity - begin <= 4096
                and end - begin <= 512,
                "ability string span outside bound",
            )
            raw = self._read(begin, end - begin + 2)
            _require(raw[-2:] == b"\0\0", "ability string lacks terminator")
            try:
                value = raw[:-2].decode("utf-16-le", errors="strict")
            except UnicodeError as exc:
                raise NativeAbilityReadError("invalid native ability UTF-16") from exc
            _require(
                value.strip() and all(ord(char) >= 32 for char in value),
                "ability string is empty or contains control characters",
            )
            _require(self._read(begin, len(raw)) == raw, "ability string changed")
            strings.append(value)
        _require(self._read(matched, 0x28C) == data, "ability definition changed")
        _require(
            all(self._read(address, 24) == raw for address, raw in visited.items()),
            "ability map path changed",
        )
        _require(
            self._u32(slot) == manager
            and self._read(manager, 8) == manager_head
            and self._read(sentinel, 16) == sentinel_head,
            "ability manager changed",
        )
        actual_id = struct.unpack_from("<I", data, 0x138)[0]
        _require(actual_id == power_id, "ability definition ID differs")
        self._current()
        return NativeAbilityDefinition(
            power_id,
            strings[1],
            strings[0],
            struct.unpack_from("<I", data, 0x1A8)[0],
            struct.unpack_from("<I", data, 0x204)[0],
            struct.unpack_from("<I", data, 0x1B4)[0],
            rank,
        )

    def resolve(self, selector: str) -> NativeAbilityDefinition:
        if not isinstance(selector, str) or not selector.strip():
            raise NativeAbilityError("ability selector must be a name or positive numeric ID")
        selector = selector.strip()
        numeric = None
        if selector.lower().startswith("0x") or selector.isdecimal():
            if not re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|[0-9]+)", selector):
                raise NativeAbilityError("invalid numeric ability ID")
            numeric = int(selector, 16 if selector.lower().startswith("0x") else 10)
            if not 0 < numeric < 2**32:
                raise NativeAbilityError("ability ID must be a positive uint32")
        self._current()
        entries = self._training.observe().powers
        _require(len(entries) <= 256, "learned ability vector exceeds inspection bound")
        _require(
            len({entry.token for entry in entries}) == len(entries), "duplicate learned ability"
        )
        eligible = [
            entry
            for entry in entries
            if entry.effective_rank_max > 0 and (numeric is None or entry.token == numeric)
        ]
        if not eligible:
            raise NativeAbilityError("ability is not learned at a positive native rank")
        definitions = [
            self._definition(entry.token, entry.effective_rank_max) for entry in eligible
        ]
        matches = [
            item
            for item in definitions
            if numeric is not None
            or selector.casefold() in (item.display_name.casefold(), item.internal_name.casefold())
        ]
        if len(matches) != 1:
            raise NativeAbilityError("ability name is missing or ambiguous among learned powers")
        # Recheck all searched identities/names before asserting unique resolution.
        _require(
            all(self._definition(item.power_id, item.learned_rank) == item for item in definitions),
            "ability definitions changed during resolution",
        )
        _require(entries == self._training.observe().powers, "learned ability vector changed")
        self._current()
        result = matches[0]
        _ = result.recipient  # Validate routing without importing the PvE policy layer.
        return result


def resolve_learned_ability(character_session, selector: str) -> NativeAbilityDefinition:
    return NativeAbilityResolver(character_session).resolve(selector)
