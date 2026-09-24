"""Worker-owned nearby discovery, with durable receipts separate from crafting jobs."""
from __future__ import annotations

import json
import time
import uuid

from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.city_window_session import NativeCityWindowSession
from shadowbane_lab.client_extension.city_window_wire import READY, Outcome
from shadowbane_lab.client_extension.condemn_progress import CondemnProgressStore
from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_completion import _read_record
from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory
from shadowbane_lab.client_observation.native_nearby_vendor_roster import (
    read_native_nearby_vendor_roster,
)
from shadowbane_lab.client_observation.reviewed_vendor_builds import REVIEWED_VENDOR_EXECUTABLES
from shadowbane_lab.record_store import exclusive_record_lock

from .vendor_job import _write


def _memory(binding):
    memory = WindowsReadOnlyProcessMemory.open_for_process("sb.exe", binding.game_process_id)
    if (
        memory.process_creation_filetime_utc != binding.game_process_started_at_100ns
        or memory.executable_sha256
        not in REVIEWED_VENDOR_EXECUTABLES
    ):
        memory.close()
        raise VendorBatchStopped("the discovery client identity or build changed")
    return memory


def open_city_session(binding):
    _memory(binding).close()
    return NativeCityWindowSession(
        NativeClientProcessIdentity(binding.game_process_id, binding.game_process_started_at_100ns),
        binding.game_window_handle,
    )


def read_roster(binding):
    memory = _memory(binding)
    try:
        return read_native_nearby_vendor_roster(memory)
    finally:
        memory.close()


def discovery_summary(store):
    path = store.root / "nearby-summary.json"
    if not path.exists():
        return None
    data = json.loads(_read_record(path, 4096))
    if data.get("schema_version") != 1 or data.get("identity") != list(store.identity):
        raise VendorBatchStopped("nearby discovery identity mismatch")
    return data


def run_discovery(store, binding, operation, session, *, cancelled,
                  reader=read_roster, clock=time.monotonic, sleep=time.sleep):
    return _run_discovery(
        store, binding, operation, session, cancelled=cancelled, reader=reader,
        clock=clock, sleep=sleep, guard=False,
    )


def _run_discovery(
    store, binding, operation, session, *, cancelled, reader, clock, sleep, guard,
):
    population = "hirelings" if guard else "vendors"
    directory = "guard-discovery" if guard else "discovery"
    summary = "guard-nearby-summary.json" if guard else "nearby-summary.json"
    path = store.root / directory / (operation.operation_id + ".json")
    with exclusive_record_lock(store.root / "execution.lock", timeout_seconds=0.1):
        CondemnProgressStore(store.root).assert_idle()
        if path.exists():
            raise VendorBatchStopped("this discovery was already attempted; its record is retained")
        record = {
            "schema_version": 1, "identity": list(store.identity),
            "operation_id": operation.operation_id,
            "game_process_id": binding.game_process_id,
            "game_creation_filetime": binding.game_process_started_at_100ns,
            "request_key": str(uuid.uuid4()), "state": "waiting",
            "detail": "Return to the game when ready; nearby discovery will continue.",
            "buildings": 0, population: 0, "roster_complete": False,
        }

        def save(state, detail):
            record.update(state=state, detail=detail)
            _write(path, record)
            _write(store.root / summary,
                   {k: v for k, v in record.items() if k not in {"roster", "open_receipt"}})

        def check():
            if cancelled():
                raise VendorBatchStopped("Nearby discovery cancelled.")
            session.renew_lease()

        save("waiting", record["detail"])
        try:
            deadline = clock() + 60
            while True:
                check()
                before = session.inspect()
                if before.outcome == Outcome.OBSERVED and before.flags & READY:
                    break
                if clock() >= deadline:
                    raise VendorBatchStopped("The game did not become ready for nearby discovery.")
                sleep(0.1)
            record.update(
                scene=before.snapshot.scene, root=before.snapshot.root,
                expected=before.snapshot.encode().hex(),
            )
            save("opening", "Opening the nearby-building window.")
            check()
            opened = session.open(before.snapshot, record["request_key"])
            record["open_receipt"] = {
                "request_key": opened.request_key, "outcome": opened.outcome.name,
            }
            if opened.outcome not in (Outcome.OBSERVED, Outcome.SUBMITTED):
                raise VendorBatchStopped(
                    "City Command opening was not confirmed; no retry was sent."
                )
            save("loading", "Reading nearby buildings and hirelings.")
            deadline = clock() + 15
            while True:
                check()
                observed = session.inspect()
                state = observed.snapshot
                if (
                    state.empty or state.scene != before.snapshot.scene
                    or state.root != before.snapshot.root
                    or state.manager != before.snapshot.manager
                ):
                    raise VendorBatchStopped("The discovery client or scene changed.")
                if observed.outcome == Outcome.OBSERVED and state.opened and not state.loading:
                    roster = reader(binding)
                    after = session.inspect()
                    if (
                        after.outcome != Outcome.OBSERVED or after.snapshot != state
                        or roster["process_id"] != binding.game_process_id
                        or roster["process_creation_filetime_utc"]
                        != binding.game_process_started_at_100ns
                        or len(roster["buildings"]) != state.building_count
                    ):
                        raise VendorBatchStopped("The nearby roster changed during verification.")
                    check()
                    record["roster"] = roster
                    record["buildings"] = len(roster["buildings"])
                    record[population] = sum(len(b[population]) for b in roster["buildings"])
                    save("complete", f"Found {record['buildings']} nearby buildings and "
                         f"{record[population]} hirelings. Full town coverage is unverified.")
                    return record
                if clock() >= deadline:
                    raise VendorBatchStopped("The nearby-building response was not confirmed.")
                sleep(0.1)
        except (OSError, RuntimeError, ValueError) as exc:
            save("cancelled" if cancelled() else "review", str(exc))
            raise
