"""Sequential building/hireling discovery with a durable intent before each native open."""

from __future__ import annotations

import time
import uuid

from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_navigation_session import NativeVendorNavigationSession
from shadowbane_lab.client_extension.vendor_navigation_wire import (
    IN_FLIGHT,
    READY,
    RESPONSE_WAIT_SECONDS,
    UNRESOLVED,
    Outcome,
)
from shadowbane_lab.client_observation.native_building_hirelings import BuildingHirelingsUnavailable
from shadowbane_lab.client_observation.native_vendor_roster import read_native_vendor_roster
from shadowbane_lab.record_store import exclusive_record_lock

from .vendor_discovery import _memory
from .vendor_job import _write


def open_navigation_session(binding, *, journal=None):
    _memory(binding).close()
    return NativeVendorNavigationSession(
        NativeClientProcessIdentity(binding.game_process_id, binding.game_process_started_at_100ns),
        binding.game_window_handle, journal=journal,
    )


def read_roster(binding, *, window):
    memory = _memory(binding)
    try:
        return read_native_vendor_roster(memory, window=window)
    finally:
        memory.close()


class _NotSubmitted(VendorBatchStopped):
    """The native receipt proves this attempt never entered its window action."""


def run_building_discovery(
    store,
    binding,
    operation,
    session,
    nearby,
    *,
    cancelled,
    reader=read_roster,
    clock=time.monotonic,
    sleep=time.sleep,
):
    return _run_building_discovery(
        store, binding, operation, session, nearby, cancelled=cancelled,
        reader=reader, clock=clock, sleep=sleep, guard=False,
    )


def _run_building_discovery(
    store, binding, operation, session, nearby, *, cancelled, reader, clock, sleep, guard,
):
    noun = "guard" if guard else "vendor"
    plural = noun + "s"
    row_key = "hireling" if guard else "vendor"
    rows_key = "hirelings" if guard else "vendors"
    hireling_type = 37 if guard else 42
    directory = "guard-navigation" if guard else "navigation"
    summary = "guard-nearby-summary.json" if guard else "nearby-summary.json"
    path = store.root / directory / (operation.operation_id + ".json")
    with exclusive_record_lock(store.root / "execution.lock", timeout_seconds=0.1):
        if path.exists():
            raise VendorBatchStopped(
                "this navigation was already attempted; no request was replayed"
            )
        if (
            nearby.get("state") != "complete"
            or nearby.get("identity") != list(store.identity)
            or nearby.get("game_process_id") != binding.game_process_id
            or nearby.get("game_creation_filetime") != binding.game_process_started_at_100ns
        ):
            raise VendorBatchStopped("the nearby building discovery belongs to another client")
        if guard and any(
            type(nearby.get(key)) is not int or nearby[key] <= 0 for key in ("scene", "root")
        ):
            raise VendorBatchStopped("The nearby guard candidates lack scene provenance.")
        candidates = nearby["roster"]["buildings"]
        ids = [row["building"]["object_id"] for row in candidates]
        if (
            not 0 < len(ids) <= 512
            or len(ids) != len(set(ids))
            or any(type(value) is not int or not 0 < value < 2**32 for value in ids)
            or any(row["building"]["object_type"] != 8 for row in candidates)
        ):
            raise VendorBatchStopped("invalid nearby building identities")
        record = {
            "schema_version": 1,
            "identity": list(store.identity),
            "operation_id": operation.operation_id,
            "state": "waiting",
            "detail": "Return to the game when ready; building discovery will continue.",
            "buildings": len(ids),
            plural: 0,
            "buildings_verified": 0,
            "roster_complete": False,
            "town_membership_verified": False,
            "game_process_id": binding.game_process_id,
            "game_creation_filetime": binding.game_process_started_at_100ns,
            "attempts": [],
            "roster": [],
        }
        baseline = None
        seen_guards = set()

        def save(state=None, detail=None):
            if state is not None:
                record["state"] = state
            if detail is not None:
                record["detail"] = detail
            _write(path, record)
            _write(
                store.root / summary,
                {key: value for key, value in record.items() if key not in {"attempts", "roster"}},
            )

        def check():
            if cancelled():
                raise VendorBatchStopped("Building discovery cancelled.")
            session.renew_lease()

        def observe():
            nonlocal baseline
            check()
            receipt = session.inspect()
            state = receipt.snapshot
            if receipt.outcome != Outcome.OBSERVED:
                raise VendorBatchStopped("The native window observation was rejected.")
            if receipt.flags & UNRESOLVED:
                raise VendorBatchStopped(
                    "A previous window request needs review; no retry was sent."
                )
            if not state.empty:
                if guard and (state.scene, state.root) != (nearby["scene"], nearby["root"]):
                    raise VendorBatchStopped("The guard candidates belong to a different scene.")
                identity = state.scene, state.root, state.manager
                if baseline is not None and identity != baseline:
                    raise VendorBatchStopped("The building discovery scene or owner changed.")
                baseline = identity
            return receipt

        def navigate(building_id, vendor_id=0):
            deadline = clock() + 60
            while True:
                before = observe()
                if before.flags & READY:
                    break
                if clock() >= deadline:
                    raise VendorBatchStopped(
                        "The game did not become ready for building discovery."
                    )
                sleep(0.1)
            if vendor_id and not before.snapshot.opened(building_id):
                navigate(building_id)
                before = observe()
                if not before.flags & READY:
                    raise VendorBatchStopped(f"The building changed before {noun} selection.")
            attempt = {
                "request_key": str(uuid.uuid4()),
                "building_id": building_id,
                noun + "_id": vendor_id,
                "state": "prepared",
                "expected": before.snapshot.encode().hex(),
            }
            record["attempts"].append(attempt)
            save(
                "opening",
                f"Opening the next {noun}." if vendor_id else "Opening the next building."
            )
            check()  # Intent is durable before publication; cancellation still sends nothing.
            open_hireling = session.open_guard if guard else session.open_vendor
            opened = (
                open_hireling(before.snapshot, building_id, vendor_id, attempt["request_key"])
                if vendor_id
                else session.open_building(before.snapshot, building_id, attempt["request_key"])
            )
            attempt.update(state="submitted", outcome=opened.outcome.name)
            save()
            if guard and opened.flags & UNRESOLVED:
                raise VendorBatchStopped(
                    "The guard window request needs review; no retry was sent."
                )
            if opened.outcome in (Outcome.UNAVAILABLE, Outcome.STALE):
                if guard and opened.flags & IN_FLIGHT:
                    raise VendorBatchStopped("The guard window has an unconfirmed active request.")
                attempt["state"] = "not_submitted"
                save()
                if opened.outcome == Outcome.STALE:
                    raise VendorBatchStopped(
                        "The game state changed before window opening; discovery stopped."
                    )
                raise _NotSubmitted(
                    "The requested window was unavailable; no action was submitted."
                )
            if opened.outcome not in (Outcome.OBSERVED, Outcome.SUBMITTED):
                raise VendorBatchStopped("Window opening was not confirmed; no retry was sent.")
            if opened.transition_request != attempt["request_key"]:
                raise VendorBatchStopped(
                    "The window request receipt did not match its durable intent."
                )
            deadline = clock() + RESPONSE_WAIT_SECONDS
            while True:
                observed = observe()
                if observed.transition_request != attempt["request_key"]:
                    raise VendorBatchStopped(
                        "Another request replaced the active window transition."
                    )
                if not observed.flags & IN_FLIGHT and observed.snapshot.opened(
                    building_id, vendor_id, hireling_type=hireling_type
                ):
                    attempt["state"] = "observed"
                    save("reading", f"Verifying the requested building and {noun} identities.")
                    return observed.snapshot
                if clock() >= deadline:
                    raise VendorBatchStopped("The requested window response was not confirmed.")
                sleep(0.1)

        def verify_roster(state, building_id, *, window, vendor_id=0):
            check()
            unavailable = None
            try:
                roster = reader(binding, window=window)
            except BuildingHirelingsUnavailable as exc:
                if not guard or window != "building":
                    raise
                unavailable, roster = exc, exc.observation
            after = observe()
            if (
                after.snapshot != state
                or after.flags & IN_FLIGHT
                or roster["process_id"] != binding.game_process_id
                or roster["process_creation_filetime_utc"] != binding.game_process_started_at_100ns
                or roster["building"] != {"object_id": building_id, "object_type": 8}
                or vendor_id
                and not any(
                    row[row_key] == {"object_id": vendor_id, "object_type": hireling_type}
                    for row in roster[rows_key]
                )
            ):
                raise VendorBatchStopped("The roster changed while its window was being verified.")
            if unavailable is not None:
                if (state.capacity or state.occupied or roster["hireling_slots"]
                        or roster["hirelings"]
                        or roster.get("building_roster_verified") is not False):
                    raise VendorBatchStopped("The unavailable building roster changed.")
                raise unavailable
            if guard:
                if (
                    roster.get("building_roster_verified") is not True
                    or roster["hireling_slots"] != state.capacity
                    or len(roster["hirelings"]) != state.occupied
                    or vendor_id and roster.get("selected_guard") != {
                        "object_id": vendor_id, "object_type": 37,
                    }
                ):
                    raise VendorBatchStopped("The guard roster counts or selected guard changed.")
            return roster

        save()
        try:
            for candidate in candidates:
                check()
                building_id = candidate["building"]["object_id"]
                result = {
                    "building": candidate["building"],
                    "display_name": candidate["display_name"],
                    "state": "opening",
                    plural: [],
                }
                record["roster"].append(result)
                try:
                    state = navigate(building_id)
                except _NotSubmitted as exc:
                    result.update(state="unavailable", detail=str(exc))
                    save()
                    continue
                if not guard and state.occupied == 0:
                    # An empty menu is not proof that this building has no other hirelings.
                    result.update(
                        state="no_visible_hirelings", detail="No populated hireling rows."
                    )
                    save()
                    continue
                try:
                    roster = verify_roster(state, building_id, window="building")
                except BuildingHirelingsUnavailable as exc:
                    if not guard:
                        raise
                    result.update(state="unavailable", detail=str(exc))
                    save()
                    continue
                result.update(state="roster_verified", roster=roster)
                record["buildings_verified"] += 1
                for vendor in roster[rows_key]:
                    if guard and vendor["hireling"]["object_type"] != 37:
                        continue
                    vendor_id = vendor[row_key]["object_id"]
                    if guard:
                        if vendor_id in seen_guards:
                            raise VendorBatchStopped("A guard appeared in more than one building.")
                        seen_guards.add(vendor_id)
                    row = dict(vendor, window_verified=False)
                    result[plural].append(row)
                    try:
                        state = navigate(building_id, vendor_id)
                    except _NotSubmitted as exc:
                        row.update(state="unavailable", detail=str(exc))
                        save()
                        continue
                    detail = verify_roster(
                        state, building_id, window=noun, vendor_id=vendor_id,
                    )
                    if guard:
                        def keys(observation):
                            return {
                                (r["hireling"]["object_id"], r["hireling"]["object_type"])
                                for r in observation["hirelings"]
                            }
                        if keys(detail) != keys(roster):
                            raise VendorBatchStopped("The building hireling membership changed.")
                        row["observation"] = detail
                    row.update(state="verified", window_verified=True)
                    record[plural] += 1
                    save()
                result["state"] = (
                    "verified"
                    if all(row["window_verified"] for row in result[plural])
                    else "partial"
                )
                save()
            if not record[plural] and not (guard and record["buildings_verified"]):
                raise VendorBatchStopped(
                    f"No {noun} windows were verified; "
                    "review building access and discovery readiness."
                )
            if guard:
                record["candidate_buildings_verified"] = all(
                    row["state"] == "verified" for row in record["roster"]
                )
            save(
                "partial" if guard and not record["candidate_buildings_verified"] else "complete",
                f"Verified {record[plural]} {noun} windows across "
                f"{record['buildings_verified']} buildings. Full town coverage is unverified.",
            )
            return record
        except (OSError, RuntimeError, ValueError) as exc:
            save("cancelled" if cancelled() else "review", str(exc))
            raise
