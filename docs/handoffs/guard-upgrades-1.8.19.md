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

Exact source a87a9849a7e6ab8f73081c0f2361c2803cb0ac32 is pushed to
origin/codex/guard-upgrades. The final package passed 2,727 host tests
(18 skipped), lint, both native build profiles and their required suites,
movement IPC and prepared-client bindings, installed-host contracts and six
additional installed guard/funding wire checks. All 61 package artifact hashes
and the archive digest were independently checked. The two previously known
graphics transparency stretch diagnostics still fail in each profile; they
remain recorded, and this is not complete graphics acceptance. The initial
package caught a version macro mismatch; the final source corrects it.

Full extension SHA-256:
db7273cb49cefb2220925a26fb468be0e4b347ffe299a9d8dfe6f14bb28da449.
Host wheel SHA-256:
f3c1131f35d0e121177012f5c48c31a86a97da5f5eaf09fd13cf5ab278e8b584.
Diagnostic archive SHA-256:
141792a6d5044006ed38d2814f56a28ac6c0f880356e9c5db9340a9f224374fd.

Guest preparation and read-only validation passed. After user-confirmed game
closure, the exact windowless lingering game process was stopped and native
1.8.19 / host 0.3.29 installed. Only the extension changed in the client inventory;
the executable is unchanged. Backups are retained. All 1,696 checked journal,
settings and evidence records are unchanged after manager restart. The dashboard
shortcut uses host 0.3.29; Vendor Test remains the same shortcut. The manager
restarted healthy, and the next user-launched game loaded native 1.8.19.

Active todo: fresh live qualification with no Ulmer/menu prerequisite.
Continue from new process-bound discovery; never replay the retained uncertain
requests. Next: outer coverage, rank/gold stopping and integration review.
Full-town and maximum-rank completion remain unverified.
