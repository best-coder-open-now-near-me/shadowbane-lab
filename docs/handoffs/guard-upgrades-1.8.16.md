# Deposit and upgrade response handling: 1.8.16 / 0.3.25

Branch: codex/guard-upgrades. Review into codex/vendor-rolling, then
codex/native-lifecycle-hardening and reviewed main. Not merged.

The continuous manual workflow exposed two related transitions. Deposit leaves
an initialized, owned building menu in idle mode 0. After upgrade confirmation,
the response replaces the building roster and closes the guard menu. Reopening
the same guard manually through the existing hook verified the exact debit and
visible upgrade progress. See [capture evidence and limits](guard-workflow-capture.md).

Native/Python navigation and the read-only building observer now recognize idle
mode 0 alongside mode 6, retaining initialized ownership, exact keys, list and
front-window checks. Amount-prompt and confirmation modes remain inadmissible.
Crafting's separate admission rules are unchanged.

An upgrade remains pending when its individual guard window closes. Only a complete
owned return roster for the same scene/root/manager/building, exact quoted debit
and same guard with a plausible rank qualifies for a revisit. A fresh inspection
from the original producer generation can reopen that guard once. The native
callback rechecks the current foreground window, producer lease, command deadline,
lifetime and full returned snapshot immediately before activation. Other native
transactions remain blocked. A failed or uncertain callback cannot be retried.

Reopening does not settle spending. A fresh guard observation must match the
returned building HUD and original typed guard identity, with exact debit and
visible upgrade progress or the next rank. A wrong identity/debit, timeout or
uncertainty remains blocked, including late responses. The upgrade never replays.

A guard receipt flag (REOPENED, bit 8) explicitly records the correlated native
revisit. The host journal permits replacement HUD/control pointers only with that
flag and matching scene/root/manager/building/guard, producer, window and original
request. Legacy receipts retain pointer equality and remain readable; old journals
are not rewritten. Wire sizes and signature remain unchanged. Ship host and native
together: an older host correctly rejects the new flag.

Source `6c6228fd8ed4e801cf6d5d82abdf269c4dd5800e` is pushed on
`codex/guard-upgrades`; integration remains pending.

Validation: 137 focused host tests, five native controller/ownership/channel
tests, full native compilation and changed-file lint passed. Native tests include
the post-deposit idle state, replacement roster, exact debit, one revisit, fresh
controls, wrong owner/rank/debit, amount-modal blocking, stale producer, uncertain
callback, timeout and duplicate upgrade. The host cycle test retains one journal
through deposit and the changed-window completion. The exact-source package passed
2,695 host tests (18 skipped), lint, both native profiles and installed-host checks.
Six additional installed guard/funding wire comparisons and correlated REOPENED
receipt round trips passed. All 61 listed artifact hashes and the archive hash
were independently verified. Two known graphics transparency stretch diagnostics
fail in each profile; the package remains diagnostic-only and is not full-product
acceptance. No live automatic spending acceptance is claimed yet.

The combined full-profile update is installed in the test VM after confirmed game
closure. Exact client/package verification, native version/hash, new host source
identity and desktop launch pins passed. All 182 retained records/settings matched
their original hashes after activation and manager restart. The 0.3.25 manager is
responding, awaiting the user-launched game; no gameplay automation ran.

Live follow-up verified the new process and worker, automatic warehouse return,
the Tree companion and eight guard windows across six buildings. A zero-slot wall
stopped discovery. One bounded funding cycle stopped at Gold activation before
any transfer; its uncertain quote request is retained. See the
[combined follow-up correction](guard-upgrades-1.8.17.md).

Active todo: validate and stage that correction, then qualify the complete
automatic funding/upgrade cycle once. Town discovery beyond the Tree, full-town
coverage, maximum-rank evidence and integration remain unfinished. Preserve all
historical uncertain requests; the user starts the game through Vendor Test.
