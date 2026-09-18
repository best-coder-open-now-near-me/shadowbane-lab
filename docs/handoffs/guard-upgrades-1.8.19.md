# Retained guard-page confirmation: 1.8.19 / 0.3.29

Branch: codex/guard-upgrades. Review into codex/vendor-rolling, then
codex/native-lifecycle-hardening and reviewed main. Not merged.

A fresh session with host 0.3.28 / native 1.8.18 discovered 180 guards in
30 towers (32 building rosters) from 60 nearby candidates, without Ulmer setup.
Eleven new upgrades and 1,343,100 gold in deposits/debits were confirmed.
The next cycle deposited 122,100, submitted Upgrade once, then stopped in review.
Its native response after 312 ms showed the exact guard, exact debit and upgrade
progress, with the original guard HUD and selected entry but a replaced building
HUD and controls. A separate strict read confirmed the same guard upgrading.
Total confirmed deposits were 1,465,200; completed-cycle accounting excludes the
last cycle. No request was replayed. Private evidence remains in the guest.

This reproduces the response shape from the prior stop, whose cause was uncertain
because the user reported possible manual interaction. The correction handles the
fully observed response independently of that attribution: it requires the same
scene, root, manager, building, guard, guard HUD and selected entry, with that guard
page frontmost before and after. Only a replaced building HUD in management mode,
an unchanged quoted cost, exact debit and progress or a single rank increment can
finish the pending transaction. A changed page without complete evidence still
stops. The original deadline and producer/lifetime admission remain in place.
Upgrade is never repeated. Existing unresolved records cannot be cleared.

Native confirmation and the host journal use the same completed-response rule.
The wire format is unchanged. Host 0.3.29 and native 1.8.19 must ship together.
Carried-only funding and insufficient-gold stopping remain unchanged.

Validation so far: 152 funding/job/upgrade tests and 219 journal/manager/discovery
checks (overlapping suites); native guard controller, guard channel and owned
navigation reader tests; changed-file lint. Regressions cover rebuilt
page progress and immediate rank completion, mismatched identities/windows/costs,
missing or wrong debits/progress, timeout, invalid captures, uncertain submissions,
immutable original submission and non-replay across journal restarts.

Active todo: exact-source packaging and guest preparation, then user game closure
for activation. No new version is installed yet. Next: fresh live qualification,
outer coverage, rank/gold stopping and integration review. Full-town and maximum
rank completion remain unverified.
