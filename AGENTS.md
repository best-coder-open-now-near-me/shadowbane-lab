# Project delivery instructions

## Deployment policy: no retained rollback artifacts

The user's explicit September 26, 2026 policy is mandatory: **do not create or
retain deployment rollback copies or archives, keep old runtimes for rollback,
or require rollback disk space before an update.** Recover software by rebuilding
from the exact committed Git revision and official client assets. Preserve user
settings, saved jobs and historical journals in place; these are not disposable
build output. Do not introduce backup/rollback gates that override this policy.

Read [the deployment policy](docs/deployment-policy.md) before preparing or
updating a runtime. It supersedes older backup/rollback instructions in handoffs,
deployment notes and carried-forward context. Native test rollback, transaction
reconciliation and fail-closed readiness checks still apply; those semantics do
not authorize retaining deployment fallback artifacts.

## Standing bot merge and installation approval

On October 2, 2026, the user said "always approved" in response to the bot
merge/install gate. Routine PvE/PvP/buff-workflow merges and installation of the
qualified runtime are authorized once the required reviews and checks pass.
Do not repeatedly ask for per-PR merge/install approval in this workflow.
Continue to verify the final PR head, exact package identity, fresh deployment
baseline and preserved user data. Ask only for genuinely missing input or actions
outside the authorized scope; this approval does not waive validation or authorize
unrelated destructive changes. Newer explicit user instructions take precedence.

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

## Private-server small updates

On October 7, 2026, the user authorized quick normal server restarts for small,
already-authorized private-server changes. After validation, use a prompt
graceful restart without an extra five-minute idle hold or another permission
prompt for that scope. Preserve existing saved data and settings, keep private
network restrictions, verify the deployed result, and remove superseded runtime
artifacts. This supersedes the earlier idle-window maintenance procedure.
