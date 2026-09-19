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

Exact source 33229a02ef7aeeebfc284b4be3d41074ef16936f is pushed to
origin/codex/guard-upgrades. Its package passed 2,754 host tests (19 skipped),
lint, both native profiles' required builds/suites, movement IPC, prepared-client
bindings and installed-host contracts. Six additional installed guard/funding
wire checks passed. All 61 artifact hashes and the archive digest were checked.
The two previously known graphics transparency stretch diagnostics still fail
in each profile and remain recorded; no complete graphics acceptance is claimed.

Full extension SHA-256:
b01624be5bd98e935cb4eb7244cf3fad5e703292547ffeab548047f8dc2728be.
Host wheel SHA-256:
ae58e8158054d06121ce4ee154d6d9e85d0870a7fe22409f45218b5b79267bc8.
Diagnostic archive SHA-256:
1aecbbe485ceeab912d036935d32d47aed521922fdaed0859db4fc957c15d181.

Guest preparation and read-only update validation passed. After user-confirmed
closure, native 1.8.20 / host 0.3.30 was installed and verified. Only the extension
changed in the client inventory; the executable is unchanged. Backups are retained.
All 2,215 checked journal, settings and evidence records are unchanged after
manager restart. The dashboard shortcut uses host 0.3.30; Vendor Test remains
the same shortcut. The manager is healthy with no game bound. The user launches
the game; no Ulmer visit or menu setup is required.

Active todo: verify a fresh user-launched game and uninterrupted live upgrades.
Retain the stopped requests without replay. Next: rank/gold stopping, outer
coverage and integration review.
Full-town and maximum-rank completion remain unverified.

## Live qualification on client 1.3.38.9

The 1.8.20 owned-response behavior is included in native 1.8.21 / host 0.3.31,
source 7d38916. After the official client update and fresh Poley login, a new
carried-gold job confirmed 22 upgrades with exact debits. Two completions kept
the guard page while both the building HUD and selected entry were rebuilt;
20 used the verified reopen path. No uncertain action occurred at this checkpoint.
[Current client/run handoff](../client-update-20260919.md) records the deployment
and active job. The original uncertain requests remain retained without replay.
The new run continues; full-town coverage, rank/gold stopping and integration
remain the next work.
