# Rendering and non-render refactor boundaries

This is the working merge contract for development after the 2026-09-01 client convergence. It is
an ownership map, not a new framework: its purpose is to let renderer and non-render changes proceed
without repeatedly resolving the same native and packaging seams.

## Stable branch base

All new production work starts from `codex/client-convergence` after it contains:

- diagnostics-client investigation tip `7245478`;
- preserved production client features;
- graphics extension 1.6.1; and
- the semantic conflict resolutions and dual-profile validation recorded by its merge commits.

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

The shared seam files are integration-owned. Renderer or non-render branches may change them only
when their slice cannot be completed through an existing API, and such changes should be isolated in
a small commit so they can be replayed once during convergence:

- `native/wonderbane_extension/extension.cpp`
- `native/wonderbane_extension/extension_api.h`
- `native/wonderbane_extension/extension.rc`
- `native/wonderbane_extension/CMakeLists.txt`
- `src/shadowbane_lab/client_extension/package.py`
- client-extension launch and publish scripts

## Non-render refactor backlog

The first production slice is an exact-process native observation snapshot. A single request must
bind progression, training, and player state to one process ID, process-creation FILETIME, capture
timestamp, and snapshot token. The current three-command PowerShell collection remains available as
compatibility aliases, but the exporter should consume the atomic snapshot so a report cannot mix
states from different client moments or a reused PID.

The non-render slice implements the ownership checkpoints as follows:

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
   passive production of the documented `camera_state` object. Until that producer lands, a run
   with identity-bound graphics status is honestly incomplete for camera state rather than silently
   falling back to guessed memory addresses.

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
- Win32 Release builds and CTest for both `full` and `diagnostics-only` profiles;
- focused compatibility tests for any retained command or public import alias; and
- a small pushed commit before the next ownership area begins.
