# Carried-gold guard upgrades: host 0.3.28

Branch: codex/guard-upgrades. Review into codex/vendor-rolling, then
codex/native-lifecycle-hardening and reviewed main. Not merged.
Native extension remains 1.8.18; this change needs only a host/worker restart.

## Behavior and ownership

The user withdrew gold manually and requested removal of the Ulmer dependency.
New guard discovery starts from an exact in-world navigation context without a
warehouse panel. Plans retain process/scene, discovery digests and exact building
and guard keys. New cycles use existing structure funds and deposit only the
remaining upgrade cost from the live character purse. They never open a warehouse
or withdraw gold. Insufficient carried gold stops the job before a deposit or
later guard cycle. Quotes, ownership, character identity, confirmed balance
changes and single-shot upgrade receipts retain the existing checks.

Prepared selections, jobs and funding cycles use schema 2 with an explicit
carried funding policy. The worker capability changes to guard_jobs_carried_v2,
preventing an older warehouse-dependent worker from executing a new job. Old
records remain readable for review, but are not migrated into executable plans,
replayed or cleared. The dashboard describes carried-only funding and no longer
requires an open warehouse.

## Validation and remaining work

263 affected funding/discovery/manager/journal tests passed. The full host suite
passed 2,709 tests and skipped 13; one dashboard socket test aborted at the local
transport layer. That exact test passed on rerun with all 28 final manager-control
tests, including rejection of old workers. Repository lint passed. Added cases
cover zero, insufficient, exact and 40-million purses without warehouse access,
warehouse-free discovery/start, and legacy-policy restart rejection.

A fresh live City Command scan still returned the previous 60 candidate keys.
Five of the 30 listed Tower Junctions had previously been unavailable before
submission; a bounded read-only loaded-object check found none of those five.
That pass verified 25 towers / 150 guards. This is evidence of incomplete
loaded coverage, not a city total or proof that the other towers lack guards.
Unprotected barracks cannot be established through the Tree protection list.

Source `764ab0a21a07595f08c850391df3622f8d12404c` is pushed. The wheel
SHA-256 is `b720cedc4e1fcb641cd8dabb334ed4c5648edb37eec02a4de3d246727de84ca7`;
all 415 packaged module/data files match the source. Host 0.3.28 is installed
and active with a healthy carried-only worker. Shadowbane stayed running with
native 1.8.18. The launchers and dashboard shortcut use the new host; their
previous copies are retained. All 559 checked historical records are unchanged;
three current-worker capability records renewed as expected. No gold moved
during installation. The first discovery opened the Tree but stopped on a
changing read; its navigation journal settled, and a subsequent read verified
the complete Tree roster. A fresh non-spending discovery finished and admitted
174 verified guards in 29 towers (31 verified rosters including Tree/warehouse)
from 60 candidates. The remaining tower and other unavailable entries remain
explicit coverage gaps.

Live carried-only qualification passed: the initial purse was 40,000,000.
Fourteen new upgrades and exactly 1,709,400 in deposits/debits are confirmed,
with zero warehouse opens or withdrawals. Three guards were already upgrading
and were observed without duplicate spending. The next cycle confirmed another
122,100 deposit, then stopped in review on upgrade confirmation. Total confirmed
deposits across cycles are 1,831,500; the job summary includes only completed
cycles. No later cycle ran and no upgrade was replayed.

Read-only native receipts isolate a separate confirmation case: 234 ms after
submission, the exact same guard already showed the exact debit, upgrade flag
and progress control, but its building HUD changed while its guard HUD remained.
No return-page request occurred (REOPENED was absent). The controller's original
SameOwner branch marked the changed ownership observation unresolved. A later
strict read independently confirmed the same guard's progress and zero remaining
structure gold. The original submission/completion record remains unresolved;
this observation has not been promoted into a synthetic native completion.
The user then reported they may have clicked accidentally. The capture does not
establish whether the window replacement was a normal game response or manual
interference; do not classify it as a proven controller bug or relax ownership
checks from this observation alone.

The job is stopped in review. Diagnostic recording ended normally on its stop
marker; private receipts and original journals remain in the guest. The carried
funding feature is delivered, while the full-town upgrade task is unfinished.

Active todo: continue from a fresh game-process-bound discovery while retaining
the current unresolved request without replay. Verify an uninterrupted run before
changing confirmation ownership rules. Then continue rank/gold stopping, outer
coverage and integration review. No full-town or
maximum-rank completion is claimed.
