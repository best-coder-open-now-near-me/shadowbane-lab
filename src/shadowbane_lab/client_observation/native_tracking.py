"""Passive native Hunt Foe result storage for the reviewed Wonderbane .16 client.

Reads the client's owned tracking objects, not rendered labels or system messages.
A loaded list can survive a previous query: sampling it does not establish response
age, current range coverage, hostility, or permission to attack. See docs/native-track.md.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .native_object import NativeObjectKey
from .native_vendor_dialog import NativeVendorDialogCaptureError
from .native_vendor_queue import _ReadSet
from .native_vendor_roster import _text

REVIEWED_TRACK_EXECUTABLES = frozenset({
    "a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a",
    "1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c",
})


class NativeTrackingError(RuntimeError):
    """The bound character's tracking list cannot be observed coherently."""


class NativeTrackingCompatibilityError(NativeTrackingError):
    """The exact executable has no qualified Track layout."""


@dataclass(frozen=True, slots=True)
class NativeTrackingContact:
    object_key: NativeObjectKey
    name: str

    def as_dict(self):
        return {
            "object_key": [self.object_key.object_type, self.object_key.object_uuid],
            "name": self.name,
        }


@dataclass(frozen=True, slots=True)
class NativeTrackingSnapshot:
    """Current storage contents; intentionally has no invented response timestamp."""

    loaded: bool
    power_id: int | None
    contacts: tuple[NativeTrackingContact, ...]

    def as_dict(self):
        return {
            "loaded": self.loaded,
            "power_id": self.power_id,
            "contacts": [contact.as_dict() for contact in self.contacts],
            "source": "native_tracking_list",
            "response_age_seconds": None,
        }


class NativeTrackingReader:
    """Borrow one exact character session; never invoke Track or acquire a producer."""

    def __init__(self, character_session):
        self._session = character_session
        self._binding = character_session.binding
        self._memory = character_session.reader.process
        b, m = self._binding, self._memory
        if (
            b.executable_sha256 not in REVIEWED_TRACK_EXECUTABLES
            or m.executable_sha256 != b.executable_sha256
            or m.executable_name.casefold() != "sb.exe"
            or m.pointer_size != 4 or m.pid != b.process_id
            or b.process_creation_filetime_utc <= 0
            or character_session.reader.process_creation_filetime_utc
            != b.process_creation_filetime_utc
        ):
            raise NativeTrackingCompatibilityError("unreviewed Track build or process lifetime")
        self._current()

    def _current(self):
        if (self._session.binding != self._binding
                or self._session.reader.process is not self._memory):
            raise NativeTrackingError("tracking character session changed")
        self._session.require_current()

    def read(self) -> NativeTrackingSnapshot:
        self._current()
        try:
            result = self._read()
        except (NativeVendorDialogCaptureError, OSError, struct.error) as exc:
            raise NativeTrackingError("native tracking objects unavailable or changed") from exc
        self._current()
        return result

    def _read(self):
        r, base = _ReadSet(self._memory), self._memory.base_address
        root = r.word(base + 0x16A7BFC)
        r.require(root, base + 0x1174884, "game window type")
        r.require(root + 0x64, 2, "in-world state")
        huds = [hud for hud in r.hud_stack(root) if r.word(hud) == base + 0x116FB58]
        if len(huds) > 1:
            raise NativeTrackingError("multiple native tracking lists")
        if not huds:
            r.verify()
            return NativeTrackingSnapshot(False, None, ())
        hud = huds[0]
        power_id = r.word(hud + 0x3B8)
        listing = r.word(hud + 0x3C0)
        if listing not in r.vector(hud + 0x54, 512):
            raise NativeTrackingError("tracking list is outside its HUD children")
        r.require(listing, base + 0x116ACF0, "tracking list type")
        r.require(listing + 0x3BC, hud, "tracking list owner")
        # Selection is not read: it has no bearing on contact identity or combat.
        contacts, entries, keys = [], set(), set()
        for control in r.vector(listing + 0x408, 512):
            r.require(control, base + 0x116AEBC, "tracking row type")
            r.require(control + 0x3BC, hud, "tracking row HUD owner")
            r.require(control + 0x458, listing, "tracking row list owner")
            entry = r.word(control + 0x44C)
            r.require(entry, base + 0x116FCC0, "tracking entry type")
            r.require(entry + 8, 0x1C, "tracking entry kind")
            key = NativeObjectKey(*struct.unpack("<II", r.read(entry + 0x10, 8)))
            if entry in entries or key in keys:
                raise NativeTrackingError("duplicate tracking contact ownership")
            name = _text(r, entry + 0x20)
            if not name.strip() or any(ord(char) < 32 for char in name):
                raise NativeTrackingError("invalid tracking contact name")
            entries.add(entry)
            keys.add(key)
            contacts.append(NativeTrackingContact(key, name))
        r.verify()
        return NativeTrackingSnapshot(True, power_id, tuple(contacts))
