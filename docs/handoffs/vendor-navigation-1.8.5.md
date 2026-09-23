# Vendor navigation 1.8.5 package and activation

## Source and validation

Release source: 89a44896b5c07fa2a1831d6decfe4c375031e1fd on
codex/vendor-rolling. Native 1.8.5 / host 0.3.14 adds automatic exact-building
and hireling opening to the dashboard discovery operation. This source is pushed,
not merged. Integration destination: codex/native-lifecycle-hardening, then
reviewed main. The normal checkout stays on main.

Exact package: E:/Projects/shadowbane/artifacts/vendor-packages/3a2ade72.
Package SHA-256: 70673f41d095614be1984465c03146b119ac440e439e3fab2b7980e20d5261be.
Full-profile DLL SHA-256: 04991aa66d859f2a209622130f8a95b7d12803e732d2740e9ceab8704ea349ef.
Wheel SHA-256: f6951066bd1727882def32517329718458efbcab27c925334a02e2b6cd3455ee.
All 61 recorded artifacts and the archive CRC were verified before staging.

The clean-source package host suite passed 2,250 tests, with 15 skipped; Ruff
passed. Both native profiles passed their required gates (158 cases, including
three private-image skips subsequently checked with the exact original/prepared
image). Real movement IPC and installed-wheel/native navigation wire agreement
passed for both profiles. The two pre-existing ideal-transparency diagnostics
remain recorded as deferred failures: this is a diagnostic package, not visual
acceptance. All seven CI jobs passed for the exact release source:
https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/34927131242

## Prepared test VM update

The existing runtime remains C:/ShadowbaneLab-Guided/vendor-1.8.3-bd08ffc.
Native 1.8.4 / host 0.3.13 is still active. Host 0.3.14 is installed alongside it.
The new payload is in upgrades/1.8.5-89a4489/payload under that runtime.
Private host preparation files are in
E:/virtual-machines/shadowbane-testing/diagnostics/vendor-1.8.5-89a4489.

The guest prepare.json says prepared_not_applied; validation.json confirms exact
installed source, verified old/new DLL identity, unchanged executable and exactly
one proposed immutable client-inventory replacement. Activation has not happened.
The initial script header had a UTF-8 decoding problem; its source header was
corrected. The guest preparation nevertheless completed, and its successful
installation and validation receipts were independently read after the command
connection timed out. Do not rerun preparation. Eight existing crafting records
are hashed in upgrades/1.8.5-89a4489/crafting-before.json for later comparison.
No existing crafting operation was resumed or edited.

## Activation procedure

The user confirmed closure; actual process exit was verified before activation.
Installation and launch steps below are complete; discovery in step 5 remains.
See the activation result below. Do not ask for manual vendor-menu setup.

1. Check current game/manager identities and operation status. Detach the idle
   worker through the manager and stop only the verified idle manager.
2. Run the staged update-runtime.py --apply using host-0.3.14/Scripts/python.exe.
   It revalidates the current launchable client and creates a five-file rollback
   before changing the DLL, package evidence, launchers and version receipt.
   On failure it restores those files; inspect receipts before any retry.
3. Preserve and update the existing dashboard shortcut to host-0.3.14 pythonw;
   retain its launcher arguments. The game shortcut retains launch-reviewed.ps1.
4. Launch with the reviewed SysWOW64 PowerShell launcher. Verify fresh game
   lifetime, native version/hash, installed source and manager/worker binding.
   Compare all eight crafting records to their saved hashes.
5. Run only Find buildings and vendors through the manager. Qualify exact
   building/hireling windows and both known workshops. Discovery performs no
   Create, Keep, disposal, travel or building-setting mutation. Stop on uncertain
   native navigation; never replay the unresolved request.

Active todo: live automatic building/vendor discovery. Remaining: automatic
recipe/inventory opening, durable selections and multi-vendor scheduling, then
complete multi-building qualification. Keep unknown affixes, exclude only
confirmed Tier 1-2 affixes, and use one fresh-capacity batch per selected vendor.
Private captures, credentials, client binaries, packages and rollback files stay
outside Git.

## Activation result

Native 1.8.5 and host 0.3.14 from 89a4489 are installed. The verified idle
manager was stopped only after the game exited. The updater verified the full
client inventory and all five rollback files. The eight pre-existing crafting
records match their saved hashes. The existing Vendor Dashboard shortcut now
uses host-0.3.14, with its original shortcut retained beside the rollback files.

The reviewed launcher started game PID 500, creation 134339213925830451,
HWND 2097324. Its fresh launch receipt records the exact release source and
DLL hash above. The manager reports extension 1.8.5 and a healthy, single worker
bound to that exact game lifetime: worker-9039aa1efef9446c9b425cb455dd17e8,
PID 3020, creation 134339214834368612. There is no active or queued operation.
The worker started automatically; a conditional manual-start helper stopped
before making any request when it detected that worker already existed.

The launcher connection timed out after spawning the detached processes; the
completed launch receipt and manager readiness were independently verified.
Do not rerun activation or launch. Refresh all identities before live actions.
The user has been asked to log Treehugger into Rooty and leave the game in front.
Login confirmation and the first automatic building/vendor discovery are next.
No Create, Keep, disposal or navigation request has been sent since activation.

## First live discovery and coordinate correction

After the user logged Treehugger into Rooty, manager operation
operation-f61bdc3d6d324a4696e3933a38e68a31 independently found 11 nearby buildings.
Every building open returned STALE before selection/dispatch. No vendor window,
Create, Keep or disposal was submitted. Its original operation record is retained.

A read-only actor/pose check confirmed the reviewed getter and stable scene,
but native Z was -52546.484375. The new building adapter incorrectly required
positive Z. Existing native movement and attachment code use x in [0,200000]
and z in [-200000,0]; this correction uses that established convention and
clamps the local query to those bounds. Tests include the observed Rooty pose,
both map corners, positive/out-of-range Z and non-finite values, while preserving
all ownership and callback invalidation checks.

Native 1.8.6 / host 0.3.15 is the corrective source candidate. The manager now
stops on a stale opening receipt instead of skipping every candidate, and a
scan with zero verified vendor windows produces review rather than success.
The focused host checks passed (38); the native building-target test and extension
build passed; whole-tree Ruff passed. Exact package validation is next.
Native 1.8.5 / host 0.3.14 remains installed until the correction is staged.
The active todo remains live automatic building/vendor discovery; no manual
vendor-window setup is needed.

The correction is now packaged, installed and launched as native 1.8.6 / host
0.3.15 from bc73085. All seven CI jobs and exact package gates passed. See the
[current activation and next discovery check](vendor-navigation-1.8.6.md).
