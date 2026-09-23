# Integration status - September 23, 2026

## Merged delivery and current base

Start independent product work from freshly fetched `origin/main`.
[PR #25](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/25)
merged on September 23 as `555f6bf8d7609a03c5a4828c56c464879b34d8dd`, preserving
reviewed head `e8062fd67151ad3e3f4eb792be05a34be78a4cb5` and its source ancestry.
All 15 hosted checks for that exact head completed successfully: the seven CI
jobs on both push and pull-request runs, plus the duel matrix. See the
[push CI](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/35911105223),
[pull-request CI](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/35911109603)
and [duel matrix](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/35911109519).
The [main push CI](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/35912650959)
also passed on merge `555f6bf`. Host 0.3.46 activation is separately verified
below; no gameplay acceptance is implied. Later commits need their own checks.

The normal project checkout was fast-forwarded cleanly to `555f6bf`. Main branch
protection was applied and verified through the GitHub API: required contexts
`quality`, `python-tests (3.11)`, `python-tests (3.12)`, `python-tests (3.13)`,
`native-tests (full)`, `native-tests (diagnostics-only)`, `powershell-syntax`, and
`matrix`, bound to GitHub Actions. Branches must be up to date; enforcement also
covers administrators. PRs and resolved conversations are required, with zero
mandatory approving reviewers. Force pushes and branch deletion are disabled;
merge commits remain permitted to preserve ancestry.

The follow-through PR removes only the duel matrix's `pull_request` path filter:
with `matrix` required, documentation-only PRs otherwise never emit that check
and cannot merge. Every PR now schedules it; existing manual and push policies
and the matrix job itself are unchanged. Hosted checks must validate this final
follow-through head before merge.

## Historical reconciliation checkpoint

Checkpoint `688ec7ed15fb4a2ec9cb6933da76675253df8b01` contains product
`74f34a3`, catch-up plan `179f065`, and movement tip `dfa766a` by ancestry.
It supersedes the September 4 PR description/base guidance. The candidate was
fast-forwarded from `f2a5ca1`, preserving every original commit, then movement
history was merged without any change to the `179f065` file tree.

Movement reconciliation reviewed all nine non-patch-equivalent commits plus the
11 equivalent patches and seven merge commits. Current source retains the older
movement implementation plus later reviewed client identities, borrowed lifetime
checks and native owner services. The only merge conflicts were packaging source
lists and required-test checks; the newer guard/Condemn gates were retained.
Focused validation: 179 passed, five environment-dependent skips. Exact combined
host/native/CI validation follows each completed integration checkpoint.

## Inclusion inventory

This is a fetched-ref snapshot at the checkpoint above. Ancestry-only counts do
not assert missing behavior. Patch-equivalent counts exclude merge commits and
can miss semantically equivalent changes. Deferred entries are retained remotely;
this inventory does not authorize their deletion or declare them integrated.
The table predates the new guard/vendor/CI worker deliveries, tracked below.

| Remote branch | Audited tip | Ancestry-only commits | Equivalent patches | Disposition / next step |
| --- | --- | ---: | ---: | --- |
| `codex/catch-up-plan` | `179f065` | 0 | 0 | Included by ancestry; retain refs until review/retirement. |
| `codex/client-convergence-v2` | `031de7e` | 2 | 0 | Deferred terrain/export delivery work; use existing terrain handoff and validate before integration. |
| `codex/client-streaming-telemetry` | `5b3e1ec` | 0 | 0 | Included by ancestry; retain refs until review/retirement. |
| `codex/fix-simulator-foundation-ci` | `ccb5b65` | 0 | 0 | Included by ancestry; retain refs until review/retirement. |
| `codex/guard-upgrades` | `74f34a3` | 0 | 0 | Included by ancestry; retain refs until review/retirement. |
| `codex/initial-simulator` | `5b00217` | 2 | 0 | Preserved historical experiment; review only for a selected simulator task. |
| `codex/integrate-current-development` | `688ec7e` | 0 | 0 | Included by ancestry; retain refs until review/retirement. |
| `codex/legal-build-map-elites-foundation` | `ee5a4c2` | 9 | 0 | Deferred simulator capability delta; reconcile in PR #23 follow-up. |
| `codex/live-entity-identity-bridge` | `8552552` | 10 | 7 | Seven equivalent patches, one introduction/revert pair, and portal capture note; compared identity/population source files are identical. |
| `codex/mod-asset-facade` | `ba95232` | 0 | 0 | Included by ancestry; retain refs until review/retirement. |
| `codex/native-lifecycle-hardening` | `542c632` | 0 | 0 | Included by ancestry; retain refs until review/retirement. |
| `codex/native-movement-controls` | `dfa766a` | 0 | 0 | Included by ancestry; retain refs until review/retirement. |
| `codex/navigation-inspector` | `14d117e` | 0 | 0 | Included by ancestry; retain refs until review/retirement. |
| `codex/particles-trails` | `69d7717` | 8 | 3 | Preserved visual lane; existing integrated fallback stays authoritative; review remaining evidence/source separately. |
| `codex/power-palettes-plan` | `771ade2` | 2 | 0 | Preserved documentation plan; implementation outside current town-workflow scope. |
| `codex/preserve-assassin-sdr-loadout` | `8ad3893` | 4 | 3 | Preserved historical experiment; review only for a selected simulator task. |
| `codex/preserve-elf-druid-kiting` | `66dce87` | 3 | 2 | Preserved historical experiment; review only for a selected simulator task. |
| `codex/pve-target-authority` | `3a605e4` | 0 | 0 | Included by ancestry; retain refs until review/retirement. |
| `codex/renderer-depth-composite-recovery` | `46a295f` | 0 | 0 | Included by ancestry; retain refs until review/retirement. |
| `codex/renderer-sustained-contours` | `bc076d7` | 0 | 0 | Included by ancestry; retain refs until review/retirement. |
| `codex/selected-character-cue` | `808872f` | 15 | 4 | Preserved visual lane; existing integrated fallback stays authoritative; review remaining evidence/source separately. |
| `codex/shadow-mantle-policy-ablation` | `1946e7e` | 3 | 0 | Preserved historical experiment; review only for a selected simulator task. |
| `codex/sky-horizon` | `04224ae` | 1 | 0 | Preserved visual lane; existing integrated fallback stays authoritative; review remaining evidence/source separately. |
| `codex/terrain-material-export-da109b0` | `08fce96` | 17 | 0 | Deferred terrain/export delivery work; use existing terrain handoff and validate before integration. |
| `codex/terrain-material-repair` | `9287c9a` | 33 | 0 | Deferred terrain/export delivery work; use existing terrain handoff and validate before integration. |
| `codex/terrain-material-repair-completion` | `6b88383` | 38 | 0 | Deferred terrain/export delivery work; use existing terrain handoff and validate before integration. |
| `codex/terrain-material-repair-final-v2` | `bc572d4` | 53 | 0 | Deferred terrain/export delivery work; use existing terrain handoff and validate before integration. |
| `codex/terrain-material-repair-implementation` | `da109b0` | 0 | 0 | Included by ancestry; retain refs until review/retirement. |
| `codex/terrain-material-repair-workspace` | `9f2446e` | 7 | 0 | Deferred terrain/export delivery work; use existing terrain handoff and validate before integration. |
| `codex/terrain-repair-snapshot` | `1ac56c6` | 1 | 0 | Deferred terrain/export delivery work; use existing terrain handoff and validate before integration. |
| `codex/texture-cache-read-export` | `0680a76` | 8 | 0 | Deferred terrain/export delivery work; use existing terrain handoff and validate before integration. |
| `codex/vendor-rolling` | `61e6fd8` | 0 | 0 | Included by ancestry; retain refs until review/retirement. |
| `codex/world-map-exact-dispatch` | `e6d5c85` | 10 | 0 | Historical alternate routing lineage; reconcile only through feature-lineage decisions, never wholesale merge. |
| `feat/simulator-foundation` | `23b9a31` | 0 | 0 | Included by ancestry; retain refs until review/retirement. |
| `feat/wonderbane-texture-tools` | `a34fd9f` | 0 | 0 | Included by ancestry; retain refs until review/retirement. |
| `fix/world-map-click-capture` | `1f3de79` | 9 | 0 | Historical alternate routing lineage; reconcile only through feature-lineage decisions, never wholesale merge. |
| `main` | `047147d` | 0 | 0 | Included by ancestry; retain refs until review/retirement. |

## Local-only and unfinished source

- Local `feat/simulator-foundation@66dce87` is three commits ahead of its named
  upstream, but that exact tip is published as `origin/codex/preserve-elf-druid-kiting`.
  It is not stranded local-only work; retained experiment status still applies.
- The existing `client-streaming-telemetry` worktree contains eight modified files
  and `performance_telemetry.cpp.rej`. They are pre-existing unfinished drafts,
  preserved in place, not staged by this task. See the historical branch map's
  private recovery archive. Owner review remains necessary before publication.
- Other pre-existing worktrees were clean during the starting audit. None was
  switched, deleted, or force-updated. Task worktrees are retained for current work.
- Power Palettes and terrain drafts remain discoverable at the remote tips above;
  no client binaries, private captures or credentials enter this integration.

## Integrated catch-up slices

Merged `main` retains these published source tips by merge ancestry:

| Source tip | Delivered behavior | Remaining qualification |
| --- | --- | --- |
| `ef5deeb` guard coverage | Bounded candidate/exception detail, observed guard ranks, selected-building Condemn completion, crash-accounting schedules | Opened Barracks observation, new-area/max-rank/resource outcomes |
| `69f54cf` vendor recovery | Exact Create/Keep source digest, ownership, partition and observed receipt-chain validation before recovery | One historical schema-2 Create validated; authentic historical Keep and live qualification remain open |
| `f0ed883` vendor recorder | Optional read-only `--vendors` workflow mode; strict recipe, roster and Inventory channels | Manual non-spending menu walkthrough; native open/select contract |
| `79505be` CI diagnostics | Narrow expected-pixel-failure classification replaces blanket tolerance | Hosted gate passed on `e8062fd`; rendering limitation remains unresolved |

Independent source reviews found no actionable issue in vendor recovery or the
CI gate. The guard/dashboard integration was also reviewed and exercised with an
offline DOM smoke. No live client action was issued by these source changes.

## Combined validation and release boundary

Installed host release: **0.3.46**, with activation evidence below. Native source
and version are unchanged from `74f34a3`; the tested native source is identical across the catch-up merges.

- Complete local host suite: **3,378 passed, 18 skipped**. Thirteen fixture-related
  skips were subsequently exercised through the bound checks below; five require
  Windows symlink privileges unavailable in this environment.
- Full and diagnostics-only Win32 Release builds passed. Each required CTest
  suite executed **169 passes and three private-client-image skips**.
- Strict diagnostic classifier passed in both profiles, retaining the two known
  effects and two known cue pixel counterexamples as explicitly unresolved.
- Bound host/native IPC suites: **63 passed per profile**, no skips.
- Host/native wire contract suites: **81 passed**, no skips.
- Ruff, PowerShell script parsing, actual dashboard script syntax, Markdown links
  and whitespace checks passed. Worker handoffs record the focused fault tests.

Local validation evidence remains in the `integration-current` worktree's ignored
`artifacts/catch-up/`; CMake outputs are under `build/native-full` and `build/native-diagnostics-only`.
Four fixture executable copies under `artifacts/vendor-native-build/Release`
are hash-linked to their original build paths by `fixture-copies.json`. They are
local test artifacts, not published client binaries or deployment payloads.
Host wheel built from clean release source
`370da56abe0724f13f9e15a3afd952163a906198`:
`shadowbane_lab-0.3.46-py3-none-any.whl`, SHA-256
`b06d27cf06194bdef20cca4372309f8474e0d3cab31dcf60f320dc9318af9f02`.
All 430 packaged source/data files match the source export. An isolated local
installation verified version, module origins, the coverage dashboard and the
vendor recorder entry point. The wheel and verification receipt remain under
`artifacts/catch-up/package/`. Later documentation-only commits do not change
that package identity. The same wheel was installed and activated as recorded below.

## Read-only historical journal qualification

The current `e8062fd` Create validator was executed in guest memory against the
one identified complete schema-2 Create journal: 1,779 bytes, one item and one
observed request. Validation passed with the unchanged installed Snapshot and
owner/item helpers. No `keep.json` was found under the vendor-manager ledger,
so authentic historical Keep compatibility remains unverified; synthetic Keep
coverage and source review do not replace that evidence.

Only the validation result was returned. No private journal contents were
exported, and no guest/game files or gameplay state were changed. The private
validation runner remains in the integration worktree's ignored
`artifacts/catch-up/check-one-vm-create.py`. This read-only check did not activate
host 0.3.46 or replay any old request.

## Verified host activation - September 23

Fresh VM inspection found no game or manager process before activation. Host
0.3.46 was staged beside 0.3.45, and all 430 installed source/data hashes matched
the verified `370da56` wheel above. The manager was then activated: PID 9888,
healthy, `bound_count=0`, and `slots=[]`. The game was not launched.

Of 9,235 prior ledger files, 9,234 remained byte-identical. The sole change was
`vendor-testing/vendor-client/dispatch.permit`: strict parsing confirmed
`allowed=false` and `health=unbound`, the expected idle dispatch revocation.
No job or historical proof changed, and no request was replayed. Host 0.3.45
and configuration backups remain under the VM's
`upgrades/host-0.3.46-370da56` rollback directory.

The private activation receipt remains at
`E:/virtual-machines/shadowbane-testing/diagnostics/guard-host-0.3.46-370da56/activation.json`.
This is verified host installation and manager health, not guard/vendor gameplay
acceptance or a carpenter capability. The next step is to identify the user's
active client: the test VM currently has no game, and another client may be in use.

## Execution queue

1. Complete: baseline/movement reconciliation, guard coverage, vendor recovery,
   passive vendor recorder and diagnostic CI policy, with combined local tests
   and all 15 hosted checks on `e8062fd`.
2. Complete: authorized PR #25 merge preserving ancestry, clean normal-main
   fast-forward and verified required-check protection. Start subsequent work
   from `origin/main`; retain deferred branches and active worktrees for separate
   owner/dirty-file/remote-reachability review.
3. Complete: exact-source host 0.3.46 package checks, side-by-side VM installation
   and healthy manager activation, with 430 installed hashes verified and all
   jobs/historical proofs preserved. No game was launched.
4. Complete: read-only validation of the available historical schema-2 Create.
   No authentic Keep journal was available; retain that qualification limit.
5. Active: identify the user's active client and whether the next observations
   belong there or require a fresh test-VM game lifetime/login. The VM manager
   is healthy and unbound; game launch awaits that clarification.
6. Pending live evidence: one manually opened Irekei Barracks and a non-spending
   vendor recipe/Inventory ownership walkthrough once the client and manual
   readiness are confirmed. Carpenter also needs building readiness confirmed.
   All client UI work uses one serialized queue; no automatic spending starts.
7. Follow-on: town vendor navigation/scheduling and qualified disposal/recurrence;
   guard new-area/rank/resource acceptance and broader Condemn coverage. Preserve
   carried-gold-only funding, whole-nation exclusions and uncertain receipts.

Source integration and host activation do not certify gameplay acceptance. No
automatic crafting, spending, Condemn write or other gameplay mutation occurred
in this activation checkpoint.
