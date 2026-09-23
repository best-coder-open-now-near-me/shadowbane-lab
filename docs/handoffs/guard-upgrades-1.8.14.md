# First-open and Gold selection correction: 1.8.14 / 0.3.23

Branch: codex/guard-upgrades. Exact packaged source: dcc33bc (pushed).
Review destination: codex/vendor-rolling, then
codex/native-lifecycle-hardening and reviewed main. Not merged. The normal main
checkout remains untouched.

## Live qualification and findings

On 1.8.13, automatic tower opening, warehouse building return and the Seneschal's
View Resources opening all completed with correlated native receipts. Warehouse
return ownership and chat ordering are now live-qualified.

Manager guard discovery stopped before opening City Command: the reviewed
constructor leaves mode uninitialized while its HUD is absent. A bounded funding
qualification reached a fresh guard quote and returned to resources, then stopped
before withdrawal because Withdraw remains disabled until Gold is selected.
No gold transfer or upgrade was submitted. Its unresolved quote-opening request
remains retained and blocked, alongside earlier uncertain requests.

## Correction

A closed City Command manager reports zero mode/count/loading; only an owned
existing HUD publishes mode and roster count. Existing-HUD validity, full list
validation and lifetime checks remain strict.

Warehouse opening permits only the normal disabled Withdraw state before Gold
selection. The exact owned, visible, enabled Gold row and its action are checked
before invoking the ordinary selection callback. Afterward the native reader
requires exactly that selected entry and an enabled Withdraw button. The callback's
event-consumption return value is not a selection receipt. Hidden, malformed,
wrong-action and still-disabled controls fail closed. Deposit never admits a
disabled button. Transfer amounts, reserve checks, balance correlation and the
shared immutable spending journal are unchanged. No wire layout changed.

## Validation and active todo

The full native extension compiled. Focused native regression tests passed for
closed/uninitialized City Command state, invalid open state, initial disabled
Withdraw, selection returning false with valid postconditions, wrong selection,
still-disabled Withdraw and disabled deposit. Five version tests and lint passed.

Exact-source packaging passed 2,675 host tests (18 skipped), required native
checks for both profiles, reviewed executable binding, real IPC and installed
host checks. Six extra installed guard/funding comparisons passed. All 61
artifact hashes and the package archive were independently verified. The same
two pre-existing graphics transparency diagnostics fail in each profile and
remain recorded; this is not whole-product acceptance.

Guest preparation and read-only update validation passed. After confirmed game
closure, the exact idle test manager was stopped and the staged update applied.
All 143 retained records/settings were unchanged; rollback files remain local.
The existing dashboard shortcut now uses host 0.3.23, and the same game shortcut
launched the verified full 1.8.14 extension. Loaded version/hash, installed source,
fresh process identity, read-only action mapping and healthy guard-capable manager
were verified. No game action was submitted during activation. Historical
journals, including the unresolved quote opening, remain retained without replay.

Active todo: user login beside the Seneschal and initial View Resources opening,
then qualify discovery and automatic funding in the fresh session. Maximum-rank proof, full-town coverage and integration
remain unfinished. No automatic gold transfer or upgrade has yet been qualified.

## Relaunch and obsolete runtime cleanup

A later relaunch failed before game startup because the test VM disk was full.
The user explicitly requested deleting the eleven obsolete host environments
(0.3.11 through 0.3.21), without archiving compiled programs. Those environments
are removed; current 0.3.23 and immediate rollback 0.3.22 remain. Game data,
settings and historical transaction journals were not deleted. About 200 MiB
became available, and the same reviewed launcher then started successfully.

The loaded 1.8.14 extension, host 0.3.23 source, new exact game-process identity
and healthy guard-capable worker were verified again. The game is awaiting login;
no guard action or gold transfer was submitted. The next todo remains login and
View Resources, followed by discovery and automatic funding qualification.

## Subsequent live discovery

The fresh warehouse building/resources round trip passed. City Command opened
and returned 60 nearby structures, qualifying the initial closed-state fix.
Discovery stopped on the Tree of Life's companion guild panel after its complete
hireling roster arrived. No gold moved; the unresolved navigation request remains
blocked. Continue with [the Tree companion correction](guard-upgrades-1.8.15.md).
