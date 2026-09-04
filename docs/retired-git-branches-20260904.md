# Retired remote branches - 2026-09-04

The owner explicitly approved deleting these 53 superseded remote branches.
The deletion was atomic and required each remote tip to match its audited SHA.
All 53 tips are ancestors of the published annotated archive tag
`archive/pre-branch-cleanup-20260904` at `151eebbc0fcc5b93617a14f96a170046e55fe81b`.
The archive tag preserves their source history; this table preserves their names.

Remote branches decreased from **76 to 23**. Open PR heads and bases, unique
development, the dirty streaming lane, and the VM setup default remain.

## Deleted remote refs

| Branch | Retained commit |
| --- | --- |
| `ci/group-foundation-hardening` | `e0dd4f9fe826a8a5b207cb07dde15bdc5ddfb348` |
| `ci/group-targeting-lint` | `e0dd4f9fe826a8a5b207cb07dde15bdc5ddfb348` |
| `codex/client-extension-bootstrap` | `e78f3ed1982631fd6945f262121516f07546ca2f` |
| `codex/client-extension-map-api` | `0670de6176826464470625047f2d0648a054d2d2` |
| `codex/client-streaming-diagnostics-v2` | `4b047c9333ee8a2c6a7580480a9e7e58f001e709` |
| `codex/convergence-integrity-gates` | `a7595444504ef4effa28efe4b97c65a4e8bf3839` |
| `codex/evidence-spine` | `8ee3d2c0d81b538d569d6bf95ddd930aed4f6ba3` |
| `codex/evidence-spine-outline` | `99fff9396c267874388650f9f8b752f6cec971f2` |
| `codex/game-behavior-corpus` | `03743b2376846b9fdd56ab30eaaa083a0e7169c5` |
| `codex/graphics-banded-lighting` | `de9367f18a70231740f1f44adefa8458c7df795d` |
| `codex/graphics-baseline-55fb` | `1261cc82608470d15276051c9df4e5db151e8c14` |
| `codex/graphics-diagnostics-client` | `89cefb0fc57f354ab089c4af374b797ceeeeac8e` |
| `codex/graphics-evidence-integration` | `d58221cacaf30af13d716cd988d3eb39fb06686e` |
| `codex/integrate-preserved-features` | `43be8c9050faff57f5748b8eb74cfe255d22a12c` |
| `codex/integrate-preserved-simulator` | `db7dd16dcd255305f60f53a49d1c1580db94383d` |
| `codex/integrate-pvp-current-client-data` | `0d55095deaf5fa2eecdd95493ef86168bc9285ce` |
| `codex/manager-permit-retry` | `cf011845150bbda523f4ae05d1edd655e2494f31` |
| `codex/modularize-cli` | `900955fb845606014e55b1e818c8c3a58811c6cf` |
| `codex/navigation-debug-overlay` | `bc076d73895166145ab4e0a90c0a4eb9cb8de47d` |
| `codex/non-render-refactor-v2` | `4b047c9333ee8a2c6a7580480a9e7e58f001e709` |
| `codex/open-build-exploration` | `eb8019e04a941c5779634995406ce031bbebca77` |
| `codex/patch-align-55fb` | `d482d0feac9acf6dc1c0d5ffd44da8e5d8ffa8ec` |
| `codex/portable-vanilla-diagnostics` | `f6c198018a7892194f92d251bf804757503c1430` |
| `codex/progression-duel-sim` | `6ffd489a9ea0961e878fce61c9f5fb17f31146c0` |
| `codex/pvp-current-client-data` | `d035f749a3763e92651b278aecfd6e37cfe206b3` |
| `codex/shadow-mantle-sim` | `c649fdedbf34bc1c5a37be08a4283dc1aa1bdbb5` |
| `codex/temporary-texture-export` | `ba95232c2c445d39e4fa60af0bc3812a2c97b8a0` |
| `codex/terrain-seam-audit` | `8df769481f5a1a1944a56771371dcf9a160b7fdc` |
| `codex/texture-lab-sandbox` | `949ec3ddb5f008b423728aa36f4c11c6047d4440` |
| `codex/vanilla-diagnostics-release` | `fff93812bd622dac14d4a7d9dc2b04ecc066a21e` |
| `codex/vendor-dialog-diagnostics` | `02d729808eb389a9565f2a83b93548974d5bbb08` |
| `codex/window-manager` | `ca71a53eb9e7d119c5c82248683ac985c2b6251d` |
| `codex/wonderbane-character-snapshot` | `be993fd66c7560f8e03792d0341d970bf043981b` |
| `codex/wonderbane-sundancer-deflock-presets` | `c2da71d17199f37e8eb07776c3e0994f65eef487` |
| `codex/worker-supervision` | `18efdbac1f62fb8cab1402d883fd568316507b3c` |
| `codex/wreck-texture-cache-swap` | `99b37c7f4140db1f465d834c089b9aa7b1bc761b` |
| `feat/build-package-compiler` | `bae7c0880ac2c818def7ee62ba397238dab0bd5a` |
| `feat/build-simulation-case-views` | `208b95c9f8e812fad629bc591d4bedc4f70a470e` |
| `feat/canonical-damage-transaction` | `8a6d81868379766bcf56e1e445f614949b675b6d` |
| `feat/client-build-alignment-foundation` | `987a9d786d6de52091fe2e44225b81b51187f531` |
| `feat/client-extension-vendor-hook` | `987a9d786d6de52091fe2e44225b81b51187f531` |
| `feat/client-extension-vendor-hook-check` | `987a9d786d6de52091fe2e44225b81b51187f531` |
| `feat/client-extension-vendor-hook-pr` | `987a9d786d6de52091fe2e44225b81b51187f531` |
| `feat/client-extension-vendor-hook-pr2` | `987a9d786d6de52091fe2e44225b81b51187f531` |
| `feat/client-extension-vendor-hook-pr3` | `987a9d786d6de52091fe2e44225b81b51187f531` |
| `feat/client-extension-vendor-hook-pr4` | `987a9d786d6de52091fe2e44225b81b51187f531` |
| `feat/client-extension-vendor-hook-pr5` | `987a9d786d6de52091fe2e44225b81b51187f531` |
| `feat/conditional-control-powers` | `1744d3e2cd74e78a4789c9dbdbcabcb587a90cf4` |
| `feat/group-targeting-foundation` | `ee0fd55feff63abe3211cd89fba58dc7d9a68366` |
| `feat/runtime-affiliation-targeting-integration` | `93c75543a5a55067598afedc864c6f4f71511a59` |
| `feat/simulation-case-views` | `bae7c0880ac2c818def7ee62ba397238dab0bd5a` |
| `feat/simulator-effect-outcomes` | `3e46c1890f40e2a08158db883c943db5cb74a294` |
| `feat/simulator-lifecycle-core` | `bae7c0880ac2c818def7ee62ba397238dab0bd5a` |

## Recovery

Fetch tags, verify the intended commit against the table, then recreate only the
specific branch needed for recovery:

```powershell
git fetch origin --tags
git branch <retired-name> <retained-commit>
git push -u origin <retired-name>
```

If that branch still exists locally, verify its tip before pushing it; do not
replace it blindly. A full private pre-deletion Git bundle and before/after remote
manifests are also retained under
`artifacts/git-cleanup/20260904T062424Z/branch-retirement/`.

## Completed local cleanup

After explicit approval, all **29 selected local branches** were deleted and
**12 obsolete cache-only worktrees** were removed. The owner then approved
archiving and removing the nine obsolete artifact checkouts. Their 4,264
non-cache local files were verified in one private ZIP before all nine folders
were removed. Local branches decreased from **38 to 9**, and worktrees decreased
from **30 to 9** (21 removed in total).

Each removed checkout's exact source commit is retained by the archive tag and
recorded below. The existing streaming draft and reject file were verified
against the preserved copies; they are unchanged.

The remaining local branches are `main`, `codex/integrate-current-development`,
`codex/client-convergence-v2`, `codex/client-streaming-telemetry`,
`codex/preserve-assassin-sdr-loadout`, `codex/pve-target-authority`,
`codex/renderer-depth-composite-recovery`, `codex/world-map-exact-dispatch`, and
`feat/simulator-foundation`. They retain the integration review, active source,
dirty draft, PR dependencies, and separately preserved history.

`feat/simulator-foundation` remains on origin because the current
`scripts/setup-wonderbane-vm.ps1` still uses it as its default. Retire it only
after that consumer is updated and validated. Historical workflow push filters
naming retired branches do not recreate those branches; their names remain
historical until the workflow itself is intentionally revised.

## Deleted local refs and worktree outcomes

Local tips can differ from the old remote tips above. Use this table when
restoring a local branch. Original checkout paths and exact operation outcomes
are saved privately in `branch-retirement/plan.json`, `worktree-results.json`,
`local-deletion-results.json`, and `final-state.json` under the recovery directory.
The later `artifact-consolidation/removed-checkouts.json` records the nine
artifact checkout removals; its `final-state.json` supersedes the earlier counts.

| Deleted local branch | Retained local commit | Worktree outcome |
| --- | --- | --- |
| `codex/client-cel-preview` | `7e62365ee5bd4c76397bd111ea9c959e647d074e` | No checked-out worktree |
| `codex/client-convergence` | `6204c7d29841b6425deed6e6b3c720cde38c5a02` | No checked-out worktree |
| `codex/client-extension-bootstrap` | `e78f3ed1982631fd6945f262121516f07546ca2f` | No checked-out worktree |
| `codex/client-extension-map-api` | `0670de6176826464470625047f2d0648a054d2d2` | No checked-out worktree |
| `codex/client-streaming-diagnostics-v2` | `4b047c9333ee8a2c6a7580480a9e7e58f001e709` | Removed clean cache-only checkout |
| `codex/convergence-integrity-gates` | `a7595444504ef4effa28efe4b97c65a4e8bf3839` | Archived local artifacts; removed checkout |
| `codex/evidence-spine` | `8ee3d2c0d81b538d569d6bf95ddd930aed4f6ba3` | Removed clean cache-only checkout |
| `codex/evidence-spine-outline` | `99fff9396c267874388650f9f8b752f6cec971f2` | Removed clean cache-only checkout |
| `codex/graphics-banded-lighting` | `de9367f18a70231740f1f44adefa8458c7df795d` | Archived local artifacts; removed checkout |
| `codex/graphics-baseline-55fb` | `de9367f18a70231740f1f44adefa8458c7df795d` | Archived local artifacts; removed checkout |
| `codex/graphics-diagnostics-client` | `89cefb0fc57f354ab089c4af374b797ceeeeac8e` | Removed clean cache-only checkout |
| `codex/graphics-evidence-integration` | `d58221cacaf30af13d716cd988d3eb39fb06686e` | Archived local artifacts; removed checkout |
| `codex/integrate-preserved-features` | `43be8c9050faff57f5748b8eb74cfe255d22a12c` | Archived local artifacts; removed checkout |
| `codex/integrate-preserved-simulator` | `db7dd16dcd255305f60f53a49d1c1580db94383d` | Removed clean cache-only checkout |
| `codex/integrate-pvp-current-client-data` | `0d55095deaf5fa2eecdd95493ef86168bc9285ce` | Removed clean cache-only checkout |
| `codex/manager-permit-retry` | `015e099a81c2968b880ef7e19cc40c0b4c473677` | Archived local artifacts; removed checkout |
| `codex/modularize-cli` | `900955fb845606014e55b1e818c8c3a58811c6cf` | Removed clean cache-only checkout |
| `codex/non-render-refactor` | `43be8c9050faff57f5748b8eb74cfe255d22a12c` | Removed clean cache-only checkout |
| `codex/non-render-refactor-v2` | `4b047c9333ee8a2c6a7580480a9e7e58f001e709` | No checked-out worktree |
| `codex/patch-align-55fb` | `d482d0feac9acf6dc1c0d5ffd44da8e5d8ffa8ec` | Archived local artifacts; removed checkout |
| `codex/portable-vanilla-diagnostics` | `f6c198018a7892194f92d251bf804757503c1430` | Removed clean cache-only checkout |
| `codex/product-convergence` | `51d3917ff0df3f0111de832090c6f4cd31a82204` | No checked-out worktree |
| `codex/pvp-current-client-data` | `d035f749a3763e92651b278aecfd6e37cfe206b3` | Archived local artifacts; removed checkout |
| `codex/renderer-diagnostics-integration` | `1551a9be2d82fae73fea3ecd085d76698b652819` | Removed clean cache-only checkout |
| `codex/vanilla-diagnostics-release` | `fff93812bd622dac14d4a7d9dc2b04ecc066a21e` | Removed clean cache-only checkout |
| `codex/vendor-dialog-diagnostics` | `02d729808eb389a9565f2a83b93548974d5bbb08` | No checked-out worktree |
| `codex/window-manager` | `ca71a53eb9e7d119c5c82248683ac985c2b6251d` | Archived local artifacts; removed checkout |
| `codex/worker-supervision` | `18efdbac1f62fb8cab1402d883fd568316507b3c` | Removed clean cache-only checkout |
| `codex/wreck-texture-cache-swap` | `99b37c7f4140db1f465d834c089b9aa7b1bc761b` | No checked-out worktree |

## Consolidated historical build archive

The private archive is
`artifacts/git-cleanup/20260904T062424Z/artifact-consolidation/retired-builds.zip`.
It contains **4,264 files**, grouped by former branch, in **23,323,923 bytes**.
Its SHA-256 is
`2d753b052b494c9cfd7c174864b14de77921da57a25346c36863753d66657993`.

The adjacent and embedded manifests record original paths, source commits, file
sizes and hashes. Every archived file and ZIP CRC was verified; the source
inventories and hashes were checked again immediately before checkout removal.
Only disposable Ruff, pytest, and Python bytecode caches were omitted. Builds,
package metadata, test outputs, and the graphics screenshot remain recoverable.
The archive stays local and ignored. No client deployment or runtime code changed.
