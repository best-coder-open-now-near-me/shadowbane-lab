# Navigation inspector implementation

Implementation branch: `codex/navigation-inspector`.
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
to the exact process and session. No navigation drawing or live command publisher
is enabled yet; those are the active work.

Validation: 154 focused inspector, pathfinding, adaptive travel, travel and PvE
controller tests pass. Observer failure is tested against identical ordinary
route results and movement decisions. Real Windows mapping lifecycle tests pass.
Both Visual Studio 2022 Win32 Release profiles build and pass all 17 native tests;
the navigation test reads the Python-generated golden frame and exercises the
real channel. Generated DLL project files confirm that the channel and protocol
sources are present only in full. Full viewer and live acceptance are pending.

## Active todos

- [x] Capture immutable raw/final plan and controller events; validate behavior isolation.
- [x] Bound saved history/replay and clearance geometry; validate the versioned wire codec.
- [x] Connect and validate Windows transport and full-profile native channel ownership.
- [ ] Active: wire live/PvE publishers, native drawing and panel controls; verify
  frame cost and complete terrain provenance.
- [ ] Validate both native profiles and combined Python/package boundaries; record
  exact source and artifact hashes for the coordinated live acceptance package.
- [ ] Complete the bounded live tests in the [developer/owner handoff](handoffs/navigation-inspector.md).

The worktree is retained for active implementation. Checkpoint pushes are source
preservation and review, not claims that the complete inspector is delivered.
