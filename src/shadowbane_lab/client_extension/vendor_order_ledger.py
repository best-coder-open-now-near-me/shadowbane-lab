"""Durable quantity progress evidence with read-only, no-replay reconstruction."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from shadowbane_lab.record_store import publish_atomic_record

from .movement_wire import request_bytes
from .vendor_batch import VendorBatchStopped, _items, _owner
from .vendor_completion import _read_record
from .vendor_order_progress import OrderProgress
from .vendor_production_responses import VendorProductionReader
from .vendor_wire import IN_FLIGHT, UNRESOLVED, Outcome, Snapshot

LIMIT = 4 * 1024 * 1024


class OrderLedger:
    def __init__(self, path: Path, admission_raw: bytes, character: tuple[int, int],
                 *, resume=False, review=False):
        self.path = Path(path)
        self.progress = OrderProgress(admission_raw, character)
        if self.path.exists():
            if not resume:
                raise VendorBatchStopped("quantity progress exists; explicit recovery is required")
            self.record = json.loads(_read_record(self.path, LIMIT))
            if (type(self.record["schema_version"]) is not int or self.record["schema_version"] != 2
                    or self.record["operation"] != "reconcile_quantity_orders"
                    or self.record["admission_sha256"] != hashlib.sha256(admission_raw).hexdigest()
                    or json.dumps(self.record["character"]) != json.dumps(list(character))
                    or self.record["state"] not in (
                        ("running", "stopped", "complete", "review") if review
                        else ("running", "stopped", "complete"))):
                raise VendorBatchStopped("invalid or uncertain quantity progress journal")
            seen = set()
            if (type(self.record["requests"]) is not list
                    or len(self.record["requests"]) > self.progress.admission["planned_items"]):
                raise VendorBatchStopped("invalid quantity Keep request count")
            for request in self.record["requests"]:
                request_bytes(request["request_key"])
                if (request["state"] != "observed" or request["request_key"] in seen
                        or type(request["item_id"]) is not int):
                    raise VendorBatchStopped("unfinished quantity Keep; never replay")
                seen.add(request["request_key"])
            self._kept_requests = set()
            self._last_keep = 0
            if type(self.record["events"]) is not list or len(self.record["events"]) > 4096:
                raise VendorBatchStopped("quantity progress evidence exceeds its bound")
            for event in self.record["events"]:
                self._apply(event)
            if self._kept_requests != seen:
                raise VendorBatchStopped("quantity Keep evidence is missing")
            self._validate_cursor(self.record["cursor"])
            if self.record["state"] == "complete" and not self.progress.complete:
                raise VendorBatchStopped("quantity progress cannot prove completion")
        else:
            self.record = dict(schema_version=2, operation="reconcile_quantity_orders",
                               state="running", admission_sha256=hashlib.sha256(
                                   admission_raw).hexdigest(), character=list(character),
                               cursor=self.progress.admission["production_cursor"],
                               events=[], requests=[])
            self._kept_requests, self._last_keep = set(), 0
            self.save()

    def _validate_cursor(self, cursor):
        admission = self.progress.admission
        VendorProductionReader(admission["process_id"],
                               admission["process_creation_filetime_utc"], None,
                               resume_cursor=cursor)
        if (cursor["sequence"] != self.progress.sequence or cursor["capture_incomplete"]
                or cursor["read_errors"] or any(cursor[key] != admission["production_cursor"][key]
                                               for key in ("rejected", "ticket_drops"))):
            raise VendorBatchStopped("quantity progress observation has a gap")

    def _apply(self, event):
        kind = event["kind"]
        p = self.progress
        if kind == "received":
            p.receive(event["records"])
        elif kind == "queue":
            kept = event["kept_item"]
            if type(kept) is not int or kept and kept != self._last_keep:
                raise VendorBatchStopped("quantity successor lacks a correlated Keep")
            p.observe(Snapshot.decode(bytes.fromhex(event["snapshot"])), event["counts"],
                      kept_item=kept)
            self._last_keep = 0
        elif kind == "keep_intent":
            request = next((r for r in self.record["requests"]
                            if r["request_key"] == event["request_key"]), None)
            if request is None or request["item_id"] != event["item_id"]:
                raise VendorBatchStopped("automatic Keep intent changed request")
            before = Snapshot.decode(bytes.fromhex(request["expected_snapshot"]))
            if (_owner(before) != _owner(p.initial)
                    or p.keep_candidate(before) != request["item_id"]):
                raise VendorBatchStopped("automatic Keep intent lacks a completed batch")
            p.expect_keep(request["item_id"])
        elif kind == "inventory":
            state = Snapshot.decode(bytes.fromhex(event["snapshot"]))
            if (_owner(state) != _owner(p.initial) or not state.inventory
                    or state.revision < p.revision or not set(event["items"]) <= set(p.items)):
                raise VendorBatchStopped("inventory proof changed quantity owner")
            p.confirm_inventory(event["items"])
        elif kind == "kept":
            request = next((r for r in self.record["requests"]
                            if r["request_key"] == event["request_key"]), None)
            if request is None or request["request_key"] in self._kept_requests:
                raise VendorBatchStopped("unrelated or duplicate quantity Keep proof")
            before = Snapshot.decode(bytes.fromhex(request["expected_snapshot"]))
            after = Snapshot.decode(bytes.fromhex(event["snapshot"]))
            item = request["item_id"]
            if (request["state"] != "observed" or event["transition_item"] != item
                    or event["transition_request"] != request["request_key"]
                    or type(event["outcome"]) is not int
                    or event["outcome"] != int(Outcome.OBSERVED)
                    or type(event["flags"]) is not int or event["flags"] not in (0, 1)
                    or event["window"] != p.admission["window"]
                    or item not in p.items or p.keep_candidate(before) != item
                    or item not in p.replies.keep_sends
                    or not before.inventory or not after.inventory
                    or _owner(before) != _owner(p.initial) or _owner(after) != _owner(p.initial)
                    or item in _items(after) or after.revision < before.revision):
                raise VendorBatchStopped("native quantity Keep did not prove inventory presence")
            p.confirm_inventory([item])
            self._kept_requests.add(request["request_key"])
            self._last_keep = item
        else:
            raise VendorBatchStopped("unknown quantity progress evidence")

    def save(self):
        raw = (json.dumps(self.record, sort_keys=True, indent=2) + "\n").encode()
        if len(raw) > LIMIT:
            raise VendorBatchStopped("quantity progress evidence exceeds its storage bound")
        publish_atomic_record(self.path, raw, temporary_label="vendor-order-progress")

    def append(self, event):
        if len(self.record["events"]) >= 4096:
            raise VendorBatchStopped("quantity progress event bound reached")
        self._apply(event)
        self.record["events"].append(event)

    def drain(self, reader):
        try:
            result = reader.drain()
            changed = result["cursor"] != self.record["cursor"]
            if result["records"]:
                self.append(dict(kind="received", records=result["records"]))
            self.record["cursor"] = result["cursor"]
            if changed or result["records"]:
                self.save()
            self._validate_cursor(result["cursor"])
            if result["capture_incomplete"]:
                raise VendorBatchStopped("quantity progress capture is incomplete")
        except Exception:
            self.record.update(state="review", cursor=reader.cursor)
            self.save()
            raise

    def observe(self, receipt, *, kept_item=None):
        if (receipt.outcome != Outcome.OBSERVED
                or receipt.window != self.progress.admission["window"]
                or receipt.flags & (IN_FLIGHT | UNRESOLVED)):
            raise VendorBatchStopped("quantity production is unresolved")
        if kept_item is None:
            kept_item = self._last_keep
        event = dict(kind="queue", snapshot=receipt.snapshot.encode().hex(),
                     counts=list(receipt.remaining_counts or ()), kept_item=kept_item)
        # Avoid storing repeated unchanged polling observations.
        last = next((e for e in reversed(self.record["events"])
                     if e["kind"] == "queue"), None)
        if event != last or kept_item:
            self.append(event)
            self.save()

    def inventory(self, state, items):
        fresh = sorted(set(items) - self.progress.inventory_confirmed)
        if fresh:
            self.append(dict(kind="inventory", snapshot=state.encode().hex(), items=fresh))
            self.save()

    def prepared_keep(self, state, key, item):
        request_bytes(key)
        if (self.progress.keep_candidate(state) != item or not state.inventory
                or any(r["state"] != "observed" for r in self.record["requests"])):
            raise VendorBatchStopped("quantity Keep is not ready")
        request = dict(request_key=key, item_id=item, state="prepared",
                       expected_snapshot=state.encode().hex())
        self.record["requests"].append(request)
        self.append(dict(kind="keep_intent", request_key=key, item_id=item))
        self.save()
        return request

    def kept(self, request, receipt):
        request["state"] = "observed"
        self.append(dict(kind="kept", request_key=request["request_key"],
                         snapshot=receipt.snapshot.encode().hex(), outcome=int(receipt.outcome),
                         window=receipt.window, flags=receipt.flags,
                         transition_item=receipt.transition_item,
                         transition_request=receipt.transition_request))
        self.save()
