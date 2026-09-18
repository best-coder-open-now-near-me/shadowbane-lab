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
Only 25 towers / 150 guards have verified rosters. This is evidence of incomplete
loaded coverage, not a city total or proof that the other towers lack guards.
Unprotected barracks cannot be established through the Tree protection list.

Active todo: install and verify host 0.3.28 without closing the game, then qualify
carried-only discovery/deposit/upgrade. Next: cover outer structures with fresh
scans as they load, preserve exact-key deduplication, verify rank progress and
available-gold stopping, and complete integration review. No full-town or
maximum-rank completion is claimed.
