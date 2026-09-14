# Vendor manager host 0.3.8

Installed source: `5c7ccfebbf639992e1da7a3f92fbead48023f4f5`.
Feature branch: `codex/vendor-rolling`; integration destination:
`codex/native-lifecycle-hardening`, followed by reviewed `main`. Unmerged.
The normal checkout remains on `main`; continue vendor work in its existing worktree.

## Installed behavior

Host 0.3.7 first deployed the bounded read-only inspection retry from `bdac6ee`.
Host 0.3.8 retains that correction and records the first cancellation cause in
the terminal worker operation receipt. Missing, denied, expired, wrong-identity
and unreadable permits, inbox errors and explicit Stop/Cancel remain distinct.
The first cause survives concurrent checks and later recovery; dispatch rules
and mutation replay restrictions are unchanged.

The exact test manager and worker passed installed identity/capability checks.
The native 1.8.2 client stayed running throughout both host upgrades. The prior
manager batch remains complete with three items independently confirmed in
inventory and empty production. No new batch was started during installation.

Two bounded passive checks exercised 1486 concurrent cancellation checks.
The second also completed 122 native inspections with no transport rejection
or inspection error. Neither probe stopped or sent a crafting command. This
does not identify the earlier intermittent cancellation or qualify an
uninterrupted crafting batch. The next real batch awaits the open random recipe.

## Package and validation

Wheel SHA-256:
`01a2c6ec9de8f0cb1abc0716c518af7b787f73329b00be8898c625c35e8301fb`.

The exact-commit archive embeds the installed source identity. Full local host
validation passed 2159 tests and 576 subtests, with 14 explicit environment skips.
Ruff and whitespace checks passed. Focused tests verify first-cause retention,
fresh strict permit checks, durable cancellation reasons, and vendor behavior.
All seven remote CI jobs for installed source `5c7ccfe` passed, including
Python 3.11/3.12/3.13, both native profiles, quality and PowerShell syntax.
Run: https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/34862945306.

Private exact-source packages remain in `artifacts/vendor-host-0.3.7` and
`artifacts/vendor-host-0.3.8` under the task worktree. VM installation and passive
check receipts remain in the existing private diagnostics/runtime locations
documented by [the previous handoff](vendor-manager-0.3.6.md). No captures,
credentials, dashboard token or client binaries are published.

## Active todo

Qualify one uninterrupted manager batch, using fresh observed free capacity,
and use the saved cancellation reason to diagnose any interruption.
The selected vendor's random recipe must be open before Start; the owner's
Inventory must be visible before automatic Keep. No unlimited refill or automatic
Junk is enabled. Later work: native window opening, inventory/resource limits,
full affix evidence and low-tier identity coverage, then discard qualification.
