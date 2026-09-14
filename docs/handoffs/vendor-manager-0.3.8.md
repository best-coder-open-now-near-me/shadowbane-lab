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
uninterrupted crafting batch by themselves. The subsequent real batch is qualified below.

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

## Uninterrupted batch qualification

After a fresh desktop launch, the exact new game lifetime and manager binding
were verified. Opening the dashboard took foreground focus; the owner returned
focus to the game with the selected random Gilded Scepter recipe open. One
manager Start filled all three observed free production slots.

The owner opened the same vendor's Inventory and left the game in front.
The existing job cooked and automatically kept all three items. Every Create
has an observed receipt; every Keep has an observed-in-inventory receipt.
An independent native inventory read found all three exact batch items and
all production slots empty. The manager reported complete, created 3, kept 3,
excluded 0, with no active or queued operation.

The operation ledger for this fresh game instance contains exactly one vendor
Start, succeeded, and zero vendor Resume operations. No job/journal was repaired,
no item was discarded, and no replacement batch was started. All three
decisions preserved unknown affixes. This qualifies one uninterrupted batch on
host 0.3.8; it does not prove that the earlier intermittent dispatch failure
cannot recur or establish its original cause.

The private verifier and receipt are, respectively,
`verify-uninterrupted-0.3.8.py` in the existing VM diagnostics share and
`vendor-manager/uninterrupted-batch-0.3.8.json` in the test runtime.
The receipt was recorded at 2026-09-14T16:34:04Z, with 563.6 seconds elapsed
since the host job began. No raw item IDs or process/window addresses are published.

## Operator entry points

The test VM desktop has **WonderBane Vendor Test** for the native 1.8.2 game
and **WonderBane Vendor Dashboard** for the installed 0.3.8 manager. The dashboard
opener starts the manager if absent or opens the existing authenticated page.
A restarted game receives a fresh binding; old process IDs must not be reused.

Current limitation: native crafting requires the game in front and the selected
vendor window ready. The dashboard can take foreground focus, and native
recipe/inventory opening is not automated yet. The qualified batch used a
programmatic manager Start after focus was restored; this is not qualification
of a seamless browser-click-to-game-focus handoff.

## Active todo

Complete: one uninterrupted capacity batch with all Create/Keep receipts and
independent inventory confirmation.

Active: production window/focus handling so dashboard actions do not require
a manual foreground handoff. Then qualify native recipe/inventory opening,
inventory/resource limits, full affix evidence and low-tier identity coverage,
and discard. No unlimited refill or automatic Junk is enabled. Preserve unknowns
and retain first-cause cancellation evidence if the earlier interruption recurs.
