# First-open and Gold selection correction: 1.8.14 / 0.3.23

Branch: codex/guard-upgrades. Review destination: codex/vendor-rolling, then
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

Next: exact-source package and installed-contract validation, guest staging and
dry-run, then activation after game closure. Live discovery, automatic funding,
maximum-rank proof, full-town coverage and integration remain unfinished.
