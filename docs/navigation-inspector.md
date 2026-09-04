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

Validation: 115 focused inspector, pathfinding, adaptive travel, travel and PvE
controller tests pass. Observer failure is tested against identical ordinary
route results and movement decisions. Full viewer and live acceptance are pending.

## Active todos

- [x] Capture immutable raw/final plan and controller events; validate behavior isolation.
- [ ] Active: complete process-bound transport, live/PvE session wiring, terrain
  provenance, native viewer, controls and saved failure inspection.
- [ ] Validate both native profiles and combined Python/package boundaries; record
  exact source and artifact hashes for the coordinated live acceptance package.
- [ ] Complete the bounded live tests in the [developer/owner handoff](handoffs/navigation-inspector.md).

The worktree is retained for active implementation. Checkpoint pushes are source
preservation and review, not claims that the complete inspector is delivered.
