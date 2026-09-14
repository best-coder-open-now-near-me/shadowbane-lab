# Vendor manager host 0.3.9

Feature branch: `codex/vendor-rolling`; integration destination:
`codex/native-lifecycle-hardening`, followed by reviewed `main`. Unmerged.
The normal checkout remains on `main`; continue vendor work in its existing worktree.

## Focus handoff

Start accepts the exact owned random Gilded Scepter recipe while the dashboard
has foreground focus. The durable job waits visibly for the game/vendor window
to become ready before submitting a crafting action. Switching away between
actions returns it to that wait; returning to the game continues the same job.
Stop, lost dispatch permission, changed ownership and the one-hour deadline
still prevent further submissions.

An already-submitted Create or Keep is reconciled against its exact request
and queue/inventory transition even while unfocused. Only correlated receipts
without in-flight or unresolved flags are accepted. No mutation is retried.
The game window is not automatically opened or focused; recipe and Inventory
opening remain manual. One job still fills one capacity batch, with no refill
or automatic disposal. Unknown affixes remain preserved.

## Validation and deployment

Local validation: 2163 host tests and 580 subtests passed, with 14 explicit
environment skips. Ruff and whitespace checks passed. Regression coverage
includes starting unfocused, focus loss after Create and Keep, receipt
reconciliation before waiting, and Stop/owner/deadline/permit changes while waiting.

Source checkpoint: this commit. Packaging, installation and the live dashboard
handoff check are next. The currently installed host remains 0.3.8 until its
replacement is recorded here. Native 1.8.2 is unchanged.
See [previous installed handoff](vendor-manager-0.3.8.md) for its exact package
and uninterrupted three-item batch evidence.

## Remaining work

Active: install and qualify the focus handoff in the test VM.
Then qualify native recipe/inventory opening, inventory/resource limits,
full affix evidence and Tier 1/2 identity coverage, and discard.
Private package artifacts stay in `artifacts/vendor-host-0.3.9`; installation
receipts stay in the existing private VM diagnostics/runtime directories.
