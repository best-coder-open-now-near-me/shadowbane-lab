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

## Source and qualified release

PR [#170](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/170)
merged at `420deb91f4c9579239d73b4133bb3ff4ed3a63f2` after all 15 hosted
checks passed at `cd3f341b143118e7e50930cf898335661e2e65e4`. Independent
review and 75 focused tests passed. The new concavity tests fail against the
original production implementation and pass against the correction.

Graphics-preserving release `590d36007eeb16dd1430ce324f13818e0e8741af` is
pushed on `codex/native-group-command-release-20261010`. It preserves the exact
native/assets trees from .103/.66 release `dc6cbbb4`; only host routing changes.
The full host suite passed 6,391 tests with 44 optional skips. Independent review
verified all 16 package stages, 1,566 archived source files and all 491
source/wheel/installed modules. Both profiles passed 107 movement, 86 combat and
245 actor IPC cases without skips, including coordinate-parent continuity.
Six desktop startup checks and one worker startup check passed.

Private evidence is under `artifacts/bot-deploy/20261012-host104`:

| Receipt | SHA-256 |
| --- | --- |
| Full host attestation | `43795eb26aef75c2fd96f56856cba71692fc504f994a2f3014c6a3890e1aee58` |
| Qualification | `053325bf8c4ad273c97101cc2c16559a2c6998eea4495c9f0629e6539b28d93f` |
| Host wheel | `06903f17281e5dce966f763cb428144a742fffc79d5538a1392f132983e5933b` |
| Source archive | `89982138b49d6283b3dcc5dad7ff843d52566be2ae5a7d90ca775aa1a12c0dc8` |

Installation is pending the fresh VM baseline and reviewed concrete host-only
plan. The current native .66 DLL and client resources remain in place. User
settings, history and learned navigation data must be preserved without retained
rollback software. Next: install the qualified host, resume upkeep and validate
one fresh grouped `/come` for route efficiency.
