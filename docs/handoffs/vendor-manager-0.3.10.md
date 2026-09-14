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

Installed source: `1aee8d5ea684b215d70e2311387e5a139ee159c9`.
Wheel SHA-256:
`835bc7e05546a8b76f4577d6e7a8b90fe867c1bd7b58023bc9f9506e8c792fd7`.
The installed verifier accepted the real runtime with its changed crash log
preserved. The test launcher now uses host 0.3.10 and retains current client
settings on launch. The dashboard shortcut, manager and worker were also
updated to 0.3.10. A fresh game launched with the exact native 1.8.2 DLL;
installed source identity, worker capability and game binding checks passed.
The new instance has no crafting job. Prior failure journals remain untouched.
Private packages are in `artifacts/vendor-host-0.3.10`; runtime receipts and
crash evidence remain in the existing private VM diagnostics locations.

All seven remote CI jobs passed, including Python 3.11/3.12/3.13, quality,
PowerShell syntax and both native profiles.
Run: https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/34908924352.
Active: wait for the owner to log in and open the random recipe, then arm
the bounded request/reply trace against this fresh game lifetime.

The 0.3.9 focus wait was observed, but its first Create remained unconfirmed.
That outcome is separate from this launch correction. See the
[prior handoff](vendor-manager-0.3.9.md) for the retained failure evidence.
Full affix coverage, native window opening, inventory/resource limits and
automatic disposal remain unfinished.
