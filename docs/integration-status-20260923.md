# Integration status - September 23, 2026

## Current candidate and delivery

`codex/integrate-current-development` is the shared review candidate for
[PR #25](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/25),
targeting `main`. Start independent product work from its freshly fetched remote
ref. The normal checkout remains on `main`; review and merge are pending.

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

The candidate retains these published source tips by merge ancestry:

| Source tip | Delivered behavior | Remaining qualification |
| --- | --- | --- |
| `ef5deeb` guard coverage | Bounded candidate/exception detail, observed guard ranks, selected-building Condemn completion, crash-accounting schedules | Opened Barracks observation, new-area/max-rank/resource outcomes |
| `69f54cf` vendor recovery | Exact Create/Keep source digest, ownership, partition and observed receipt-chain validation before recovery | Historical private journal/live qualification |
| `f0ed883` vendor recorder | Optional read-only `--vendors` workflow mode; strict recipe, roster and Inventory channels | Manual non-spending menu walkthrough; native open/select contract |
| `79505be` CI diagnostics | Narrow expected-pixel-failure classification replaces blanket tolerance | Hosted-run confirmation; rendering limitation remains unresolved |

Independent source reviews found no actionable issue in vendor recovery or the
CI gate. The guard/dashboard integration was also reviewed and exercised with an
offline DOM smoke. No live client action was issued by these source changes.

## Combined validation and release boundary

Host release candidate: **0.3.46**. Native source and version are unchanged from
`74f34a3`; the tested native source is identical across the catch-up merges.

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

Local validation evidence is in this worktree's ignored `artifacts/catch-up/`;
CMake outputs are under `build/native-full` and `build/native-diagnostics-only`.
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
`artifacts/catch-up/package/`; this is prepared host source, not VM activation.
Later documentation-only commits do not change that package identity.

## Execution queue

1. Complete: current-base/movement reconciliation and the three integrated source
   slices, with the independent read-only vendor capture mode.
2. Active: current-head hosted CI for PR #25; local 0.3.46 wheel verification is complete.
3. Next: obtain merge authorization, merge preserving ancestry, then fast-forward
   main and apply reviewed required checks. Branch/worktree retirement remains
   separate because historical/deferred work and active owners are retained.
4. Pending live evidence: one opened Irekei Barracks; vendor recipe/Inventory
   ownership trace. Carpenter discovery waits for its building to finish.
5. Follow-on: town vendor navigation/scheduling and qualified disposal/recurrence;
   guard rank and coverage acceptance. Preserve current spending/exclusion policy.

Source integration does not certify installation or live acceptance. Guards and
Condemn share one client UI admission queue with vendor/carpenter work. No live
mutation or deployment was performed by this catch-up source checkpoint.
