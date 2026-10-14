"""Worker-owned preflight collection before planning a new funded vendor batch."""
from __future__ import annotations

import re

from shadowbane_lab.client_extension.condemn_progress import CondemnProgressStore
from shadowbane_lab.client_extension.guard_spending_journal import GuardSpendingJournal
from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_collection import (
    LIMIT,
    collect_completed_items,
    validate_collection,
)
from shadowbane_lab.client_extension.vendor_completion import _read_record
from shadowbane_lab.record_store import exclusive_record_lock


def require_collections_idle(store):
    for path in sorted((store.root / "collections").glob("*/collection.json")):
        try:
            record = validate_collection(_read_record(path, LIMIT))
            if record["context"]["identity"] != list(store.identity):
                raise ValueError("collection belongs to another worker")
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise VendorBatchStopped(
                "Unresolved completed-item collection; its Keep requests cannot be replayed."
            ) from exc


def collect_saved_vendor_results(store, binding, operation, session, selection, *, cancelled,
                                reader):
    from .vendor_recipes import require_saved_owner

    if not re.fullmatch(r"operation-[0-9a-f]{32}", operation.operation_id):
        raise ValueError("a canonical vendor operation is required")
    if (session.identity.process_id, session.identity.creation_filetime_utc, session.window) != (
        binding.game_process_id, binding.game_process_started_at_100ns, binding.game_window_handle,
    ):
        raise VendorBatchStopped("completed-item collection belongs to another client lifetime")
    with exclusive_record_lock(store.root / "execution.lock", timeout_seconds=.1):
        current = store.current()
        if current and current["state"] not in {"complete", "stopped"}:
            raise VendorBatchStopped("review the existing vendor job before collecting results")
        CondemnProgressStore(store.root).assert_idle()
        GuardSpendingJournal(store.root).assert_idle()
        require_collections_idle(store)
        verified = require_saved_owner(selection, binding, session, reader=reader)
        context = dict(identity=list(store.identity), owner=verified["owner"])
        path = store.root / "collections" / operation.operation_id / "collection.json"
        result = collect_completed_items(session, path, context=context, cancelled=cancelled)
        checked = validate_collection(_read_record(path, LIMIT))
        if (checked != result or checked["context"] != context
                or (checked["process_id"], checked["creation"], checked["window"])
                != (binding.game_process_id, binding.game_process_started_at_100ns,
                    binding.game_window_handle)):
            raise VendorBatchStopped("completed-item collection evidence changed owner")
        return result
