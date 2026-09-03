# Project recovery ledger

Snapshot: 2026-09-02 23:42 America/New_York (2026-09-03 UTC).
This is a branch/evidence inventory, not a claim that all listed features are
integrated, deployed, or live-verified. Re-fetch before acting: two remote tips
advanced during this audit.

## Start here

Keep `codex/client-convergence-v2` as the one long-lived experiment/product
branch. It was still at `a6344d8` when inspected; newer product work has accumulated
on topic branches instead of returning to convergence. This ledger's documentation
checkpoint does not merge that code.

The committed work is recoverable. In the main repository:

- No commits reachable from local branches were absent from all fetched origin refs.
- `git fsck --no-reflogs --unreachable` found no unreachable commits.
- These checks do not protect uncommitted files or guarantee another machine's
  unpushed work has been captured.
- No branches, stashes, files, or worktrees were deleted, reset, or rewritten.

## Exact feature inventory

All branch names below have the `codex/` prefix unless stated otherwise.
Counts compare the audited tips, before this documentation checkpoint.

| Lane | Verified remote tip | What is present | Integration / acceptance state |
| --- | --- | --- | --- |
| Shared convergence | `client-convergence-v2@a6344d8` | Preserved features, simulator/PvP data, non-render ownership extractions, evidence/diagnostic tools and integrity gates | Does not contain the newer lanes below |
| PvE + renderer recovery | `pve-target-authority@3a605e4` | Bounded native action transport/probe, exact active-character CFG selection, reviewed pre-UI capture boundary, extension 1.6.9 | 31 commits beyond convergence; not yet merged back; visual acceptance pending |
| Texture engine + public asset facade | `mod-asset-facade@ba95232` | Shared cache mutation engine, mod schema, build-specific components, conflict resolution, immutable compiled texture profiles and receipts | 23 commits unique versus PvE; no client installation/relaunch coordinator or Texture Lab GUI in this slice |
| Texture predecessor | `texture-lab-sandbox@949ec3d` | Shared texture-cache engine extraction | Fully contained by mod facade; do not merge separately |
| Legal builds + training | `legal-build-map-elites-foundation@b65eb73` | Legal-build compiler, candidate/strict archive admission, compiler-backed mutation, semantic-duel evaluation and Irekei Assassin search | 5 commits unique versus PvE, forked at `3999d2e`; repaired push CI passes, PR matrix pending |
| Contour topic | `renderer-sustained-contours@9891839` | Mod facade plus two source-export workflow commits | No sustained-contour implementation yet; still lacks the 1.6.9 boundary recovery |
| Terrain topic | `terrain-seam-audit@ba95232` | Exactly the asset-facade tree/history | No terrain audit changes yet |
| Portable clean-client diagnostics | `portable-vanilla-diagnostics@f6c1980` | Standalone read-only capture app, portable package, location lookup and separately launched Druid macro utility | 6 commits unique versus PvE; released separately, not integrated into convergence |
| Portable predecessor | `vanilla-diagnostics-release@fff9381` | Original isolated vanilla capture/release | Contained by portable branch; do not merge separately |
| Proposed sandbox coordinator | `verified-texture-sandbox-session` | Design/handoff only in the inspected refs | No remote branch or implementation found at the snapshot |

The old `pvp-current-client-data@d035f74`, preserved-feature integration,
`client-streaming-telemetry@5b3e1ec`, manager reliability tip, old convergence
attempts, and both frozen v2 aliases are already ancestors of `a6344d8`.
They are not missing feature merges. Do not replay them.

## Handoff drift resolved during this audit

The simulator handoff described a training loop while the remote initially exposed
only `ba1c70c` (compiler/archive foundation). A fresh push to `f485037` supplied
the training implementation during the audit, followed by rank repair `b65eb73`.
Treat the committed implementation as the source of truth, not the older prose:

- The module is `shadowbane_lab.optimization.irekei_assassin`, not
  `shadowbane_lab.build_optimization.irekei_assassin`.
- Its documented options include `--iterations`, `--rollout-seeds`,
  `--distances` and `--max-ticks`; do not copy the older generations/offspring command.
- The current documentation permits trained-attribute mutation and describes a
  Deflock/Elf Druid league, unlike the earlier handoff.
- PR #23 appeared during the final recheck and targets `codex/pve-target-authority`.
  The earlier missing-PR concern is resolved.
- Candidate training is not a verified current-live optimum. Opaque requirements,
  affix effects and full training-cost legality remain explicit gaps.

## Validation blockers

### Training: rank mismatch repaired; PR checks still pending

At `f485037`, all three Python jobs (3.11/3.12/3.13) fail the two end-to-end
training tests. The guide ruleset has Shadow Bolt compiled at rank 40 while the
selected build requests rank 5. The experiment constructs a default guide ruleset
before submitting the presets' rank selections. Preserve the compiler's exact-rank
rejection; the repair must reconcile build/ruleset inputs instead of weakening
the legality boundary.

Native full/diagnostics-only, quality and PowerShell checks passed in that run.
[Failed training CI](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/33711846973).

`b65eb73` subsequently derives exact rank overrides from all three presets and
rejects conflicting requests. Its full push matrix passed. PR #23's separate
matrix was still running at this snapshot; the rank-mismatch blocker is repaired,
not an outstanding implementation todo.
[Repaired push CI](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/33712055555).
[Training PR](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/23).
[PR checks](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/33712187220).

### Shared test: vendor-dialog wall-clock sensitivity

The renderer 1.6.9 push matrix passed, but the PR matrix failed
`NativeVendorDialogTracerTests.test_captures_request_and_decoded_menu_with_option`
with `4 != 1`. The older foundation run at `ba1c70c` failed the same test on a
different Python version. The fixture uses a real 100 ms timeout and 10 ms settling
window. This is evidence of a timing-sensitive test, not proof of a renderer
regression; make the fixture deterministic and rerun both matrices.

[Renderer push passed](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/33711354235).
[Renderer PR failed](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/33711354783).
[Earlier foundation failure](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/33706837893).

### Portable diagnostics: release success is not shared-CI success

The v1.0.1 release workflow succeeded, but the inherited Linux protocol CI failed:
missing Pillow/Capstone-dependent coverage and Windows-path deployment assertions.
Carry this source into the current dependency/platform-aware validation matrix;
do not equate a successful portable build with a green shared product.

[Portable release](https://github.com/best-coder-open-now-near-me/shadowbane-lab/releases/tag/vanilla-diagnostics-portable-v1.0.1).
[Inherited CI failure](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/33640028087).

Asset facade `ba95232` and contour export `9891839` have successful shared CI.
The latter validates the inherited asset code/export workflow, not a new contour algorithm.

## Merge feasibility and order

Non-mutating `git merge-tree --write-tree` previews found no textual conflicts for:

- `3a605e4 + ba95232` (PvE/renderer + assets);
- `3a605e4 + b65eb73` (PvE/renderer + training);
- `3a605e4 + f6c1980` (PvE/renderer + portable diagnostics).

These are pairwise previews, not a validated combined build. No real merges were
performed. The shared ancestors are respectively `46a295f`, `3999d2e`, and
`99b37c7`. The training branch is missing eight PvE-side commits, including
active-profile selection and 1.6.9 recovery; it must not replace the PvE tip.

Recovery queue:

1. Stabilize the shared vendor-dialog fixture in its own checkpoint, and confirm
   PR #23's final matrix after the already-pushed rank repair. Recheck moving refs
   before editing.
2. Merge the PvE/1.6.9 history into convergence, then the asset facade, then the
   repaired training slice, then portable diagnostics. Preserve each feature's
   boundaries and evidence; do not select one entire branch as the replacement.
3. Run the complete Python/dependency matrix, lint, PowerShell parser, both Win32
   profiles/CTest, package boundaries, and focused new-feature tests on the combined
   source. Commit and push each validated integration slice.
4. Reconcile stale PR destinations only after choosing the containing checkpoint.
   PR #22 still targets renderer recovery, PR #21 targets main for already inherited
   texture tools, and draft PR #16 targets an old simulator-CI branch. Do not click
   merge on all three as a substitute for this convergence.
5. Prepare an exact testing-VM package and verify the 1.6.9 outline recovery live.
   Keep deployment distinct from source integration; do not touch the plain VM.
6. Deliver the verified sandbox session coordinator as the next end-to-end
   asset-testing workflow, then continue terrain audit and contour work from the
   new shared tip.
7. Only after capture ownership and experiment identity are stable, proceed to
   semantic surface provenance, world targets, normal/class buffers, AO and the
   larger compatibility-renderer sequence.

## Ownership boundaries to retain

- Asset facade: public package identities, build variants and explicit conflicts.
  One internal texture engine owns texture-cache parsing and binary mutation.
- Sandbox coordinator: orchestrates verified installation, exact launch, renderer
  settings acknowledgement and evidence identity. It must reuse the existing
  package/process/graphics/evidence owners, not replace them with one service.
- Baseline content is a first-class `vanilla-assets` descriptor above the current
  non-empty texture-plan type. It does not mean the whole client is unmodified.
- Materialized profiles remain immutable verified sources, never live client caches
  or writable hard links. Switching needs a durable journal and recovery states.
- Receipts form a chain: materialization -> closed-client switch -> exact launched
  session. Record PID plus creation time, canonical executable/hash, extension
  version/hash, content receipt/hash and applied renderer revision.
- Terrain audit is read-only: borders, gradients, material layers, corners, source
  hashes and coordinates. No terrain repair, cache writes, or authoritative draw
  classification belongs in that audit.
- Contours own depth-edge logic and versioned graphics controls, not cache writes.
  Their current asset-based branch must incorporate 1.6.9 before renderer edits
  are promoted; otherwise the early-capture regression can return.
- Simulator owns offline legality, rules, search and replay. It must not depend on
  the renderer, native actuation or a live game to validate the training loop.
- Truly plain-client diagnostics remain distinct from an extension's
  diagnostics-only build. Consolidating their source does not authorize deploying
  the extension or automatically starting the bundled macro.

## Local leftovers: preserve, do not replay blindly

| Location / history | Observed state | Disposition |
| --- | --- | --- |
| Main `wreck-texture-cache-swap` checkout | Six tracked Python formatting changes; 229 untracked entries under `status -uall`, including patches, screenshots, scratch analyses and worktree markers | Do not stage wholesale or clean recursively; private evidence stays private |
| `.worktrees/client-streaming-telemetry` | Eight modified files plus `performance_telemetry.cpp.rej`; partial `hotspot/frame_activity` schema-2 patch | Python diff contains a broken consecutive `elif`; not a release candidate. Modern convergence already implements schema-2 `aggregate/frame_summary` with grouped counters. Reconcile intent, do not replay the draft |
| Other registered worktrees | No tracked/untracked changes at the snapshot | Clean does not mean retired; many are historical or detached release snapshots |
| Testing share clone | `pve-target-authority@d00af62`, 22 pre-existing untracked helpers/screenshots | Remote-tracking state in this separate clone is stale; preserve files before any later fast-forward |
| `stash@{0}` | `45b836d`, old simulator/pre-main-update stash | Still retained; prior preservation registry records its tracked work and private audit evidence. Do not pop or drop casually |

Local refs that report "ahead" of their own old upstream are not necessarily
unpublished: the manager, graphics baseline and simulator tips are all retained
through other fetched remote refs.

Historical independent tips also remain on origin: the initial simulator prototype,
Shadow Mantle ablation recipes, earlier exact-map dispatch histories, and the
Assassin SDR preservation branch. Ancestry alone does not prove whether a replayed
feature is missing. The old prototype is explicitly superseded; ablations are
experiments; SDR patches have replay equivalents. Keep the refs until feature-level
coverage and private evidence are verified. Do not resurrect old workflows/reverts
just to make every branch an ancestor.

## Existing tools versus remaining field work

Convergence already includes exact-process observation snapshots, record-store
ownership, package/runtime-drift separation, camera producer/consumer contracts,
aggregate frame/cache/upload telemetry, markers, timeline correlation and a CPU-stack
capture planner. The broken streaming draft is not the only copy of those intentions.
See `docs/refactor-boundaries.md`, `docs/evidence-spine-delivery-plan.md` and the
diagnostics modules before starting another rewrite.

This inventory does not certify all live evidence collection as finished.
The Maelstrom stationary slowdown, preserved captures, warm revisit and optional
short CPU-stack capture remain investigation work. Texture lifetime tracking is
conditional on evidence of repeat uploads; no new invasive capture is authorized here.
The untracked network residency launcher must not be executed or incorporated.

## Deployment truth

No VM was changed in this audit. The testing share is a separate clone, not the
main checkout or the renderer implementation worktree. A branch push does not update
its scripts, DLLs, installed packages or running client.

The prior 1.6.9 release is built and pushed, but testing publication and visual
acceptance are pending. Use the pinned artifact hashes and acceptance conditions in
`docs/investigations/renderer-scene-boundary.md` on `pve-target-authority@3a605e4`
until that journal is merged here. The required latest-frame facts include a
verified mapping, exactly one main scene/boundary, successful composite, zero late
world draws, and a boundary after the final world draw. Also verify text/UI,
character and prop outlines, baseline reset, repeat launch, revisit and frame time.

## Keeping this ledger useful

Every future handoff should record: exact source commit, containing convergence
commit (or "not merged"), validation run, artifact hash/profile, deployed target
(or "not deployed"), and the next concrete todo. Planned, implemented, CI-verified,
integrated, packaged and live-verified are different states.

Refresh this snapshot at each integration checkpoint. Keep historical journals as
evidence, but use this ledger for the current queue rather than old chat claims.
