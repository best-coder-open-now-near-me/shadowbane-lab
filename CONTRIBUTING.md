# Contributing

## Choose the right starting point

`main` is the canonical development base and shared merge destination.
[PR #25](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/25)
merged the consolidated history as `555f6bf`; start from freshly fetched
`origin/main`. See [the branch map](docs/git-branch-map.md) for deferred source
that remains outside this integration.

From a clean checkout, refresh references before inspecting or branching:

```powershell
git status --short --branch
git fetch origin --prune
git branch --show-current
git worktree list
```

For normal work from a clean checkout not owned by another active task:

```powershell
git switch main
git pull --ff-only
git switch -c codex/describe-the-change
```

The [integration inventory](docs/integration-status-20260923.md) records included
and deferred source; the [catch-up plan](docs/catch-up-plan-20260923.md) assigns
parallel ownership. Older feature and integration branches are historical
references, not the default base. Never assume a checked-out topic is current.

## Keep independent tasks in separate checkouts

Local Codex tasks share the branch of their project directory. Use a worktree
when another task must retain its checkout. A branch can be checked out in only
one worktree at a time:

```powershell
git worktree add -b codex/describe-the-change .worktrees/describe-the-change origin/main
```

Use another base only for an explicit, documented dependency. Do not force a
branch checkout or switch a directory another task is modifying. After delivery, leave the normal project directory on
`main` when clean; the task branch and its remote PR retain the work.

## Deliver a complete handoff

Commit coherent, validated slices and push with upstream tracking:

```powershell
git add -- path/to/changed-file
git diff --staged
git diff --staged --check
git commit -m "Describe the resulting behavior"
git push -u origin HEAD
```

Open a PR targeting `main`, or identify its explicit pending dependency. Include
the exact source SHA, included and excluded work, validation results, and remaining
acceptance checks. Publishing source does not update an installed client or VM.

Use `.github/workflows/ci.yml` for the current shared validation requirements.
These include Ruff, Python 3.11/3.12/3.13 tests, both Win32 native profiles, PowerShell syntax validation, and the duel matrix.
Main protection requires these eight GitHub Actions check contexts and an
up-to-date branch, including for administrators. Changes go through a PR with
resolved conversations; no mandatory approving-review count has been added.
Force pushes and branch deletion are disabled. Existing CI results certify
their exact commit only.

## Find apparently missing work

```powershell
git fetch origin --prune
git branch -a --contains <commit-sha>
git log --all --oneline -- path/to/file
git log origin/main..origin/codex/feature-branch --oneline
git rev-list --left-right --count origin/main...origin/codex/feature-branch
```

Replace `codex/feature-branch` with the actual branch being investigated.
A branch being pushed does not mean it was merged into `main`. Compare ancestry
before replacing a newer tree with an older feature branch. Uncommitted drafts
cannot be retrieved from GitHub: publish reviewed source drafts with explicit
unfinished status, and keep private evidence out of source commits.

Store local scratch files and captures under ignored `artifacts/`; keep useful
source in its owning module. Never use a blanket clean, hard reset, force push,
or bulk branch deletion to hide unfinished work. Verify retained remote ancestry
and preserve dirty files before retiring a checkout.


The shared native suites require the cue's visible native-material gate and the
effects runtime suppression tests. Run required native tests with
`ctest --test-dir build/native-full -C Release -LE stretch-diagnostic --output-on-failure`.
Run `python scripts/check_transparency_diagnostics.py --build-dir build/native-full`
for the deferred diagnostics, and repeat for the diagnostics-only build.
The [diagnostic policy](docs/ci-transparency-diagnostics.md) accepts only reviewed
pixel counterexamples or the exact supported environment skip; additional
failures still fail CI. JUnit and console logs retain the unresolved findings.
These results do not certify visible world glow or particles/trails. The package
builder separately rejects missing/skipped required fallback tests and records
diagnostic findings. Never substitute a diagnostic pass for a required runtime gate.
