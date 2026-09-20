# Guard travel controls

Installed in the test VM from `codex/guard-upgrades`; safe Travel is live-verified.
Continue here after moving remains pending.
Integration destination: `codex/vendor-rolling`, then
`codex/native-lifecycle-hardening`, then reviewed `main`.

Travel and Continue here live in the manager dashboard, with no game overlay.
Travel completes and accounts for the current funding cycle before displaying
Safe to move. Continue here scans fresh building rosters, opens personal menus
only for newly discovered guards, and extends the same durable job. Guards outside
the current scan remain remembered but are not scheduled. New guards have priority;
known guards retain rank floors, timers, upgrade counts, and confirmed gold totals.
An area without remaining offers returns to Travel; it does not claim maximum rank.

Each area retains immutable discovery digests and exact process/scene ownership.
Worker restarts preserve this progress. This does not import progress into a new
game lifetime: original scene pointers and native receipts must not be rebound.
The upgraded manager requires the matching travel-capable worker. Uncertain
requests remain blocked; Travel cannot clear the existing live navigation failure.

Validation: focused scheduler, discovery, dashboard, and worker tests cover safe
transaction boundaries, area merging, new guard priority, retained rank timers,
wrong-scene rejection, and guard-menu skipping from a fresh owned roster.

Next: the user moves to another area, then verify Continue here preserves the
same job and remembered guards.
The installed client is 1.8.22 / host 0.3.32; the prior failed request and all
174 confirmed first-pass upgrade records remain untouched.

## Navigation lease regression

The heartbeat/clock race is reproduced: renewing the shared heartbeat after the
caller's clock sample makes the previous HostLeaseIsActive return false for an
otherwise current host. The regression fails on the old implementation and passes
with an additional clock sample after observing a newer heartbeat. Expired and
actually future heartbeats, and wrong host generations, still fail. All six native
movement/vendor/city/navigation/guard/funding channel tests pass. The retained live
error does not uniquely prove this was its cause; no historical receipt is invented.

Release versions for packaging: native 1.8.22 / host 0.3.32. Installation requires
closing the game. The 174 prior upgrade receipts remain archived; the new lifetime
requires fresh guard verification once. Subsequent Travel scans in that lifetime
reuse remembered guards and do not restart the completed pass.

## Verified package and VM staging

Release source: `cd8c8a8d41a696817daf2ade6e676d264637d09e` (pushed), including
travel checkpoint `f28eb21` and lease fix `68a9e23`. Host 0.3.32 / native 1.8.22.
The exact committed package passes 2,775 Python tests (18 environment-dependent
skips), Ruff, required native checks in both profiles, IPC/binding checks, installed
entry points, and six additional installed guard wire-contract checks. The two
pre-existing optional graphics transparency diagnostics still fail in each profile;
they remain recorded diagnostic limitations, not claimed fixed by this update.

Package archive SHA-256:
`3195ad4496a3929718fa4f603f76f57c930376874afbb02c3a80d6c489f1036a`.
Full DLL SHA-256:
`740db74bc52451187d5aed383096467f944ae84bc8087936ba0b4d3df3e30f5f`.
Wheel SHA-256:
`92ac4ede7a872c8ff5e8216df8c486cfb70c8a172f721fc080f159891347e393`.

VM staging and exact-baseline validation passed. Only the extension changes in the
client inventory; the current official executable and assets remain unchanged.
The manager host is staged separately. No running component has been replaced and
no gold action was issued. Existing settings, receipts and journals remain retained.
The current stopped job still reports 174 upgrades and 24,868,800 confirmed gold
spent. User closure has been requested because the extension is loaded by the game.
Normal checkout remains on main; this lane awaits integration via vendor-rolling.

## Activation verified

The user closed the game. Its original process remained alive without a window;
its exact executable, process lifetime and absent window were verified before
ending that leftover process. The previous manager and worker had already exited.
The staged update applied successfully with five rollback files. All 5,578 retained
record/settings files matched their pre-update hashes, including old uncertain
requests. No spending or navigation request was replayed.

Installed native DLL, prepared executable, source identity and host 0.3.32 match
the verified package. The manager restarted hidden and its authenticated dashboard
serves Travel and Continue here. The existing WonderBane Vendor Test shortcut still
points to the same updated launcher. The game was not automatically launched.
The user has been asked to log Poley into town; loaded-module/worker checks and
live travel acceptance remain next. This is installation verification, not a claim
that guard maximum rank or full-town coverage has been achieved.

## Live discovery and safe Travel verified

Poley is verified in the updated client; the loaded extension reports 1.8.22 and
the healthy worker advertises the travel-capable protocol. The first discovery
cancelled after 21 guards because a dispatch permit expired. All 44 window attempts
were terminal and the journal was idle; no gold moved. That operation remains
retained. A new read-only discovery was admitted after those checks. A 40-second
permit watch observed continuous renewal; the original interruption's cause is
not proven or claimed fixed.

The new discovery completed its candidate pass: 174 guards, 31 verified building
rosters, 60 candidates, and 379 terminal window attempts. Coverage is partial;
this is not a full-town census. A new carried-gold job started from that exact plan.
Travel was requested while its first cycle was active. The cycle confirmed that
the guard was already upgrading at observed rank 3, recorded its wait timer, and
then paused. The dashboard reports Safe to move; the active cycle and operation
are empty, and the spending journal is idle. No gold was spent in this new job.

All 174 guard records remain in the same job. The user has been asked to move
Poley toward another area; Continue here and new-area merging are the remaining
live acceptance steps. No historical request was cleared or replayed.
