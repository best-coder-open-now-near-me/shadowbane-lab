# Integration and town-workflow catch-up plan

Execution update: September 23. The current review base is
`origin/codex/integrate-current-development`; see the
[inclusion inventory and execution queue](integration-status-20260923.md).
Carpenter is waiting for its building to finish. Guard coverage, vendor recovery
and the passive recorder, and strict diagnostic CI gates are integrated; host
0.3.46 package/CI verification is current. Full town/vendor behavior still needs
the live observations recorded in the execution queue.

Planning date: September 23, 2026. This plan coordinates the repository review,
guard upgrades, Condemn, vendor rolling, and carpenter discovery. It records
planned execution; it does not claim a merge, deployment, or new live acceptance.

## Verified starting point

Use `origin/codex/guard-upgrades` at `74f34a348de7662c49eb2ad05a149ce575d58f92`
as the common product baseline until a reviewed integration candidate supersedes
it. `main` at `047147d` is the final shared destination and is 1,027 commits
behind this baseline. The normal project checkout stays on `main`; feature
work uses isolated worktrees. Existing feature worktrees must not be switched
under their owners.

The movement branch's 27 ancestry-only commits are not 27 missing changes:
`git cherry` finds 11 equivalent non-merge patches already in the baseline,
including controller profiles and newer door work. Seven are merge commits;
nine require further content review. A positive patch difference alone does
not prove functionality is absent. Power Palettes and all other remote tips,
local-only commits, and unpublished drafts also need explicit inclusion status.

Current evidence, not promises about the present live session:

| Area | Established | Remaining |
| --- | --- | --- |
| Guards | Carried-gold upgrades, confirmed spending, Travel and remembered-guard Continue here | Wider census, genuinely new-guard continuation, rank completion and terminal-state qualification |
| Condemn | 30 observed towers / 1,410 current-nation entries; 47 nations at the latest audit | Five unopened Irekei Barracks, wider coverage; nation inheritance/combat behavior remains unverified |
| Vendors | One uninterrupted three-item Create/wait/Keep batch; native navigation and durable records | Automatic recipe/Inventory lifecycle, saved town selection and cross-vendor scheduling, full affix/resource qualification |
| Carpenter | No carpenter-specific implementation or documented failure found in inspected source | User is inspecting the service; intended behavior and failing boundary unknown |

The September 22 CI for `74f34a3` passed its required jobs. Its ideal-transparency
diagnostics fail as documented; production suppression is separately tested.
Test counts do not replace live acceptance or qualify a later integration SHA.

## Parallel ownership

Run a coordinator plus three focused workers. These are work assignments, not
instructions to create duplicate long-lived tasks or activate old tasks.

| Lane | Owner responsibilities | First deliverable | Parallel boundary |
| --- | --- | --- | --- |
| A: integration and reliability | Coordinator owns inclusion inventory, candidate, shared contracts, package and live-test queue | Accurate inclusion map and reviewable integration candidate | Independent of B/C/D analysis and focused source work |
| B: guards and Condemn | One worker owns shared discovery plus both workflow completions | Barracks diagnosis and scoped coverage/terminal-state plan | Can code/test while C works; live UI access is serialized |
| C: vendor rolling | One worker owns vendor plan, policy and scheduler | Automatic multi-vendor capacity run with saved selection | Starts from current guard baseline, not old vendor tip |
| D: carpenter | One worker owns reproduction and boundary diagnosis | Reproducible failure and client/server ownership finding | Discovery proceeds now; implementation scope follows evidence |

Before editing shared files, assign one owner for that checkpoint. In particular,
native command-channel/runtime wiring, shared navigation, manager worker/control,
dashboard/API routing, version metadata and packaging cannot have competing
owners. Feature workers provide narrow commits and interface needs to that owner.
Independent feature modules and fixtures may proceed concurrently. Keep central
dispatch admission, UI exclusion, cancellation and pending-transaction barriers.

## Execution sequence and acceptance

### A. Establish a trustworthy development base

1. Fetch and audit branch/worktree status, ancestry, patch equivalence and actual
   source deltas. Record each lane as included, equivalent, changed, deferred, or
   unpublished. Preserve meaningful drafts and private evidence separately.
2. Reuse the existing consolidation candidate if it can be updated without
   disturbing an owner; otherwise create one explicitly named successor from
   the verified baseline. Document why it supersedes the old candidate/PR.
   Preserve useful ancestry; do not blindly merge old movement content over
   newer code. Door feature completion is not a prerequisite for consolidation.
3. Make README, CONTRIBUTING and the branch map agree on the candidate, exact
   source, remaining work and `main` destination. Label older handoffs historical
   rather than treating every old 'Next' paragraph as a current task.
4. Review and run the required host, native-profile and packaging checks on the
   exact combined SHA. Obtain the required merge authorization/review, advance
   `main`, and set required checks/protection through the normal repo workflow.
   Verify remote ancestry before retiring any obsolete branch/worktree.

In parallel, B/C can branch from the pinned baseline and D can investigate.
They do not need to wait for the administrative merge to begin useful work.
Reconcile through the candidate before packaging; do not form another long
chain of integration-by-feature-branch.

After the candidate is stable, A adds deterministic state-machine/fault-schedule
tests around permit renewal, publication, expiry, observation, cancellation and
persistence/restart boundaries. Assert no duplicate mutation, no dispatch after
authority loss, durable uncertainty, and progress only from qualified evidence.
Replace blanket diagnostic tolerance with reviewed expected-failure signatures;
unexpected failures, crashes or missing tests must still fail the gate.

### B. Finish guards and Condemn as one town-completion lane

1. Inspect one manually opened Irekei Barracks beside the character. Compare its
   exact building identity, roster and menu path with the unavailable attempts.
   Resolve reachability versus different service behavior before changing code.
2. Extend the coverage ledger from fresh observations, distinguishing accessible,
   out of range, unsupported, empty and unverified. Reuse verified towers;
   do not blindly reapply the completed Condemn set.
3. Continue upgrades using existing structure funds plus carried gold only.
   Preserve current jobs, confirmed rank floors/timers/spending and unresolved
   requests. Qualify a newly discovered guard joining the existing area workflow,
   resource exhaustion, normal rank progression, and a positively identified
   maximum-rank condition. 'No offer' is not evidence of maximum rank.
4. Apply the existing whole-nation exclusion policy only to fresh selected
   targets. Reconcile current nation identity/catalog changes; do not expand to
   guilds or individuals. Keep all earlier uncertain transaction records.
5. Show completed and unavailable coverage separately, plus confirmed spending
   and rank state. Stop/pause/restart checks must preserve pending barriers and
   must not replay toggles, deposits or upgrades. Qualify nation inheritance or
   combat separately if a stronger gameplay claim is needed.

Done means the explicitly selected town scope has verified terminal outcomes or
visible explained exceptions, not an unsupported claim of full-town/max-rank
completion. If resources or access prevent completion, report the exact remaining
scope. Use the latest [guard Travel](handoffs/guard-travel.md),
[carried funding](handoffs/guard-carried-gold-0.3.28.md), and
[Condemn handoff](handoffs/guard-crest-lists.md) as source evidence.

### C. Deliver the complete bounded vendor workflow

1. Verify service/recipe identity and current building/hireling navigation on the
   shared baseline. Reuse guard fixes while preserving vendor-specific ownership.
2. Implement automatic recipe and Inventory opening/reopening, with exact native
   owner-thread commands and receipt qualification. Never require manual menu
   preparation as the normal finished workflow.
3. Deliver saved town/building/vendor selection, compatible recipes, durable
   scheduler, progress and Pause/Stop together. Each vendor retains its own
   Create/Keep evidence; the town run references those receipts. Revisit cooking
   vendors without busy waiting or blocking independent source work.
4. Qualify mixed services, changing capacity/rank/resources, inaccessible vendors,
   menu replacement, stale plans, focus/scene loss, interruption and recovery.
   Live acceptance covers multiple vendors across multiple buildings from a
   single Start, without manual window setup, with independently confirmed output.
5. Complete affix classification and the requested confirmed Tier 1/2 exclusion
   behavior only against verified identities and a qualified disposal path.
   Unknowns remain kept. Until that path qualifies, expose the limitation rather
   than describing keep-all batching as complete filtered rolling.
6. Add bounded recurring rolling against the same durable scheduler after
   Create/Keep/disposal are qualified. Before enabling recurrence, settle the
   selected vendors/recipes, desired-result rule and resource/spending limits.
   Stop on those limits, inventory fullness, unavailable access or uncertainty.

The production architecture supports these phases; it must not introduce a
throwaway scheduler. The current accepted scope is one capacity batch per selected
vendor. Recurring rolling is a follow-on completion milestone with an explicit
stop/budget policy; unlimited spending is not inferred. Old uncertain Create/Keep
records stay retained; they
cannot be adopted as new unsent work. See [town vendor plan](town-vendor-plan.md)
and [latest vendor navigation handoff](handoffs/vendor-navigation-1.8.9.md).

### D. Make carpenter scope concrete

1. Record NPC/location, exact build, ordinary action, expected useful result,
   actual result, and ownership/rank/resource prerequisites from the user's visit.
2. Locate the failure: access, menu, missing service/recipe, rejected request,
   completion, or unusable output. Compare a working service on the same build.
3. Start with existing building/hireling/UI observations. Add bounded dialog or
   crafting instrumentation only when needed; retain sanitized fixtures and a
   precise reproduction. The historical [vendor protocol mismatch](wonderbane-vendor-dialog-protocol-bug.md)
   is a comparison case, not a diagnosis of carpenter.
4. Implement a client fix if the server capability exists; otherwise prepare a
   developer-ready server/template/recipe contract finding. Coordinate both sides
   if necessary. 'Usable' does not automatically mean automated crafting.

Done means the agreed ordinary carpenter workflow succeeds through its persistent
result on the reviewed build, or a demonstrated external blocker has a precise
owner and next action. No guessed carpentry recipes or generalized framework.

## Shared testing and delivery cadence

- First gather the two high-value observations: carpenter behavior while the
  user is there, and one manually opened Irekei Barracks when convenient.
- Source work, fixture tests and independent builds can run in parallel using
  separate worktree/output paths. One operator coordinates client actions,
  instrumented captures and activation. For the same character, guards, Condemn,
  vendor work and carpenter tests never compete for menu ownership.
- A guard rank timer alone does not free the client. Use Travel and wait for
  its confirmed idle boundary and settled spending journal before handing the
  character to vendor, Condemn or carpenter work.
- One package owner selects a coherent combined candidate. Keep loaded native,
  host and client identities explicit; run exact-source required checks once per
  candidate, then focused live acceptance. Batch compatible changes to reduce
  restarts, but do not delay a completed fix for an unrelated blocked feature.
- Commit each coherent validated slice, review staged files, push with tracking,
  and record the integration destination plus acceptance state. Record source,
  package and live acceptance separately. Preserve old durable records and test
  their readability/recovery constraints whenever persistence changes.
- Keep broad simulator, renderer and diagnostics decompositions outside this
  catch-up critical path. Fix only demonstrated defects or boundaries needed by
  these workflows; retain a separate prioritized refactor backlog.

## Planning checkpoint and next todos

- Complete: refreshed baseline and reviewed branch/CI claims.
- Complete: parallel read-only assessments of town completion, vendors and carpenter.
- Complete: coordinated plan with owners, dependencies and acceptance criteria.
- Next execution item: A's integration inclusion inventory; B/C focused work and
  D's user-informed reproduction can start alongside it when execution begins.
- Subsequent: reviewed candidate, completed feature slices, shared package/live
  acceptance, then integration and safe retirement. Carpenter scope remains open.

This document is published on `codex/catch-up-plan`, based on `74f34a3`, for
inclusion in the reviewed integration candidate and ultimately `main`. The plan
branch does not itself integrate the divergent history. No existing task or
feature worktree is retired by this planning checkpoint.
