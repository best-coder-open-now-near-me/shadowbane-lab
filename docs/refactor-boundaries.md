# Client convergence ownership boundaries

This is the working merge contract for development after the 2026-09-01 client convergence. It is
an ownership map, not a new framework or a pair of product branches. Its purpose is to keep one
continuously integrated client while preventing renderer and non-render code from taking ownership
of each other's runtime responsibilities.

## Integration branch policy

`codex/client-convergence-v2` is the only long-lived, advancing product and experiment branch.
Rendering, non-render, streaming, and diagnostics are ownership lanes within that history, not
parallel release lines.

Risky or concurrent work may use a short-lived topic branch from the latest convergence tip. A
topic must remain a small reviewable slice, pass the shared validation matrix, and merge back
promptly. The topic branch must not become a second integration base or accumulate unrelated work.

The former v2 workstream names are frozen recovery aliases at their shared pre-policy tip:

- `codex/non-render-refactor-v2`;
- `codex/client-streaming-diagnostics-v2`.

Do not advance or delete those aliases. Retire them only after Git confirms that convergence
contains their complete histories and the containing convergence tip is published.

All runtime variants build from convergence. In particular, the plain VM uses the compile-time
`diagnostics-only` profile from the same source as the testing VM; it does not require a separate
diagnostics product branch.

Do not base new slices directly on `codex/graphics-diagnostics-client`,
`codex/graphics-banded-lighting`, or the older preserved-feature branch. Those remain evidence and
recovery refs, not parallel product bases.

## Ownership map

| Surface | Rendering slice owns | Non-render slice owns | Shared integration seam |
| --- | --- | --- | --- |
| Native draw path | draw classification, fixed-function mirror, cel lighting, depth/normal/class targets, scene composite, UI exclusion | none | status fields may be consumed read-only by diagnostics |
| Graphics diagnostics | per-present timing, graphics context, depth/composite counters, graphics-control state, and passive camera/view/projection samples | capture, bounded ring drainage, sealing, spatial correlation, reporting, and exact-process validation | additive `camera_state` producer schema under versioned graphics status |
| Native client services | no travel, manager, or action policy | event transport, world-map capture, performance records, native snapshot inputs | `extension.cpp` startup/rollback and `extension_api.h` |
| Runtime control | graphics presets and render-thread application | launcher selection and observation only | versioned graphics-control mapping |
| Package and launch | renderer DLL/version and reviewed graphics evidence | immutable/runtime-drift policy, publication, cleanup, launch orchestration | CMake, resource/version files, package manifest, launch/publish scripts |
| Simulator | none | rules, builds, policies, replay, search, and deterministic evidence | product convergence only; no native-render dependency |

The shared seam files are integration-owned. Short-lived renderer or non-render topics may change
them only when their slice cannot be completed through an existing API, and such changes must be
isolated in a small commit and merged once into convergence:

- `native/wonderbane_extension/extension.cpp`
- `native/wonderbane_extension/extension_api.h`
- `native/wonderbane_extension/extension.rc`
- `native/wonderbane_extension/CMakeLists.txt`
- `src/shadowbane_lab/client_extension/package.py`
- client-extension launch and publish scripts

## Non-render ownership backlog

The first production slice is an exact-process native observation snapshot. A single request must
bind progression, training, and player state to one process ID, process-creation FILETIME, capture
timestamp, and snapshot token. The current three-command PowerShell collection remains available as
compatibility aliases, but the exporter should consume the atomic snapshot so a report cannot mix
states from different client moments or a reused PID.

The non-render lane implements the ownership checkpoints as follows:

1. Exact-process observation is composed in `client_observation/native_snapshot.py`; focused
   observation commands remain compatibility surfaces.
2. Manager wire schemas and public imports remain in their existing owners, while durable
   heartbeat, permit, stop, and receipt replacement is owned by `manager/record_store.py`.
3. Package evidence is loaded and the disposable tree inventoried once per audit. Immutable
   publication and reviewed runtime drift are policies over that result; the mutable-path allowlist
   is owned by `client_extension/runtime_drift.py`.
4. Exact process selection remains in diagnostics/manager process inspectors, package cleanup
   remains in the verified package transaction, and the bounded graphics startup wait is owned by
   `client_extension/graphics_status_wait.py`. Evidence capture and sealing remain in diagnostics
   and evidence modules. None of these services owns renderer hooks or state.
5. The preserved simulator line is merged only at product convergence. Canonical affiliation
   interchange already owns serialization, with the byte codec retained as a compatibility facade;
   rollout search remains in `rollouts/open_builds.py`, and bracket construction now belongs to
   `rollouts/builds.py`. Scenario-coupled policies remain with their scenario runner. Existing
   `rollouts` and `rollouts.duel` imports and CLI commands remain compatible.
6. Capture-once diagnostics samples reviewed native LT/LG/altitude on the process-metric monotonic
   clock and seals renderer camera rings through `diagnostics/camera.py`. Diagnostics owns exact
   identity validation, retention, gap accounting, and offline correlation. The renderer owns only
   passive production of the documented `camera_state` object. Extension 1.6.2 supplies it from
   unique base-stack fixed-function state per present; ambiguous frames fail closed as producer
   drops rather than falling back to guessed memory addresses.

This is intentionally distributed ownership, not one launch god-object: exact identity, package
retirement, status validation, and evidence sealing have different failure and authority models.

## Merge and validation rules

- Renderer code may add versioned diagnostic fields; it must not own capture retention, report
  sealing, or manager decisions.
- The renderer camera producer must declare how it selects the stable world view, emit normalized
  forward vectors and complete matrices, and preserve monotonic sequence/drop accounting. The
  diagnostics consumer must not reinterpret heuristic alignment as camera mapping authority.
- Non-render code may read renderer evidence; it must not install draw hooks, copy framebuffers, or
  mutate OpenGL state.
- Diagnostics-only builds must remain passive. A new service is full-profile-only unless its entire
  purpose is identity-bound observation and it performs no renderer or client mutation.
- One process identity must flow through every observation in a diagnostic bundle. PID alone is not
  identity; creation FILETIME and executable identity are required.
- The original renderer remains the fail-safe path when capability checks, shader creation, frame
  resources, or reviewed imports fail.
- The untracked network residency launcher is outside this plan and must not be run or incorporated.

Every shared checkpoint requires:

- `git diff --check` and no unresolved merge markers;
- the complete Python suite with declared dependencies;
- Ruff lint and PowerShell parser checks for changed surfaces;
- Win32 Release builds and CTest for both `full` and `diagnostics-only` profiles;
- full-renderer and diagnostics-only package-boundary checks;
- focused compatibility tests for any retained command or public import alias; and
- a small pushed commit before the next ownership area begins.
