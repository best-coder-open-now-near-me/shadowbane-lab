# Integration and town-workflow catch-up plan

Execution update: September 24. **PvP resumes alongside random vendor rolling.**
The user set guard investigation aside and then explicitly stopped carpenter work.
Preserve their source, installed runtime and private evidence; do not continue
carpenter implementation, packaging or live tests without renewed direction.

Freshly fetched `origin/main@a91dfd5` remains the canonical base. Vendor source
`a3a5d3782a2ce47b949ef099be197894a1521335` is pushed in draft PR #38, with
native 1.8.31 / host 0.3.51 reserved for the candidate now running package gates.
The completed source slice loads actual recipes, saves an immutable choice per
character/building/vendor, prepares its exact random specification, fills one
available-capacity batch and automatically opens Inventory for Keep. The ordinary
CREATE control preserves game resource/cost checks. New generalized evidence
preserves unknown affixes and cannot be downgraded to legacy Scepter journals.
The full Win32 build, 13 affected native tests and 895 affected host tests
(449 subtests, 4 skips), Ruff and independent source review passed. No installation
or live crafting is implied. Full town scheduling remains unfinished.

The VM still has native 1.8.30 / host 0.3.50 from exact source
`8ba181868fca7ca113f94361b61118ce74a9d4a1`; the user launch entry point remains
WonderBane Vendor Test. Stopping carpenter work did not change the installed client.
Its startup/panel verification, material failure and placement evidence are retained
in the [deployment handoff](handoffs/furniture-response-diagnostics.md).
The later cutout shader fix `6ea434c` is source-only in PR #35; automatic preview
integration and visual acceptance are unfinished.

PvP restart status: freshly fetched `main@a91dfd5` contains the identity,
attack-list command and passive native-event work through `542c632`. Saved
player identity, add/remove/list/clear, command concurrency, party/pet observations,
attacker-key calibration and stale/retired trace rejection have source evidence.
These are not completed automatic combat. Full listed-target binding, attributed
response ingestion, native player selection/attack and PvE-to-PvP recovery remain
unfinished. Native event records still explicitly publish combat_authority=false.

Explicit saved attack-list combat can progress independently of response-driven
retaliation. Offline qualification maps ordinary player selection, native attack
submission and the conditional local combat exit. Dispatcher success only means
handled; Clear Target does not stop the retained combat target. Next is truthful
request submission receipts plus list/party/operation invalidation and guarded
cancellation, preserving native restrictions and reference ownership. See the
[explicit-list combat handoff](handoffs/explicit-list-combat-20260924.md).

Response-driven retaliation remains blocked on server session ordering across
buffered input. The receive buffer can retain bytes across a local character
change; decode-time freshness cannot prove old-character events were fenced. This
limitation does not block explicit saved-list combat. No fight or new user
walkthrough is needed for the current source work. Continue from current main,
not the old native-lifecycle branch. The [PvP plan](pve-pvp-attack-list-plan.md)
retains historical detail; no new attack or deployment has been performed.

Read-only vendor observation on September 24 verified the open random-roll recipe
against the exact installed runtime. Three stable samples agree on the selected
row, activated row and retained Anthame template; Magic is mode 1, table 16.
The seven production slots were empty. Current automation still explicitly
requires Gilded Scepter, so this observation does not qualify dagger automation.
The passive recorder ended normally at 21:16:41 UTC; private captures are retained.
No crafting, inventory mutation, manager job or deployment was performed.

Offline PvP qualification now maps deferred action construction, queue consumption
and disposal, including discard and direct-processing paths. It also proves that
an active socket can retain bytes before a character-generation change and decode
them afterward. Decode-time freshness alone is therefore insufficient for combat
authority. Response ingestion requires a qualified ordered server session boundary (or proven
connection replacement), followed by complete event-to-action identity handling. No user fight
is needed for this investigation; automatic combat remains unfinished.

Planning date: September 23, 2026. The original planning rationale and milestones
below remain useful; their starting inventory is historical. Current status and
next todos are recorded at the end and in the integration inventory. Source
integration, deployment and live acceptance are separate milestones.

## Historical starting point

The initial product baseline was `codex/guard-upgrades` at
`74f34a348de7662c49eb2ad05a149ce575d58f92`; pre-integration `main@047147d` was
1,027 commits behind it. PR #25 supersedes that base and the former serial
integration chain. New feature work branches from freshly fetched `origin/main`
in isolated worktrees. Existing feature worktrees must not be switched under
their owners.

The movement branch's 27 ancestry-only commits are not 27 missing changes:
`git cherry` finds 11 equivalent non-merge patches already in the baseline,
including controller profiles and newer door work. Seven are merge commits;
nine required content review, since completed in the integration inventory.
A positive patch difference alone does not prove functionality is absent. Power Palettes and all other remote tips,
local-only commits, and unpublished drafts are recorded with explicit inclusion
status in that inventory.

Current evidence, not promises about the present live session:

| Area | Established | Remaining |
| --- | --- | --- |
| Guards | Carried-gold upgrades, confirmed spending, Travel and remembered-guard Continue here | Wider census, genuinely new-guard continuation, rank completion and terminal-state qualification |
| Condemn | 30 observed towers / 1,410 current-nation entries; 47 nations at the latest audit | Five unopened Irekei Barracks, wider coverage; nation inheritance/combat behavior remains unverified |
| Vendors | One uninterrupted three-item Create/wait/Keep batch; native navigation and durable records | Automatic recipe/Inventory lifecycle, saved town selection and cross-vendor scheduling, full affix/resource qualification |
| Carpenter | No carpenter-specific implementation or documented failure found in inspected source | Building readiness, intended behavior and failing boundary remain to be confirmed |

The September 22 CI for `74f34a3` passed its required jobs. Its ideal-transparency
diagnostics fail as documented; production suppression is separately tested.
Test counts do not replace live acceptance or qualify a later integration SHA.

## Parallel ownership

Run a coordinator plus three focused workers. These are work assignments, not
instructions to create duplicate long-lived tasks or activate old tasks.

| Lane | Owner responsibilities | First deliverable | Parallel boundary |
| --- | --- | --- | --- |
| A: integration and reliability | Coordinator owns main, shared contracts, package and live-test queue | Merged inventory and verified package completed; coordinate remaining release/live gates | Independent of B/C/D analysis and focused source work |
| B: guards and Condemn | One worker owns shared discovery plus both workflow completions | Barracks diagnosis and scoped coverage/terminal-state plan | Can code/test while C works; live UI access is serialized |
| C: vendor rolling | One worker owns vendor plan, policy and scheduler | Automatic multi-vendor capacity run with saved selection | Starts from current main, with source-only recovery/recorder work included |
| D: carpenter | One worker owns reproduction and boundary diagnosis | Reproducible failure and client/server ownership finding | Discovery waits for confirmed client/building readiness; implementation follows evidence |

Before editing shared files, assign one owner for that checkpoint. In particular,
native command-channel/runtime wiring, shared navigation, manager worker/control,
dashboard/API routing, version metadata and packaging cannot have competing
owners. Feature workers provide narrow commits and interface needs to that owner.
Independent feature modules and fixtures may proceed concurrently. Keep central
dispatch admission, UI exclusion, cancellation and pending-transaction barriers.

## Execution sequence and acceptance

### A. Establish a trustworthy development base

Source consolidation, review, local validation and hosted CI are complete; PR #25
is merged. The normal main checkout is fast-forwarded and required-check
protection is verified. The steps below retain the reconciliation method; safe
retirement remains a separate audit.

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

B/C now branch from current main; D can inspect the service once the building
is ready. Reconcile through reviewed PRs to main before packaging; do not form
another long chain of integration-by-feature-branch.

Source checkpoints added focused fault-schedule and recovery tests. Further
demonstrated gaps should receive deterministic coverage around permit renewal,
publication, expiry, observation, cancellation and persistence/restart boundaries. Assert no duplicate mutation, no dispatch after
authority loss, durable uncertainty, and progress only from qualified evidence.
Blanket diagnostic tolerance has been replaced with reviewed expected-failure
signatures; unexpected failures, crashes or missing tests fail the gate.

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

- Gather the next high-value observations through one client queue: a manually
  opened Irekei Barracks and vendor recipe/Inventory ownership. Carpenter follows
  once its building is ready.
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

## Current checkpoint and next todos

- Complete: branch/patch reconciliation, preserved source inventory, reviewed
  ancestry-preserving PR #25 merge, clean main fast-forward and verified branch
  protection with eight required check contexts.
- Complete: guard coverage/terminal visibility, exact vendor Create/Keep recovery,
  passive vendor workflow recorder and narrow diagnostic CI classification.
- Complete: combined local validation, all 15 hosted checks on `e8062fd`, and an
  exact-source host 0.3.46 wheel with isolated local verification. Main merge
  `555f6bf` push CI also passed.
- Complete: the available historical schema-2 Create passed the current validator
  read-only in the VM. No authentic Keep journal was available; historical Keep
  compatibility remains unverified. No guest/game state changed.
- Complete: host 0.3.46 VM installation and healthy manager activation; all 430
  installed hashes matched, 9,234 of 9,235 ledger files were unchanged, and only
  the expected idle dispatch permit was revoked. Jobs and proofs were preserved.
  No game was launched and no historical request was replayed.
- Complete: reviewed client 1.3.38.11 update, native 1.8.27 / host 0.3.47 package,
  both VM client copies, five shortcuts and non-launching preflight. Of 9,441
  retained files, 9,440 are unchanged; only the revoked idle permit refreshed.
- Complete: carpenter reproduction, passive request/response recorder, combined
  preview/recorder 1.8.30 / 0.3.50 deployment and live startup/panel verification.
  The saved capture isolates the Bench material rejection before cloning and
  reproduces an unchanged empty primary placement response.
- Stopped at user direction: carpenter implementation and live testing, including
  automatic preview integration. Preserve pushed source and unfinished edits;
  no further package/deployment or user test is scheduled for this lane.
- Active: validate the exact-source 1.8.31 / 0.3.51 vendor package and prepare
  supervised saved-recipe/one-batch acceptance. Durable town visits follow.
- Complete saved-recipe slice: `eb7c239`, versioned as `a3a5d37` in PR #38.
  Recipe preferences, preparation, generalized Create, Inventory and Keep share
  durable ownership and recovery. Combined validation: 895 host tests, 449
  subtests and 13 native tests passed; 4 host tests skipped. Not installed.
- Complete source checkpoint: `codex/vendor-town-workflow@a1a0793`, draft PR #38
  to main. Typed owner-thread menu operations and durable menu recovery now
  integrate with the existing finished-batch Inventory/Keep handoff. The full DLL
  build, 12 affected native tests, 172 affected host tests/85 subtests and Ruff
  passed. Hosted CI is tracked separately; not merged, packaged or installed.
- Complete live walkthrough: selected/activated/retained Anthame and Balanced
  Dagger identities agree in Magic/random mode, table 16, quantity 1, single
  mode. Inventory close/reopen retained the same 65 displayed item identities.
  Full inventory freshness/completeness and generalized spending remain unproven.
- Follow-up read-only capture: all three samples at 22:03 UTC identified the
  owned Inventory list and one unnamed event-50 close control. The assumed named
  CANCEL is absent. Correction `4608188` is pushed and the full DLL build plus
  three native menu tests passed. The check sent no game command and did not
  change the installed runtime.
- Complete recipe catalog source: `a1a0793` exposes typed template keys, actual
  labels and separate selected/activated/retained state through a bounded
  read-only reader and inspection CLI. 139 catalog/CLI/vendor-reader tests and
  101 subtests passed; Ruff/diff clean. This observation is not crafting
  authority or a complete server catalog. Not installed or live-accepted.
- Parallel PvP implementation: a separate `codex/explicit-list-combat` worktree
  connects attack-list mutation revocation to a Windows host/native admission
  fence. Real process races and crash ordering are being validated; native
  attack/cancel transactions remain next. No combat or deployment performed.
  Native listed-player selection/attack and local
  combat exit are mapped. Complete truthful submission receipts and guarded
  cancellation before enabling the explicit saved-list combat runner. Automatic
  response ingestion retains its separate server-session ordering blocker.
- Set aside at user direction: further guard/Barracks investigation and live
  qualification. The user reports equivalent native functionality; that claim
  has not been independently inspected. Existing guard/Condemn work and receipts
  remain preserved. Do not request another Barracks walkthrough without renewed
  user direction.
- Retained carpenter finding: original placement needs server handler/response
  evidence, which is unavailable. The private developer note and raw captures
  remain saved. This lane is stopped, not awaiting another user request to the dev.
- Complete live walkthrough: random recipe selection and Inventory close/reopen.
  The recorder stopped normally at 21:30:36 UTC. Bart is released for normal use;
  no further user test is currently queued. No Barracks or carpenter test is queued.
- Subsequent: production town vendor navigation/scheduling and qualified affix,
  resource/disposal/recurrence behavior. Guard live work is set aside.
- Deferred: broad refactors, unrelated historical feature lanes, and branch/worktree
  retirement until ownership, dirty files and retained remote history are checked.

The original plan `179f065` and completed source slices are now retained in main.
No source merge implies full-town, maximum-rank, vendor recurrence or carpenter
acceptance, and no existing feature worktree is retired by this handoff.
