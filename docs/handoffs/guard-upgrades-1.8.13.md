# Chat window ordering: 1.8.13 / 0.3.22

Branch: codex/guard-upgrades. Exact packaged source: 3b05f0b (pushed).
Review destination: codex/vendor-rolling, then
codex/native-lifecycle-hardening and reviewed main. Not merged. The normal main
checkout is untouched. This version retains the warehouse return ownership fix.

## Live finding and correction

The return test submitted one tower-menu open. Its complete owned roster arrived,
but an ArcChannelHud chat window stayed at the head of the active HUD list. The
old front-window test therefore never confirmed the menu and retained an
unresolved request. No warehouse return, gold transfer or upgrade was submitted.
That request remains blocked; it must not be cleared or replayed.

The shared native ordering rule now selects the first non-chat HUD for direct
native transaction checks. Only the exact reviewed ArcChannelHud class is skipped.
Every other class, including unknown HUDs, amount dialogs and confirmation
windows, still blocks a transaction behind it. All list nodes and ownership are
still validated, including chat nodes. Navigation, guard upgrades, funding and
vendor actions use the same rule; the guard reader reuses its validated navigation
snapshot instead of rereading the raw list head. The scene, foreground, request
lease, range, exact source, quote, reserve and spending-journal checks remain.
No wire layout changed. A chat-only list cannot qualify a transaction.

## Validation and next work

The full native library compiled. Focused navigation/guard, funding and vendor
capture tests passed for chat before the target, amount/unknown windows blocking
and malformed chat-list links. Version consistency tests and source lint passed.
Exact-source packaging passed 2,674 host tests (19 skipped), required native
checks for both profiles, reviewed executable binding, real IPC, installed host
entry-point/panel checks and native/host contracts. Six extra installed guard
funding/upgrade comparisons passed. All 61 artifact hashes and the package
archive were independently verified. The same two pre-existing stretch graphics
diagnostics remain unresolved in each profile; no whole-product acceptance is
claimed.

Guest preparation and read-only update validation passed. After confirmed game
closure, the exact idle test manager was stopped and the staged update applied.
All 120 retained records/settings were unchanged; rollback copies are local.
The existing dashboard shortcut now uses host 0.3.22 and the same game shortcut
launched the verified full 1.8.13 extension. Loaded module version/hash, installed
host source, matching read-only action-channel identity and healthy guard-capable
manager checks passed. No game action was submitted during activation. Earlier
unresolved requests remain retained without reset or replay.

Automatic tower/warehouse/resources return subsequently passed with exact native
receipts. Discovery exposed uninitialized City Command mode before first open.
A bounded guard funding qualification reached the fresh quote and warehouse
return, then stopped before withdrawal because Gold had not yet enabled Withdraw.
No transfer or upgrade was submitted; the uncertain opening request stays blocked.
See [the combined correction and active todos](guard-upgrades-1.8.14.md).
