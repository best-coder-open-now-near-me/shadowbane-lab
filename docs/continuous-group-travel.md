# Continuous group travel

## Measured failure and scope

The October 11 host .102 / native .65 Treehugger `/come` moved Umbra toward
Rooty but did not arrive. Existing worker and native records identify operation
`operation-7f20bd7465a97a820ed75c328ff89120`. All 17 destination submissions
were accepted; median endpoint spacing was 50 world units and median dispatch
interval was 2,101.5 ms. Final distance was 188.08 units against a 75-unit
arrival radius. A* was enabled, with no direct fallback or learned replan.
A native segment labeled `direct` does not mean planner fallback.

The native stop was `scene_changed`, at tick 84484828, with a 79 ms update
interval. The matching lifetime publication changed only the actor's parent:
actor, world, window and character identity remained unchanged. Native event
sequences 1 through 21 were contiguous with no reported drops. This is separate
from the earlier .101 producer heartbeat failure.

The user reported obstruction beside a building. Existing records do not retain
all per-step positions or complete planned route geometry, so they do not prove
a collision. Source inspection establishes a coverage gap: active terrain maps
contain height discontinuity blockers and population density costs, but no
placed building footprints. A downward native terrain ray validates endpoint
height, not the horizontal corridor.

## Parity with the accepted `/go` route

The accepted `/go lat long` baseline is source `7e719d6f`. The recorded tree
runs in [the navigation handoff](handoffs/navigation-inspector.md) exercised
measured stall detection, a physical backtrack, learned fine-cell blockers,
local refinement and confirmed arrival. That working bot route is the reuse
boundary; native movement internals are not evidence of usable obstacle routing.

Compared with current shared `main` at `79461bde`, that baseline has byte-identical
`travel/controller.py`, `adaptive.py`, `model.py`, `runtime.py` and `arrival.py`.
Both the current `/go` listener and group-command manager call `_run_travel` with
the active-zone terrain source and shared learned navigation map. The supported
listener and manager defaults agree on a 200 ms observation poll, 2,000 ms periodic
dispatch interval and 300-second session. The manager loads and saves the same
learned-map schema; later persistence changes merge evidence under a lock rather
than removing it. Terrain resampling improvements are separate from the follower.

The substantive execution migration replaced the old calibrated minimap input
adapter with native movement dispatch and a scene-bound operation grant. The
latest `/come` record still used A*, refreshed terrain twice and recorded zero
learned replans before the parent-only ownership interruption. It therefore does
not demonstrate that the established obstacle recovery was omitted or that a
building defeated it. The continuous follower checkpoint is
[`5f5990ad`](https://github.com/best-coder-open-now-near-me/shadowbane-lab/commit/5f5990adbd64117bbc05959127af8b3f1f6e4b6b),
under [PR #166](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/166).
It changes endpoint pacing and qualified waypoint handoffs while retaining that
planner and recovery. New obstacle geometry and speculative native-route
integration are deprioritized until execution parity is established.

## Implementation boundaries

The combined branch is `codex/coordinate-parent-continuity-20261011`, targeting
`main`. It contains the follower checkpoint from PR #166 and native continuity
checkpoint `7dc6355d`; the follower is not a separate deployment.
Its follower work advances native destinations from observed motion and remaining
endpoint distance, recognizes intermediate waypoints passed between samples,
and uses the actual route grid for obstacle and cost-preserving lookahead.
The follower retains each certified partial handoff as a routing hint until
observed reach/passage; later target changes must preserve its corridor and cost.
Hint tolerance comes from the skipped intermediate points, never a large final
arrival radius. Final arrival and session timeout remain separate requirements.

Target replenishment uses measured motion and remaining distance, retains the
50-unit destination bound, and is limited by the configured refresh interval
(default 200 ms). No-motion pending targets are not changed by this early path.
The existing `maximum_clicks` budget counts periodic/recovery attempts; actual
publications, including progress refreshes, remain reported separately. Early
refreshes do not reset the periodic stall sample or consume that retry budget.
This preserves existing bounded PvE and travel configurations while avoiding
endpoint dwell. Grid checks protect modeled obstacles; they do not claim building
geometry that the planner does not yet have.

Coordinate-only travel now has a distinct native acquisition mode. A verified
parent-only transition retains the original producer lease and operation identity,
retires scene-bound references, and advances the scene and grant generation.
The host acknowledges that successor through a correlated continuation command
before sending another destination. Native cleanup must finish first; only the
last accepted world coordinate may be resumed. The acknowledgement can be retried
without repeating movement, and cancellation takes priority over continuation.
Actor replacement, world change, lost lifetime observation, expired authority and
player takeover still revoke ownership. Combat and PvE mixed-action grants keep
their existing policy and cannot use coordinate-only continuation.

The fixed-width movement wire remains schema 3. Capability bit 128 and verbs 54
(coordinate acquisition) and 55 (parent continuation) require a matched host/DLL
update. Missing capability is rejected before coordinate acquisition; there is no
silent fallback to an older DLL. The runner stages waypoint decisions until native
acceptance, deferring unsent proposals during cleanup without consuming movement
attempts or treating the pause as an obstacle. Session and health limits remain
active. Learned obstacle changes from an escape proposal commit only after its
accepted dispatch. No runtime correction is installed by this source work yet.

## Evidence and current todos

Private evidence remains at
`artifacts/bot-deploy/20261011-host102/come-investigation-20261011/`.
The ten-member evidence index SHA-256 is
`d2dde6ab5c589ed338cd28872d421a57baf2e57845d90e2eee2390ee84bbb61a`;
summary SHA-256 is
`1416cadc2f2a29f9ca2fc0cec52a8f05ff600f8292be75473b3df8c3954a7f4b`.
Raw captures remain private. Investigation issued no new command or Resume.
Recorded poststatus had a healthy worker, no active/queued operation, and idle
upkeep after confirmed native cleanup. It is a timestamped observation.

- Complete: preserve and decode the existing live failure; merge .102 delivery
  documentation through PR #165 at `79461bde`.
- Complete: continuous follower source and independent review. Focused routing,
  native travel, CLI and PvE validation passed 288 tests before the final-radius
  regression; 58 final follower/consumer tests and 50 independent corridor/follower
  tests passed afterward. Live acceptance is not implied.
- Complete: native continuity `7dc6355d`, required package IPC gates `c56a3753`,
  and host continuation `4f80596c` are pushed. Native review and 55 native cases
  passed; 28 final host continuation cases include actual cross-process IPC.
- Active: finish independent review of transactional follower dispatch and qualify
  the combined host .103/native .66 update.
- Next: verify the preserved `/go` planner and recovery through the corrected
  native execution boundary, qualify the coherent update, then request one fresh
  live run. Revisit obstacle coverage only if the resulting evidence requires it.
