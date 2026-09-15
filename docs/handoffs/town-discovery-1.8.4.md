# Town discovery 1.8.4 / host 0.3.12

Source: c268cc0124f64af54a8d068a8e778ff297fb7b38 on codex/vendor-rolling.
Integration destination: codex/native-lifecycle-hardening, then reviewed main.
The feature is pushed, not merged. The normal project checkout remains on main.

## Delivered behavior and remaining scope

The dashboard has a worker-owned **Find nearby buildings** operation. It waits
for the game to be ready/in front, opens City Command through its ordinary
action dispatcher on the existing native owner thread, and reads the nearby
building/hireling cache. Exact process, scene, lease, request, window and roster
checks guard the operation. Opening is never automatically retried after an
uncertain result. Discovery uses separate durable records and preserves the
old crafting job in review.

This is nearby discovery, not certified town coverage or a complete town runner.
Populated live roster qualification, building/hireling window selection,
town identity/completeness/access, the saved town plan and its scheduler remain
unfinished. No Select all/Start is presented against unqualified native paths.
Keep unknown affixes; exclude only confirmed Tier 1/2. Disposal remains unqualified.

## Exact package and validation

Private package directory:
E:\Projects\shadowbane\artifacts\vendor-packages\11e219d4

- Archive: navigation-inspector-diagnostic.zip
- Archive SHA-256: c4c690c09e4ed65a06f254ad3e6a8587d911f75f4593b63e816cb3f0354ee19f
- Full-profile DLL SHA-256: bc05d61b5eb40b0bd47499cf632e737d759d61fd8d673670275e910090bd7cc5
- Host wheel SHA-256: 019b1698427332a13a3a00a3a8c7b7eeacebcf296c87502e1deba8eebdeff023
- Patched EXE remains bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87.

All 60 receipt-listed artifacts match their hashes and sizes; archive CRC passes.
The exact package builder passed using the project's .venv: 2199 Python tests
passed, 14 skipped. The default Python's separate full run passed 2200 tests,
16 skipped, 680 subtests. Both native profiles passed all 145 executed required
tests; three private-image checks per profile skipped in CTest were subsequently
run directly against the reviewed/private prepared images and passed. Native
movement IPC, wheel-from-sdist, installed panels, vendor contract and targeted
action reader gates passed. The installed wheel also agrees byte-for-byte with
both compiled City Command fixtures. Whole-tree Ruff and all seven CI jobs passed:
https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/34919040690

This remains a diagnostic package: the two pre-existing ideal-transparency
diagnostics are retained as known deferred findings. It is not visual acceptance.
The first package attempt, 413183da, stopped only because the default Python
lacked the build module; it is not a successful package. Its private logs remain
at that artifact directory. Use 11e219d4, not the failed attempt.

## Test VM preparation

The test VM setup credential is authorized; keep it private. Do not print it or
include captures, credentials, game binaries or package archives in Git.

Existing runtime stays at:
C:\ShadowbaneLab-Guided\vendor-1.8.3-bd08ffc

Its directory label is retained to avoid another multi-gigabyte copy or moving
the existing manager journals. The running game/manager still use DLL 1.8.3 /
host 0.3.11. Preparation installed host 0.3.12 alongside host 0.3.11; it did not
activate it. No game, worker, settings, crafting journal or desktop shortcut was
changed by preparation.

Private host payload:
E:\virtual-machines\shadowbane-testing\diagnostics\vendor-1.8.4-c268cc0

Guest share:
\\VBOXSVR\codexdiag\vendor-1.8.4-c268cc0

Staged guest payload:
C:\ShadowbaneLab-Guided\vendor-1.8.3-bd08ffc\upgrades\1.8.4-c268cc0\payload

The guest upgrades/1.8.4-c268cc0/prepare.json says prepared_not_applied.
validation.json says update_verified_not_applied, exact new installed source
confirmed, one immutable client inventory entry changes (the extension), EXE
unchanged, crafting journals unchanged. The preparation wrapper timed out, but
these completed receipts were subsequently read and verified; do not rerun
prepare-town-update.ps1.

The private updater defaults to read-only validation. Its --apply mode refuses
while any sb process or the recorded manager PID is alive. It verifies the
current launchable copy, old/new DLL hashes, manifest and unchanged EXE; preserves
the original evidence inventory except the independently hashed extension entry;
backs up the original DLL, package evidence, game launcher, dashboard launcher
and preparation receipt outside the client; and restores those files if update
verification fails. Backups are created only on application. It preserves
runtime settings and crafting journals.

## Next activation and live qualification

The user confirmed Shadowbane is closed; activation is now the next step.
No further manual vendor-menu preparation is required for discovery.

1. Confirm the game is closed. Read the exact manager process identity and current
   operation status. Detach any idle old worker through the existing manager
   action, verify no active/queued work, and stop only that verified manager.
   Do not resume, reset or edit the old crafting journal.
2. Run the staged payload/update-runtime.py --apply with
   host-0.3.12/Scripts/python.exe. Inspect update-receipt.json and the restoration
   manifest. If it times out, inspect receipts before deciding what remains.
3. Update the existing WonderBane Vendor Dashboard desktop shortcut's target to
   host-0.3.12/Scripts/pythonw.exe, retaining its current launcher arguments and
   working directory. Preserve the prior shortcut. The game shortcut remains
   on launch-reviewed.ps1; the updater replaces its expected hashes/source and
   host path, retaining existing settings import and launch verification.
4. Launch through the existing reviewed SysWOW64 PowerShell launcher. Verify the
   fresh launch receipt, actual loaded DLL hash, source and game lifetime. Start
   the new manager using its updated dashboard launcher; preserve the existing
   token, manifest, journals and review state. Verify the exact worker binding.
5. Invoke only vendor-discover through that manager and return focus to the game.
   Inspect the native open receipt and independent nearby roster record.
   A successful nearby scan still does not certify Rooty's full town boundary,
   permissions or complete vendor population.
6. Continue the active discovery todo, then automatic building/vendor selection
   and the durable town scheduler. The prior Keep/multiple-item qualification
   stays unfinished until revisited through the qualified window lifecycle.

No automatic Create, Keep, disposal, travel or building-setting mutation is part
of this update or its first discovery check.
