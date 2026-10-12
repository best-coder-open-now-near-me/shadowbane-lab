# Use the existing fine grid from the first travel leg

The installed .104/.66 run arrived, but the user reported that its initial route
was not fine enough. Retained evidence index
`de499176c62cdacc223b480f7c181a294c052c875ab2915cf4da3e0881273add`
under `artifacts/bot-deploy/20261012-host104/come-4b46d8-evidence` records arrival
63.9466 units from the goal inside its 75-unit radius, 25 accepted destinations,
two progress refreshes, six replans and three backtracks at 21.016, 29.000 and
35.734 seconds. The last dispatch was at 40.125 seconds. Repeated initial
destinations and stationary observations occurred at 16.406-20.641 seconds.
Upkeep was maintaining after completion. The output does not retain candidate
route polylines and cannot assign each stall to a particular coarse/fine choice.
This run and the earlier .103 run used different routes; their counts are not a
controlled performance comparison.

## Historical subgrid is retained

The existing implementation introduced at `e8b24b57` remains the planner. An AST
comparison of `WeightedAStarPlanner.plan_refined` and
`SparseNavigationMap.mark_refined_learned_blocked` in installed release
`590d3600` against `7e719d6f` finds identical functions, ignoring formatting.
The historical [navigation acceptance](navigation-inspector-acceptance-20260904.md)
and [handoff](handoffs/navigation-inspector.md) record a 20-unit global grid,
10-unit local grid and bounded 120-unit refinement after collision. The accepted
cold dense route had one stall/backtrack and two replans, settling 3.047 units
from the goal. Its warm repeat had no stalls, backtracks or replans and settled
3.155 units away. It retained fine child `(8597, 7109)` and conservative coarse
parent `(4298, 3554)`. That warm run initially used the global coarse detour;
it did not prove fine planning from the first dispatch.

Later changes indexed learned children, separated terrain-derived blockers for
bounded resampling, and added exact-world corridor/cost checks. They did not
remove the subgrid routine. Before this change, the routine was invoked after
learned-obstacle recovery. This change uses that same routine from the first
leg and continues its bounded local slices along a retained coarse itinerary.

## Route and dispatch boundaries

A coarse route retains its mandatory bends and original destination. Each fine
leg targets the next unreached coarse waypoint with the existing six-coarse-cell
maximum distance. Successful local completion advances the itinerary or creates
the next bounded slice; it neither rebuilds the coarse route nor spends an
obstacle-recovery replan. A changed map token, an invalid current corridor or
obstacle recovery still triggers normal replanning. Completing a coarse planning
horizon obtains a new horizon without treating successful progress as failure.

Fine search keeps the existing clearance, learned child evidence, structural and
terrain provenance, and costs. Its exact grid validates the world-space route
corridor and follower shortcuts. If fine search or that corridor is unavailable,
the remaining coarse route and its own grid stay in use. No direct obstacle
bypass or fabricated building footprint is introduced.

The route cursor and active leg participate in the existing proposal/acknowledge
transaction. A deferred dispatch does not spend an attempt, skip a required bend
or learn a blocker. Physically observed passage of a local endpoint survives
that deferral, using the follower's existing swept-waypoint predicate. A local
endpoint is never global arrival: the original destination still requires an
actual in-radius observation and the existing independent arrival confirmation.
Session and attempt bounds continue across all legs; recovery limits retain
their obstacle-recovery purpose.

Model bounds alone are not occupied world geometry. A future obstacle ingestion
slice needs qualified placed-instance transforms and collision semantics before
it can add a distinct navigation obstruction layer. This change does not claim
that native movement supplies building-avoiding pathfinding.

## Validation and delivery

Geometric regressions cover structural and costly concavities from the first
fine leg, retained later bends, persisted fine children, safe coarse fallback,
map changes, more successful fine slices than the recovery budget, deferred
slice/bend transitions, original session expiry and physical final arrival.
The relevant travel, pathfinding, corridor and command-line suite passes 228
tests. Native movement and runtime versions are unchanged. Package qualification,
installation and a new live travel acceptance remain separate follow-up work.
