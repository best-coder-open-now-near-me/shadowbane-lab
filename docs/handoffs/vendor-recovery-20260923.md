# Vendor recovery and remaining town workflow - September 23

## September 24: candidate scene provenance

`codex/vendor-town-workflow` is based on freshly fetched `main@a91dfd5` and targets
reviewed `main` through a new draft PR. This host-only checkpoint is not included
in the furnishing-preview package or installed runtime.

Vendor discovery previously checked scene continuity within each phase but dropped
the originating scene/root between City Command discovery and building navigation.
A scene change while the worker closed the city transport and opened navigation
could therefore use old candidates against a new scene. The guard path already
carried this provenance.

Both modes now persist the city scene/root and expected snapshot before opening
City Command, carry scene/root into navigation records and summaries, and require
every navigation observation to match those original candidates. Missing, malformed,
or stale provenance produces durable review before any building/hireling open.
Old records are not migrated, rebound or replayed. City and asset navigation use
different native managers, so manager pointers are checked within their own phase,
not compared across the handoff.

Validation: 241 focused vendor, city, guard, worker and Condemn-preparation tests
passed; one optional native city-wire executable comparison skipped because its
fixture executable was not built. Affected-file Ruff and diff checks passed. New
regressions first reproduced stale/missing provenance dispatch, then verified no
opens after a scene/root change during the real worker handoff, durable early review,
missing guard roster-only provenance, and unchanged-scene success with distinct
city/navigation managers. No native source, versions, packages or VM state changed.

Next: review and merge this checkpoint, then include it in a future validated host
package. Automatic recipe/Inventory selection and the complete town capacity run
still require the non-spending menu qualification described below.

## Historical September 23 checkpoint

Source lane: `codex/vendor-town-workflow`, based on catch-up checkpoint `179f065`.
Integration destination: `codex/integrate-current-development` / PR #25, then
reviewed `main`. This source checkpoint is not installed or live-qualified.

## Completed source fix

A job-save interruption can leave complete Create/Keep journals behind an older
job phase. Recovery previously accepted the terminal labels and matching client/
vendor fields, without checking that Keep belonged to the exact Create batch.
An orphaned Keep file, changed source batch, missing inventory receipts or a
same-vendor journal from another building could therefore report success.

Recovery now checks the bounded historical Create chain (schemas 1 and 2),
capacity growth and each exact expected owner/queue before using it. Keep must
name the exact batch and source-file SHA-256, partition its items into kept and
excluded, and contain a unique sequential observed-inventory receipt for every
kept item. The job must own the original building/menu and pre-existing items.
Recovered counts and phase come from this validated chain, not stale job totals.
The same Create validation applies before a fresh Keep phase.

Each journal is read once during recovery, with the existing 1 MiB bound and
at most sixteen requests. Pending, inconsistent or missing evidence puts the job
in review without sending a native action or rewriting its journals. No schema
migration, receipt adoption, disposal, or retry is introduced. Historical valid
single-slot/multiple-slot batches and known exclusions retain their behavior.

Validation: 99 focused vendor, discovery, policy and assessment tests passed
(two environment-dependent tests skipped), affected-file Ruff and diff checks.
Regressions cover a save gap after Keep, orphaned Keep, changed exact source
bytes, wrong operation/schema/building, missing/pending/duplicate receipts,
incorrect queue ownership and item partitions. Positive cases include rank
growth, multiple-slot recipe closure, unknown preservation and retained exclusions.
This host-only change does not alter native commands or require native rebuilding.

## Next: acquire recipe and Inventory entry evidence

The current production implementation still requires a manually opened random
Gilded Scepter recipe and later Inventory. It has no qualified typed recipe
open/select command and no complete town scheduler. Do not expose town Start
against unconnected adapters or claim complete filtered auto rolling.

Existing exact-build evidence identifies asset-management Inventory action
`0x58c` (see `guard-upgrades.md`, warehouse resource entry). It is distinct from
warehouse resources. Prior private `vendor-protocol` captures qualify Create/
Keep builders and city/building navigation; they do not qualify ordinary recipe
opening or selection. A UI action number alone is not its owned control/call
contract.

One serialized, non-crafting manual walkthrough can supply the missing states:

1. Pin the current reviewed executable hash, PID/creation time, extension and
   manager identities. Reach a confirmed idle manager boundary and retain old
   uncertain vendor records. Do not adopt or replay an earlier batch.
2. Open one known workshop and exact vendor normally; record its building and
   vendor keys, current production menu and control ownership. Open the ordinary
   recipe list, select the existing Gilded Scepter random recipe, leave it visible,
   then close it without Create. Open Inventory, leave it visible, close and
   reopen the same menu. Leave each state visible for several sample intervals.
3. Capture `workflow_capture.read_window_context` for HUD order and owned
   management controls; `read_native_vendor_roster(..., window="vendor")` for
   exact membership; `read_native_vendor_queue` for the typed recipe, production
   slots and Inventory. These are read-only host observers. The queue CLI is
   `client observe-native-vendor-queue --process-id PID --json`; the roster CLI is
   `client observe-native-vendor-roster --process-id PID --window vendor --json`.
4. Correlate the observed control identities with exact-client static handler
   evidence, including selection versus activation, arguments, enabled/visible
   state and result ownership. Sampling may miss short-lived calls; collect a
   bounded call-path trace only if static evidence and snapshots cannot settle
   that contract. No Create, Keep, Junk, gold transfer or game restart is needed
   for this walkthrough.

After qualification, implement typed owner-thread open/select/reopen actions
with ordinary permission checks, exact response ownership and durable intent.
Then complete saved building/vendor/recipe selections and the multi-vendor
capacity run as one end-to-end slice. Shared worker/dashboard/channel edits
remain coordinated by the integration owner. Unknown affixes stay kept;
unqualified disposal and recurring spending remain disabled.

## Ready passive vendor walkthrough recorder

The optional `--vendors` mode now joins the existing window/control context with
`vendor_roster` and `vendor_queue` channels. It uses the same pinned read-only
process handle and existing duration/stop/output safeguards. The strict queue
reader includes current recipe selection, production state and owned Inventory;
missing or changing ownership is recorded as unavailable. Displayed Inventory
entries never imply complete inventory coverage or known capacity.

Run using the host that contains this source checkpoint, after supplying the
fresh verified PID/creation pair and two new private artifact paths:

```powershell
& $vendorHostPython -m shadowbane_lab.client_observation.workflow_capture `
    --vendors --process-id $vendorProcessId --creation $vendorCreationFiletime `
    --output $vendorCapturePath --stop-file $vendorStopPath `
    --duration 300 --interval 0.2
```

The paths must have an existing private parent directory; neither output nor stop
marker may already exist. After `Workflow recorder armed.`, perform only the
ordinary menu walkthrough above. Create the stop marker to end early, or let the
five-minute deadline finish. The recorder does not open menus, craft, transfer,
Keep, Junk, acquire a native command channel, or attach a debugger. Retain the
session-end record and exact source identity with the private evidence.

Validation for this recorder checkpoint: all 54 workflow/vendor queue, roster
and inventory tests passed; affected-file Ruff and diff checks passed. Tests use
the real strict memory readers for closed-menu, recipe and Inventory transitions,
separate unavailable channels, unchanged opt-in behavior and exact-lifetime CLI
binding/handle cleanup. Native rebuilding and live acceptance are not claimed.

Next active todo: the serialized non-spending vendor menu capture. Automatic
recipe/Inventory commands and the complete multi-vendor capacity run remain open.
