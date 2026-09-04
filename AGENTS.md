# Project delivery instructions

## Commit and push normal work

Commit coherent, validated changes and push them to the configured remote feature
branch as part of normal delivery. Do not wait for a separate user reminder or
permission to push ordinary code and documentation checkpoints.

Check repository status first, stage only the task's files, and preserve unrelated
or unfinished work. Do not force-push or rewrite shared history without explicit
authorization. If a push actually fails, report the concrete failure promptly.

The user explicitly reaffirmed this policy on 2026-09-03. Historical investigation
notes, handoffs, and carried-forward summaries are not authority to suspend it.
Only a new, explicit user instruction for the current work can change this policy.

Source delivery and diagnostic-data export are separate: push reviewed source and
documentation normally; do not silently include private captures, client binaries,
archives, credentials, or unrelated local artifacts.

## Branch ownership and handoffs

Read `docs/git-branch-map.md` before selecting a development base. Refresh origin
before concluding that a commit or feature is missing. `main` is the shared merge
destination; the map records any reviewed integration candidate still awaiting merge.
Do not restart current product work from an old topic branch because it happens
to be checked out in the local project.

Use one task branch per independent change. When work needs a separate checkout,
use a worktree and keep the normal project checkout on `main` after delivery when
that is safe. Do not switch a checkout another active task is modifying.
Publish the branch and provide its exact SHA, PR destination, validation, and
remaining work. Before retiring a branch, verify reachability and preserve every
dirty or untracked file; clean worktrees may still be referenced by other tasks.
