# Feature lineage and preservation registry

This registry records capabilities that remain outside `main`, the exact history that owns each
one, and the conditions for integrating or retiring its branch. It exists to preserve behavior and
design intent without treating every historical branch as an independent product surface.

The registry snapshot was taken on 2026-08-31 after fetching `origin`. A verified Git bundle
captured all 92 refs, including `refs/stash`, before any preservation commits or pushes. Dirty
worktrees were also exported as binary patches. Machine-local patcher-audit evidence remains in the
private preservation archive and must not be committed.

## Status vocabulary

- **Production candidate**: coherent, tested behavior intended for the consolidated product, but
  not yet merged into `main`.
- **Integrated production candidate**: reconciled on `codex/integrate-preserved-features` with its
  production validation recorded below, but not yet merged into `main`.
- **Preserved experiment**: useful code or evidence whose assumptions still require review before
  production integration.
- **Superseded history**: behavior represented patch-equivalently or as an ancestor of another
  retained branch.
- **Reverted decision**: the commit remains reachable for its design evidence, but the current
  branch intentionally removes its behavior.

## Production feature capsules

| Capsule | Owning range or ref | Capabilities and durable APIs | Dependencies | Current evidence |
| --- | --- | --- | --- | --- |
| Texture authoring tools | `047147d..a34fd9f` (`origin/feat/wonderbane-texture-tools`) | Alpha-safe image loading, border-key inference, LAB quantization, safety masks, deterministic low-frequency noise, bark/foliage flare, and legacy-friendly texture sculpting | `origin/main` | Retained on its remote branch and embedded in every client-extension descendant |
| Immutable extension bootstrap | `a34fd9f..e78f3ed` (`origin/codex/client-extension-bootstrap`) | `freeze_client_baseline`, `align_patch_sites`, `build_patch_plan`, `prepare_patched_client_copy`, `verify_patched_client_copy`, `discard_patched_client_copy`, reviewed x86 loader authoring, and process-lifetime heartbeat evidence | Texture tools | Retained remotely; ancestor of all later extension branches |
| Exact event and bounded action stack | `e78f3ed..7e62365` (`codex/client-cel-preview`) | Bounded shared-memory event transport, consumer leases, `ClientActionRunner`, `WorldMapDestinationClickAction`, tagged input verification, and `ExactExtensionEventRouter` | Immutable extension bootstrap | Retained by later remote descendants; the intermediate local ref is superseded |
| Versioned native map API | `7e62365..0670de6` (`origin/codex/client-extension-map-api`) | Router diagnostics, bootstrapped native-layout registration, extension lifetime pinning, and versioned client upgrades | Event and action stack | Retained remotely; common parent of the current production lines |
| Manager and travel reliability | `0670de6..015e099` (`codex/manager-permit-retry`) | Worker-record retry, responsive native hooks, cancellation separate from physical input, local terrain horizons, duplicate-map resolution, exact map closure, and safe reachable A* frontiers | Versioned native map API | All commits are present on `origin/codex/client-streaming-telemetry` |
| Shared 55fb rendering foundation | `015e099..79dbeaf` | Exact 55fb alignment, stale-artifact retirement, timestamped baselines, adaptive A*, immutable texture overlays, renderer diagnostics, bounded production cel rendering, and Control Center reconnect | Manager and travel reliability | Shared ancestor of both retained rendering leaves |
| Verified 55fb graphics publication | `origin/codex/graphics-baseline-55fb` at `1261cc8`; replayed as `7f42cab` and `abf495d` | Hash-derived content-build identity, reviewed loader-manifest authoring, a no-write package gate, exact-match dry-run receipt reuse, local free-space enforcement, isolated graphics-only publication, post-copy verification, and immutable publication receipts | Shared 55fb rendering foundation and client-copy package commands | The wrapper parses cleanly and all 21 focused client-extension tests pass locally (one intentional skip). The exact source branch is published; VM execution remains an explicit release validation step. |
| Streaming and performance telemetry | `79dbeaf..5b3e1ec` (`origin/codex/client-streaming-telemetry`) | Bounded frame/cache/texture telemetry, binary parser contracts, performance profiles, verified renderer exclusions, removable renderer overrides, and reduced native hot-path overhead | Shared 55fb rendering foundation | Remote tip includes the two formerly local-only commits |
| Refined cel outlines | `79dbeaf..d482d0f` (`origin/codex/patch-align-55fb`) | Local-scene filtering, perspective-scaled strokes, component bounds capture, centered hull expansion, and mutually exclusive hull/line fallback | Shared 55fb rendering foundation | Release x86 build and all four native tests passed at `d482d0f` |
| Release evidence and isolated runtimes | `0670de6..a12ef15` (`origin/codex/wreck-texture-cache-swap`) | Reversible texture-cache swaps, immutable overlays, renderer diagnostics, isolated runtime provisioning, runtime consistency capture/promotion/gating, and verified official patch diffs | Versioned native map API | Retained remotely; three policy experiments in this range are reverted at the tip |
| Exact world-map dispatch | `047147d..e6d5c85` (`origin/codex/world-map-exact-dispatch`) | Selective pointer capture, map-aware interaction routing, immutable captured coordinates and process identity, left-click selection capture, and exact worker dispatch after focus changes | `origin/main`; overlaps the event/action stack at integration points | Retained remotely as the historical pointer-hook capsule. Its durable identity, map-close, cancel, and exact-worker semantics are superseded in production by the native event channel plus `ExactExtensionEventRouter`; replaying the old hook would create a second capture owner. |
| CLI modularization | `a12ef15..c997a45` (`origin/codex/modularize-cli`) | Compatibility-preserving `shadowbane_lab.cli` facade with parser, client, manager, character, and progression implementations in focused modules | Release-evidence line | Replayed as `5052d60`; newer token, cancellation, pathfinding, and native-event behavior was relocated into its owning modules. Ruff and all 1,060 Python tests pass on the integrated result. |

The integrated production candidate is `codex/integrate-preserved-features`. Renderer reconciliation
is checkpointed at `01523ff`, release/runtime reconciliation at `c5ad38f`, and the modular CLI replay
at `5052d60`. The graphics-only publication and resumability replays are checkpointed at `7f42cab`
and `abf495d`. Its final production gate passed the x86 Release build and probe, all five native
tests, Ruff, and all 1,060 Python tests (one intentional skip); the additional publication wrapper
passed its focused local gate but has not been executed inside the test VM.

## Simulator feature capsules

| Capsule | Owning range or ref | Capabilities | Status and evidence |
| --- | --- | --- | --- |
| Target-relative kiting and Elf Druid | `23b9a313..66dce87`; preserved as `origin/codex/preserve-elf-druid-kiting`; replayed as `cb091e9` and `be4fac0` | `open_range_action`, target-relative retreat intent, sourced Elf Healer Druid sheet, Druid matchup matrix, healing/cleanse/kiting behavior, and documentation | Integrated on current `main` lineage in `origin/codex/integrate-preserved-simulator` |
| Assassin SDR and Greater Concoction reconstruction | `origin/codex/preserve-assassin-sdr-loadout` at `8ad3893`; replayed as `db7dd16` | Sourced SDR jewelry and Saedrium armor, explicit attribute and skill deltas, resistances, Greater Concoction pre-fight state, and updated deterministic matchup evidence | Integrated on current `main` lineage in `origin/codex/integrate-preserved-simulator` |
| Shadow Mantle policy ablations | `origin/codex/shadow-mantle-policy-ablation` | Reproducible forced-priority and mana-reservation experiments | Preserve as an experiment recipe, not an always-on GitHub workflow |
| Initial deterministic/MAP-Elites prototype | `origin/codex/initial-simulator` | Original catalog, genome, search, policy, and simulator concepts | Superseded by the integrated `shadowbane_lab` simulator; retain only as architecture and experiment history |

The original `refs/stash` remains present after materialization. Its tracked simulator changes are
now represented by `8ad3893`; its untracked patcher-audit files are intentionally private.

The integrated simulator candidate is `codex/integrate-preserved-simulator` at `db7dd16`. Ruff and
all 922 Python tests pass on that branch. The focused Elf Druid and Assassin preset gates also pass
after replay onto the current lineage.

## Reverted decisions that must remain visible

The release-evidence branch contains three policy commits followed by explicit reverts:

| Concept | Introduced | Reverted | Integration rule |
| --- | --- | --- | --- |
| Pin every managed runtime file hash | `84ea1b6` | `a12ef15` | Do not restore implicitly. Reintroduce only with a migration and measured startup-cost evidence. |
| Persist listener opt-out policy | `c71159f` | `b979f9d` | Preserve the operator-intent concept, but define ownership and reset semantics before implementation. |
| Refuse Control Center startup on integrity drift | `e980891` | `ec4f760` | Preserve as a fail-closed design option; require recovery UX and field evidence before restoring the hard gate. |

These commits are not dead code to cherry-pick wholesale. Their value is the rejected design,
tests, and failure modes recorded in history.

## Integration order

Production consolidation must preserve the dependency order and avoid replaying duplicate patches:

1. Start with the versioned native map API lineage, which already includes texture tools, immutable
   bootstrap, exact event transport, and bounded client actions.
2. Apply the manager/travel reliability range.
3. Reconcile the release-evidence line from its map-API fork. Keep its net production capabilities;
   leave the three reverted policies disabled.
4. Apply the shared 55fb rendering foundation once.
5. Combine streaming/performance telemetry with refined cel outlines. Resolve their shared native
   rendering files semantically; do not select one leaf wholesale over the other.
6. Reconcile `codex/world-map-exact-dispatch` by behavior, not patch identity. The integrated native
   event channel and exact router already own every durable production invariant from that capsule,
   so no old pointer-hook commit is replayed and the remote branch remains the preserved design and
   test record.
7. Reapply CLI modularization last, relocating newly integrated command behavior into its owning
   command module rather than restoring a monolithic `cli.py`.
8. Run native Win32 tests, Ruff, the complete Python suite, and the existing package/runtime
   verifiers before publishing the integration branch.

Simulator consolidation is a separate dependency line:

1. Replay target-relative kiting onto current `main` and validate its generic movement contracts.
2. Replay the Elf Druid profile and matchup matrix with current ruleset compilation.
3. Replay the SDR/Greater Concoction reconstruction, resolving current source/profile changes
   explicitly rather than accepting conflict markers mechanically.
4. Run the complete simulator suite and regenerate deterministic trace expectations only when the
   sourced input changed.

## Final preservation audit

After the final fetch and publication pass on 2026-08-31:

- zero commits are reachable only from local branches;
- both integration branches and the late-discovered 55fb graphics branch are published on
  `origin`;
- four previously unreachable alternate implementation drafts are named and published under
  `archive/` tags rather than exposed as active development branches;
- the verified 92-ref bundle remains the lossless fallback, with SHA-256
  `806eaa9b91eca2eaf33f8f57a8ce204b949baef3508c74b80297c3d652402935`;
- ten of eleven linked worktrees are clean; the only dirty linked checkout is the original main
  checkout, whose six modified Python files and diagnostic screenshots were backed up and left
  unstaged;
- the original stash and private patcher-audit evidence remain intact; and
- no branch, stash, worktree, or diagnostic artifact was deleted during preservation.

## Cleanup gate

A branch or worktree may be removed only after all of the following are true:

- its tip is reachable from a retained remote ref or the verified preservation bundle;
- any dirty diff and untracked evidence has a verified private copy;
- its capsule is integrated, explicitly classified as an experiment, or marked superseded here;
- the retained integration branch passes its required validation; and
- `git branch --contains <tip>` confirms the intended durable descendant.

This gate allows old names and worktrees to disappear without losing their code, evidence, or
design rationale.
