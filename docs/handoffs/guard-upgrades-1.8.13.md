# Chat window ordering: 1.8.13 / 0.3.22

Branch: codex/guard-upgrades. Exact packaged source: 3b05f0b (pushed).
Review destination: codex/vendor-rolling, then
codex/native-lifecycle-hardening and reviewed main. Not merged. The normal main
checkout is untouched. Installed 1.8.12 / 0.3.21 retains the warehouse return fix.

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

Guest preparation and read-only update validation passed. The full extension and
host package are staged separately; installed 1.8.12 / 0.3.21 and its unresolved
request remain unchanged. The updater preserves all historical worker JSON,
settings and qualification records, with rollback copies on activation.

Active todo: await confirmed game closure, then activate the verified update.
Then qualify automatic tower/warehouse/resources return, followed by live guard
funding and upgrades. Maximum-rank proof, full-town coverage and integration are
unfinished. The earlier unresolved action remains retained through deployment.
