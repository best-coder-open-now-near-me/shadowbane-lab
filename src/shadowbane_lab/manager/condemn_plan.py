"""Pinned map identities and nearby guard-building selections for Condemn jobs.

Names are display labels only. Guild and nation roles never substitute for one
another, and cached map membership never proves a complete guild directory.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict

from shadowbane_lab.client_extension.condemn_evidence import Lifetime, canonical, key
from shadowbane_lab.client_extension.condemn_progress import MAX_ATTEMPTS, CondemnProgressStore
from shadowbane_lab.client_extension.condemn_wire import Target
from shadowbane_lab.client_extension.vendor_navigation_wire import Snapshot
from shadowbane_lab.record_store import exclusive_record_lock, read_record_bytes

from .condemn_cycle import CondemnContext, CondemnCycleStopped
from .guard_owner import require_owner
from .guard_plan import operation_id
from .vendor_job import _write

LIMIT = 32 * 1024 * 1024


def _key(value, kind=None, empty=False):
    if not isinstance(value, dict) or set(value) != {"object_id", "object_type"}:
        raise ValueError("invalid observed identity")
    return key((value["object_id"], value["object_type"]), kind=kind, empty=empty)


def _label(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("invalid observed name")
    return value


def catalog_entries(registry):
    if (
        not isinstance(registry, dict)
        or set(registry)
        != {
            "cities",
            "cache_count",
            "cache_freshness_verified",
            "complete_guild_directory_verified",
            "command_admitted",
        }
        or any(
            registry[k] is not False
            for k in (
                "cache_freshness_verified",
                "complete_guild_directory_verified",
                "command_admitted",
            )
        )
        or type(registry["cache_count"]) is not int
        or not isinstance(registry["cities"], list)
        or not 0 <= registry["cache_count"] == len(registry["cities"]) <= 2048
    ):
        raise ValueError("invalid cached city catalog")
    entries, seen, missing = {}, set(), 0
    for city in registry["cities"]:
        city_key = _key(city["city_key"])
        if city_key in seen:
            raise ValueError("duplicate cached city")
        seen.add(city_key)
        city_name = _label(city["city_name"])
        for scope, name in ((4, "guild"), (5, "nation")):
            identity = _key(city[name]["key"], kind=23, empty=True)
            label = _label(city[name]["name"])
            if identity == (0, 0):
                missing += 1
                continue
            token = f"{scope}:{identity[0]}"
            entry = entries.setdefault(
                token, dict(token=token, scope=scope, identity=list(identity), names=[], cities=[])
            )
            if label and label not in entry["names"]:
                entry["names"].append(label)
            entry["cities"].append(dict(key=list(city_key), name=city_name))
    for entry in entries.values():
        entry["names"].sort()
        entry["cities"].sort(key=lambda c: c["key"])
    return dict(
        entries=sorted(entries.values(), key=lambda e: (e["scope"], e["identity"])),
        city_count=len(seen),
        missing_roles=missing,
        complete_guild_directory_verified=False,
        cache_freshness_verified=False,
        nation_inheritance_verified=False,
    )


def building_entries(nearby, identity, context):
    life = context.lifetime
    if (
        nearby.get("schema_version") != 1
        or nearby.get("state") != "complete"
        or nearby.get("identity") != list(identity)
        or (
            nearby.get("game_process_id"),
            nearby.get("game_creation_filetime"),
            nearby.get("scene"),
            nearby.get("root"),
        )
        != (life.process_id, life.creation, life.scene_epoch, context.root)
    ):
        raise ValueError("nearby buildings belong to another client or area")
    roster = nearby["roster"]
    if (
        roster.get("schema_version") != 1
        or roster.get("scope") != "active_city_command_cached_nearby_buildings"
        or (roster.get("process_id"), roster.get("process_creation_filetime_utc"))
        != (life.process_id, life.creation)
        or any(
            roster.get(k) is not False
            for k in (
                "town_membership_verified",
                "roster_complete",
                "server_response_verified",
                "management_permission_verified",
                "command_admitted",
            )
        )
    ):
        raise ValueError("invalid nearby building provenance")
    buildings = roster["buildings"]
    if (
        type(nearby.get("buildings")) is not int
        or nearby["buildings"] != len(buildings)
        or type(nearby.get("hirelings")) is not int
        or nearby["hirelings"] != sum(len(b["hirelings"]) for b in buildings)
    ):
        raise ValueError("nearby discovery totals changed")
    if not isinstance(buildings, list) or not 0 < len(buildings) <= 512:
        raise ValueError("nearby building count exceeds its bound")
    seen, hirelings, result = set(), set(), []
    for row in buildings:
        building = _key(row["building"], kind=8)
        if building in seen:
            raise ValueError("duplicate nearby building")
        seen.add(building)
        label = _label(row["display_name"])
        if not isinstance(row["hirelings"], list) or len(row["hirelings"]) > 256:
            raise ValueError("invalid nearby hirelings")
        guards = []
        for h in row["hirelings"]:
            k = _key(h["hireling"])
            if k in hirelings:
                raise ValueError("duplicate nearby hireling")
            hirelings.add(k)
            if k[1] == 37:
                guards.append(k)
        if guards:
            result.append(dict(building=list(building), name=label, guards=len(guards)))
    if len(hirelings) > 4096:
        raise ValueError("nearby hireling count exceeds its bound")
    return sorted(result, key=lambda b: b["building"])


def verified_building_entries(rosters, nearby, identity, context):
    """Use response-verified rosters, never treat an empty nearby cache as empty guards."""
    # Retain and validate the original cache separately.
    building_entries(nearby, identity, context)
    life = context.lifetime
    candidates = {_key(r["building"], 8): r for r in nearby["roster"]["buildings"]}
    if (
        rosters.get("schema_version") != 1 or rosters.get("roster_only") is not True
        or rosters.get("state") not in ("complete", "partial")
        or rosters.get("identity") != list(identity)
        or rosters.get("operation_id") != nearby["operation_id"]
        or (rosters.get("game_process_id"), rosters.get("game_creation_filetime"),
            rosters.get("scene"), rosters.get("root"))
        != (life.process_id, life.creation, life.scene_epoch, context.root)
        or rosters.get("roster_complete") is not False
        or rosters.get("town_membership_verified") is not False
        or rosters.get("guards") != 0
        or rosters.get("buildings") != len(candidates)
        or not isinstance(rosters.get("roster"), list)
        or len(rosters["roster"]) != len(candidates)
        or not isinstance(rosters.get("attempts"), list)
        or len(rosters["attempts"]) != len(candidates)
    ):
        raise ValueError("invalid verified building discovery provenance")
    attempts, requests = {}, set()
    for attempt in rosters["attempts"]:
        building = key((attempt["building_id"], 8), kind=8)
        if (building not in candidates or building in attempts or attempt["guard_id"] != 0
                or attempt["state"] not in ("observed", "not_submitted")
                or attempt["request_key"] in requests):
            raise ValueError("invalid building discovery attempt")
        if str(uuid.UUID(attempt["request_key"])) != attempt["request_key"]:
            raise ValueError("invalid building discovery request")
        expected = Snapshot.decode(bytes.fromhex(attempt["expected"]))
        if (expected.scene, expected.root) != (life.scene_epoch, context.root):
            raise ValueError("building discovery attempt changed area")
        requests.add(attempt["request_key"])
        attempts[building] = attempt
    seen, hirelings, result, verified, guard_total = set(), set(), [], 0, 0
    for row in rosters["roster"]:
        building = _key(row["building"], 8)
        if building not in candidates or building in seen:
            raise ValueError("unexpected verified building identity")
        seen.add(building)
        if row["display_name"] != candidates[building]["display_name"]:
            raise ValueError("verified building label changed")
        if row["state"] == "unavailable":
            if row["guards"] or "roster" in row or "snapshot" in row:
                raise ValueError("unavailable building contains verified rows")
            continue
        if row["state"] != "verified" or attempts[building]["state"] != "observed":
            raise ValueError("building roster lacks a completed response")
        snapshot = Snapshot.decode(bytes.fromhex(row["snapshot"]))
        raw = row["roster"]
        if (
            not snapshot.opened(building[0])
            or (snapshot.scene, snapshot.root) != (life.scene_epoch, context.root)
            or snapshot.manager != Snapshot.decode(
                bytes.fromhex(attempts[building]["expected"])
            ).manager
            or raw.get("building_roster_verified") is not True
            or _key(raw["building"], 8) != building
            or (raw.get("process_id"), raw.get("process_creation_filetime_utc"))
            != (life.process_id, life.creation)
            or raw.get("hireling_slots") != snapshot.capacity
            or not isinstance(raw.get("hirelings"), list)
            or len(raw["hirelings"]) != snapshot.occupied
        ):
            raise ValueError("verified building roster changed")
        guards = []
        for h in raw["hirelings"]:
            identity_key = _key(h["hireling"])
            if identity_key in hirelings:
                raise ValueError("duplicate verified hireling")
            hirelings.add(identity_key)
            if identity_key[1] == 37:
                guards.append(h)
        expected_guards = [dict(g, window_verified=False, state="roster_verified") for g in guards]
        if row["guards"] != expected_guards:
            raise ValueError("verified guard roster changed")
        verified += 1
        guard_total += len(guards)
        if guards:
            result.append(dict(building=list(building), name=_label(row["display_name"]),
                               guards=len(guards)))
    complete = verified == len(candidates)
    if (len(hirelings) > 4096
            or rosters.get("buildings_verified") != verified
            or rosters.get("guards_observed") != guard_total
            or rosters.get("candidate_buildings_verified") is not complete
            or rosters["state"] != ("complete" if complete else "partial")):
        raise ValueError("verified building discovery totals changed")
    return sorted(result, key=lambda b: b["building"])


def _coverage(record):
    """Describe every candidate from an already validated, immutable preparation.

    Unavailable windows do not distinguish range from unsupported services. Old
    cache-only plans cannot establish either an empty roster or accessible guards.
    This projection never changes selection, claims town membership, or scans jobs.
    """
    rosters = {
        row["building"]["object_id"]: row
        for row in record.get("verified_rosters", {}).get("roster", [])
    }
    rows = []
    for candidate in record["nearby"]["roster"]["buildings"]:
        building = candidate["building"]
        observed = rosters.get(building["object_id"])
        guards = None
        if observed is None:
            state, detail = "unverified", "Cached candidate; building roster not verified."
        elif observed["state"] == "unavailable":
            state = "unavailable"
            detail = observed.get("detail", "Building roster unavailable; guard count unknown.")
            if not isinstance(detail, str):
                raise ValueError("invalid building coverage detail")
            detail = detail[:4096]
        else:
            guards = len(observed["guards"])
            state = "verified_guards" if guards else "verified_no_guards"
            detail = "Owned roster verified." if guards else "Owned roster verified without guards."
        rows.append(dict(building=[building["object_id"], building["object_type"]],
                         name=candidate["display_name"], state=state, guards=guards, detail=detail))
    return dict(
        candidate_buildings=len(rows),
        verified_guard_buildings=sum(r["state"] == "verified_guards" for r in rows),
        verified_no_guard_buildings=sum(r["state"] == "verified_no_guards" for r in rows),
        unavailable_buildings=sum(r["state"] == "unavailable" for r in rows),
        unverified_buildings=sum(r["state"] == "unverified" for r in rows),
        town_coverage_verified=False,
        buildings=sorted(rows, key=lambda row: row["building"]),
    )


class CondemnPlanStore:
    def __init__(self, store):
        self.store, self.root = store, store.root / "condemn-plans"

    def path(self, preparation):
        return self.root / (operation_id(preparation) + ".json")

    def prepare(self, preparation, context, owner, nearby, registry, *, rosters=None):
        if type(context) is not CondemnContext:
            raise ValueError("an exact Condemn context is required")
        require_owner(owner, owner)
        record = dict(
            schema_version=1 if rosters is None else 2,
            preparation_id=operation_id(preparation),
            identity=list(self.store.identity),
            context=asdict(context),
            owner=owner,
            nearby=nearby,
            registry=registry,
        )
        if rosters is not None:
            record["verified_rosters"] = rosters
        # Validate the entire source before publishing it. Never turn malformed
        # entries into an apparently smaller successful selection.
        self._validate(record)
        if len((json.dumps(record, sort_keys=True, indent=2) + "\n").encode()) > LIMIT:
            raise ValueError("crest preparation exceeds its storage bound")
        with exclusive_record_lock(self.root / "plans.lock"):
            if self.path(preparation).exists():
                raise CondemnCycleStopped("This crest preparation already exists.")
            _write(self.path(preparation), record)
            _write(self.root / "current.json", {"preparation_id": preparation})
        return self.summary(preparation)

    def _validate(self, record):
        if (
            set(record)
            != {
                "schema_version",
                "preparation_id",
                "identity",
                "context",
                "owner",
                "nearby",
                "registry",
            } | ({"verified_rosters"} if record.get("schema_version") == 2 else set())
            or type(record["schema_version"]) is not int
            or record["schema_version"] not in (1, 2)
            or record["identity"] != list(self.store.identity)
        ):
            raise ValueError("invalid crest preparation")
        operation_id(record["preparation_id"])
        if record["nearby"].get("operation_id") != record["preparation_id"]:
            raise ValueError("crest preparation has another discovery source")
        context = CondemnContext(
            Lifetime(**record["context"]["lifetime"]), record["context"]["root"]
        )
        require_owner(record["owner"], record["owner"])
        catalog = catalog_entries(record["registry"])
        buildings = (
            verified_building_entries(record["verified_rosters"], record["nearby"],
                                      self.store.identity, context)
            if record["schema_version"] == 2
            else building_entries(record["nearby"], self.store.identity, context)
        )
        return context, catalog, buildings

    def read(self, preparation):
        record = json.loads(read_record_bytes(self.path(preparation), LIMIT))
        if record["preparation_id"] != preparation:
            raise ValueError("crest preparation identity changed")
        self._validate(record)
        return record

    def current(self):
        path = self.root / "current.json"
        if not path.exists():
            return None
        record = json.loads(read_record_bytes(path, 256))
        if set(record) != {"preparation_id"}:
            raise ValueError("invalid crest preparation pointer")
        return self.summary(record["preparation_id"])

    def summary(self, preparation):
        record = self.read(preparation)
        _, catalog, buildings = self._validate(record)
        return dict(
            preparation_id=preparation,
            sha256=hashlib.sha256(canonical(record)).hexdigest(),
            catalog=catalog,
            buildings=buildings,
            coverage=_coverage(record),
            town_coverage_verified=False,
            management_permission_verified=False,
        )

    def select(self, preparation, digest, crest_tokens, building_ids):
        record = self.read(preparation)
        if hashlib.sha256(canonical(record)).hexdigest() != digest:
            raise CondemnCycleStopped("The prepared crest selection changed; refresh it.")
        context, catalog, buildings = self._validate(record)
        crests = {e["token"]: e for e in catalog["entries"]}
        available = {b["building"][0]: b for b in buildings}
        if (
            not isinstance(crest_tokens, (tuple, list))
            or not 0 < len(crest_tokens) <= 512
            or any(not isinstance(t, str) or t not in crests for t in crest_tokens)
            or len(set(crest_tokens)) != len(crest_tokens)
            or not isinstance(building_ids, (tuple, list))
            or not 0 < len(building_ids) <= 512
            or any(type(b) is not int or b not in available for b in building_ids)
            or len(set(building_ids)) != len(building_ids)
        ):
            raise ValueError("select distinct observed crests and guard buildings")
        count = len(crest_tokens) * len(building_ids)
        progress = CondemnProgressStore(self.store.root).read()
        if progress["active"] is not None:
            raise CondemnCycleStopped("An earlier Condemn request needs review.")
        remaining = MAX_ATTEMPTS - len(progress["attempts"])
        if count > remaining:
            raise CondemnCycleStopped(
                f"This selection needs {count} checks; saved history has room for {remaining}."
            )
        ordered = tuple(
            Target(
                tuple(available[b]["building"]), tuple(crests[t]["identity"]), crests[t]["scope"]
            )
            for b in sorted(building_ids)
            for t in sorted(crest_tokens, key=lambda t: (crests[t]["scope"], crests[t]["identity"]))
        )
        return dict(
            preparation_id=preparation,
            preparation_sha256=digest,
            context=asdict(context),
            owner=record["owner"],
            targets=[t.encode().hex() for t in ordered],
            town_coverage_verified=False,
            complete_guild_directory_verified=False,
            nation_inheritance_verified=False,
        )
