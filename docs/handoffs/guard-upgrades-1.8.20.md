# Owned guard response identity: 1.8.20 / 0.3.30

Branch: codex/guard-upgrades. Review into codex/vendor-rolling, then
codex/native-lifecycle-hardening and reviewed main. Not merged.

The fresh 1.8.19 session verified 174 guards across 29 towers, with one previously
reachable tower unavailable. Eight new upgrades and 1,278,750 gold in completed
deposits/debits were confirmed, including three rank-2 upgrade offers and five
rank-1 offers. The next cycle deposited 122,100 and submitted Upgrade once.
Its response after 250 ms showed the exact guard, exact debit and progress, but
rebuilt both the building page and selected roster entry. A separate owned-roster
read confirmed Laszlo upgrading. The job stopped in review without replay.
Total confirmed deposits were 1,400,850. Private receipts remain in the guest.

Response identity now follows the same scene, root, manager, typed building and
typed guard keys. UI addresses can change after submission. Native capture
independently validates the current owned roster and now explicitly requires
the selected entry pointer to equal the matched roster row's entry. A detached
copy with the same key is rejected. The host journal mirrors native confirmation.

A replacement response can complete only while the original transaction is
pending, before its original deadline, with the guard page frontmost before and
after, the same quoted cost, exact debit, and visible upgrade progress or one
rank increment. A changed UI with incomplete evidence still stops. Pre-spend
snapshot equality remains strict. Reopened-page ownership, producer/lifetime
checks, immutable submission receipts and single-shot Upgrade are unchanged.
Existing unresolved actions cannot be cleared or replayed.

Validation: 185 focused host tests, native guard controller/channel and owned
navigation-reader tests, and changed-file lint pass. Native and host regressions
cover all 16 combinations of rebuilt building HUD, guard HUD, roster entry and
controls for both progress and rank completion. Rejection tests cover wrong
stable identities, detached selection, front-page mismatch, wrong cost/debit,
missing progress, invalid capture, uncertainty and deadline expiry.

Active todo: exact-source packaging and guest preparation, then game closure
for activation. Nothing from this version is installed yet. Next: fresh live
qualification, rank/gold stopping, outer coverage and integration review.
Full-town and maximum-rank completion remain unverified.
