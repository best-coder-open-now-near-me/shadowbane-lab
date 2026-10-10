"""Read-only canonical native actor facts; clocks establish freshness, never expiry.

The native writer owns a retained actor lifetime and publishes complete copied
facts or explicit unknown. The host never reconstructs missing effects by reading
object memory, queue receipts, names, UI state, or timers.
"""

from __future__ import annotations

import ctypes as c
import math
import struct
from dataclasses import dataclass, replace
from enum import IntEnum, IntFlag

from .actor_selector_manifest import Manifest, Selector
from .combat_fence_windows import Windows

HEADER_SIZE = 256
SLOT_SIZE = 32768
SIZE = HEADER_SIZE + 2 * SLOT_SIZE
_HEADER = struct.Struct("<8s6IQ16s32s4IQi140s")
_FRAME = struct.Struct("<QQ16sQQ8IQI164s")
_EFFECT = struct.Struct("<10I")
_READY = struct.Struct("<26I24s")
_TIMING = struct.Struct("<IIQ8s")
_APPLICATION = struct.Struct("<32s32sQQ4I32s")
_DESCRIPTOR = struct.Struct("<3IBB2s")
assert (
    _HEADER.size,
    _FRAME.size,
    _EFFECT.size,
    _READY.size,
    _APPLICATION.size,
    _DESCRIPTOR.size,
) == (256, 256, 40, 128, 128, 16)


class AdmissionBlock(IntFlag):
    INITIATION = 1
    NATIVE_USE = 2
    LOCAL_ACTION = 4
    FOREIGN_TARGET = 8
    CHILD_CLEANUP = 16
    MANUAL_ACTIVITY = 32


class PublicationError(RuntimeError):
    pass


class Coverage(IntEnum):
    UNKNOWN = 0
    MISSING = 1
    PARTIAL = 2
    PRESENT = 3


class Readiness(IntEnum):
    UNKNOWN = 0
    READY = 1
    NOT_LEARNED = 2
    INITIATION_PENDING = 3
    GLOBAL_RECOVERY = 4
    POWER_REUSE = 5
    STANCE_INELIGIBLE = 6
    UNSUPPORTED = 7
    ITEM_UNAVAILABLE = 8


def _require(ok, message):
    if not ok:
        raise PublicationError(message)


def _address(value):
    return 0x10000 <= value < 0x80000000 and value % 4 == 0


@dataclass(frozen=True, slots=True)
class Identity:
    process_id: int
    process_creation: int
    actor_lifetime: bytes
    manifest_digest: bytes
    actor_key: tuple[int, int]
    actor_address: int
    scene: int


@dataclass(frozen=True, slots=True)
class Header:
    identity: Identity
    active: int

    @classmethod
    def decode(cls, payload):
        _require(
            type(payload) is bytes and len(payload) == HEADER_SIZE,
            "invalid publication header size",
        )
        v = _HEADER.unpack(payload)
        _require(
            v[:3] == (b"WBAPUB3\0", 3, SIZE)
            and v[3]
            and v[4:7] == (SLOT_SIZE, 2, 0)
            and v[7]
            and any(v[8])
            and any(v[9])
            and v[10]
            and v[11] == 53
            and _address(v[12])
            and not v[13]
            and v[14]
            and v[15] in (-1, 0, 1)
            and not any(v[16]),
            "invalid publication identity/geometry",
        )
        return cls(Identity(v[3], v[7], v[8], v[9], (v[10], v[11]), v[12], v[14]), v[15])


@dataclass(frozen=True, slots=True)
class Effect:
    descriptor_id: int
    action_id: int
    rank: int
    native_class: int
    source_tag: int
    source_words: tuple[int, int, int]
    action_class: int
    suppression: int


@dataclass(frozen=True, slots=True)
class Descriptor:
    descriptor_id: int
    action_id: int
    action_class: int
    suppression: int
    present: bool


@dataclass(frozen=True, slots=True)
class ActionFacts:
    selector: Selector
    learned_rank: int
    category: int
    target_mode: int
    delivery: int
    required_mode: int
    coverage: Coverage
    readiness: Readiness
    descriptors: tuple[Descriptor, ...]
    item_key: tuple[int, int]
    template_key: tuple[int, int]
    item_hint: int
    template_hint: int
    quantity: int
    item_type: int
    item_flags: int
    remaining_ms: int | None = None
    deadline_stamp: int | None = None

    @property
    def renewal_due(self):
        """Scheduling hint for the one qualified early-renewal item, never expiry."""
        return (
            self.selector.kind == 4
            and self.selector.template_id == 980066
            and self.selector.coverage_power_id == 429021400
            and self.selector.coverage_kind == 0
            and self.coverage is Coverage.PRESENT
            and self.remaining_ms is not None
            and self.deadline_stamp is not None
            and self.remaining_ms <= 15000
        )


class ApplicationState(IntEnum):
    # Journal states differ from action-wire Application (UNKNOWN=3 there).
    NONE = 0
    PENDING = 1
    OBSERVED = 2
    INTERRUPTED = 3


@dataclass(frozen=True, slots=True)
class Application:
    group_digest: bytes
    command_digest: bytes
    submitted_revision: int
    observed_revision: int
    entry: int  # Native journal: never entered=0, entered=1, uncertain=2.
    state: ApplicationState  # Local interruption is not server effect consumption.
    local_settled: bool
    queued: bool


@dataclass(frozen=True, slots=True)
class Publication:
    identity: Identity
    sequence: int
    revision: int
    snapshot_id: bytes
    sampled_tick: int
    effect_epoch: int
    unknown: int
    complete: bool
    actor_mode: int
    initiation_clear: bool
    effects: tuple[Effect, ...]
    actions: tuple[ActionFacts, ...]
    applications: tuple[Application, ...]
    admission_revision: int
    admission_blocks: AdmissionBlock
    stationary: bool = False

    def action_facts(self):
        """Countdown is sampled; deadline identity and renewal boundary are facts."""
        return tuple(
            (replace(a, remaining_ms=0 if a.remaining_ms is not None else None), a.renewal_due)
            for a in self.actions
        )

    def eligibility_facts(self):
        """Exact native SameEligibility projection, excluding journal/effect history.

        Descriptor offsets are canonical cumulative counts checked by decode;
        descriptor content is intentionally outside the native readiness record.
        """
        return (
            self.complete,
            self.unknown,
            self.actor_mode,
            self.initiation_clear,
            self.stationary,
            self.admission_blocks,
            tuple(
                (
                    replace(a, descriptors=(), remaining_ms=(
                        0 if a.remaining_ms is not None else None
                    )),
                    len(a.descriptors),
                    a.renewal_due,
                )
                for a in self.actions
            ),
        )

    @classmethod
    def decode(cls, header, payload, manifest):
        _require(
            isinstance(header, Header)
            and isinstance(manifest, Manifest)
            and type(payload) is bytes
            and len(payload) == SLOT_SIZE,
            "invalid publication inputs",
        )
        _require(
            header.identity.manifest_digest == manifest.digest
            and header.identity.process_id == manifest.client_pid
            and header.identity.process_creation == manifest.client_creation,
            "publication manifest/process mismatch",
        )
        v = _FRAME.unpack_from(payload)
        (
            sequence,
            revision,
            snapshot,
            tick,
            epoch,
            unknown,
            complete,
            ec,
            rc,
            ac,
            dc,
            mode,
            clear,
            admission_revision,
            admission_blocks,
            reserved,
        ) = v
        stationary = int.from_bytes(reserved[:4], "little")
        reserved = reserved[4:]
        _require(
            0 < sequence < 2**63
            and sequence % 2 == 0
            and revision
            and any(snapshot)
            and tick
            and unknown <= 10
            and complete <= 1
            and ec <= 256
            and rc <= 32
            and ac <= 32
            and dc <= 256
            and clear <= 1
            and stationary <= 1
            and 0 < admission_revision < 2**64
            and admission_blocks & ~63 == 0
            and not any(reserved)
            and not any(payload[22784:]),
            "invalid or incomplete publication frame",
        )
        if not complete:
            _require(
                unknown
                and not any((epoch, ec, rc, ac, dc, mode, clear, stationary, admission_blocks))
                and not any(payload[256:]),
                "unknown publication contains factual authority",
            )
            return cls(
                header.identity,
                sequence,
                revision,
                snapshot,
                tick,
                epoch,
                unknown,
                False,
                mode,
                False,
                (),
                (),
                (),
                admission_revision,
                AdmissionBlock(admission_blocks),
            )
        _require(
            not unknown and epoch and rc == len(manifest.selectors) and 1 <= mode <= 3,
            "incomplete native coverage publication",
        )
        _require(
            not any(payload[256 + ec * 40 : 10496])
            and not any(payload[10496 + rc * 128 : 14592])
            and not any(payload[14592 + ac * 128 : 18688])
            and not any(payload[18688 + dc * 16 : 22784]),
            "unused publication records must be zero",
        )
        effects = []
        for i in range(ec):
            e = _EFFECT.unpack_from(payload, 256 + i * 40)
            _require(
                e[0] and e[1] and e[3] <= 2 and e[4] <= 1 and e[8] <= 6 and e[9] <= 255,
                "unsupported native effect record",
            )
            effects.append(Effect(*e[:5], e[5:8], *e[8:]))
        descriptors = []
        for i in range(dc):
            d = _DESCRIPTOR.unpack_from(payload, 18688 + i * 16)
            _require(
                d[0] and d[1] and d[2] <= 6 and d[4] <= 1 and not any(d[5]),
                "unsupported descriptor metadata",
            )
            descriptors.append(Descriptor(*d[:4], bool(d[4])))
            _require(
                bool(d[4]) == any(e.descriptor_id == d[0] for e in effects),
                "descriptor presence disagrees with native effect census",
            )
        actions = []
        offset = 0
        for i in range(rc):
            r = _READY.unpack_from(payload, 10496 + i * 128)
            _require(
                _READY.pack(*r)[:32] == manifest.selectors[i].encode()
                and r[8] <= 9999
                and r[13] <= 3
                and r[14] <= 8
                and r[15] == offset
                and 1 <= r[16] <= 64
                and r[16] <= dc - offset,
                "readiness selector/descriptor mismatch",
            )
            timing_flags, remaining_ms, deadline_stamp, timing_reserved = _TIMING.unpack(r[26])
            deadline = struct.unpack("<d", struct.pack("<Q", deadline_stamp))[0]
            _require(
                timing_flags in (0, 1)
                and not any(timing_reserved)
                and (
                    (timing_flags == 0 and remaining_ms == 0 and deadline_stamp == 0)
                    or (timing_flags == 1 and math.isfinite(deadline) and deadline > 0
                        and r[13] == Coverage.PRESENT)
                ),
                "invalid native finite timing",
            )
            selection = tuple(descriptors[offset : offset + r[16]])
            offset += r[16]
            selector = manifest.selectors[i]
            if selector.kind == 3:
                _require(not any(r[17:26]), "power publication contains item operand")
                if r[14] == Readiness.READY:
                    _require(
                        r[8]
                        and r[9] <= 1
                        and r[10] == 2
                        and not r[11]
                        and 1 <= r[12] <= 3
                        and not (r[12] == 2 and mode > 1),
                        "unsupported power cannot advertise ready",
                    )
            elif r[14] == Readiness.UNKNOWN:
                _require(not any(r[17:26]), "unknown item contains operand")
            elif any(r[21:24]):
                _require(
                    r[17]
                    and r[18]
                    and r[19] == selector.template_id
                    and not r[20]
                    and _address(r[21])
                    and _address(r[22])
                    and r[21] != r[22]
                    and r[23]
                    and r[24:26] == (8, 10),
                    "unqualified retained item operand",
                )
            else:
                _require(
                    not any(r[17:26]) and r[14] == Readiness.ITEM_UNAVAILABLE,
                    "unavailable item cannot advertise readiness",
                )
            present = sum(d.present for d in selection)
            _require(
                selector.kind != 3 or r[14] != Readiness.READY or clear or stationary,
                "ready power requires clear initiation or positive stationary state",
            )
            expected = (
                Coverage.PRESENT
                if present == len(selection)
                else Coverage.PARTIAL
                if present
                else Coverage.MISSING
                if not any(d.suppression for d in selection)
                else Coverage.UNKNOWN
            )
            _require(r[13] == expected, "coverage disagrees with copied native descriptors")
            actions.append(
                ActionFacts(
                    selector,
                    *r[8:13],
                    Coverage(r[13]),
                    Readiness(r[14]),
                    selection,
                    r[17:19],
                    r[19:21],
                    *r[21:26],
                    remaining_ms if timing_flags else None,
                    deadline_stamp if timing_flags else None,
                )
            )
        _require(offset == dc, "unreferenced descriptor metadata")
        applications = []
        for i in range(ac):
            a = _APPLICATION.unpack_from(payload, 14592 + i * 128)
            _require(
                any(a[0])
                and any(a[1])
                and a[2]
                and a[4] <= 2
                and a[5] <= 3
                and a[6] <= 1
                and a[7] <= 1
                and not any(a[8])
                and (not a[7] or a[4] == 1)
                and (a[5] != 1 or a[4] != 0)
                and (a[5] not in (2, 3) or (a[4] != 0 and a[3] > a[2]))
                and (a[5] != 3 or (a[4] == 1 and a[7] == 1))
                and (a[5] in (2, 3) or not a[3])
                and a[2] <= revision and a[3] <= revision,
                "invalid native application history",
            )
            _require(
                all(old.command_digest != a[1] for old in applications),
                "duplicate application command",
            )
            applications.append(Application(*a[:5], ApplicationState(a[5]), bool(a[6]), bool(a[7])))
        return cls(
            header.identity,
            sequence,
            revision,
            snapshot,
            tick,
            epoch,
            unknown,
            True,
            mode,
            bool(clear),
            tuple(effects),
            tuple(actions),
            tuple(applications),
            admission_revision,
            AdmissionBlock(admission_blocks),
            bool(stationary),
        )


def mapping_name(manifest):
    if not isinstance(manifest, Manifest):
        raise PublicationError("typed selector manifest required")
    return (
        f"Local\\WonderBane.ActorPublication.v3.{manifest.client_pid}."
        f"{manifest.client_creation}.{manifest.digest.hex()}"
    )


def _copy_mapping(name):
    api = Windows()
    mapping = api.checked(api.k.OpenFileMappingW(4, False, name), "OpenFileMappingW")
    view = 0
    try:
        view = api.checked(api.k.MapViewOfFile(mapping, 4, 0, 0, SIZE), "MapViewOfFile")
        for _ in range(3):
            before = c.string_at(view, HEADER_SIZE)
            header = Header.decode(before)
            _require(header.active >= 0, "native publication retired/unavailable")
            at = view + HEADER_SIZE + header.active * SLOT_SIZE
            first = c.string_at(at, SLOT_SIZE)
            second = c.string_at(at, SLOT_SIZE)
            after = c.string_at(view, HEADER_SIZE)
            if before == after and first == second:
                return header, first
        raise PublicationError("native publication changed during bounded read")
    finally:
        if view:
            api.k.UnmapViewOfFile(view)
        api.k.CloseHandle(mapping)


def _tick():
    api = c.WinDLL("kernel32", use_last_error=True)
    api.GetTickCount64.argtypes, api.GetTickCount64.restype = [], c.c_uint64
    return api.GetTickCount64()


class Reader:
    """One session/manifest; actor-lifetime substitution permanently revokes it."""

    def __init__(self, session, manifest, *, max_age_ms=500):
        _require(
            isinstance(manifest, Manifest) and type(max_age_ms) is int and 0 < max_age_ms <= 1000,
            "invalid publication reader contract",
        )
        self.session, self.manifest, self.max_age_ms = session, manifest, max_age_ms
        self.identity = self.last = None
        self.revoked = False

    def read(self):
        _require(not self.revoked, "publication actor lifetime was revoked")
        self.session.require_current()
        binding = self.session.binding
        _require(
            binding.process_id == self.manifest.client_pid
            and binding.process_creation_filetime_utc == self.manifest.client_creation
            and binding.executable_sha256
            in ("0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d",
                "78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903",
                "e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437",
                "1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c",
                "baa6c84e5f28aab01d516f12257354b42375d11e8e8e98930cfcf754aeec24e9"),
            "unqualified publication session",
        )
        header, payload = _copy_mapping(mapping_name(self.manifest))
        result = Publication.decode(header, payload, self.manifest)
        key = binding.object_key
        _require(
            result.identity.actor_key == (key.object_type, key.object_uuid),
            "publication actor key changed",
        )
        if self.identity is not None and result.identity != self.identity:
            self.revoked = True
            raise PublicationError("native actor lifetime changed")
        now = _tick()
        _require(
            result.sampled_tick <= now <= result.sampled_tick + self.max_age_ms,
            "native publication freshness unavailable",
        )
        self.session.require_current()
        if self.last is not None:
            _require(result.revision >= self.last.revision, "native publication revision regressed")
            _require(
                result.admission_revision >= self.last.admission_revision,
                "native admission revision regressed",
            )
            if result.revision == self.last.revision:
                _require(
                    result.snapshot_id == self.last.snapshot_id
                    and result.effect_epoch == self.last.effect_epoch
                    and result.unknown == self.last.unknown
                    and result.complete == self.last.complete
                    and result.actor_mode == self.last.actor_mode
                    and result.initiation_clear == self.last.initiation_clear
                    and result.stationary == self.last.stationary
                    and result.effects == self.last.effects
                    and result.action_facts() == self.last.action_facts()
                    and result.applications == self.last.applications
                    and result.admission_revision == self.last.admission_revision
                    and result.admission_blocks == self.last.admission_blocks,
                    "same native revision changed facts",
                )
            if result.admission_revision == self.last.admission_revision:
                _require(
                    result.eligibility_facts() == self.last.eligibility_facts(),
                    "same native admission revision changed eligibility",
                )
        self.identity, self.last = result.identity, result
        return result


def read(session, manifest):
    """One guarded read; coordinators should retain Reader across observations."""
    return Reader(session, manifest).read()
