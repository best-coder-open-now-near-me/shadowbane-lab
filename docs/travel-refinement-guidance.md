# Preserve detour guidance during local route recovery

The installed .103/.66 `/come` completed within its 75-unit arrival radius, but
it spent much of the run repeating stopped destinations and backing up. Retained
evidence index `1fa842b16a0ddd27d57990adbf80c86ca9c6113823562404b254f990d473707e`
under `artifacts/bot-deploy/20261011-host103/come-0c8dd198-evidence` records 60
accepted destinations, 31 progress refreshes, six backtracks and seven replans.
The last dispatch occurred at 83.672 seconds; final distance was 37.8776 units.
Passive observations retained the same operation while the native scene changed
from 1 through 5. Automatic upkeep resumed after completion. The retained native
ring was read after completion and does not contain every continuation receipt.

The trace contains stationary positions and repeated destinations, but not the
candidate route polylines or costs. It cannot attribute every recovery event to
one planner decision. Independent production-code reproduction does establish a
specific defect: after finding a coarse route around a concave barrier, local
refinement projected its bounded endpoint straight toward the global goal. That
could send the bot deeper into the pocket which the coarse route already avoided.

Local refinement now targets the next unreached mandatory coarse waypoint,
clipped by the existing distance bound along that leg. It skips only waypoints
whose own arrival radius is already physically satisfied; the final goal's larger
radius is not borrowed. Fine-grid search, cost handling and corridor checks remain
in use. A local detour endpoint remains a frontier and cannot declare global
arrival. Failed refinement retains the coarse route.

Geometric tests cover a long concavity with structural blockers and with costly
boundaries, accepted obstacle learning, frontier continuation, failed refinement
and an unobstructed final leg. Existing learned map state and operation-level
session, attempt and replan limits already survive follower replacement; this
change does not invent another recovery timer or reset rule. Repeated stationary
failures may still require obstacle learning. Live efficiency improvement remains
to be validated after package qualification and installation.
