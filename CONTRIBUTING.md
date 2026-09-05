# Contributing

## Choose the right starting point

`main` is the shared merge destination. See [the branch map](docs/git-branch-map.md)
for the pending consolidated development candidate and later work outside it.
Check that a needed feature is present before starting from an older release.

From a clean checkout, refresh references before inspecting or branching:

```powershell
git status --short --branch
git fetch origin --prune
git branch --show-current
git worktree list
```

For normal work after the consolidated candidate is merged:

```powershell
git switch main
git pull --ff-only
git switch -c codex/describe-the-change
```

While the candidate is awaiting review, dependent work can use
`origin/codex/native-lifecycle-hardening` as an explicit base. Record that
dependency in its PR. Never assume the currently checked-out topic is current.

## Keep independent tasks in separate checkouts

Local Codex tasks share the branch of their project directory. Use a worktree
when another task must retain its checkout. A branch can be checked out in only
one worktree at a time:

```powershell
git worktree add -b codex/describe-the-change .worktrees/describe-the-change origin/main
```

Use the pending integration ref instead of `origin/main` above when the change
depends on that candidate. Do not force a branch checkout or switch a directory
another task is modifying. After delivery, leave the normal project directory on
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
On the consolidated candidate these include Ruff, Python 3.11/3.12/3.13 tests,
both Win32 native profiles, and PowerShell syntax validation. Existing CI results
certify their exact commit only.

## Find apparently missing work

```powershell
git fetch origin --prune
git branch -a --contains <commit-sha>
git log --all --oneline -- path/to/file
git log origin/main..origin/codex/native-lifecycle-hardening --oneline
git rev-list --left-right --count origin/main...origin/codex/native-lifecycle-hardening
```

A branch being pushed does not mean it was merged into `main`. Compare ancestry
before replacing a newer tree with an older feature branch. Uncommitted drafts
cannot be retrieved from GitHub: publish reviewed source drafts with explicit
unfinished status, and keep private evidence out of source commits.

Store local scratch files and captures under ignored `artifacts/`; keep useful
source in its owning module. Never use a blanket clean, hard reset, force push,
or bulk branch deletion to hide unfinished work. Verify retained remote ancestry
and preserve dirty files before retiring a checkout.
