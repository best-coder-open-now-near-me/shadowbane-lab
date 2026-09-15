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

## Next activation

The user has been asked to close Shadowbane; confirmation is pending. Confirm
actual process exit before replacing its loaded extension. Do not ask for any
manual vendor-menu setup.

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
