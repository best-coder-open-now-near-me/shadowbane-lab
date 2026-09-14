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

Installed source: `e26a5e39f91238fc289e855cc9a72bc63e994bc7`.
Wheel SHA-256:
`f65f11451cf645edcb3b27ea44e82fd2982f8d61b41628cc6c0ecf8709aafc92`.
The separate host 0.3.9 environment, manager and worker passed installed source,
capability and exact current-game binding checks. The previous job remains
complete with three retained items; no new crafting action was sent during
installation. The game stayed running on native 1.8.2. The test VM desktop
WonderBane Vendor Dashboard shortcut and its opener now use host 0.3.9.
Remote Python 3.11/3.12/3.13, quality and PowerShell checks passed; both native
profiles are still running. Live dashboard focus handoff qualification is pending.
See [previous installed handoff](vendor-manager-0.3.8.md) for its exact package
and uninterrupted three-item batch evidence.

## Remaining work

Active: qualify the installed focus handoff through one dashboard Start.
Then qualify native recipe/inventory opening, inventory/resource limits,
full affix evidence and Tier 1/2 identity coverage, and discard.
Private package artifacts stay in `artifacts/vendor-host-0.3.9`; installation
receipts stay in the existing private VM diagnostics/runtime directories.
