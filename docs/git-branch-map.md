# Git branch map

Snapshot: 2026-09-04, updated after the approved remote and local retirement.
This is a source and review map; it does not certify deployment or live gameplay
acceptance.

## Current delivery status — September 12

Active priority: [PvE/PvP attack-list delivery](pve-pvp-attack-list-plan.md).
Blacklist means attack list, populated by commands or attributed responses.

| State | Source and evidence | Scope |
| --- | --- | --- |
| Installed diagnostic, capture armed | Product 1.8.1 / wheel 0.3.1, `6e1485b`; [package, hashes and review](handoffs/targeted-action-diagnostic-1.8.1.md) | Original targeted-action key capture and current identity/attack-list command work. All package checks and seven CI jobs passed; no automatic retaliation. Next: supervised hit/miss calibration. |
| Prior accepted client; old client copy retired | Product 1.7.8 / wheel 0.2.8, `97612e6`; [receipt and acceptance](handoffs/combined-candidate-1.7.8.md) | Movement/controller/chat baseline; focused user acceptance passed. Physical disconnect/reconnect remains unconfirmed. |
| Verified package, not installed | Product 1.8.0 / wheel 0.3.0, `433dc81`; [package handoff](handoffs/combined-candidate-1.8.0.md) | Movement/camera/cancel remapping; package checks, seven CI jobs and independent source review passed. No live remapping acceptance. |
| Included in 1.8.1 diagnostic package | Selected identity changes through `8552552` (cherry-picked; includes `ab8f440`) | Exact character keys, player/NPC classification, coherent party observations and positive pet ownership. No completed combat activation. |
| In development | [Door interaction](handoffs/door-interaction.md) | Character-forward ranking and collection/collision dependencies only; native selection/cue/Interact unfinished. |
| Deferred | Particles/native transparency | Unfinished and outside current combat scope. The visible character highlight was accepted as a baseline; ideal glow/material coverage remains separate. |

Package validation, source review and live acceptance are distinct. No full visual
bundle or PvP completion is claimed. The integration branch remains
`codex/native-lifecycle-hardening`; main remains unchanged. No new installation
is implied by later source commits. Reuse accepted navigation and movement evidence.

## Guard hostility investigation - September 21

The existing guard lane now includes [crest-list observation and workflow mapping](handoffs/guard-crest-lists.md).
Saved Heraldry, KOS and crest-options classes are identified. A tested read-only
recorder channel retains identity keys and raw window state. A loaded nation-scoped
Condemn entry matches the selected building. Root-owned KOS lookup and ordinary
request/response paths are traced. The tested read-only city catalog is live-qualified
with 89 city records and separate guild/nation identities. Native hostility writes,
response correlation and full guild coverage remain unfinished. The 1.8.23 / 0.3.34
source adds bounded response capture with lifetime checks and loss reporting;
package source `d300a7c` passes required validation and is installed in the test VM.
The updated manager is healthy and loaded 1.8.23 is verified. The manual nation
add/enable/reopen workflow is captured and qualified: operation 12 lists omit the
building key; operation 17 confirms a keyed row-state change. The native handler
is a toggle, so blind retries are unsafe. Automated command ownership and durable
hostility execution remain unfinished. Source belongs to
`codex/guard-upgrades`, awaiting integration through `codex/vendor-rolling` and
`codex/native-lifecycle-hardening` into reviewed `main`.
The response observer is installed. Later source adds tested exact response qualification
and a separate durable enable journal with replay/loss barriers; those components
now have tested low-level native open/add/enable helpers in both profiles. Typed
command routing, transaction ownership and manager controls are still unfinished.
The native recorder now also has a tested locked copy boundary and non-rearmable
response qualification interval, required by packaging in both native profiles.
Automatic aggression remains unavailable, with no additional deployment implied.

## Guard-upgrade detour — September 17

`codex/guard-upgrades` starts at vendor checkpoint `61e6fd8` in its own worktree.
The user wants guards upgraded toward maximum rank as available gold permits.
Read-only guard/deposit observers are live-qualified. Native/host source now
supports distinct guard navigation and funded guard-upgrade commands with exact
ownership, quoted-cost admission, immutable submission receipts and observed
progress/debit correlation. A user-operated warehouse withdrawal, structure
deposit and upgrade start are verified. Warehouse quotes/reserves are now live-qualified,
and guard host intents/submission/completion records are durable across restarts.
Native/host funding from owned quotes now checks the live purse, reserve and both
balance changes. Quote opening, transfers and upgrades share one durable spending gate. Amount
windows can now open through verified parent-panel controls. Complete building
roster observation and typed nearby guard discovery/traversal are source-tested;
the open-building reader is live-qualified. A live warehouse navigation attempt
identified a selection-versus-activation defect; its tested native fix is in this
lane, with the unresolved old request retained and no replay. Warehouse resources
are now live-observed and distinct from hireling management Inventory. Exact-key
warehouse access is source-tested with version-3 navigation/guard receipts and
front-window confirmation; ship
host/native together. Full-town coverage remains unfinished; no new build is
deployed. Guard navigation now shares the durable spending gate, so lost
window replies block transfers/upgrades across restarts. The persistent funding
cycle now joins exact guard quotes, shortfall withdrawal, structure deposit and
upgrade confirmation under one execution lock and journal. Process-bound guard plans
now retain discovery digests and exact warehouse/guard keys. A persistent queue
rotates guards, waits for ranks, records confirmed gold totals, and recovers only
fully confirmed cycles without replay. No-offer remains unverified maximum rank.
The manager now admits guard work through exact worker permits and exposes
discovery, exact prepared-plan start, pause/resume/stop and confirmed progress.
Full native 1.8.14 / host 0.3.23 (source dcc33bc) is installed and verified.
The warehouse panel's retained NPC ownership is confirmed and used for return
visits. A live tower open exposed chat-window ordering; the timed-out request
remains retained. This version corrects chat ordering across native transactions.
Package, guest activation, loaded module and manager checks passed. Automatic
tower/warehouse/resources return is now live-qualified. Discovery's first-open
state and funding's Gold-selection ordering exposed two further blockers before
any money moved. Native 1.8.14 / host 0.3.23 (source dcc33bc) corrects both.
Package, installed checks, guest staging and activation verification passed.
All retained records/settings were preserved. Live City Command first-open now
passes and exposes 60 nearby structures. Discovery then stopped on the Tree of
Life's companion guild panel above its confirmed hireling roster. Native 1.8.15 /
host 0.3.24 (source 861985e) adds a roster-only, same-building ownership check.
Package checks, guest staging and activation verification passed. All 171 retained
records/settings were unchanged and the background manager restarted healthy.
The user-launched extension was verified. A continuous manual workflow capture and
non-spending guard revisit confirmed withdrawal, deposit and upgrade progress.
[Workflow analysis](handoffs/guard-workflow-capture.md) identified idle post-deposit
mode and post-upgrade guard-window closure. The [combined 1.8.16 / 0.3.25 correction](handoffs/guard-upgrades-1.8.16.md)
recognizes owned idle menus and revisits the exact guard once within its original
pending transaction. Source `6c6228f` is pushed; exact-source packaging, both native
profiles, 2,695 host tests and installed contract checks pass. Guest preparation
and read-only validation pass. The combined 1.8.16 / 0.3.25 update is now installed
after confirmed closure; all 182 retained records/settings are unchanged and the
manager restarted successfully. User login and the new worker are verified.
The Tree companion and eight guard windows passed; a zero-slot wall stopped the
scan. A bounded cycle stopped on Gold activation before any transfer, retaining
its uncertain quote request. The [1.8.17 / 0.3.26 source correction](handoffs/guard-upgrades-1.8.17.md)
combines exact-row scrolling, resource activation and unavailable zero-slot
building handling. Source `1fb4c0c` is pushed. Exact-source packaging passed
2,700 host tests, both native profiles and installed contract checks. Guest
preparation/read-only validation passed. After confirmed closure, native 1.8.17 /
host 0.3.26 was installed and verified; all 249 retained records/settings are
unchanged. The manager restarted healthy and the user-launched session passed.
The manager checked 60 candidates and verified 150 guard windows across 27
building rosters. Two complete automatic withdrawal/deposit/upgrade cycles passed;
a third completed its funding but stopped after the one submitted guard-return
activation produced no window before its deadline. The job remains in review,
with the uncertain third upgrade retained and no replay. The user-opened page
subsequently confirmed the third upgrade's progress and exact debit. The
[1.8.18 / 0.3.27 correction](handoffs/guard-upgrades-1.8.18.md) adds bounded retries
only for a submitted guard-page request that produced no response. Upgrade is
still single-shot. Source `826de6a` is pushed; exact-source package checks and
guest preparation/read-only validation pass. After confirmed closure, native
1.8.18 / host 0.3.27 was installed and verified. All 642 retained records/settings
are unchanged, the dashboard shortcut is updated and the background manager
restarted healthy. Fresh user login and automatic batch verification are next.
The user now requests carried-gold-only upgrades. The [host 0.3.28 update](handoffs/guard-carried-gold-0.3.28.md)
removes warehouse setup and withdrawal from new discovery/plans/cycles, stops on
insufficient carried gold, and rejects legacy worker/job funding policies without
replay. Source `764ab0a` is pushed; host 0.3.28 is installed with a healthy
carried-only worker. All 559 historical records checked are unchanged; the three
current-worker capability records renewed. Native 1.8.18 and its running game
process are unchanged. Warehouse-free discovery admitted 174 guards in 29 towers;
14 new carried-only upgrades and 1,709,400 gold in exact deposits/debits are
confirmed, with zero warehouse actions. The next funded upgrade stopped in
review: its same-guard response already showed progress/debit, but a replacement
building HUD failed the original SameOwner confirmation branch after 234 ms.
The user reported possible accidental menu interaction; the cause is not proven.
The original request remains unresolved without replay. Carried-only funding is
qualified; next is fresh-session uninterrupted verification, then rank/gold
stopping, outer coverage and integration review.
A fresh carried-only session verified 180 guards in 30 towers and confirmed
11 additional upgrades before the same retained-guard/replaced-building response
stopped confirmation. [Native 1.8.19 / host 0.3.29](handoffs/guard-upgrades-1.8.19.md)
adds a matched native/host rule for this already-complete exact-debit response.
Source a87a984 is pushed; exact-source packaging passed 2,727 host tests and
both native profiles' required checks. After user-confirmed closure, native
1.8.19 / host 0.3.29 was installed and verified, all 1,696 checked records/settings
were preserved, and the manager restarted healthy. Fresh user login loaded the
new extension; live qualification is next. The stopped requests remain unresolved
without replay.
The fresh 1.8.19 run confirmed eight upgrades, including rank-2 offers, then
stopped on a rebuilt selected roster entry despite exact debit/progress.
[Native 1.8.20 / host 0.3.30](handoffs/guard-upgrades-1.8.20.md) separates stable
guard/building identity from disposable UI pointers and strengthens current
selected-entry roster membership. Source 33229a0 is pushed; 2,754 host tests,
both native profiles' required gates, installed contracts and artifact hashes
pass. After user-confirmed closure, native 1.8.20 / host 0.3.30 was installed
and verified. All 2,215 checked records/settings are unchanged and the manager
restarted healthy. Fresh user launch and live qualification are next; prior
stopped requests remain retained without replay.
Known graphics
stretch failures remain diagnostic-only. Maximum-rank and full-town evidence
remain unfinished; earlier uncertain requests stay retained without replay.
See [Tree companion navigation and next work](handoffs/guard-upgrades-1.8.15.md).
Review this lane into `codex/vendor-rolling`, then the documented integration
destination and main.
See [guard-upgrade source, qualification and todos](handoffs/guard-upgrades.md).
The normal main checkout and unfinished vendor branch remain untouched.

## Vendor overlay — September 14

September 15: the correct full native 1.8.8 / host 0.3.17 is installed and its
action mapping is verified. A live scan confirmed the selected-vacancy fix and
healthy permission renewal, but Tree of Life's secondary panel changes the
last-dispatched-manager global and prevented window confirmation. Source 1.8.9 /
0.3.18 corrects that ownership check. Exact source 7870b3f passed package checks
and all seven CI jobs. Following confirmed closure, full native 1.8.9 / host
0.3.18 is installed and relaunched; the exact DLL hash, healthy worker and
read-only action mapping are verified. Crafting journals are unchanged. Login
and one fresh town scan are next. No failed request was replayed. See [current correction and next work](handoffs/vendor-navigation-1.8.9.md).

Current owner priority: [town building/vendor selection and automatic window control](town-vendor-plan.md).
The last single-vendor job is in review before Keep; do not replay it.
Current-building hireling observation is implemented and tested. The broader
city roster and automatic window selection remain the active discovery work.
Native 1.8.4 from c268cc0 / host 0.3.13 from 8352bd2 is installed. Automatic
City Command opening and an independently verified stable roster of 11 nearby
buildings are live-qualified; the user also confirmed the visible window.
Later source checkpoints add building-menu hireling discovery, retained exact-key
building selection (e3967ee), and typed owner-thread building/hireling commands
(28a3328). The native movement ownership dependencies through dfa766a are retained
as e7ca4a4, b637e47 and 4ad7d81. The current native 1.8.5 / host 0.3.14 candidate
connects automatic building/vendor visits to the dashboard discovery operation.
Source 89a4489 passed exact package validation and all seven CI jobs.
Native 1.8.5 / host 0.3.14 is now installed, with exact loaded DLL and healthy
worker binding verified; eight existing crafting records are unchanged. See the
[activation handoff](handoffs/vendor-navigation-1.8.5.md). Login and automatic
building/vendor discovery qualification remains incomplete. The first scan found
11 buildings but all opens rejected a wrongly signed native Z bound before
dispatch. Native 1.8.6 / host 0.3.15 corrects that bound and zero-result reporting;
Source bc73085 passed exact packaging and all seven CI jobs and is now installed.
The failed scan is retained without replay. The corrected game is launched;
login and discovery qualification are next. See the
[corrective activation](handoffs/vendor-navigation-1.8.6.md).
See [building navigation](handoffs/building-vendor-navigation.md) for the source
boundaries, checks and next automatic selection work.
Both exact-source checkpoints passed all seven CI jobs. Crafting-vendor
association, complete town coverage and automatic building/vendor switching
remain unfinished. See [package and live handoff](handoffs/town-discovery-1.8.4.md).

`codex/vendor-rolling` (worktree `.worktrees/vendor-rolling`) contains vendor
work through dependency `542c632` plus native dispatch and a durable host batch.
The integration destination is `codex/native-lifecycle-hardening`, followed by
reviewed `main`; this vendor work is not merged. Manual Create,
Keep and owned inventory are qualified. Native typed commands, strict wire and
capacity-aware queue filling are implemented and tested, including rank growth.
Package 1.8.2 / wheel 0.3.2 from `8aad37f` passed local required gates and all
seven CI jobs. The separate test runtime is running with its exact DLL verified.
The first live automatic batch filled three free slots with distinct verified
queue additions. Host-only 0.3.3 from `25dd627` then finalized all three using
automatic Keep with independent inventory confirmation. Native 1.8.2 remained
unchanged. Installed host 0.3.6 from `4a5a9b0` completed its first manager-started
three-item batch with two reviewed, pre-Keep recoveries. Independent inventory
reads confirmed all three retained items and empty production. Live Pause/Resume
kept the same job and item count. This is assisted qualification, not an
uninterrupted unattended run. Installed host 0.3.8 from `5c7ccfe` adds bounded
read-only inspection recovery and durable first-cause cancellation diagnostics.
It passed installed identity/worker checks, 1486 passive cancellation checks
and 122 native inspections without failure. A fresh game instance then completed
one uninterrupted three-item manager batch: all Create/Keep receipts and independent
inventory were confirmed, with one Start and no Resume or repair. Unknowns were
kept. Host 0.3.9 adds a tested foreground readiness wait with pending receipt
reconciliation. Source `e26a5e3` is installed and its exact worker/game binding
passed read-only checks. The focus wait was observed, but its first Create
remains unconfirmed. Host 0.3.10 corrects launch validation for the exact
client-written crash log. Source `1aee8d5` is installed; the exact runtime
reopened and passed worker/binding checks. A fresh manual multiple-slot trace
confirmed one quantity-1 request filling three free slots. Native 1.8.3 / host
0.3.11 support is implemented and its exact package from `bd08ffc` passed all
required local gates and seven CI jobs. The isolated VM runtime has launched;
loaded DLL, matching manager/worker binding and both desktop shortcuts are
verified. The first automatic multiple-mode Create filled the one available slot,
with an independently matched queue item and the three manual items preserved.
Its automatic Keep and a future automatic multi-addition batch remain pending.
See [multiple-slot handoff](handoffs/vendor-multiple-1.8.3.md).
Then native window opening and exclusion/disposal/resources remain.
See [previous manager handoff](handoffs/vendor-manager-0.3.10.md),
[exact vendor package](handoffs/vendor-rolling-1.8.2.md) and
[vendor status and validation](vendor-rolling.md).

## Historical candidate notes

The entries below are historical snapshots, not current installation instructions.
1.7.7 keyboard acceptance and controller detection findings were superseded by the
1.7.8 installed baseline above. Retained candidate handoffs preserve their evidence.
Earlier September 11 movement follow-up: installed diagnostic package 1.7.4 identified
manual latching after native update gaps. Repair candidate 1.7.5 / wheel 0.2.5
is built from `29ef530`, independently source-reviewed and locally package-verified;
CI and connected acceptance status are tracked in
[the 1.7.5 handoff](handoffs/combined-candidate-1.7.5.md). The existing integration
branch remains the destination; main and the running diagnostic client are unchanged.

Current September 6 candidate: `04b7bdb` (native 1.7.3 / wheel 0.2.3) passed
all package/CI checks and independent focused review, and was installed with
owner approval. It addresses the live terrain/movement conflict found in 1.7.2.
See [the 1.7.3 handoff](handoffs/combined-candidate-1.7.3.md) for exact identities
and pending in-world movement checks. Main remains unchanged.

September 6 movement repair: exact package source `a98a6b3` (native 1.7.2 / wheel
0.2.2) completes local package checks and independent source review. See
[the current movement repair candidate](handoffs/combined-candidate-1.7.2.md)
for exact hashes, CI status and the targeted connected check. VM deployment is
not implied. Particles remain paused; newer PvP identity work is outside this package.

Later September 6 update: the owner requires a visible selection effect. Native
1.7.1 / wheel 0.2.1 is verified from `becc58fdb4b1ae51fa6c82617c42dceea41a9e94`, including cue
source `2a9997316f0a11739e439d6aef71320ae020f790`. The earlier 1.7.0
receipt below remains historical; it does not certify this change. Particles
remain unavailable pending correct transparency; they do not block the cue update.
See [the verified visible-selection candidate](handoffs/combined-candidate-1.7.1.md)
for exact artifacts, executed gates and the coordinated acceptance update.

September 6 verified candidate: native 1.7.0 / wheel 0.2.0, exact build source
`89c3b1ecb7087c8da3d1de697b6dfb507682a8f8`. Package, installed controls and
all final CI jobs verified; connected acceptance remains pending in the existing
Sol testing task. World glow/particles are explicitly suppressed per owner scope.
See [the exact candidate and single acceptance procedure](handoffs/combined-candidate-1.7.0.md).
Later evidence-only commits are not the packaged source.


Use `codex/native-lifecycle-hardening` for this batch's combined source and review;
its separate checkout is `.worktrees/native-lifecycle-hardening`. Exact common
base: `14d117e8c5194c6dff55dac608b2d3f683187d31`. The normal checkout remains
`main`; do not reset or switch another developer's checkout. This does not
supersede historical source/retirement records below or authorize main merge or VM deployment.

The four feature source branches target this integration owner:
`codex/particles-trails`, `codex/selected-character-cue`, `codex/sky-horizon`, and
`codex/native-movement-controls`. GitHub metadata rechecked September 5: all
four PRs (28-31) are merged checkpoints targeting `codex/native-lifecycle-hardening`,
not open reviews of newer work. PR28 records merge `4e908b4`; PR29 records
`5519a8e`. Later source deltas are integrated separately; exact inclusion and
validation are recorded in the active handoff. A merged PR does not certify
complete feature delivery, package identity or owner acceptance.
Useful dependencies are merged during development. Features enter rolling owner
candidates only when complete; newer movement work must not indefinitely delay
completed older features. Shared scene/context/startup and manager ownership
remain with the integration owner.

See [the active source and validation handoff](handoffs/native-lifecycle-hardening.md)
for exact included revisions, committed repairs and outstanding gates. The September 6 owner scope prioritizes artifact avoidance: world glow and
particles/trails are conservatively suppressed, with explicit controls/status.
Ideal native transparency remains deferred diagnostic evidence; required runtime
fallback tests must execute and pass. See the updated shared acceptance plan. Movement now registers one native update/input runtime after shared startup,
defaults disabled, and composes native stop, camera, steering, terrain-pick and
drag with exact lifetime and HWND safety handling. Native preferences and the selected-client
Graphics Lab settings entry are included. Manager operations now use immutable native
grants, renewal and exact cleanup. Standalone live travel/PvE now use the same
native authority, with no minimap movement fallback. No connected capability is certified. The exact verified wheel/DLL candidate identity is recorded in the September 6
handoff above; no connected acceptance or deployment is claimed. Preserve all active branches/worktrees; retirement
requires verified inclusion and applicable approval.

## Current handoffs and terrain follow-up

The navigation inspector is implemented on codex/navigation-inspector in
[draft PR #27](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/27),
targeting codex/integrate-current-development. Use that feature branch for inspector
review and the integration branch for independent development. The inspector's
publisher, native overlay, controls and saved evidence are outside the shared
integration branch until PR #27 is accepted. See the [usage and validation record](navigation-inspector.md)
and [developer/owner live handoff](handoffs/navigation-inspector.md). This inspector
package excludes the separate terrain material repair. The normal checkout is
clean on main; the inspector worktree is retained for live acceptance and review.

Branch/worktree counts in the retirement section below are the cleanup snapshot.
The active inspector adds one branch and one worktree; it is not an obsolete
checkout to retire before acceptance.

A later September 4 fetch found convergence at `031de7e` and the new terrain
repair branch at `9287c9a` ([PR #26](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/26)).
The convergence changes since `da109b0` are only a merge workflow and validation
note; the terrain implementation has not landed there. Its generation, Windows
terrain tests and merge workflow have failures, and product build/startup wiring
is absent at the repair tip. See [the exact delivery check](handoffs/terrain-delivery-check-20260904.md)
before selecting a terrain-enabled base or package. The staged correction branch
`codex/terrain-material-repair-final-v2@3b344f0` adds a revised delivery path, but
its first delivery run fails before assembly/validation with an unset Git committer
identity and uploads no artifacts. Convergence is still `031de7e`.
Earlier pinned snapshots below retain their historical meaning.

## Completed branch and worktree retirement

The owner approved and completed deletion of **53 superseded remote branches**;
**23 remote branches remain**. Every retired tip is contained in the published
`archive/pre-branch-cleanup-20260904` tag at `151eebb`. The
[retirement registry](retired-git-branches-20260904.md) records all original names
and full SHAs, recovery commands, retained dependencies, and local outcomes.

After explicit local approval, **29 obsolete local branches** and **12 cache-only
worktrees** were removed. The owner then approved archiving the nine remaining
obsolete artifact checkouts: their **4,264 non-cache files** were hash-verified
in one private ZIP, and all nine checkout folders were removed. **9 local
branches and 9 worktrees remain** (21 worktrees removed in total).
The existing dirty streaming draft is unchanged. Consult the registry before
restoring a retired name; routine fetches will not recreate deleted refs.

## Shared starting point

| Role | Branch and pinned checkpoint | Meaning |
| --- | --- | --- |
| Shared merge destination | `main` at `047147d` | August 30 release. It does not yet contain the consolidated client development below. |
| Proposed integration into main | `codex/integrate-current-development` | Review branch created from `da109b0`, plus this repository navigation and workflow cleanup. No additional feature branches were merged in the cleanup. |
| Preserved development source | `codex/client-convergence-v2` at `da109b0` | 386 commits beyond `047147d`; main is an ancestor. Contains client, renderer, diagnostics, asset facade, PvE, PvP data, and simulator integration. |
| Former local checkout | `codex/wreck-texture-cache-swap` at `99b37c7` | 61 commits beyond main, but already contained in `da109b0`. An older topic, not the current combined product. |

Review the [proposed integration](https://github.com/best-coder-open-now-near-me/shadowbane-lab/compare/main...codex/integrate-current-development).
The source checkpoint has [successful shared CI](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/33835010581).
The PR's own checks must also pass. Green CI does not close known runtime review
findings or unfinished terrain acceptance.

For the feature contents, see the [recovery ledger](project-recovery-status.md),
[feature lineage](feature-lineage.md), and [tool ownership map](tooling-map.md).
Those documents contain dated historical queues; use this map for branch selection.

## Work outside the proposed integration

Counts below compare each pinned tip to `da109b0`. A missing ancestor commit does
not by itself establish missing behavior: some historical features were replayed.

| Branch | Tip | Commits outside convergence | Disposition |
| --- | --- | ---: | --- |
| `codex/legal-build-map-elites-foundation` | `ee5a4c2` | 9 | Later training-budget and static-capability work. The branch lacks 86 convergence commits; integrate its delta after review instead of replacing convergence. PR #23 still targets the older PvE branch. |
| `codex/texture-cache-read-export` | `0680a76` | 8 | Forks at `a1f8a77`, with 34 convergence commits absent. Review its exporter changes separately and retain the newer terrain/diagnostics work. |
| `codex/terrain-material-export-da109b0` | `bb516fe` | 10 | Descends from `da109b0`; adds export/review/publisher workflows and encoded implementation payloads. A payload or publisher is not evidence that its source changes were integrated. |
| `codex/terrain-material-repair-workspace` | `9f2446e` | 7 | Separate handoff workspace, missing the final convergence draft checkpoint. Preserve and inspect its delta. |
| `codex/terrain-repair-snapshot` | `1ac56c6` | 1 | Separate snapshot, missing the final convergence draft checkpoint. Preserve for handoff. |

`codex/terrain-material-repair-implementation` currently points to `da109b0`
itself; its name does not mean the planned implementation has landed.

Historical refs outside convergence are retained: `codex/initial-simulator`,
`codex/shadow-mantle-policy-ablation`, `codex/preserve-assassin-sdr-loadout`,
`codex/preserve-elf-druid-kiting`, `codex/world-map-exact-dispatch`, and
`fix/world-map-click-capture`. Consult the feature lineage registry for the
superseded prototype, experiments, replayed features, and exact-map routing
decisions before integrating or retiring these refs.

## Existing PRs and review boundaries

- PR #21 (texture tools), #22 (PvE authority), and #24 (sustained contours)
  have source tips contained in `da109b0`. Their open state does not mean those
  capabilities are absent from the candidate. They remain open until the
  consolidated review determines how to close their original review records.
- PR #23 contains the later simulator delta described above. Its older base must
  be reconciled after the consolidated base is accepted.
- PR #16 is a historical exact-map draft against an old simulator-CI branch.
  Do not merge it simply to empty the PR list.
- `native/wonderbane_extension/terrain_material_plan.h` and `.cpp` at `da109b0`
  are explicitly unfinished source drafts. Their publication preserved handoff
  access; it did not enable or complete the terrain repair.
- The recent repository review identified manager permit lifetime, failed-launch
  cleanup, heartbeat shutdown, worker-start concurrency, and native publisher
  shutdown findings. Texture-export publication findings belong to the separate
  export branch. Recheck each against its exact intended source before closing it.

## Local cleanup and recovery

The September 4 cleanup preserved all refs and the old stash in a verified local
Git bundle. It archived 193 scratch entries (2,695 files), verified each SHA-256,
and saved the six existing formatting edits in a named stash. None of those
private scratch files was added to the integration PR.

The private local recovery directory is
`artifacts/git-cleanup/20260904T062424Z/`. It contains the bundle, before-state
refs/configuration/worktrees, both dirty-checkout patches, branch audit, scratch
manifest and archive, and the exact new formatting-stash SHA. Preserve it until
the owner decides that recovery copies are no longer needed.

The old streaming worktree still contains eight modified files and one reject
file. Its draft was backed up and left in place. There are now 9 worktrees and
9 local branches. The retirement registry records the 53 retired remote names,
29 local names and exact tips, including local tips that differed from origin.
All retired commits remain under the archive tag. Historical build artifacts
from nine obsolete checkouts are consolidated in
`artifact-consolidation/retired-builds.zip` under the recovery directory, with
original paths and file hashes in its manifest. Those checkout folders have
been removed; the retained streaming checkout still contains its unfinished work.

The normal project checkout is returned to `main` after preparing the PR.
Repository-local `fetch.prune=true` and `pull.ff=only` keep ref refresh and update
behavior explicit. The old `codex/client-convergence` branch's incorrect upstream
to `codex/graphics-diagnostics-client` was removed without changing either tip.

After merging the consolidated PR, fast-forward the main checkout, update this
map's shared-base section, and review the outstanding deltas above. Retire only
branches/worktrees whose history and local files are demonstrably preserved.

## September 12 PvE/PvP priority

The active delivery plan is [PvE/PvP attack-list integration](pve-pvp-attack-list-plan.md).
Blacklist means the attack list, populated manually or through attributed responses.
The plan retains applicable review follow-ups without making broad cleanup or unfinished
visual/door features prerequisites. Identity changes through 8552552 are integrated; attack-list storage and chat editing are integrated. Durable player identity and command completion are active; response attribution and combat transitions remain pending.

## Official client refresh — September 19

The guard lane now reviews official client 1.3.38.9 with native 1.8.21 / host
0.3.31. [Exact client review and deployment todo](client-update-20260919.md).
Source 7d38916 is pushed; exact package and guest dry-run validation pass.
The update is installed in both clients; manager restart and preservation of
2,232 records/settings are verified. Poley login and the loaded extension are
verified. The carried-gold job started one confirmed upgrade for all 174
discovered guards, spending 24,868,800. A later non-spending building-open recheck
failed navigation admission; the job is stopped for review with its original
intent retained and no replay. Eleven retained-page completions live-qualify
rebuilt building HUD/selected-entry ownership. Next: fix navigation admission
and continue rank checks; outer coverage and maximum-rank completion remain open.
Keep the current carried-gold guard journals, including unresolved requests.
This work remains outside the shared integration branch and main.

## Guard travel controls — September 19

The active `codex/guard-upgrades` worktree now owns the
[dashboard Travel / Continue here feature](handoffs/guard-travel.md).
Area scans extend the same job and preserve rank floors, timers and confirmed
spending; only new guards require discovery of their personal menus. This is
installed and activation-verified as 1.8.22 / host 0.3.32 from `cd8c8a8`.
A reproduced heartbeat race is corrected; the previous rejected request remains
retained without replay; all 5,578 saved record/settings files passed preservation
checks. The existing desktop shortcut is unchanged. Loaded extension and worker
are verified. Fresh discovery retains 174 guards; Travel has live-paused safely
after an active cycle with no spending or pending request. Next: user repositioning
and Continue here to verify saved progress and new-area merging.
Integration remains
`codex/guard-upgrades` → `codex/vendor-rolling` →
`codex/native-lifecycle-hardening` → reviewed `main`.


### Guard Travel host continuation — September 19

The active guard lane now contains host 0.3.33's same-character area continuation
fix. Historical scenes stay immutable; only guards in fresh owned rosters gain
the current area context. See [guard Travel](handoffs/guard-travel.md) for
validation and accepted host-only activation. Host source 4f20a81 is installed;
live Continue here retains 174 guards and schedules the 168 in fresh rosters.
Native 1.8.22 is unchanged. Additional town coverage/rank completion remain.
Integration remains guard-upgrades -> vendor-rolling -> native-lifecycle-hardening
-> reviewed main. The ordinary main checkout is unchanged.
