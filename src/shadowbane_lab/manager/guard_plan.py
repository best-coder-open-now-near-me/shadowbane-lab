"""Admit exact guard targets from retained discovery and a warehouse observation."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from shadowbane_lab.client_extension.vendor_navigation_wire import Snapshot
from shadowbane_lab.record_store import read_record_bytes

from .guard_funding_cycle import GuardFundingCycleStopped, GuardFundingTarget


def operation_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"operation-[0-9a-f]{32}", value):
        raise ValueError("a canonical guard operation is required")
    return value


@dataclass(frozen=True, slots=True)
class GuardUpgradePlan:
    discovery_operation_id: str
    discovery_sha256: str
    navigation_sha256: str
    warehouse_snapshot: str
    targets: tuple[GuardFundingTarget, ...]
    initial_ranks: tuple[int, ...]
    candidate_buildings: int
    verified_buildings: int


def build_guard_upgrade_plan(store, binding, discovery_id, warehouse: Snapshot):
    """Use discovered keys, never names or a caller-authored target list.

    The worker captures the warehouse snapshot through its exact native session.
    This plan pins that source and the retained discovery files to one process and
    scene. Every cycle still requires fresh native admission before each action.
    Loaded candidate coverage does not establish city membership or a town census.
    """
    operation_id(discovery_id)
    warehouse.encode()
    if not warehouse.warehouse_opened(warehouse.building_id, warehouse.warehouse_id):
        raise GuardFundingCycleStopped("An exact open warehouse is required for guard funding.")
    raw = [read_record_bytes(store.root / folder / (discovery_id + ".json"), 64 * 1024 * 1024)
           for folder in ("guard-discovery", "guard-navigation")]
    nearby, discovery = map(json.loads, raw)
    for record in (nearby, discovery):
        if (record.get("schema_version") != 1
                or record.get("operation_id") != discovery_id
                or record.get("identity") != list(store.identity)
                or record.get("game_process_id") != binding.game_process_id
                or record.get("game_creation_filetime") != binding.game_process_started_at_100ns):
            raise GuardFundingCycleStopped("Guard discovery belongs to another client lifetime.")
    if (nearby.get("state") != "complete" or discovery.get("state") not in {"complete", "partial"}
            or (nearby.get("scene"), nearby.get("root")) != (warehouse.scene, warehouse.root)):
        raise GuardFundingCycleStopped("Guard discovery is incomplete or belongs to another scene.")
    attempts = discovery.get("attempts", [])
    if not attempts or any(
        (Snapshot.decode(bytes.fromhex(a["expected"])).scene,
         Snapshot.decode(bytes.fromhex(a["expected"])).root) != (warehouse.scene, warehouse.root)
        for a in attempts
    ):
        raise GuardFundingCycleStopped("Guard navigation lacks matching scene provenance.")
    candidates = [b["building"] for b in nearby["roster"]["buildings"]]
    buildings = discovery["roster"]
    if (not 0 < len(candidates) <= 512 or len(buildings) != len(candidates)
            or [b["building"] for b in buildings] != candidates
            or any(type(k.get("object_id")) is not int or not 0 < k["object_id"] < 2**32
                   or k.get("object_type") != 8 for k in candidates)
            or len({k["object_id"] for k in candidates}) != len(candidates)):
        raise GuardFundingCycleStopped("Guard discovery candidate membership changed.")
    targets, ranks, seen, verified = [], [], set(), 0
    for building in buildings:
        if building["state"] == "unavailable":
            continue
        if building["state"] not in {"verified", "partial"}:
            raise GuardFundingCycleStopped("A guard building has unfinished discovery.")
        roster = building["roster"]
        rows = roster["hirelings"]
        if (roster.get("building_roster_verified") is not True
                or roster.get("building") != building["building"]
                or roster.get("process_id") != binding.game_process_id
                or roster.get("process_creation_filetime_utc")
                != binding.game_process_started_at_100ns
                or not 0 <= len(rows) <= roster["hireling_slots"] <= 128):
            raise GuardFundingCycleStopped("A guard building lacks a complete owned roster.")
        keys = {(r["hireling"]["object_id"], r["hireling"]["object_type"]) for r in rows}
        expected_guards = {key for key in keys if key[1] == 37}
        guards = building["guards"]
        if (len(keys) != len(rows) or len(guards) != len(expected_guards)
                or {(g["hireling"]["object_id"], g["hireling"]["object_type"])
                    for g in guards} != expected_guards):
            raise GuardFundingCycleStopped("The discovered guard list differs from its roster.")
        verified += 1
        for guard in guards:
            if guard.get("window_verified") is not True:
                continue
            detail, key = guard["observation"], guard["hireling"]
            matching = [r for r in detail["hirelings"] if r["hireling"] == key]
            if (guard.get("state") != "verified" or key["object_id"] in seen
                    or detail.get("process_id") != binding.game_process_id
                    or detail.get("process_creation_filetime_utc")
                    != binding.game_process_started_at_100ns
                    or detail.get("building_roster_verified") is not True
                    or detail.get("building") != building["building"]
                    or detail.get("selected_guard") != key or len(matching) != 1
                    or {(r["hireling"]["object_id"], r["hireling"]["object_type"])
                        for r in detail["hirelings"]} != keys):
                raise GuardFundingCycleStopped("A guard window no longer matches its owned roster.")
            rank = matching[0]["rank"]
            if type(rank) is not int or not 0 < rank < 2**32 - 1:
                raise GuardFundingCycleStopped("A guard lacks a valid observed rank.")
            targets.append(GuardFundingTarget(
                binding.game_process_id, binding.game_process_started_at_100ns,
                warehouse.scene, warehouse.root, warehouse.building_id, warehouse.warehouse_id,
                building["building"]["object_id"], key["object_id"],
            ))
            ranks.append(rank)
            seen.add(key["object_id"])
    if not targets or discovery.get("guards") != len(targets):
        raise GuardFundingCycleStopped("No complete matching guard selection is available.")
    return GuardUpgradePlan(
        discovery_id, *(hashlib.sha256(data).hexdigest() for data in raw),
        warehouse.encode().hex(), tuple(targets), tuple(ranks), len(candidates), verified,
    )
