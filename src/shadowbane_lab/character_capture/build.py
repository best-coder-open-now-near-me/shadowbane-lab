"""Bounded observation of current local equipment, runes and stat components.

External repeated reads detect observed changes, not an atomic game-thread epoch.
These are capture facts, never operands authorizing gameplay or database writes.
"""
from __future__ import annotations

import hashlib
import math
import struct
from pathlib import Path

from shadowbane_lab.client_alignment.pe import inspect_pe_bytes

ORIGINAL_14 = "e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e"
PREPARED_14 = "78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903"
SUPPORTED_IMAGES = {ORIGINAL_14, PREPARED_14}
STAT_NAMES = {
    0x8AC3C0E6: "strength", 0xE07B3336: "dexterity", 0xB15DC77E: "constitution",
    0xFF665EC3: "intelligence", 0xACB82E33: "spirit",
}
SLOT_NAMES = {
    1: "main_hand", 2: "off_hand", 3: "head", 4: "chest", 5: "arms", 6: "hands",
    7: "ring_1", 8: "ring_2", 9: "neck", 10: "legs", 11: "feet",
    17: "beard", 18: "hair",
}
RUNE_ROLES = {1: "race", 2: "base_class", 3: "class", 4: "discipline", 5: "trait"}
# Filled from the original .14 disk image. Prepared .14 must match every span too.
CODE_RECEIPTS = (
    (0x795da0, 267, 'b74f5cd96d56f0aef7885539e0cef9f3592c8243fd98781711a4f3ae6289cab6'),
    (0x7963e0, 243, 'f443f45191496f1342b9b52a5a3152357a2e6a9ece77284b3271e9d89890f703'),
    (0x1485b0, 288, '376d5e3bdf37364d01e228514091b6f5b2b7c29ef33e46e8c9c19176fe5c885b'),
    (0x5cfb0, 7300, '67978990d883b3475c717849dff9126cee95482e65a4b3a7246d87f8ea820fb5'),
    (0x556e0, 4200, '123d30e1501ad281427bf65e80c8b6babf06fe10bfa73593a542efb25623afe7'),
    (0x272150, 2500, '006d87824078a3ed32affc281f706fd24d7cb37b95e0e53745d6087531a77d37'),
    (0x69350, 200, '575398f67bf8203ec2b4f4962b602f52e68bc7cd7f1a55dba2e86c6e48d4cc58'),
    (0x2ec1d0, 390, '9ab7960821f34970c8ea5ab7f82f2c14edeb11124540f890123b2a49b9e0b7f8'),
    (0x68020, 550, '60343c7c5a8c88b42db7bcf3bbebb96b782f9a931c9ed6538aaf9c6386def46a'),
    (0x88760, 200, 'cc90c23687955dd5ec56153cb1b601c95c0200811684d4cdacc1e5a8d3b06aa2'),
    (0xb8b30, 80, '3c224f3ea760908c5232750120fbe4e0ca177ee4310691e1ab3999b254896574'),
    (0xb8cb0, 80, '0cdb9e3d8453c64f50645ba0b4a8caa5db79e9bac56f04c887235c999b6f2fdd'),
    (0x1143274, 8, 'd0e954df8bdb90aaed004ee18ecf5d0742f6744641e2edca8659fa3d0f3450f1'),
    (0x1142744, 8, 'e519ba80780409967e5bcdb191c3c8ebec4ae5cb768e0e01eb71b3d766c53793'),
    (0x114792c, 8, 'c35ff241feec33e3965c0826440646adc7b8adf7d474e7961c3b13cf0ab16852'),
)


class BuildReadError(RuntimeError):
    pass


def verify_build_image(path, expected_sha256):
    data = Path(path).read_bytes()
    image = inspect_pe_bytes(data)
    if image.sha256 != expected_sha256 or image.sha256 not in SUPPORTED_IMAGES:
        raise BuildReadError("Automatic build capture requires a reviewed exact .14 image.")
    for rva, length, digest in CODE_RECEIPTS:
        sections = [s for s in image.sections
                    if s.virtual_address <= rva
                    and rva + length <= s.virtual_address + s.raw_size]
        if len(sections) != 1:
            raise BuildReadError("Build-reader code receipt is outside a mapped disk section.")
        offset = sections[0].raw_offset + rva - sections[0].virtual_address
        if hashlib.sha256(data[offset:offset + length]).hexdigest() != digest:
            raise BuildReadError(f"Build-reader layout code differs at RVA {rva:#x}.")


class ReadSet:
    def __init__(self, process):
        self.process = process
        self.blocks = {}
        self.bytes = 0

    def read(self, address, size):
        if not 0x10000 <= address < address + size <= 0x7FFF0000 or size > 8192:
            raise BuildReadError("Invalid bounded build pointer.")
        key = (address, size)
        if key not in self.blocks:
            self.bytes += size
            if self.bytes > 262144 or len(self.blocks) >= 8192:
                raise BuildReadError("Build read budget exhausted.")
            self.blocks[key] = self.raw(address, size)
        return self.blocks[key]

    def raw(self, address, size):
        pieces = []
        for offset in range(0, size, 64):
            length = min(64, size - offset)
            try:
                value = self.process.read(address + offset, length)
            except Exception as exc:
                raise BuildReadError("Could not read a current build record.") from exc
            if len(value) != length:
                raise BuildReadError("Short build record.")
            pieces.append(value)
        return b"".join(pieces)

    def words(self, address, count=1):
        return struct.unpack("<" + "I" * count, self.read(address, 4 * count))

    def verify(self):
        for (address, size), value in self.blocks.items():
            if self.raw(address, size) != value:
                raise BuildReadError("Build changed during observation; retry.")

    def tree(self, address, record_words, maximum):
        head, count = self.words(address, 2)
        if count > maximum or head % 4:
            raise BuildReadError("Invalid build tree header.")
        root, first, last = self.words(head + 4, 3)
        seen, ordered = set(), []

        def walk(node, parent, depth):
            if node in (0, head):
                return
            if node % 4 or node in seen or len(seen) >= maximum or depth > 32:
                raise BuildReadError("Cyclic or oversized build tree.")
            seen.add(node)
            row = self.words(node, record_words)
            if row[1] not in ((0, head) if parent == head else (parent,)):
                raise BuildReadError("Build tree parent mismatch.")
            walk(row[2], node, depth + 1)
            ordered.append((node, row))
            walk(row[3], node, depth + 1)

        walk(root, head, 0)
        if (len(seen) != count or first != (ordered[0][0] if ordered else head)
                or last != (ordered[-1][0] if ordered else head)):
            raise BuildReadError("Build tree count/extrema mismatch.")
        if [r[4] for _, r in ordered] != sorted(r[4] for _, r in ordered):
            raise BuildReadError("Build tree ordering mismatch.")
        return [row for _, row in ordered]

    def string(self, address):
        _, begin, end, capacity = self.words(address, 4)
        if begin == end == capacity == 0:
            return ""
        if (begin % 2 or end < begin or (end - begin) % 2 or end - begin > 1024
                or capacity < end + 2 or capacity > 0x7FFF0000):
            raise BuildReadError("Invalid item name bounds.")
        raw = self.read(begin, end - begin + 2)
        if raw[-2:] != b"\0\0":
            raise BuildReadError("Unterminated item name.")
        try:
            return raw[:-2].decode("utf-16-le")
        except UnicodeError as exc:
            raise BuildReadError("Invalid item name encoding.") from exc


class NativeCharacterBuildReader:
    def __init__(self, session):
        self.session = session
        self.process = session.reader.process
        verify_build_image(self.process.executable_path, self.process.executable_sha256)

    def observe(self):
        session, process = self.session, self.process
        session.require_current()
        r = ReadSet(process)
        player = session.binding.identity.player_pointer
        base = process.base_address
        slots = r.words(player + 0xBA8, 19)
        equipment, item_keys = [], set()
        for slot, pointer in enumerate(slots):
            entry = {"slot": slot, "slot_name": SLOT_NAMES.get(slot), "item": None}
            if pointer:
                if pointer % 4 or r.words(pointer)[0] != base + 0x1142748:
                    raise BuildReadError("Equipped object is not a reviewed ArcItem.")
                template_id, template_type, item_id, item_type = r.words(pointer + 0x10, 4)
                if not template_id or template_type or not item_id or item_type not in (30, 40):
                    raise BuildReadError("Invalid equipped item keys.")
                if (item_id, item_type) in item_keys:
                    raise BuildReadError("Duplicate equipped item identity.")
                item_keys.add((item_id, item_type))
                current, maximum = struct.unpack("<ff", r.read(pointer + 0x5CC, 8))
                if not all(math.isfinite(v) and v >= 0 for v in (current, maximum)):
                    raise BuildReadError("Invalid item durability.")
                entry["item"] = {
                    "template_id": template_id, "object_key": [item_id, item_type],
                    "name": r.string(pointer + 0xD8),
                    "durability": {"current": current, "maximum": maximum},
                    "stack_quantity": r.words(pointer + 0x6B8)[0],
                    "charges_remaining": r.words(pointer + 0x744)[0],
                    "effects": self._effects(r, pointer),
                }
            equipment.append(entry)
        runes = []
        for row in r.tree(player + 0xBF4, 6, 128):
            role, pointer = row[4:6]
            # ArcRune primary (ArcItem base at zero); no inventory-container scan.
            if role not in RUNE_ROLES or r.words(pointer)[0] != base + 0x1143278:
                raise BuildReadError("Unsupported applied rune record.")
            template, template_type, instance, kind = r.words(pointer + 0x10, 4)
            if not template or template_type or not instance or not kind:
                raise BuildReadError("Invalid applied rune identity.")
            runes.append({"role": RUNE_ROLES[role], "role_id": role, "template_id": template,
                          "object_key": [instance, kind]})
        stats = []
        for row in r.tree(player + 0xCB0, 11, 32):
            token = row[4]
            raw = row[5:]
            signed = struct.unpack("<6i", struct.pack("<6I", *raw))
            # Deliberately retain unnamed components instead of guessing allocations.
            stats.append({"token": token, "name": STAT_NAMES.get(token),
                          "current_raw": signed[0], "cap_raw": signed[4],
                          "wire_adjustment": signed[5], "component_words": list(raw)})
        if {s["token"] for s in stats} != set(STAT_NAMES) or len(stats) != 5:
            raise BuildReadError("The five required character stat records are incomplete.")
        r.verify()
        session.require_current()
        return {"schema_version": 1, "equipment": equipment, "applied_runes": runes,
                "attributes": stats, "consistency": "repeated_external_reads",
                "database_import_ready": False,
                "unresolved": ["base_attribute_allocations", "destination_content_mapping",
                               "item_effect_names_and_prefix_suffix_roles"]}

    def _effects(self, r, pointer):
        begin, end, capacity = r.words(pointer + 0x58C, 3)
        if (begin > end or end > capacity or begin % 4 or (end - begin) % 8
                or (capacity - begin) % 8 or capacity - begin > 256 * 8
                or (not begin and (end or capacity))):
            raise BuildReadError("Invalid equipped effect vector.")
        if begin == end:
            return []
        records, seen = [], set()
        for token, effect in struct.iter_unpack("<II", r.read(begin, end - begin)):
            if not token or effect in seen or effect % 4:
                raise BuildReadError("Invalid or duplicate equipped effect.")
            seen.add(effect)
            definition = r.words(effect)[0]
            if (r.words(definition)[0] != self.process.base_address + 0x1147930
                    or r.words(definition + 0x14)[0] != token
                    or r.words(effect + 0x14)[0] != definition + 0x5C):
                raise BuildReadError("Unreviewed equipped effect descriptor.")
            records.append({"token": token, "rank": r.words(effect + 0x10)[0]})
        return records
