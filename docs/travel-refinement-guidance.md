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

## Installed host

The fresh .103 baseline
`00b82b33eb996ad0965c83e1a87f1ada703436ad4f1669900c35b4a750945814`
verified the current game and worker, 491 modules and 9,659 live retained rows.
Five unstable live files were recorded without preservation exemptions.
The reviewed concrete host-only plan is
`761672dfa5053f10fd32da4ec20c97029af58d37c6c68bffa1669a2e6ae3331e`.
After normal Pause and exact old manager/worker closure, the switch and activation
verified 9,657 stopped-state records with zero exclusions, 491 installed modules
and ten typed startup changes. There were zero client-file writes. Live and
stopped row counts are distinct captures, not an equality waiver.

| Installation receipt | SHA-256 |
| --- | --- |
| Prepare | `dee3be2af59b5fd15655b394bdd4971d20d961e93839749c938f8ac31711eb45` |
| Stop | `cf7a75a1b6c6e81e30b06e515ab299530e367bfe8e25eb43d53be233e0cfb8c1` |
| Apply | `da05b09019c67e3f3fefbfc3c1a671fab7111a79d55e6da836cd0bec8544532e` |
| Shortcuts | `004284bf50db3012ce677b678188c21f073bcbb49074a47f8d8281d5a287113c` |
| Activation | `d5f643d85ab9acac80a96ca5c1475b9ff0f24c5db69c1f3199341ef474c39b38` |

Host .104/native .66 is installed and activated from release `590d3600`.
Manager 3940/parent 2280 and worker 9144 are healthy. Client 6304, lifetime
134362493784203356/window 328578, retains the exact native .66 DLL
`9451ea36b4069dec028f1469ea5084aa1a0b9a443b3e72c10dce06020c533d01`.
No game restart, command replay or rollback copies were required.

Normal Resume returned success. The current listener and worker are healthy,
with no active or queued operation; upkeep returned to current maintaining.
The coverage snapshot is four buff groups present and concoction application
pending, not proof of all five groups applied.

## Live outcome and remaining precision work

The fresh .104 operation `operation-4b46d8d13295c2a94fd55f0390ee3d2f`
completed within the 75-unit arrival radius at 63.9466 units. Private evidence
index `de499176c62cdacc223b480f7c181a294c052c875ab2915cf4da3e0881273add`
is under `artifacts/bot-deploy/20261012-host104/come-4b46d8-evidence`. It issued 25 accepted
destinations, six replans and three backtracks at 21.016, 29.000 and 35.734 seconds;
last dispatch was at 40.125 seconds. Initial movement stalled around 16.4-20.6
seconds. Upkeep resumed after terminal success. Different route lengths prevent
using duration alone as a before/after improvement measure.

The user's initial coarseness observation is consistent with the source: initial
planning remains coarse and fine refinement is normally recovery-triggered.
The next production slice should retain a coarse itinerary while refining its
successive legs from the outset, without spending recovery-replan budget on
successful local-slice continuation. No flawless obstacle avoidance is claimed.

Local retirement receipt
`879ba8af34f15bdbcfe4374bdd28d68e019afdff6d1361093d9d2222f847d240`
records removal of one obsolete staged .103 wheel (1,803,759 bytes); all 197
nonlisted files are unchanged, with current B66/source/evidence outside scope.
Guest obsolete-host retirement remains pending review and execution.

Remaining: finish guest retirement and document its receipt; implement and
validate finer initial routing as a separate source slice.
