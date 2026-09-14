# Vendor manager host 0.3.10

Branch: `codex/vendor-rolling`. Integration destination:
`codex/native-lifecycle-hardening`, followed by reviewed `main`. Unmerged.
The normal checkout remains on `main`; continue in the existing vendor worktree.

## Launch correction

The client can append to `Logs/crash.txt` after a crash. Launch verification
previously treated that change as immutable package drift and blocked restart.
The runtime policy now permits exactly that client-written log path, alongside
the existing reviewed runtime files. Executable, DLL, unrelated log and nested
path checks remain strict. The log is preserved; baseline evidence is unchanged.

The regression reproduces a changed baseline crash log, verifies launch
acceptance and preservation, and rejects a neighboring DLL and changed game
executable. The focused package/policy tests passed (21 tests, 6 subtests).
Full host validation passed 2163 tests and 582 subtests, with 15 skips.
Ruff and diff whitespace checks passed. Native 1.8.2 is unchanged.

## Delivery and next steps

This commit is the package source checkpoint. Package and install host 0.3.10,
update the test launcher's verifier to that host, and preserve current settings
on relaunch. Then bind the prepared crafting trace to the fresh game lifetime.
No failed crafting journal is replayed or cleared.

The 0.3.9 focus wait was observed, but its first Create remained unconfirmed.
That outcome is separate from this launch correction. See the
[prior handoff](vendor-manager-0.3.9.md) for the retained failure evidence.
Full affix coverage, native window opening, inventory/resource limits and
automatic disposal remain unfinished.
