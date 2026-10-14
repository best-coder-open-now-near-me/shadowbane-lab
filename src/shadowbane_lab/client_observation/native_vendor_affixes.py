"""Current-image owned affix assessment; never grants recycling authority."""
from __future__ import annotations

import hashlib
import re
import shlex
import struct
import time

from shadowbane_lab.equipment.affix_reference import load_bundled_affix_reference
from shadowbane_lab.equipment.crafting_assessment import compact_affix_token
from shadowbane_lab.equipment.model import AffixPosition
from shadowbane_lab.equipment.rolling_policy import evaluate_roll_tiers

from .native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from .native_vendor_queue import _inventory, _owned_vendor, _qualified_memory, _ReadSet
from .native_vendor_roster import _text

_IMAGE = "6bd0e391edc1c773b4c96d8a9801db45f96db9e34202afcfc8d383d4971fe5ad"
_EFFECTS_SHA = "2f9a68e28cd8cc478b9aceeab571deac7de044f57b007f78e9e98429b6a59a2b"
_ITEMS_SHA = "9188a03d2aa4d6f1a277281f6041f447e06931726d2036448f7ed0715c63ebcf"
_REGISTRY = 0x1387738
_TEMPLATE = 26990


class _AffixReadSet(_ReadSet):
    def __init__(self, memory):
        super().__init__(memory)
        self.calls, self.bytes, self.deadline = 0, 0, time.monotonic() + 3

    def read(self, address, size):
        self.calls += 1
        self.bytes += size
        if (self.calls > 32768 or self.bytes > 2 * 1024 * 1024
                or time.monotonic() > self.deadline):
            raise NativeVendorDialogCaptureError("affix transaction exceeds its read bound")
        return super().read(address, size)

    def verify(self):
        super().verify()
        if time.monotonic() > self.deadline:
            raise NativeVendorDialogCaptureError("affix transaction exceeds its time bound")


def _dictionaries(effects, items):
    for raw, expected in ((effects, _EFFECTS_SHA), (items, _ITEMS_SHA)):
        if (type(raw) is not bytes or len(raw) > 4 * 1024 * 1024
                or hashlib.sha256(raw).hexdigest() != expected):
            raise NativeVendorDialogCompatibilityError("affix dictionary identity differs")
    rows = []
    for line in items.decode("cp1252").splitlines():
        stripped = line.strip()
        if stripped and stripped.split(maxsplit=1)[0].isdigit():
            fields = shlex.split(line)
            if int(fields[0]) == _TEMPLATE:
                rows.append(fields)
    if (len(rows) != 1 or len(rows[0]) != 4 or rows[0][1:]
            != ["Gilded Scepter", "N", "!PREFIX! !ITEMNAME! !SUFFIX!"]):
        raise NativeVendorDialogCompatibilityError("affix item-name grammar differs")
    names = {"prefix": set(), "suffix": set()}
    for line in effects.decode("utf-16").splitlines():
        if not line.startswith('"Effect'):
            continue
        fields = shlex.split(line)
        if len(fields) != 4:
            raise NativeVendorDialogCaptureError("invalid current affix dictionary row")
        for role in names:
            if fields[0].startswith("Effect" + role.capitalize() + ":"):
                names[role].add(fields[3])  # Current ItemENGLISH gender is N.
    if not all(names.values()):
        raise NativeVendorDialogCaptureError("current affix dictionary is empty")
    return names, rows[0][1]


class _Parents:
    def __init__(self, reads, base):
        self.r, self.base, self.cache = reads, base, {}
        self.manager = reads.word(base + _REGISTRY)
        self.sentinel, count = struct.unpack("<II", reads.read(self.manager, 8))
        if not 0 < count <= 4096:
            raise NativeVendorDialogCaptureError("affix registry count exceeds its bound")
        self.root = reads.word(self.sentinel + 4)

    def get(self, token):
        if token in self.cache:
            return self.cache[token]
        node, low, high, seen, definition = self.root, 0, 2**32 - 1, set(), None
        while node and node != self.sentinel:
            if node in seen or len(seen) >= 64:
                raise NativeVendorDialogCaptureError("affix registry cycle or path bound")
            seen.add(node)
            raw = struct.unpack("<6I", self.r.read(node, 24))
            key = raw[4]
            if not low < key <= high:
                raise NativeVendorDialogCaptureError("affix registry ordering differs")
            if key == token:
                definition = raw[5]
                break
            if token < key:
                high, node = key - 1, raw[2]
            else:
                low, node = key, raw[3]
        result = None
        if definition is not None:
            identifier = _text(self.r, definition + 4)
            if re.fullmatch(r"(?:PRE|SUF)-[0-9]{3}", identifier):
                if (self.r.word(definition + 0x1C) != token
                        or compact_affix_token(identifier) != token):
                    raise NativeVendorDialogCaptureError("affix parent key and definition differ")
                kind = self.r.word(definition) - self.base
                if kind == 0x1148B48:
                    children = (self.r.word(definition + 0x88),)
                elif kind == 0x1148B84:
                    children = self.r.vector(definition + 0x88, 64)
                else:
                    children = None
                if children and all(children) and len(set(children)) == len(children):
                    result = dict(token=token, identifier=identifier,
                                  role="prefix" if identifier.startswith("PRE") else "suffix",
                                  children=list(children), definition_address=definition,
                                  action_class_rva=kind)
        self.cache[token] = result
        return result


def _tier(reference, name, role):
    rows = reference.lookup(name, position=AffixPosition(role))
    # Do not assign an armor-only tier to a scepter or resolve reused names by guess.
    applicable = [row for row in rows if any(
        "scepter" in group.casefold() or group == "Weapons (source category)"
        for group in row.equipment)]
    tiers = {row.tier for row in applicable}
    return next(iter(tiers)) if len(tiers) == 1 else None


def _assess(row, label, parents, names, base_name, reference):
    unknown = dict(disposition="keep", reason="unknown_affix_preserved",
                   prefix_tier=None, suffix_tier=None, command_admitted=False)
    if (row.get("name") or not row.get("has_item_data") or label.count(base_name) != 1
            or any(e["source_type"] != 1 or e["trains"] for e in row.get("effects", []))):
        return unknown
    tokens = [e["token"] for e in row.get("effects", [])]
    if len(set(tokens)) != len(tokens):
        return unknown
    by_role = {"prefix": [], "suffix": []}
    covered = set()
    for parent in parents:
        if parent:
            by_role[parent["role"]].append(parent)
            covered.update((parent["token"], *parent["children"]))
    if covered != set(tokens) or any(len(p) > 1 for p in by_role.values()):
        return unknown
    before, after = label.split(base_name)
    labels = dict(prefix=before.strip(), suffix=after.strip())
    tiers, identities = {}, {}
    for role, text in labels.items():
        candidates = by_role[role]
        if not candidates and not text:
            tiers[role], identities[role] = 0, None
        elif len(candidates) == 1 and text and text in names[role]:
            tiers[role] = _tier(reference, text, role)
            identities[role] = dict(candidates[0], display_name=text)
        else:
            return unknown
    disposition = evaluate_roll_tiers(tiers["prefix"], tiers["suffix"], completed=True)
    return dict(disposition=str(disposition),
                reason=("unknown_affix_preserved" if None in tiers.values()
                        else "confirmed_low_tier" if disposition == "exclude"
                        else "no_excluded_tier"),
                prefix_tier=tiers["prefix"], suffix_tier=tiers["suffix"],
                prefix=identities["prefix"], suffix=identities["suffix"], command_admitted=False)


def read_native_vendor_affixes(memory, *, building, vendor, effects_dictionary, item_dictionary):
    """Assess displayed owned scepters using current labels, parents and child coverage.

    This is a presence-only observation. Unknowns override exclusion. No stock
    removal, absence, whole-inventory capacity or command authority is inferred.
    The caller must revalidate exact current native ownership before any action.
    """
    lifetime = _qualified_memory(memory)
    if memory.executable_sha256 != _IMAGE:
        raise NativeVendorDialogCompatibilityError("affix identity is unqualified for this image")
    names, base_name = _dictionaries(effects_dictionary, item_dictionary)
    r, base = _AffixReadSet(memory), memory.base_address
    root, manager, hud, active, owned_building, _, owned_vendor = _owned_vendor(r, base)
    if owned_building != building or owned_vendor != dict(object_id=vendor, object_type=42):
        raise NativeVendorDialogCaptureError("affix inventory belongs to another vendor")
    inventory = _inventory(r, base, active, manager)
    if inventory is None:
        raise NativeVendorDialogCaptureError("affix inventory is not currently visible")
    parents, reference, items = _Parents(r, base), load_bundled_affix_reference(), []
    for row in inventory["items"]:
        if row["template"] != dict(object_id=_TEMPLATE, object_type=0):
            continue
        label = _text(r, row["native_item_address"] + 0xD8)
        definitions = [parents.get(e["token"]) for e in row.get("effects", [])]
        assessment = _assess(row, label, definitions, names, base_name, reference)
        items.append(dict(item=row["item"], template=row["template"], display_name=label,
                          effects=row.get("effects"), assessment=assessment))
    r.verify()
    return dict(schema_version=1, record_type="owned_vendor_affix_assessment",
                process_id=memory.pid, process_creation_filetime_utc=lifetime,
                executable_sha256=memory.executable_sha256, root=root, manager=manager, menu=hud,
                building=dict(object_id=building, object_type=8), vendor=owned_vendor,
                effects_dictionary_sha256=_EFFECTS_SHA, item_dictionary_sha256=_ITEMS_SHA,
                reference_edition=reference.edition, reference_sha256=reference.source_sha256,
                scope="displayed_entries", complete_inventory=False, items=items,
                command_admitted=False)
