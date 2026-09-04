# Navigation inspector implementation

Implementation branch: `codex/navigation-inspector`.
Draft review: [PR #27](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/27).
Base: `f2a5ca137b6d524c52bc492cc83081ee55929c71` on
`codex/integrate-current-development`; integration destination is that branch
while PR #25 remains open. This work does not include the separate terrain repair.

## Current status

Checkpoint 1 adds immutable planner and movement events. Both complete and
reachable-frontier searches publish the raw cells before smoothing, the smoothed
path, exact movement destinations and original map evidence. Failed searches
publish a failed plan to distinguish them from the last successful route.

Optional observers receive actual position samples, controller command requests,
waypoint changes, stalls, planned escape, cancellation and completion. Command
requests are not input acceptance or proof of movement. A* travel and PvE route
controllers retain the planner's observer when routes are replaced. No live
transport or native drawing is enabled by this checkpoint.

Checkpoint 2 adds bounded immutable history, manual/failure freeze and strict
saved-capture replay. Zone changes invalidate frozen live placement. The clearance
audit compares the swept circle to original cells, including rounded end caps,
and reports the operator-estimated character radius, uncertainty and margin.
Only measured movement trail vertices have known world height. Planned paths
remain explicitly projected until final world elevation can be verified.

The versioned wire codec binds frames to PID, creation time, session and zone;
checks size, sequence, complete-frame checksum, finite coordinates and producer
lease; and distinguishes a frozen sample from an expired producer. This checkpoint
defines and tests the codec.

Checkpoint 3 connects a real Windows mapping, exclusive producer/panel ownership,
and the native bounded reader. The full extension creates the optional channel
at startup and releases it if startup fails. Diagnostics-only excludes these
runtime sources. Readers reject corrupt, torn, expired, wrong-process and
wrong-zone data; restarting a producer also replaces cached session data even
if its sequence restarts. Panel controls are independently versioned and bound
to the exact process and session.

Checkpoint 4 wires optional live sessions into `/go` and `/pve`. A bounded worker
owns mapping publication and geometry; movement callbacks enqueue immutable events.
The panel may arm the next session for its exact client; the developer override is
`SHADOWBANE_NAV_INSPECTOR=1`. With no armed inspector there is no worker. A missing
channel or diagnostic failure does not stop movement. No drawing or panel UI is
enabled by that checkpoint.

Search evidence and the route currently owned by movement are separate. Direct
travel has an execution route without claiming A* ran. Moving targets update the
actual final destination, and a failed replacement search preserves the route
movement continues to own. PvE records native chase, reposition, camp return and
actual input outcomes. Zone/map provenance comes from the navigation source; an
outdated static PvE map is labeled unavailable after a zone change. Expired zone
observations invalidate live placement, including frozen samples. Frozen evidence
can remain inspectable separately from live placement.

Clearance audits are cached per immutable plan, active route and radius; each
layer has a bounded share of display geometry, so dense history cannot consume
the entire obstacle display budget.

Checkpoint 5 wires drawing through the reviewed scene/UI boundary. Planned
geometry is shown in an explicitly labeled projected map with a visible legend;
only measured trail samples enter the world view. Normal world drawing uses
scene depth without writing it; optional x-ray is dashed and a different color.
The viewer accepts only the current, unambiguous camera and matching viewport.
Shader, texture-unit, matrix, enable, mask, scissor and other touched state are
restored. No draw hooks or inspector runtime sources enter diagnostics-only.
Checkpoint 6 adds the desktop panel (shadowbane-navigation-inspector). Connect
the exact client before starting /go or /pve, select layers, adjust explicit
clearance estimates, and freeze/resume. Save and open strict captures without
republishing them to the game. Expired or unknown-zone evidence remains available
in the projected panel while native live placement expires. Tests exercise real
Tk widgets without showing a window, replay controls and Windows stale evidence.
Source/build identity and the combined acceptance package remain active.

Validation: 212 focused inspector, pathfinding, adaptive travel, travel and PvE
controller, terrain and command tests pass. Observer failure is tested against identical ordinary
route results and movement decisions. Real Windows mapping lifecycle tests pass.
Both Visual Studio 2022 Win32 Release profiles build and pass all 18 native tests;
the navigation test reads the Python-generated golden frame and exercises the
real channel. A hidden-window OpenGL test exercises real occlusion, dashed x-ray,
no depth writes and state restoration with a nondefault GLSL program and multiple
texture units. The local NVIDIA OpenGL 4.6 harness measured 0.145 ms per simple
view and 0.541 ms at the 16,384-line capacity; these are synthetic harness values,
not live-game frame-cost acceptance. Its image and build output stay under ignored
`artifacts/navigation-inspector/`. Generated DLL projects confirm all four
inspector runtime sources are present only in full. Complete panel/package and
live acceptance are pending.

## Active todos

- [x] Capture immutable raw/final plan and controller events; validate behavior isolation.
- [x] Bound saved history/replay and clearance geometry; validate the versioned wire codec.
- [x] Connect and validate Windows transport and full-profile native channel ownership.
- [x] Wire live travel/PvE publishers, active-route ownership and map provenance.
- [x] Wire native drawing and verify real OpenGL depth/state isolation and bounded draw cost.
- [x] Complete the desktop panel and saved-evidence inspection.
- [ ] Active: prepare source/build identity and the combined acceptance package.
- [ ] Validate both native profiles and combined Python/package boundaries; record
  exact source and artifact hashes for the coordinated live acceptance package.
- [ ] Complete the bounded live tests in the [developer/owner handoff](handoffs/navigation-inspector.md).

The worktree is retained for active implementation. Checkpoint pushes are source
preservation and review, not claims that the complete inspector is delivered.
