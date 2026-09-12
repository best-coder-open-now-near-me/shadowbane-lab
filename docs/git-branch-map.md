# Git branch map

Snapshot: 2026-09-04, updated after the approved remote and local retirement.
This is a source and review map; it does not certify deployment or live gameplay
acceptance.

## Current delivery status — September 12

Active priority: [PvE/PvP attack-list delivery](pve-pvp-attack-list-plan.md).
Blacklist means attack list, populated by commands or attributed responses.

| State | Source and evidence | Scope |
| --- | --- | --- |
| Last verified installed client | Product 1.7.8 / wheel 0.2.8, `97612e6`; [receipt and acceptance](handoffs/combined-candidate-1.7.8.md) | Movement/controller/chat baseline; focused user acceptance passed. Physical disconnect/reconnect remains unconfirmed. |
| Verified package, not installed | Product 1.8.0 / wheel 0.3.0, `433dc81`; [package handoff](handoffs/combined-candidate-1.8.0.md) | Movement/camera/cancel remapping; package checks, seven CI jobs and independent source review passed. No live remapping acceptance. |
| Awaiting integration review | Identity branch `8552552` | Exact character keys, player/NPC classification, coherent party observations and positive pet ownership. No completed combat activation. |
| In development | [Door interaction](handoffs/door-interaction.md) | Character-forward ranking and collection/collision dependencies only; native selection/cue/Interact unfinished. |
| Deferred | Particles/native transparency | Unfinished and outside current combat scope. The visible character highlight was accepted as a baseline; ideal glow/material coverage remains separate. |

Package validation, source review and live acceptance are distinct. No full visual
bundle or PvP completion is claimed. The integration branch remains
`codex/native-lifecycle-hardening`; main remains unchanged. No new installation
is implied by later source commits. Reuse accepted navigation and movement evidence.

## Historical candidate notes

The entries below are historical snapshots, not current installation instructions.
1.7.7 keyboard acceptance and controller detection findings were superseded by the
1.7.8 installed baseline above. Retained candidate handoffs preserve their evidence.
Earlier September 11 movement follow-up: installed diagnostic package 1.7.4 identified
manual latching after native update gaps. Repair candidate 1.7.5 / wheel 0.2.5
is built from `29ef530`, independently source-reviewed and locally package-verified;
CI and connected acceptance status are tracked in
[the 1.7.5 handoff](handoffs/combined-candidate-1.7.5.md). The existing integration
branch remains the destination; main and the running diagnostic client are unchanged.

Current September 6 candidate: `04b7bdb` (native 1.7.3 / wheel 0.2.3) passed
all package/CI checks and independent focused review, and was installed with
owner approval. It addresses the live terrain/movement conflict found in 1.7.2.
See [the 1.7.3 handoff](handoffs/combined-candidate-1.7.3.md) for exact identities
and pending in-world movement checks. Main remains unchanged.

September 6 movement repair: exact package source `a98a6b3` (native 1.7.2 / wheel
0.2.2) completes local package checks and independent source review. See
[the current movement repair candidate](handoffs/combined-candidate-1.7.2.md)
for exact hashes, CI status and the targeted connected check. VM deployment is
not implied. Particles remain paused; newer PvP identity work is outside this package.

Later September 6 update: the owner requires a visible selection effect. Native
1.7.1 / wheel 0.2.1 is verified from `becc58fdb4b1ae51fa6c82617c42dceea41a9e94`, including cue
source `2a9997316f0a11739e439d6aef71320ae020f790`. The earlier 1.7.0
receipt below remains historical; it does not certify this change. Particles
remain unavailable pending correct transparency; they do not block the cue update.
See [the verified visible-selection candidate](handoffs/combined-candidate-1.7.1.md)
for exact artifacts, executed gates and the coordinated acceptance update.

September 6 verified candidate: native 1.7.0 / wheel 0.2.0, exact build source
`89c3b1ecb7087c8da3d1de697b6dfb507682a8f8`. Package, installed controls and
all final CI jobs verified; connected acceptance remains pending in the existing
Sol testing task. World glow/particles are explicitly suppressed per owner scope.
See [the exact candidate and single acceptance procedure](handoffs/combined-candidate-1.7.0.md).
Later evidence-only commits are not the packaged source.


Use `codex/native-lifecycle-hardening` for this batch's combined source and review;
its separate checkout is `.worktrees/native-lifecycle-hardening`. Exact common
base: `14d117e8c5194c6dff55dac608b2d3f683187d31`. The normal checkout remains
`main`; do not reset or switch another developer's checkout. This does not
supersede historical source/retirement records below or authorize main merge or VM deployment.

The four feature source branches target this integration owner:
`codex/particles-trails`, `codex/selected-character-cue`, `codex/sky-horizon`, and
`codex/native-movement-controls`. GitHub metadata rechecked September 5: all
four PRs (28-31) are merged checkpoints targeting `codex/native-lifecycle-hardening`,
not open reviews of newer work. PR28 records merge `4e908b4`; PR29 records
`5519a8e`. Later source deltas are integrated separately; exact inclusion and
validation are recorded in the active handoff. A merged PR does not certify
complete feature delivery, package identity or owner acceptance.
Useful dependencies are merged during development. Features enter rolling owner
candidates only when complete; newer movement work must not indefinitely delay
completed older features. Shared scene/context/startup and manager ownership
remain with the integration owner.

See [the active source and validation handoff](handoffs/native-lifecycle-hardening.md)
for exact included revisions, committed repairs and outstanding gates. The September 6 owner scope prioritizes artifact avoidance: world glow and
particles/trails are conservatively suppressed, with explicit controls/status.
Ideal native transparency remains deferred diagnostic evidence; required runtime
fallback tests must execute and pass. See the updated shared acceptance plan. Movement now registers one native update/input runtime after shared startup,
defaults disabled, and composes native stop, camera, steering, terrain-pick and
drag with exact lifetime and HWND safety handling. Native preferences and the selected-client
Graphics Lab settings entry are included. Manager operations now use immutable native
grants, renewal and exact cleanup. Standalone live travel/PvE now use the same
native authority, with no minimap movement fallback. No connected capability is certified. The exact verified wheel/DLL candidate identity is recorded in the September 6
handoff above; no connected acceptance or deployment is claimed. Preserve all active branches/worktrees; retirement
requires verified inclusion and applicable approval.

## Current handoffs and terrain follow-up

The navigation inspector is implemented on codex/navigation-inspector in
[draft PR #27](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/27),
targeting codex/integrate-current-development. Use that feature branch for inspector
review and the integration branch for independent development. The inspector's
publisher, native overlay, controls and saved evidence are outside the shared
integration branch until PR #27 is accepted. See the [usage and validation record](navigation-inspector.md)
and [developer/owner live handoff](handoffs/navigation-inspector.md). This inspector
package excludes the separate terrain material repair. The normal checkout is
clean on main; the inspector worktree is retained for live acceptance and review.

Branch/worktree counts in the retirement section below are the cleanup snapshot.
The active inspector adds one branch and one worktree; it is not an obsolete
checkout to retire before acceptance.

A later September 4 fetch found convergence at `031de7e` and the new terrain
repair branch at `9287c9a` ([PR #26](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/26)).
The convergence changes since `da109b0` are only a merge workflow and validation
note; the terrain implementation has not landed there. Its generation, Windows
terrain tests and merge workflow have failures, and product build/startup wiring
is absent at the repair tip. See [the exact delivery check](handoffs/terrain-delivery-check-20260904.md)
before selecting a terrain-enabled base or package. The staged correction branch
`codex/terrain-material-repair-final-v2@3b344f0` adds a revised delivery path, but
its first delivery run fails before assembly/validation with an unset Git committer
identity and uploads no artifacts. Convergence is still `031de7e`.
Earlier pinned snapshots below retain their historical meaning.

## Completed branch and worktree retirement

The owner approved and completed deletion of **53 superseded remote branches**;
**23 remote branches remain**. Every retired tip is contained in the published
`archive/pre-branch-cleanup-20260904` tag at `151eebb`. The
[retirement registry](retired-git-branches-20260904.md) records all original names
and full SHAs, recovery commands, retained dependencies, and local outcomes.

After explicit local approval, **29 obsolete local branches** and **12 cache-only
worktrees** were removed. The owner then approved archiving the nine remaining
obsolete artifact checkouts: their **4,264 non-cache files** were hash-verified
in one private ZIP, and all nine checkout folders were removed. **9 local
branches and 9 worktrees remain** (21 worktrees removed in total).
The existing dirty streaming draft is unchanged. Consult the registry before
restoring a retired name; routine fetches will not recreate deleted refs.

## Shared starting point

| Role | Branch and pinned checkpoint | Meaning |
| --- | --- | --- |
| Shared merge destination | `main` at `047147d` | August 30 release. It does not yet contain the consolidated client development below. |
| Proposed integration into main | `codex/integrate-current-development` | Review branch created from `da109b0`, plus this repository navigation and workflow cleanup. No additional feature branches were merged in the cleanup. |
| Preserved development source | `codex/client-convergence-v2` at `da109b0` | 386 commits beyond `047147d`; main is an ancestor. Contains client, renderer, diagnostics, asset facade, PvE, PvP data, and simulator integration. |
| Former local checkout | `codex/wreck-texture-cache-swap` at `99b37c7` | 61 commits beyond main, but already contained in `da109b0`. An older topic, not the current combined product. |

Review the [proposed integration](https://github.com/best-coder-open-now-near-me/shadowbane-lab/compare/main...codex/integrate-current-development).
The source checkpoint has [successful shared CI](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/33835010581).
The PR's own checks must also pass. Green CI does not close known runtime review
findings or unfinished terrain acceptance.

For the feature contents, see the [recovery ledger](project-recovery-status.md),
[feature lineage](feature-lineage.md), and [tool ownership map](tooling-map.md).
Those documents contain dated historical queues; use this map for branch selection.

## Work outside the proposed integration

Counts below compare each pinned tip to `da109b0`. A missing ancestor commit does
not by itself establish missing behavior: some historical features were replayed.

| Branch | Tip | Commits outside convergence | Disposition |
| --- | --- | ---: | --- |
| `codex/legal-build-map-elites-foundation` | `ee5a4c2` | 9 | Later training-budget and static-capability work. The branch lacks 86 convergence commits; integrate its delta after review instead of replacing convergence. PR #23 still targets the older PvE branch. |
| `codex/texture-cache-read-export` | `0680a76` | 8 | Forks at `a1f8a77`, with 34 convergence commits absent. Review its exporter changes separately and retain the newer terrain/diagnostics work. |
| `codex/terrain-material-export-da109b0` | `bb516fe` | 10 | Descends from `da109b0`; adds export/review/publisher workflows and encoded implementation payloads. A payload or publisher is not evidence that its source changes were integrated. |
| `codex/terrain-material-repair-workspace` | `9f2446e` | 7 | Separate handoff workspace, missing the final convergence draft checkpoint. Preserve and inspect its delta. |
| `codex/terrain-repair-snapshot` | `1ac56c6` | 1 | Separate snapshot, missing the final convergence draft checkpoint. Preserve for handoff. |

`codex/terrain-material-repair-implementation` currently points to `da109b0`
itself; its name does not mean the planned implementation has landed.

Historical refs outside convergence are retained: `codex/initial-simulator`,
`codex/shadow-mantle-policy-ablation`, `codex/preserve-assassin-sdr-loadout`,
`codex/preserve-elf-druid-kiting`, `codex/world-map-exact-dispatch`, and
`fix/world-map-click-capture`. Consult the feature lineage registry for the
superseded prototype, experiments, replayed features, and exact-map routing
decisions before integrating or retiring these refs.

## Existing PRs and review boundaries

- PR #21 (texture tools), #22 (PvE authority), and #24 (sustained contours)
  have source tips contained in `da109b0`. Their open state does not mean those
  capabilities are absent from the candidate. They remain open until the
  consolidated review determines how to close their original review records.
- PR #23 contains the later simulator delta described above. Its older base must
  be reconciled after the consolidated base is accepted.
- PR #16 is a historical exact-map draft against an old simulator-CI branch.
  Do not merge it simply to empty the PR list.
- `native/wonderbane_extension/terrain_material_plan.h` and `.cpp` at `da109b0`
  are explicitly unfinished source drafts. Their publication preserved handoff
  access; it did not enable or complete the terrain repair.
- The recent repository review identified manager permit lifetime, failed-launch
  cleanup, heartbeat shutdown, worker-start concurrency, and native publisher
  shutdown findings. Texture-export publication findings belong to the separate
  export branch. Recheck each against its exact intended source before closing it.

## Local cleanup and recovery

The September 4 cleanup preserved all refs and the old stash in a verified local
Git bundle. It archived 193 scratch entries (2,695 files), verified each SHA-256,
and saved the six existing formatting edits in a named stash. None of those
private scratch files was added to the integration PR.

The private local recovery directory is
`artifacts/git-cleanup/20260904T062424Z/`. It contains the bundle, before-state
refs/configuration/worktrees, both dirty-checkout patches, branch audit, scratch
manifest and archive, and the exact new formatting-stash SHA. Preserve it until
the owner decides that recovery copies are no longer needed.

The old streaming worktree still contains eight modified files and one reject
file. Its draft was backed up and left in place. There are now 9 worktrees and
9 local branches. The retirement registry records the 53 retired remote names,
29 local names and exact tips, including local tips that differed from origin.
All retired commits remain under the archive tag. Historical build artifacts
from nine obsolete checkouts are consolidated in
`artifact-consolidation/retired-builds.zip` under the recovery directory, with
original paths and file hashes in its manifest. Those checkout folders have
been removed; the retained streaming checkout still contains its unfinished work.

The normal project checkout is returned to `main` after preparing the PR.
Repository-local `fetch.prune=true` and `pull.ff=only` keep ref refresh and update
behavior explicit. The old `codex/client-convergence` branch's incorrect upstream
to `codex/graphics-diagnostics-client` was removed without changing either tip.

After merging the consolidated PR, fast-forward the main checkout, update this
map's shared-base section, and review the outstanding deltas above. Retire only
branches/worktrees whose history and local files are demonstrably preserved.

## September 12 PvE/PvP priority

The active delivery plan is [PvE/PvP attack-list integration](pve-pvp-attack-list-plan.md).
Blacklist means the attack list, populated manually or through attributed responses.
The plan retains applicable review follow-ups without making broad cleanup or unfinished
visual/door features prerequisites. Identity checkpoint 8552552 still needs integration.
