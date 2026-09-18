# Continuous guard workflow capture

Branch: codex/guard-upgrades. Review into codex/vendor-rolling, then the documented
integration branch and reviewed main. This diagnostic is host-only and does not
require a game extension reinstall.

Run src/shadowbane_lab/client_observation/workflow_capture.py with the installed
host Python, an exact --process-id and --creation FILETIME, --output JSONL path,
and a distinct absent --stop-file path. Default duration is 30 minutes and sample
interval is 200 ms. Create the stop marker to finish gracefully. Output is exclusive
and flushed after every record. Keep captures private in the local artifact area.

The recorder holds a read-only process handle for one reviewed executable lifetime.
It never connects to an action channel or sends game actions. It continuously joins
ordered HUD and owned management-control observations, nearby building cache,
complete current building roster, guard quotes/progress, warehouse withdrawal quotes
and structure deposit quotes. Closed, inconsistent and unsupported panels become
explicit unavailable records; other channels and later samples continue. Unknown
HUD identities remain visible without interpreting their layouts. Repeated states
are deduplicated; health records retain observation/error counts and sample timing.

This is sequential state sampling, not exhaustive function-call tracing or atomic
cross-channel evidence. Brief transitions between polls can be missed. Leave each
new window visible briefly during the manual walkthrough. Existing strict readers
still determine semantic validity. Raw manager fields can be uninitialized and never
grant transaction authority. Session completion does not prove workflow completeness,
server acceptance, town coverage or maximum rank.

The capture ends on the explicit marker, duration limit, process loss or interruption.
It never rebinds to another process. Unexpected errors leave an error end record;
partial files without an end record must be treated as interrupted evidence.

Validation: recorder tests and existing building/guard/withdrawal/deposit observer
checks passed (139 tests). Tests cover unavailable-to-observed transitions, continued
capture, deduplication, explicit stopping, process loss, identity mismatch, exclusive
files, unknown HUDs and changing controls. Lint passed. Live preflight confirmed
in-world window observations with the currently installed 1.8.15 extension; no
management panels were open, and semantic channels correctly reported unavailable.

## Manual sequence captured and analyzed

The completed manual recording ended on request after 449 seconds, with 2,154
samples and no window-channel failures. It observed the guard quote, warehouse
withdrawal prompt, structure deposit prompt, building funds increasing by the quoted
amount, the upgrade confirmation dialog and the return to the warehouse. A separate
read of the still-open warehouse confirmed the exact debit. Journal-gated navigation
then reopened the same building and guard without spending, confirming upgrade in
progress, visible progress control and the matching building debit. This qualifies
the manual sequence and the existing revisit hook, not automatic spending.

Two related gaps are now identified together:

- Deposit completion leaves the initialized, owned building window in idle mode 0.
  Opening the guard from there also preserves mode 0. Native and Python navigation
  validation, plus the Python building reader, currently require mode 6. Native
  funding already recognizes both modes outside an amount prompt.
- Upgrade confirmation returns to a fresh building roster and closes the individual
  guard window. The upgrade controller currently waits for a selected-guard snapshot
  with both progress/rank evidence and an exact debit. It needs a correlated revisit
  of that same guard while retaining the pending spending request. Debit alone must
  not settle the request, and the upgrade must never be resubmitted.

City Command remained uninitialized in this recording. It adds no new town-discovery
or Tree-companion qualification; existing earlier evidence remains separate.

Active todo: implement and validate these two transitions together against the full
captured sequence before the next native deployment. Include wrong-owner/scene,
missing or mismatched debit, unexpected modal, duplicate and late response cases.
The user need not repeat this walkthrough. Automatic funding, full-town coverage,
maximum-rank evidence and integration remain unfinished.
