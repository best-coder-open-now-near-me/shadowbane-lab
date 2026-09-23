# Guard and Condemn coverage checkpoint - September 23

Source lane: `codex/guard-coverage`, based on the published catch-up plan at
`179f065`. Integration destination: `codex/integrate-current-development`, PR 25,
then reviewed `main`. This checkpoint is source delivery; it is not installed or
live accepted. Existing guard/Condemn source and durable records remain the base.

## Delivered behavior

Condemn preparations now show every observed building candidate, including exact
identity, name, verified guards, a verified roster without guards, unavailable
rosters with their recorded explanation, and legacy cache-only unverified rows.
Unavailable guard counts stay unknown. Names do not identify buildings and an
unavailable window does not establish range, an unsupported service, or emptiness.
The dashboard shows counts and an expandable, scrollable list whose open state
survives polling. It never expands selected Condemn targets automatically.

A completed roster-only candidate pass where every building is unavailable can
now publish these exceptions. It exposes no selectable targets, and the dashboard
cannot open an empty selection. Ordinary guard/vendor discovery still rejects a
pass with no verified service; interrupted passes remain unfinished.

Condemn job summaries distinguish confirmed selected buildings from remaining
selected buildings. Every selected crest on a building must be proven before that
building counts as confirmed. Counts refer to this selection, not historical town
coverage. No earlier job is scanned, adopted, reset, or replayed.

Guard summaries separate remembered states from current-area states, show guards
outside the current area and last observed rank counts, and retain confirmed gold
spending. An expected post-upgrade rank is not shown as an observed rank. A missing
offer remains unavailable; maximum rank and full-town coverage remain unverified.

All projections use existing retained records. No storage migration, new journal,
additional receipt validation pass, native command, or package version is added.
Candidate details retain the existing 512-building bound. Shared navigation has
only the narrow roster-only completed-pass exception described above.

## Validation

- 292 focused tests passed across guard jobs/control/discovery, Condemn
  preparation/plans/jobs/control/proof caches, vendor discovery, and dashboard.
- After adding explicit ordinary-guard rejection and interrupted-pass checks,
  all 41 guard discovery tests passed (294 distinct tests across these runs).
- Sixteen deterministic crash schedules cover before/after durable accounting,
  four terminal cycle outcomes, immediate/delayed restart, and lost dispatch
  authority. Confirmed costs are accounted exactly once, old receipts remain
  byte-identical, timers do not cause new dispatch, and expected rank is not
  promoted to observed rank.
- Four Condemn partial-progress schedules verify building completion counts and
  fresh-manager reconstruction without replay or durable record changes.
- Ruff and whitespace checks pass. Node parsed the actual dashboard script and
  executed its slot renderer with offline DOM doubles: empty/nonempty selections,
  escaped text labels, expandable details across refresh, and observed guard ranks.
  This is an offline UI smoke check, not browser or game acceptance.

## Remaining todos

1. Integrate this checkpoint into PR 25 and validate/package the combined source.
2. Capture one manually opened Irekei Barracks nearby to identify the actual
   access/menu boundary; guard counts in the five unopened barracks remain unknown.
3. Qualify genuinely new-guard continuation, rank progression/resource exhaustion,
   and a positively identified maximum-rank condition in serialized live sessions.
4. Extend fresh selected scope without repeating the 30 previously verified towers;
   the prior 1,410 current-nation entries are historical evidence, not a new census.
5. Nation inheritance/combat behavior remains a separate qualification.

No live game input, source installation, or client deployment occurred in this lane.
The task worktree stays on its published feature branch until integration is
verified; retirement is deferred while the coordinator depends on it.
