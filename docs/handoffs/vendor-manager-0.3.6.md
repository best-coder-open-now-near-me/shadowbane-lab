# Vendor manager host 0.3.6

Installed source: `4a5a9b071fbeb734b130e3220eb87fe38b44f68f`.
Feature branch: `codex/vendor-rolling`.
Integration destination: `codex/native-lifecycle-hardening`, followed by reviewed
`main`. The feature remains unmerged; continue vendor work in its existing worktree.
The normal shared checkout remains on `main`.

## Installed behavior and live qualification

The separate test manager and exact worker run host 0.3.6. Native 1.8.2 from
`8aad37f` stayed running throughout the host upgrades.

The authorized first manager batch filled all three available production slots.
Each Create has an observed receipt, and an independent queue read confirmed
three distinct batch items cooking. Live Pause changed the job to paused; Resume
returned that same job to cooking, with three items and no replacement batch.
The owner opened the vendor Inventory. Completion then stopped on a read-only
inspection: the retained native error was `invalid_or_expired_vendor_lease`,
stage FAILED, error 13. The job was in its waiting phase with complete Create
receipts and no Keep journal. Fresh native inspection confirmed the same owner,
all three completed batch items, visible inventory and READY without pending or
unresolved actions. The original job and fresh snapshot were preserved privately
before explicitly returning this reviewed job to a resumable state.

That Resume reached Keep preparation but cancelled before its first request.
The saved Keep journal contained zero requests, kept items or exclusions. A
150-sample passive permit/operation-ledger diagnostic found no current failures;
the precise dispatch interruption remains unproven. After another fresh owner
and item check, the empty cancelled journal was archived beside its original
job evidence. No nonempty mutation journal was replayed or removed.

The next Resume completed all three automatic Keeps. An independent inventory
read found all three batch items and all production slots empty; manager status
reported complete, created 3, kept 3, excluded 0, with no active operation.
This qualifies manager Create, Pause/Resume and Keep with reviewed recovery.
It does not qualify an uninterrupted unattended batch.

The job fills current capacity once, accommodates rank growth while filling,
waits for cooking and owned inventory, and preserves unknown affixes. Actions
remain bound to the exact client, current job, vendor and current dispatch permit.
Incomplete or uncertain journals require review and cannot be blindly replayed.
Automatic disposal and recurring replacement batches remain disabled.

## Package and validation

Wheel SHA-256:
`9c12ac2baa84e2e12147046052f304c1e331ab38ed4708eb1e52009bc9b952e1`.

The wheel was built from the exact source archive with embedded identity.
Installed identity and manager/worker capability checks passed. Three targeted
regressions also passed inside the test VM, covering long Windows job paths,
transient permit reads and permit expiry after a read retry.

The full local host suite passed 2153 tests and 571 subtests, with 14 explicit
environment skips for symlink privilege and unbound native movement fixtures.
Ruff and whitespace checks passed. Earlier dashboard syntax/layout validation
remains applicable; native files did not change.

The first 0.3.6 remote run failed only the deep-path test's cleanup containment
assertion. The store resolved the Windows temporary directory, while the test
compared it to an unresolved alias. Test-only commit `48fe2f4` resolves both sides;
all 13 vendor job tests and two subtests passed locally. The remote Python checks
subsequently passed on 3.11, 3.12 and 3.13; all seven CI jobs for `48fe2f4` passed.
This does not change the installed host artifact.

See the [prior handoff](vendor-manager-0.3.4.md) for the two diagnosed pre-action
failures and their corrections. Both failed starts were independently confirmed
to have created no items before retrying.

## Evidence and remaining work

Private package archives/builds remain under the task worktree's
`artifacts/vendor-host-0.3.4`, `vendor-host-0.3.5` and `vendor-host-0.3.6`.
VM helpers and installation evidence remain under the private
`E:\virtual-machines\shadowbane-testing\diagnostics\vendor-1.8.2-8aad37f`
directory; live job receipts/logs stay in the test runtime's `vendor-manager`.
Credentials, dashboard token, raw captures and client binaries are not published.

Host 0.3.7 source now bounds read-only inspection retries to three attempts for
a transport timeout or the exact failed expired-lease response. Every attempt
uses fresh command/request identities and all existing native correlation checks.
Create/Keep and mismatched, contradictory or unknown-service responses are never
retried. Failure messages preserve native stage/error/detail for diagnosis.
The full 0.3.7 host suite passed 2156 tests and 576 subtests, with the same
14 environment skips; whole-tree Ruff and whitespace checks passed.
The installed runtime remains 0.3.6; this source correction is not yet deployed.

Active: deploy the inspection correction and diagnose the separate dispatch
interruption before uninterrupted manager acceptance.
Next: native recipe/inventory opening, complete affix evidence and low-tier
identity coverage, inventory/resource capacity, and live discard qualification.
No unlimited run is enabled by the one-batch authorization.
