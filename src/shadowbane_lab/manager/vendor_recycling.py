"""Durable post-production exclusions for one newly admitted vendor batch."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped, _owner
from shadowbane_lab.client_extension.vendor_completion import _read_record
from shadowbane_lab.client_extension.vendor_production_responses import VendorProductionReader
from shadowbane_lab.client_extension.vendor_recycle_evidence import RecycleEvidence
from shadowbane_lab.client_extension.vendor_recycle_manifest import plan_exclusions
from shadowbane_lab.client_extension.vendor_wire import (
    IN_FLIGHT,
    READY,
    UNRESOLVED,
    NativeRecycleBatch,
    Outcome,
    Snapshot,
)
from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory
from shadowbane_lab.client_observation.native_vendor_affixes import read_native_vendor_affixes
from shadowbane_lab.client_observation.native_vendor_queue import (
    NativeVendorObservationChanged,
    read_native_vendor_inventory,
)
from shadowbane_lab.record_store import publish_atomic_record

POLICY = "confirmed_tier_1_2_exclude_unknown_keep_v1"
LIMIT = 16 * 1024 * 1024


class _RecyclingStopped(VendorBatchStopped):
    pass


def _write(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    if len(raw) > LIMIT:
        raise VendorBatchStopped("recycling journal exceeds its evidence bound")
    publish_atomic_record(path, raw, temporary_label="vendor-recycling")


def _read(path):
    return json.loads(_read_record(path, LIMIT))


def _semantic(item):
    row = item["inventory_row"]
    value = {k: row[k] for k in ("item", "template", "name", "has_item_data", "base_value",
                                "value", "quantity_raw", "durability", "effects")}
    value["display_name"] = item["display_name"]
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def owned_observation(session, state):
    memory = WindowsReadOnlyProcessMemory.open_for_process("sb.exe", session.identity.process_id)
    try:
        if memory.process_creation_filetime_utc != session.identity.creation_filetime_utc:
            raise VendorBatchStopped("recycling client lifetime changed")
        config = Path(memory.executable_path).parent / "Config"
        effects, items = (config / "EffectsENGLISH.txt").read_bytes(), (
            config / "ItemENGLISH.txt").read_bytes()
        assessment = read_native_vendor_affixes(
            memory, building=state.building, vendor=state.vendor,
            effects_dictionary=effects, item_dictionary=items)
        inventory = read_native_vendor_inventory(memory)
        if (effects != (config / "EffectsENGLISH.txt").read_bytes()
                or items != (config / "ItemENGLISH.txt").read_bytes()):
            raise VendorBatchStopped("recycling dictionaries changed during assessment")
    finally:
        memory.close()
    return assessment, inventory


def _owned(session, state, assessment, inventory, eligible, template):
    if (assessment["process_id"] != session.identity.process_id
            or assessment["process_creation_filetime_utc"] != session.identity.creation_filetime_utc
            or inventory["process_id"] != session.identity.process_id
            or inventory["process_creation_filetime_utc"] != session.identity.creation_filetime_utc
            or inventory["executable_sha256"] != assessment["executable_sha256"]
            or (assessment["root"], assessment["manager"], assessment["menu"])
            != (state.root, state.manager, state.menu)
            or (inventory["native_window_address"], inventory["manager_address"],
                inventory["menu_address"]) != (state.root, state.manager, state.menu)
            or assessment["building"] != inventory["building"]
            or assessment["vendor"] != inventory["vendor"]
            or inventory["building"] != dict(object_id=state.building, object_type=8)
            or inventory["vendor"] != dict(object_id=state.vendor, object_type=42)
            or inventory["inventory"] is None
            or inventory["inventory"]["window_address"] != state.inventory):
        raise VendorBatchStopped("recycling observation belongs to another vendor visit")
    stock = {row["item"]["object_id"]: row for row in inventory["inventory"]["items"]}
    if len(stock) != len(inventory["inventory"]["items"]) or not set(eligible) <= stock.keys():
        raise VendorBatchStopped("recycling job item is missing or ambiguous; no absence authority")
    if any(stock[i]["template"] != dict(object_id=template, object_type=0) for i in eligible):
        raise VendorBatchStopped("recycling job item changed template")
    for item in assessment["items"]:
        if stock.get(item["item"]["object_id"]) != item["inventory_row"]:
            raise NativeVendorObservationChanged("affix and inventory observations changed")


def _binding(record, initial, eligible):
    return dict(job_id=record["job_id"], process_id=record["process_id"],
                creation=record["process_creation_filetime_utc"], window=record["window"],
                owner=list(_owner(initial)), inventory=initial.inventory,
                character=record["recipe_owner"]["key"], policy=POLICY, eligible=sorted(eligible))


def _validate_plan(plan, binding):
    if plan.get("schema_version") != 1 or plan.get("binding") != binding:
        raise VendorBatchStopped("recycling plan changed the exact job or vendor visit")
    assessment = plan["assessment"]
    owner = binding["owner"]
    if (assessment["process_id"] != binding["process_id"]
            or assessment["process_creation_filetime_utc"] != binding["creation"]
            or (assessment["root"], assessment["manager"], assessment["menu"])
            != (owner[1], owner[2], owner[3])
            or assessment["building"] != dict(object_id=owner[5], object_type=8)
            or assessment["vendor"] != dict(object_id=owner[6], object_type=42)):
        raise VendorBatchStopped("recycling assessment changed the admitted owner")
    original = plan_exclusions(assessment, binding["eligible"])
    if (plan["batches"] != [b["items"] for b in original]
            or plan["candidates"] != [i for b in original for i in b["items"]]
            or plan["semantics"] != {str(item["item"]["object_id"]): _semantic(item)
                                     for item in assessment["items"]
                                     if item["item"]["object_id"] in plan["candidates"]}):
        raise VendorBatchStopped("recycling plan or item content changed")


def finish_exclusions(store, session, record, eligible, **kwargs):
    try:
        return _finish_exclusions(store, session, record, eligible, **kwargs)
    except _RecyclingStopped:
        return _finish_stopped(store, session, record, sorted(eligible))


def _finish_exclusions(store, session, record, eligible, *, observation_reader=owned_observation,
                      reader_factory=None, cancelled=lambda: False,
                      clock=time.time, sleeper=time.sleep, update=lambda *args: None):
    """Caller owns execution.lock; prepared/submitted intents are never replayed."""
    if record.get("schema_version") != 5 or record.get("exclusion_policy") != POLICY:
        raise VendorBatchStopped("historical jobs cannot adopt automatic disposal")
    directory = store.directory(record["job_id"]) / "recycling"
    if ((directory / "complete.json").exists()
            and _read(directory / "complete.json").get("state") == "stopped"):
        raise VendorBatchStopped("stopped recycling job cannot resume")
    initial = Snapshot.decode(bytes.fromhex(record["initial_snapshot"]))
    eligible = sorted(eligible)
    if (len(set(eligible)) != len(eligible) or len(eligible) > 160
            or any(type(i) is not int or not 0 < i < 2**32 for i in eligible)):
        raise VendorBatchStopped("recycling requires this batch's exact inventory-confirmed IDs")

    def gate():
        while True:
            if cancelled() or store.control(record["job_id"]) == "stop":
                raise _RecyclingStopped("recycling stopped before the next batch")
            if clock() >= record["deadline_at"]:
                raise VendorBatchStopped("recycling reached the original job deadline")
            receipt = session.inspect_recycle()
            if (receipt.outcome != Outcome.OBSERVED or receipt.window != record["window"]
                    or _owner(receipt.snapshot) != _owner(initial)
                    or receipt.flags & (IN_FLIGHT | UNRESOLVED)
                    or receipt.recycle_completion is None
                    or not receipt.snapshot.inventory
                    or any(slot.item for slot in receipt.snapshot.slots)):
                raise VendorBatchStopped("recycling native owner or operation is unresolved")
            if receipt.flags & READY and store.control(record["job_id"]) == "run":
                return receipt
            session.renew_lease()
            paused = store.control(record["job_id"]) == "pause"
            update("paused" if paused else "attention", "Paused before the next recycling batch."
                   if paused else "Return focus to Shadowbane to continue the recycling batch.")
            sleeper(0.25)

    def observe(state, expected):
        for attempt in range(3):
            try:
                assessment, inventory = observation_reader(session, state)
                _owned(session, state, assessment, inventory, expected,
                       record["recipe_spec"]["template"]["object_id"])
                return assessment, inventory
            except NativeVendorObservationChanged:
                if attempt == 2:
                    raise
                sleeper(0.1)
        raise AssertionError("unreachable observation retry")

    fresh = gate()
    binding = _binding(record, fresh.snapshot, eligible)
    plan_path = directory / "plan.json"
    if plan_path.exists():
        plan = _read(plan_path)
    else:
        assessment, _ = observe(fresh.snapshot, eligible)
        batches = plan_exclusions(assessment, eligible)
        candidates = [i for batch in batches for i in batch["items"]]
        rows = {item["item"]["object_id"]: item for item in assessment["items"]}
        plan = dict(schema_version=1, binding=binding,
                    batches=[batch["items"] for batch in batches],
                    semantics={str(i): _semantic(rows[i]) for i in candidates},
                    assessment=assessment, candidates=candidates)
        _write(plan_path, plan)
    # Recompute the original immutable plan, including all protections, before
    # trusting any stored batch group or completed command.
    _validate_plan(plan, binding)
    recycled, protected = [], []
    for index, group in enumerate(plan["batches"]):
        path = directory / f"batch-{index:02d}.json"
        if path.exists():
            receipt = _read(path)
            validate_batch(receipt, binding, group)
            recycled.extend(receipt["items"])
            protected.extend(receipt["protected"])
            continue
        fresh = gate()
        assessment, inventory = observe(fresh.snapshot, group)
        rows = {item["item"]["object_id"]: item for item in assessment["items"]}
        if any(i not in rows or _semantic(rows[i]) != plan["semantics"][str(i)] for i in group):
            raise VendorBatchStopped("recycling candidate contents changed before admission")
        current = plan_exclusions(assessment, group)
        selected = [i for batch in current for i in batch["items"]]
        protected_now = sorted(set(group) - set(selected))
        if not current:
            receipt = dict(schema_version=1, binding=binding, group=group,
                           state="protected", items=[], protected=protected_now)
            _write(path, receipt)
            protected.extend(protected_now)
            continue
        if len(current) != 1:
            raise VendorBatchStopped("recycling group exceeds one native admission")
        batch = NativeRecycleBatch(tuple(selected), current[0]["fingerprint"],
                                   current[0]["gold_before"], current[0]["refund"])
        if reader_factory is None:
            from shadowbane_lab.client_extension.event_reader import (
                WindowsSharedMemorySnapshotReader,
            )
            reader = VendorProductionReader(session.identity.process_id,
                                             session.identity.creation_filetime_utc,
                                             WindowsSharedMemorySnapshotReader())
        else:
            reader = reader_factory(session)
        bookmark = reader.bookmark()
        if (bookmark["cursor"]["capture_incomplete"] is not False
                or bookmark["cursor"]["read_errors"]):
            raise VendorBatchStopped("recycling bookmark is incomplete")
        key = str(uuid.uuid4())
        proof = RecycleEvidence(inventory, scene=fresh.snapshot.scene,
                                character=record["recipe_owner"]["key"],
                                sequence=bookmark["cursor"]["sequence"],
                                gold_before=batch.gold_before, item_ids=selected)
        request = dict(schema_version=1, binding=binding, group=group, state="prepared",
                       items=selected, protected=protected_now, request_key=key,
                       expected_snapshot=fresh.snapshot.encode().hex(),
                       batch=current[0], assessment=assessment, inventory_before=inventory,
                       bookmark=bookmark, received=[], native_receipt=None)
        _write(path, request)
        again = gate()
        if again.snapshot != fresh.snapshot:
            raise VendorBatchStopped("recycling owner changed after durable intent; never replay")
        result = session.recycle(fresh.snapshot, key, batch)
        if (result.request_key != key or result.window != record["window"]
                or result.outcome != Outcome.SUBMITTED or result.flags != IN_FLIGHT
                or result.snapshot != fresh.snapshot or result.recycle_completion is None):
            raise VendorBatchStopped("recycling submission is uncertain; never replay")
        request["state"] = "submitted"
        _write(path, request)
        until = min(clock() + 15, record["deadline_at"])
        while True:
            received = reader.drain()
            request["received"].extend(received["records"])
            request["cursor"] = received["cursor"]
            _write(path, request)
            if received["capture_incomplete"]:
                raise VendorBatchStopped("recycling capture is incomplete; never replay")
            proof.receive(received["records"])
            observed = session.inspect_recycle()
            if (observed.outcome != Outcome.OBSERVED or observed.window != record["window"]
                    or _owner(observed.snapshot) != _owner(initial) or observed.flags & UNRESOLVED
                    or observed.recycle_completion is None):
                raise VendorBatchStopped("recycling native receipt is unresolved; never replay")
            if observed.transition_request == key:
                request["native_receipt"] = dict(
                    snapshot=observed.snapshot.encode().hex(), flags=observed.flags,
                    count=observed.transition_item, request_key=key,
                    inspect_request=observed.request_key, window=observed.window,
                    outcome=int(observed.outcome), host=observed.host.encode().hex(),
                    completion=dict(floor=observed.recycle_completion.floor,
                                    sequence=observed.recycle_completion.sequence,
                                    refund=observed.recycle_completion.refund,
                                    gold_after=observed.recycle_completion.gold_after))
                _write(path, request)  # Preserve the native result before validation can fail.
                # The owner may publish completion between this reader's drain
                # and its inspection. Catch up observation without repeating
                # the action or discarding the already-positive native receipt.
                if (proof.sequence < observed.recycle_completion.sequence or proof.lineage):
                    if clock() >= until:
                        raise VendorBatchStopped("recycling server observation remains incomplete")
                    sleeper(0.1)
                    continue
                if (observed.flags & IN_FLIGHT or observed.transition_item != len(selected)
                        or not proof.server_verified
                        or observed.recycle_completion.floor != bookmark["cursor"]["sequence"]
                        or observed.recycle_completion.sequence != proof.acknowledgment["sequence"]
                        or observed.recycle_completion.refund != batch.refund
                        or observed.recycle_completion.gold_after
                        != batch.gold_before + batch.refund):
                    raise VendorBatchStopped("recycling native/server receipt correlation failed")
                _, after = observe(observed.snapshot, [])
                proof.corroborate_inventory(after)
                request.update(state="observed", inventory_after=after, proof=proof.summary())
                _write(path, request)
                recycled.extend(selected)
                protected.extend(protected_now)
                break
            if not observed.flags & IN_FLIGHT or clock() >= until:
                raise VendorBatchStopped("recycling remains unconfirmed; never replay")
            sleeper(0.1)
    result = dict(schema_version=1, binding=binding, state="complete", recycled=sorted(recycled),
                  retained=sorted(set(eligible) - set(recycled)), protected_after_refresh=protected)
    _write(directory / "complete.json", result)
    return result


def validate_batch(receipt, binding, group):
    if (receipt.get("schema_version") != 1 or receipt.get("binding") != binding
            or receipt.get("group") != group
            or receipt.get("state") not in ("observed", "protected")
            or sorted(receipt["items"] + receipt["protected"]) != group
            or len(set(receipt["items"] + receipt["protected"])) != len(group)):
        raise VendorBatchStopped("recycling batch is uncertain or changed; never replay")
    if receipt["state"] == "protected":
        if receipt["items"]:
            raise VendorBatchStopped("protected recycling batch contains a disposal")
        return
    state = Snapshot.decode(bytes.fromhex(receipt["expected_snapshot"]))
    before = receipt["inventory_before"]
    if (list(_owner(state)) != binding["owner"] or state.inventory != binding["inventory"]
            or before["process_id"] != binding["process_id"]
            or before["process_creation_filetime_utc"] != binding["creation"]
            or (before["native_window_address"], before["manager_address"], before["menu_address"])
            != (state.root, state.manager, state.menu)):
        raise VendorBatchStopped("stored recycling observation changed its exact owner")
    planned = plan_exclusions(receipt["assessment"], group)
    if (len(planned) != 1 or planned[0] != receipt["batch"]
            or receipt["items"] != planned[0]["items"]):
        raise VendorBatchStopped("stored recycling action changed its qualified exclusion policy")
    proof = RecycleEvidence(receipt["inventory_before"], scene=state.scene,
                            character=binding["character"],
                            sequence=receipt["bookmark"]["cursor"]["sequence"],
                            gold_before=receipt["batch"]["gold_before"], item_ids=receipt["items"])
    proof.receive(receipt["received"])
    proof.corroborate_inventory(receipt["inventory_after"])
    cursor, original = receipt["cursor"], receipt["bookmark"]["cursor"]
    if (cursor["process_id"] != binding["process_id"] or cursor["creation"] != binding["creation"]
            or cursor["sequence"] != proof.sequence
            or cursor["overwritten"] != max(0, proof.sequence - 256)
            or cursor["rejected"] != original["rejected"]
            or cursor["ticket_drops"] != original["ticket_drops"]
            or cursor["read_errors"] != 0 or cursor["capture_incomplete"] is not False):
        raise VendorBatchStopped("stored recycling capture is incomplete or changed")
    native = receipt["native_receipt"]
    after = Snapshot.decode(bytes.fromhex(native["snapshot"]))
    if (proof.summary() != receipt["proof"] or native["request_key"] != receipt["request_key"]
            or native["count"] != len(receipt["items"]) or native["flags"] not in (0, READY)
            or native["window"] != binding["window"] or native["outcome"] != int(Outcome.OBSERVED)
            or list(_owner(after)) != binding["owner"] or after.inventory != binding["inventory"]
            or native["completion"] != dict(floor=proof.bookmark,
                                            sequence=proof.acknowledgment["sequence"],
                                            refund=proof.refund,
                                            gold_after=proof.gold_before + proof.refund)):
        raise VendorBatchStopped("stored recycling receipt lacks exact native/server correlation")


def require_recycling_idle(store, session, record):
    if record["state"] == "stopped" and record["phase"] != "recycling":
        return
    directory = store.directory(record["job_id"]) / "recycling"
    complete = _read(directory / "complete.json")
    current = session.inspect_recycle()
    initial = Snapshot.decode(bytes.fromhex(record["initial_snapshot"]))
    if (current.outcome != Outcome.OBSERVED or current.window != record["window"]
            or current.flags & (IN_FLIGHT | UNRESOLVED) or current.recycle_completion is None
            or _owner(current.snapshot) != _owner(initial)):
        raise VendorBatchStopped("recycling handback remains unresolved")
    if not (directory / "plan.json").exists():
        expected = dict(schema_version=1,
                        binding=_binding(record, current.snapshot, complete["binding"]["eligible"]),
                        state="stopped", recycled=[], retained=complete["binding"]["eligible"],
                        protected_after_refresh=[])
        if (record["state"] != "stopped" or complete != expected or record["excluded"]
                or len(expected["retained"]) != record["kept"]
                or list(directory.glob("batch-*.json"))):
            raise VendorBatchStopped("stopped recycling handback lacks its no-action receipt")
        return
    plan = _read(directory / "plan.json")
    binding = _binding(record, current.snapshot, plan["binding"]["eligible"])
    _validate_plan(plan, binding)
    recycled, protected, last = [], [], None
    for index, group in enumerate(plan["batches"]):
        path = directory / f"batch-{index:02d}.json"
        if not path.exists() and record["state"] == "stopped":
            continue
        receipt = _read(path)
        validate_batch(receipt, binding, group)
        recycled.extend(receipt["items"])
        protected.extend(receipt["protected"])
        if receipt["state"] == "observed":
            last = receipt
    expected = dict(schema_version=1, binding=binding, state=record["state"],
                    recycled=sorted(recycled),
                    retained=sorted(set(binding["eligible"]) - set(recycled)),
                    protected_after_refresh=protected)
    if (complete != expected or record["excluded"] != len(recycled)
            or len(binding["eligible"]) != record["kept"]
            or last and not _last_matches(current, last)):
        raise VendorBatchStopped("recycling handback changed the completed item receipts")


def _last_matches(current, last):
    completion = current.recycle_completion
    return (current.transition_request == last["request_key"]
            and current.transition_item == len(last["items"])
            and dict(floor=completion.floor, sequence=completion.sequence,
                     refund=completion.refund, gold_after=completion.gold_after)
            == last["native_receipt"]["completion"])


def _finish_stopped(store, session, record, eligible):
    directory = store.directory(record["job_id"]) / "recycling"
    current = session.inspect_recycle()
    initial = Snapshot.decode(bytes.fromhex(record["initial_snapshot"]))
    if (current.outcome != Outcome.OBSERVED or current.window != record["window"]
            or current.flags & (IN_FLIGHT | UNRESOLVED) or current.recycle_completion is None
            or _owner(current.snapshot) != _owner(initial)):
        raise VendorBatchStopped("recycling Stop still has an unresolved native action")
    binding = _binding(record, current.snapshot, eligible)
    recycled, protected, last = [], [], None
    if (directory / "plan.json").exists():
        plan = _read(directory / "plan.json")
        _validate_plan(plan, binding)
        expected_paths = {directory / f"batch-{i:02d}.json" for i in range(len(plan["batches"]))}
        if not set(directory.glob("batch-*.json")) <= expected_paths:
            raise VendorBatchStopped("recycling Stop found an unrelated action journal")
        for index, group in enumerate(plan["batches"]):
            path = directory / f"batch-{index:02d}.json"
            if path.exists():
                receipt = _read(path)
                validate_batch(receipt, binding, group)
                recycled.extend(receipt["items"])
                protected.extend(receipt["protected"])
                if receipt["state"] == "observed":
                    last = receipt
    elif list(directory.glob("batch-*.json")):
        raise VendorBatchStopped("recycling Stop found an action without its plan")
    if last and not _last_matches(current, last):
        raise VendorBatchStopped("recycling Stop cannot confirm its last native action")
    result = dict(schema_version=1, binding=binding, state="stopped", recycled=sorted(recycled),
                  retained=sorted(set(eligible) - set(recycled)), protected_after_refresh=protected)
    _write(directory / "complete.json", result)
    return result
