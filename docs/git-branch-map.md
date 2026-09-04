# Git branch map

Snapshot: 2026-09-04, updated after the approved remote and local retirement.
This is a source and review map; it does not certify deployment or live gameplay
acceptance.

## Completed branch and worktree retirement

The owner approved and completed deletion of **53 superseded remote branches**;
**23 remote branches remain**. Every retired tip is contained in the published
`archive/pre-branch-cleanup-20260904` tag at `151eebb`. The
[retirement registry](retired-git-branches-20260904.md) records all original names
and full SHAs, recovery commands, retained dependencies, and local outcomes.

After explicit local approval, **29 obsolete local branches** and **12 cache-only
worktrees** were also removed. **9 local branches and 18 worktrees remain**.
The nine artifact-containing checkouts were kept at their exact original detached
commits. The existing dirty streaming draft is unchanged. Consult the registry
before restoring a retired name; routine fetches will not recreate deleted refs.

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
file. Its draft was backed up and left in place. There are now 18 worktrees and
9 local branches. The retirement registry records the 53 retired remote names,
29 local names and exact tips, including local tips that differed from origin.
All retired commits remain under the archive tag. Artifact-containing checkouts
were preserved; ignored containers do not mean every checkout is clean.

The normal project checkout is returned to `main` after preparing the PR.
Repository-local `fetch.prune=true` and `pull.ff=only` keep ref refresh and update
behavior explicit. The old `codex/client-convergence` branch's incorrect upstream
to `codex/graphics-diagnostics-client` was removed without changing either tip.

After merging the consolidated PR, fast-forward the main checkout, update this
map's shared-base section, and review the outstanding deltas above. Retire only
branches/worktrees whose history and local files are demonstrably preserved.
