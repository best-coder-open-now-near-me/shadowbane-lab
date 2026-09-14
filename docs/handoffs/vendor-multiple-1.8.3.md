# Vendor multiple-slot candidate 1.8.3 / host 0.3.11

Branch: `codex/vendor-rolling`. Integration destination:
`codex/native-lifecycle-hardening`, then reviewed `main`. This work is not merged.
The installed test runtime remains native 1.8.2 / host 0.3.10.

## Live basis

On September 14, the owner clicked Create in Malik's Create Multiple Items
window with the random Gilded Scepter selected, quantity 1 and three free slots.
The passive trace recorded one outgoing Produce request (wire quantity 0,
multiple-slot flag 1), three successful server confirmations, and three distinct
item IDs. An independent queue read matched all three as cooking. All replies
reported remaining count 0. The tracer finished and detached normally.
The recipe closed after Create. This qualifies quantity 1 only; larger quantities
remain rejected. It does not establish the cause of the earlier single-Create
timeout.

Private evidence remains in the test runtime's vendor-manager directory:
`multiple-create-qualified.json`, the timestamped multiple-create trace, and
`multiple-create-trace-status.json`. No raw capture or client binary is published.
The later queue read failed because the selected vendor was unavailable;
the manual batch's current disposition is unconfirmed.

## Implemented behavior

The native controller snapshots the free-slot count before dispatch. Multiple
mode expects that many new items; single mode still expects one. Partial arrivals
remain pending. Removed or excess items, owner changes and invalid observations
make the request unresolved. Repeating a request returns the cached submission
without another invocation. A completed receipt identifies one member and carries
the full queue snapshot for host reconciliation.

The host persists the expected count before sending, then records all additions
atomically only after the exact request's full transition. Recipe closure does
not invalidate a pending receipt or require reopening after a full queue is
confirmed. Partial timeouts never retry or authorize Keep. Rank growth does not
expand the request already submitted; subsequent free capacity requires the
same qualified recipe mode before another request.

Single-item Create journals remain schema 1. Multiple-slot journals use schema 2,
with expected_item_count and item_ids per request. Keep validates the complete
request chain and retains unknown affixes once, with inventory confirmation.
Confirmed Tier 1/2 exclusions remain queued; automatic disposal is still disabled.
Existing single-item journals remain readable.

Native 1.8.3 is required for multiple-slot automatic dispatch. Native 1.8.2
rejects that command without dispatch; a host upgrade alone is insufficient.
No wire envelope size or command number changed.

## Validation and remaining work

The focused suite passed 74 tests plus 106 subtests. The full host run passed
2170 tests with 15 skips and 597 subtests, with one version-consistency failure;
all five tests in that version suite passed after correcting all runtime version
surfaces. Whole-tree Ruff passed. The Win32 full build passed all 142 executed required
native tests; three image-binding tests skipped without their private inputs and
will run explicitly in the exact package builder.

Next: complete native gates, build the exact committed package, qualify installed
multiple-slot Create and Keep against a fresh process. Preserve the three manual
diagnostic items; do not fabricate a manager journal to adopt them. Native window
opening and exclusion/disposal/resources remain broader unfinished vendor work.
