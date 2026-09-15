# Vendor navigation 1.8.6 corrective activation

## Current status

Native 1.8.6 / host 0.3.15 from
bc730855f81c04b5e2ec3caa227599ca7338d6f5 is installed and launched on the test VM.
Source is pushed on codex/vendor-rolling, not merged. The integration destination
remains codex/native-lifecycle-hardening, then reviewed main. The normal checkout
remains on main; this task continues in its existing vendor-rolling worktree.

The first 1.8.5 live discovery found 11 buildings but rejected every opening
before selection/dispatch because its native Z range had the wrong sign. This
correction uses the existing movement convention x=[0,200000], z=[-200000,0],
with query bounds clamped around the player's world pose. Stale opening now stops
discovery rather than skipping all candidates. Zero verified vendors is review,
not success. See the [first live finding](vendor-navigation-1.8.5.md).

## Exact validation

Private package: E:/Projects/shadowbane/artifacts/vendor-packages/6c64ae20.
Package SHA-256: 7ad9c394c330e5bbb0fb73e9bc94899bfbcdd95f5ab17bd3063e1ca8b766ce1b.
DLL SHA-256: 38fae6f99c3773c156a1cf46f881d021d9259368872d5d02c805c1c85447ef16.
Wheel SHA-256: 0999dc2d62252016a4588c9ff8bc7b523e1040feb8a91d36e427de50de2f1b1c.
All 61 artifacts and the archive CRC were verified before staging.

Clean-source host suite: 2,253 passed, 14 skipped; Ruff passed. Both native
profiles passed required gates, exact private original/prepared image checks,
real movement IPC, and installed-wheel/native navigation contract checks.
Regressions cover actual Rooty coordinates, map edges, out-of-range/non-finite
positions, unchanged ownership guarantees, stale stopping and zero-result review.
The two pre-existing ideal-transparency diagnostics remain deferred findings;
this is a diagnostic package, not visual acceptance. All seven CI jobs passed:
https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/34931737991

## Activation evidence

Runtime path remains C:/ShadowbaneLab-Guided/vendor-1.8.3-bd08ffc.
Private updater/payload source:
E:/virtual-machines/shadowbane-testing/diagnostics/vendor-1.8.6-bc73085.
Guest evidence and rollback: upgrades/1.8.6-bc73085 under the runtime.

The user confirmed game closure; actual exit and the exact idle manager were
verified. The updater checked the current client inventory, replaced only its
extension inventory entry, and verified all five rollback files. The existing
Vendor Dashboard shortcut now uses host-0.3.15, with its old shortcut preserved.
All eight original crafting records and three records for the failed discovery
(manager ledger, city discovery and navigation) match their saved hashes.
Preparation completed despite its connection timeout; do not rerun preparation
or activation. The update receipt says updated_verified_not_launched; the later
launch receipt records the completed launch below.

Fresh game: PID 8748, creation 134339232565274274, HWND 3212236. Its loaded
extension hash and source match this exact corrective package. Refresh identities
before actions. The user has been asked to log Treehugger into Rooty again.
No corrected discovery request has been submitted yet.

## Next work

Verify current manager/worker readiness after login, then run the one-time
private discover-through-manager.py through host-0.3.15. It persists intent before
submitting vendor-discover and never repeats the old operation. Confirm exact
building/hireling opening and the two known workshops; keep uncertain requests
stopped. No Create, Keep, disposal, travel or building-setting changes are part
of this discovery qualification.

The active todo remains automatic building/vendor discovery. Next: automatic
recipe/inventory opening, durable selections and multi-vendor scheduling, then
complete multi-building qualification. Preserve unknown affixes, exclude only
confirmed Tier 1-2 affixes, and use one fresh-capacity batch per selected vendor.
Captures, credentials, binaries, packages and rollback files remain outside Git.

## September 15 login blocker

The desktop shortcut still launches this reviewed runtime, but the normal client
in Downloads has been patched to 1.3.38.7. This runtime is still based on 1.3.38.6,
explaining the user's patch-required login report. Corrected discovery has not run.
The exact 1.8.7 / host 0.3.16 replacement from c64eb0d has passed packaging and is
installed and launched following renewed connection approval. Both changed
official game assets are included, and the same desktop shortcuts are verified.
Login and fresh corrected discovery remain pending.
See [updated client review, package hashes and next steps](../client-update-20260915.md).
