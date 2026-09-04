# Navigation inspector: developer and owner handoff

Prepared 2026-09-04. Implementation has started on `codex/navigation-inspector`;
see the [implementation, usage and current todos](../navigation-inspector.md).
Publisher, viewer, controls and replay are implemented in draft PR #27. Exact
package validation is complete; the [acceptance receipt](../navigation-inspector-acceptance-20260904.md)
identifies the tested source and package. The coordinated live acceptance remains pending. The
starting-point terrain observations below are historical, not a fresh terrain audit.
The owner wants this surface before further pathfinding tuning, to support
reliable `/go` and `/pve` movement.

## Objective and starting point

Deliver a complete in-client navigation inspector that compares the raw search
path, final movement route, character clearance, modeled obstacles, and actual
movement. A developer and the owner should be able to identify whether a failed
approach comes from missing map data, search, smoothing, clearance, movement
execution, or recovery decisions using one captured failure.

Use `codex/integrate-current-development` at this handoff's containing commit.
Its product source derives from `da109b04bc80bdb9ac451846e936c75082635396`;
`607282aae2d6190045d6252b4f03e2fbf593874b` is the pre-handoff review checkpoint.
PR #25 remains the proposed integration into main. Main is still the older
release and should not be the feature base before that integration is accepted.

The terrain developer's completion claim has not been verified in published
source. Read [the terrain status check](terrain-delivery-check-20260904.md).
At this snapshot, `031de7e` adds merge-workflow/validation files to convergence,
not the terrain repair itself. Do not treat it as a terrain-enabled base. The
inspector can proceed independently; integrate the accepted terrain change
through its own reviewed commit before combined visual acceptance.
The staged v2 delivery correction at `3b344f0` still fails before generation or
validation and has no uploaded artifacts; it does not change this starting point.

The retired `codex/navigation-debug-overlay` ref pointed to `bc076d7`, an old
renderer checkpoint. No dedicated inspector implementation is present in the
current integration tree. Earlier chat claims are not an implementation handoff.
If a separate patch is recovered, inspect and validate it against this base.

## Ownership

| Owner | Responsibility |
| --- | --- |
| Inspector developer | Diagnostic contract, planner/controller publishers, native viewer, controls, regression tests, exact build/package evidence, and one review branch. |
| Project owner | Identify the known clipping route and representative slope/camp; review the legend and usability; perform the coordinated testing-VM acceptance with the developer. |
| Terrain developer | Finish and verify terrain source/build delivery separately; coordinate shared native startup and build-file changes. |
| Integration owner | Reconcile shared files, record accepted source/package hashes, and coordinate one testing build. This role may be held by the inspector developer. |

Use one new implementation branch, suggested `codex/navigation-inspector`, from
the containing review head. Check remote names before creating it. Use one
isolated worktree when implementation begins; leave the normal checkout on main.
Target the integration branch while #25 is open, then reconcile onto accepted
main. Commit and push coherent checkpoints. Implementation now uses codex/navigation-inspector in its isolated worktree;
PR #27 targets the integration branch. The normal checkout remains on main.

## Existing boundaries to extend

- `src/shadowbane_lab/travel/pathfinding.py`: publish both ordinary and reachable-
  frontier plans. `_search()` produces raw cells, but `AStarRoute.cells` currently
  receives `smoothed`. Capture raw cells at that seam without changing the
  existing route contract or calculating a second route for display.
- `travel/adaptive.py` and `travel/controller.py`: publish the active waypoint,
  actual position samples and genuine command/stall/escape/replan/terminal events.
- `pve/approach.py`: publish selected-target approach, reposition and camp return
  through the same contract, including native-chase phases with no A* route.
- `travel/terrain.py`, `world_data/terrain.py`, and `world_data/object_navigation.py`:
  supply height and obstacle provenance. Density masks do not locate exact trees.
- `native/wonderbane_extension/cel_shading.cpp`: the reviewed scene/UI boundary
  and camera capture already exist. Add one narrow viewer call through that owner.
  Keep protocol parsing, geometry preparation and drawing in dedicated modules.
- Preserve camera observation, scene/depth ownership, transparency and OpenGL
  state-coherence work already contained in the source. Coordinate edits to
  `CMakeLists.txt`, native startup, graphics controls and Python launch wiring.

## One shared diagnostic contract

Use a versioned, bounded, process-bound snapshot transport consistent with the
existing native channels. Include exact PID plus process creation identity,
session/zone identity, sequence, sample age, map revision and route revision.
Reject torn, stale, non-finite, wrong-process, wrong-zone and oversized frames.
Report truncation and unavailable data explicitly. Producer failure must not
change route selection, input dispatch or cancellation behavior.

Each snapshot should contain:

- Raw A* cells and the final route/destinations actually given to movement.
- Active segment/waypoint, target or camp destination, and arrival radius.
- Physical blockers, learned blockers and traversal costs with provenance.
- Character radius, movement uncertainty and margin used for clearance display.
- Actual player trail and controller-emitted lifecycle events, with timestamps.
- Coordinate convention, origin, units and sampled elevation/provenance needed
  to place the data in the correct world scene.

Keep the raw physical-obstacle representation separate from the expanded planning
grid. Audit the swept character corridor against original blockers; do not
inflate already-expanded cells a second time. Mark object-density evidence as
uncertain, never as verified collision geometry. A clear modeled corridor means
only that the available model permits it.

The renderer consumes diagnostics. It must not infer stalls from a static route,
issue input, select targets, learn obstacles, or change planner/controller policy.
Changes to those behaviors belong in later focused work after diagnosis.

## In-game presentation

Provide independently selectable layers and a visible legend:

| Layer | Purpose |
| --- | --- |
| Raw search path / final route | Identify a shortcut introduced by smoothing. |
| Swept clearance corridor | Show character-width overlap despite a clear centerline. |
| Physical / learned / uncertain obstacles | Explain what is known, learned or estimated. |
| Active waypoint / destination / arrival radius | Show the current movement objective. |
| Actual movement trail | Expose divergence from the route. |
| Command / stall / escape / replan / completion / failure | Explain controller transitions. |

Use the accepted scene camera, viewport and depth at the world/UI boundary.
Normal rendering is depth-tested with depth writes disabled; optional x-ray is
visually distinct. Preserve UI ordering and restore all touched graphics state.
Verify the LT/LG-to-world transform against observed movement before acceptance.
Sample terrain elevation along route segments, not only at the player or endpoint.
If elevation is unavailable or ambiguous, show an explicitly identified projected
view/unknown-height state rather than presenting guessed heights as world truth.

Include layer toggles, live/frozen state, manual freeze and freeze on terminal
failure. Keep a bounded event/trail history and save a reproducible diagnostic
snapshot with source/build identities, route/map revisions and coordinate data.
Saving and transport must not block the render thread. Keep live captures in the
existing ignored diagnostics locations. A navigation-layer failure must not affect
normal gameplay; diagnostics-only builds must not acquire navigation draw hooks.

## Delivery checkpoints and acceptance

1. Freeze the diagnostic contract and add publishers at the existing seams.
   Verify raw versus smoothed capture, reachable-frontier results, actual waypoint
   progression, controller-owned events and producer failure isolation.
2. Complete the native viewer, terrain-height alignment, controls and saved-frame
   inspection. Test wrong identity, stale/torn frames, capacities, invalid values,
   graphics-state restoration and cleanup through the production code paths.
3. Validate the combined source: focused travel/PvE regressions, relevant full
   Python/quality checks, Win32 full and diagnostics-only builds/CTest, and package
   boundaries. Prove the new viewer is compiled and called; inherited green CI
   alone is insufficient. Record exact commit, profile, DLL/package hashes and
   measured frame-time cost with the overlay off and on.
4. Coordinate one testing-VM acceptance package. First verify open-ground `/go`
   alignment, then a slope with camera rotation, then the known tree/wall clipping
   route. Confirm raw/final paths, corridor and actual trail stay aligned and
   normal occlusion differs correctly from x-ray.
5. Exercise PvE approach, a stall/replan, camp return and cancellation. Freeze and
   reload a failure so both people can explain it from the evidence. Compare
   overlay-off behavior and verify terrain, transparency and UI remain correct.
   If terrain blending is included, record its separately accepted source and
   repeat the established boundary-tile check on the combined package.

Checkpoints are reviewable commits toward one complete inspector. The delivery
is complete only when the publisher, viewer, controls, saved evidence and live
acceptance work together. Do not request repeated exploratory VM installs for
known-incomplete builds. Build and test first; coordinate the bounded live pass
with the owner once the exact package is ready.

## Required final handoff

Report the pushed branch and full SHA, review destination, source inclusion of
terrain (or its explicit absence), exact validation runs, package/profile hashes,
where it was deployed, live acceptance result, remaining limitations and next todo.
A workflow, generated payload, version label or successful old target does not
prove the feature is in the delivered binary.

Next todo: use the verified package and receipts to perform the bounded live
pass above with the owner. Planned geometry is explicitly
projected until final terrain elevation is observed. Terrain delivery remains
a separate follow-up; this package does not contain that repair.


### Destination execution correction (active)

The owner confirmed continued movement after the first camera-enabled `/go` run
reported completion. A center click is not a verified immediate stop. The current
full-radius directional actuator must be replaced by destination-aware clicks
and observed arrival before more visual acceptance. See the dated acceptance record.

The read-only minimap investigation identifies ArcMapHud object/control vtables
at RVAs `0x116da48` / `0x116da0c`. Screen-to-world is `0x661010`; the inverse
world-to-map function is `0x661270`. The projection uses parent-local child control
ID `0x4a` when present, otherwise the parent rectangle. The observed content vtable `0x1169ec0` uses getter slot `+0x1c` -> thunk
`0x8ddc` -> `0x56c3e0`, which copies the control's `+4` rectangle.
The initially assumed generic getter `0x25167` is not this content-control slot. Scale is the float at `0x11661a4`
(approximately 0.13) multiplied by live zoom at `+0x37c`. The center-position
getter `0x661440` reads the same player pointer/position getter already owned by
native position observation. LT increases to the right; LG increases upward.

The verified running `3534418` client has parent rectangle `(1710,14,1920,224)`,
child rectangle `(3,3,207,207)`, center `(1815,119)`, and zoom
`2.078929901123047`. A 45-unit waypoint projects about 12 pixels from that center,
whereas the old actuator always selects its 82-pixel radius. The native minimap
reader and its projection tests were committed as `ab9b367`. The next source checkpoint
wires both travel and PvE to bounded absolute destinations, verifies stationary arrival,
and removes the assumed center-click stop. PvE observes settling on coherent frames
without dropping combat actions. Regression tests cover pass-through overshoot, slow
drift, changed/ambiguous geometry, coarse zoom, cancellation and action sequencing.
This source is not yet a deployed or live-accepted fix.

Next todo: build the exact committed correction, verify package/runtime identities,
then repeat one short owner-assisted walk with post-arrival position evidence. Only
then resume normal/x-ray, slope, obstacle and PvE acceptance.
