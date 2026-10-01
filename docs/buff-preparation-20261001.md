# Automatic buff preparation - October 1, 2026

## Scope and source status

The user authorized automatic application and refresh of missing Greater Concoction
Potion, Precision, Beorc Rune, Transform and Defensive Stance effects. This record
captures requirements, native read-only findings and the production ownership
boundaries. **The complete native/host slice is installed as .63/.43 but not yet
live-qualified.** Shared actor ownership, canonical native observations, automatic
preparation, saved intent and both NPC/manual-player runners are integrated.
Independent review, regression suites and exact-source package qualification
passed for source `e8aec9942e84ef367593461b698fee9eb143e3aa`. Deployment and
live-acceptance helper migration is the active, source-only preparation step.

The focused branch is `codex/native-buff-preparation-20261001`. Its dependency,
[PR #58](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/58),
is merged into main at `8fa16aa`; this branch has incorporated that merge. The
qualified ownership package retains source `7f37ff53e181288ce1ae695f2e2699ecf2bb8ff2`.
See the [native service ownership changes](native-owner-liveness-20261001.md).
The installed .62/.42 subsequently passed bounded two-encounter recovery and
native reuse-blocked opener fallback. That combat gate does not qualify buffs.
This dependency does not establish a buff action, actor-only authority, effect
observer or potion inventory resolver. Main inclusion, package qualification and
installation remain separate delivery gates recorded in the [branch map](git-branch-map.md).

## Required behavior

- Apply missing configured buffs and refresh them from qualified native evidence.
  Do not repeatedly cast an already active effect.
- The user reports that Greater Concoction Potion applies after roughly ten seconds.
  This is an application delay, not an effect duration or a required wait before
  other buffs. Keep its pending application separate from active effect presence;
  permit other native-ready buffs during that delay. Elapsed time alone never
  confirms application or permits another potion.
- Defensive Stance is a learned ability. Do not add a host-side combat-mode
  prerequisite or substitute the combat-mode toggle for the ability. Native
  definition requirements and current native admission remain authoritative.
- Transform is one coverage group: either Rat Shape or Skree'ekt Shape satisfies
  it. When neither is present, choose a qualified, currently ready alternative.
  The user reports cooldowns roughly twice each form's duration; these estimates
  are not scheduling constants or permission to recast. Do not replace an active
  form merely because the other becomes ready.
- Preserve legitimate actions already in flight. No fixed cast sleeps, hotkeys,
  UI selection, system-message parsing or simulated effects may drive this path.

## Initial passive observations and remaining live qualification

These initial captures preceded the retained native observer implementation. Their
limitations remain attached to the captures; the later source checkpoints below
record resolver, mutation-boundary and publication qualification. Live expiry and
application still require acceptance of the new installed runtime.

Passive learned-power observations for Umbra on Wonderbane identified:

| Intent | Native power ID | Observed rank |
| --- | --- | --- |
| Precision | `429545819` | 40 |
| Beorc Rune | `429590426` | 19 |
| Defensive Stance | `676005819` | 40 |
| Rat Shape (`WRT-001`) | `429513599` | 20 |
| Skree'ekt Shape (`WRT-002`) | `429415295` | 20 |

Precision, Beorc Rune and Defensive Stance were observed as category 0, target
mode 2, delivery 0: actor-directed powers. These are character observations,
not universal learned-rank defaults. Resolve and validate the current exact
character's definitions and positive learned ranks at run admission. The form
alternatives also require their exact supported native definition and effect
mapping before activation. Potion identity was qualified separately below.

A fresh read-only capture from the verified .62 process resolved these coverage
candidates through native action definitions:

| Power | Effect descriptor / Transform marker |
| --- | --- |
| Precision | `496654667` |
| Beorc Rune | `496699274` |
| Defensive Stance | `743114667` |
| Rat Shape | Transform marker `496622447` |
| Skree'ekt Shape | Transform marker `496524143` |

Use the actual Transform markers for alternative-form coverage, not a conjunction
of their auxiliary ApplyEff records. Native stance requirement was 3 (either
stance) for Precision, Beorc Rune and Defensive Stance; the forms were 2
(peace-side native mode). These definition requirements are distinct from the
Defensive Stance buff. The diagnostic captured 20 effect records, with none of
these five markers, but it explicitly does **not** authorize an absence or expiry
claim. Descriptor retention flags and mutation-safe publication remain to qualify.
The inventory component rejected an identity mismatch and remains unknown; this
is not evidence of an empty inventory or a missing Greater Concoction Potion. No buff
or item action was sent by that capture.

The effect audit distinguishes the primary descriptor identity from the
`ArcPowerAction` definition identity in the record. Neither can be assumed equal
to a learned power ID. ApplyEff, ApplyEffs and Transform paths link action
information to effect descriptors; observations must preserve repeated records
and source tags. The local actor uses derived effect handlers: add skips
certain descriptors, so selectors must be proved observable in that collection.
An equipment-linked path also prunes records inline. Rebuild clears records before
callbacks reapply them; equal passive rereads can therefore observe an intermediate
empty list. Authoritative absence requires owner-boundary publication excluding
all qualified mutation/rebuild paths, not just a double-read. Transform membership
changes bracket model changes; appearance is not needed as authority.

The inspected remaining-time getter does not remove expired records and can
return a small positive value after a deadline, or a sentinel for unsupported
records. It is not expiry authority. Queue receipts prove local submission,
not effect presence, server acceptance or duration. Coverage/expiry publication
remains unqualified.

For the inspected ordinary item-use branch, native code constructs an
`ArcObjectActionMessage` with subtype 2, operation 1 and the exact item key,
queues it and returns without changing the actor's mode, action or AF8 in that
branch. This supports separating local submission from delayed application.
This branch is restricted to the inspected template flag and ordinary item types;
special UI-use branches are excluded. The actor's inventory interface has a
qualified lookup path through its containers, returning an owned reference under
the native lock. Reuse that path and release the returned reference; vendor HUD
pointers and crafting deposit decoders are not substitutes. Positive exact-request
append, not the native return register, must prove enqueue. Incoming quantity
changes do not prove delayed effect application.

Actual concentration-potion template metadata, branch eligibility and its effect
mapping still require evidence. The qualified generic lookup and sender paths do
not by themselves authorize an unidentified item.

## Implemented primitives and exact-image checks

Shared append ownership is published at `1756737`; item/power collisions reject
all claimants and consume one transferred native message reference. The pure
preparation policy is published at `cd1e4ed` with 43 tests. It separates local
settlement from remote application, retains possible-entry history, permits
other ready groups while a potion is pending, and treats partial coverage as
insufficient permission to consume another potion.

The native effect observer installs only from the synchronous reviewed client
bootstrap, before original entry. Its global mutation depth/epoch covers local
add/remove, full incoming effect rebuild, all three rebuild call sites and all
six equipment-prune call sites. Four isolated fault/exception/install/exhaustion
modes passed, and both exact client .13 images passed 43 conformance checks.
These probes instrument lookup, allocation, notification and UI dependencies;
they do not establish live server application or elapsed effect lifetime.

Item entry binds the exact owned inventory object and template address as well
as keys. It is restricted to the reviewed type 8 / flags 0xA branch, retains and
rechecks membership, and quarantines uncertain reference ownership. Both exact
images passed 10 conformance cases over 48 reviewed native primitives. The
shared power observer now distinguishes explicit actor-only authority from
engagement authority; actor-only authority cannot carry a target or invoke a
targeted power. Focused power tests and both native image probes passed.

After the user's manual potion activation, native observation identified
**Greater Concoction Potion**, item key `[5802955,30]`, template `[980066,0]`,
quantity 3. The nine added effect descriptors match source power `429021400`
(`POT-016`): `294901960`, `495999176`, `496031944`, `496064712`, `496097480`,
`496163016`, `496195784`, `496228552`, `496326856`. Each descriptor's local
retention flag +4C was zero. Potion template and coverage-source power remain
separate configured facts; no static template-to-power linkage is inferred.
These passive captures did not establish absence, expiry or exact application delay.

The installed runtime remains .62/.42. These source checkpoints are not an
installed buff implementation. Next: canonical retained observation, one actor
owner with target contexts, versioned wire/fences, runner integration, complete
qualification and a new merge/install approval.

## Production integration contract

Use one canonical native effect/inventory observation source, bound to the exact
character session, process lifetime and actor identity. Policy, diagnostics and
native admission must agree on identities and freshness. A rejected, partial or
changing snapshot is unknown, not an empty inventory or a missing buff.

Preparation policy belongs beside PvE policy, with generic configured coverage
groups and action alternatives. Keep coverage state (present, missing, unknown)
separate from action disposition (never entered, queued, uncertain) and pending
application. A pending potion application must suppress duplicate potion use
without becoming a global queue barrier. Native readiness decides whether each
other action may enter. Entered uncertainty retains the original immutable
request; it never becomes permission for a fresh retry. A bounded observation
deadline may report unresolved application but cannot fabricate success or
silently consume another item.

The current combat proposal and fence require an NPC or listed-player target.
Even `SELF_POWER` carries that engagement binding. Preparation before combat
therefore needs explicit actor-scoped authority; do not supply a fake NPC,
nullable combat target or self-target workaround. Extend the shared native action
owner and coordinator coherently. The existing cleanup registry permits one
obligation per exact Grant, so a second independent coordinator cannot acquire
parallel cleanup ownership. Preserve per-action records inside the shared owner,
with native-qualified handoff and stop semantics. Delayed remote application is
not automatically a local stop obligation or proof that local cleanup finished.

The proposed protocol separates three lifetimes:

| Scope | Identity and responsibility |
| --- | --- |
| Parent actor owner | Exact client/Host/Grant, scene, actor key/address and native name/server; one aggregate cleanup obligation. |
| Child context | Monotonic context ordinal and full binding digest; explicit actor-preparation authority or separately fenced NPC/manual-player target authority. Actor-only context has no target or list fields. |
| Action | Immutable context/request identity and tagged power-ID or concrete item operand; entry state, queued history and local continuation tracked independently of remote application. |

An item operand must bind its exact key, retained address identity and qualified
template identity; it must not be packed into a power ID or a fake target field.
Receipts correlate the complete operand as well as owner/context/request. Preserve
bounded replay histories and high-water rejection, including cancellation before
entry. New scope needs explicit capabilities and a versioned, tagged wire/fence
schema; freeze geometry and cross-language golden fixtures before implementation.
The existing fixed command/receipt/fence layouts must not be reinterpreted silently.

Keep one unresolved native entry/status sequence at a time, but allow independent
pending applications. For the qualified immediate item branch, exact append plus
normal return and owned-reference cleanup can settle local responsibility while
its remote application remains pending. A subsequent ready power needs no potion
wait. Attach combat target authority to the same parent owner without inserting
`StopActive` between preparation actions. The shared actor runtime avoids a blanket pause and retains optional target
contexts beneath its actor parent.
Native action-specific continuation checks still govern handoff. Empty initiation
signals or an effect observation alone are not universal local-release proof.
Terminal cancellation revokes future actions across all child contexts before
settling native responsibilities; it cannot promise to recall an already queued
server application or erase its history.

The runner should arbitrate preparations and encounters from fresh observations.
Safety, unresolved command status and required cleanup retain priority; preparing
buffs must not cancel an unrelated legitimate cast. Permit independent pending
applications without concurrent, uncoordinated gameplay writers. Standalone and
manager maintenance continue to renew/check the exact lease and settle terminal
cleanup; they must not become background buff-submission threads. Preserve
foreground, manual takeover, scene and producer-lifetime protections.

Extend character-scoped `pve/settings.py` and the `pve-settings` command with an
explicit schema migration, retaining existing policy and opener settings. Save
intent only, using the current exact-owner checks, revision CAS and atomic write;
do not persist observed presence, timers or stale item addresses. Resolve native
identities through the current session. The common `_run_pve` composition is
already shared by direct CLI, listener and manager paths, so all should consume
the same settings and preparation implementation.

Expose each coverage group's observed state, pending action, native readiness
reason and last exact effect confirmation in trace/status output. Distinguish
queued from active, unavailable inventory from empty inventory, and unknown
observation from confirmed absence. Keep preparation accounting separate from
encounter kills, optional opener skips and server-effect claims.

## Migration and validation boundary

The shared migration touches Python `client_extension` wire/fence/channel/session
and cleanup ownership, `pve/native_combat.py`, model/runner/settings, the new
preparation policy and common CLI composition. Production native counterparts are the actor v3
controller/runtime/entry/queue and v4 parent/context fences, channel dispatch, power observer,
qualified item entry and canonical effect publication. Existing NPC/manual-player
admission, lifecycle commands after capability loss, old-owner cleanup and
uncertain immutable-request behavior must remain covered during migration.

Required production-path regressions include pending potion plus ready powers
without duplicate consumption; Transform alternative coverage; reset/prune and
unsupported-descriptor snapshots remaining unknown; exact actor/context/item
replacement; no fresh submission after entered uncertainty; independent context
revocation; and aggregate terminal cleanup without fabricated remote cancellation.
Cross-language wire fixtures, native owner-thread tests and real channel tests
must cover actor-only actions without an NPC. Settings migration/CAS and direct,
listener and manager composition must use the same policy and observations.

## Delivery checklist

1. Complete: qualify potion metadata, retained inventory, native effect mutation
   boundaries, canonical publication and actor/context ownership contracts.
2. Complete: integrate the shared native runtime, host coordinator, preparation
   policy, settings migration and NPC/manual-player runner/status paths.
3. Complete: independent review, complete regression suites, published integrated
   checkpoints `a03e729` / `e8aec99`, and exact-source .63/.43 package qualification.
4. Complete: prepare and independently review deployment/readiness/retirement helpers.
   Automatic approval review initially rejected creating the b43 verifier as
   outside prior .62/.42 approval. The user subsequently approved source-only
   preparation and reported the game closed; no merge/install is implied by
   that source-only approval.
5. Complete: the user approved merge/install; PR #59 merged and .63/.43 is installed.
6. **Active:** finish bounded acceptance-helper review and run live acceptance against fresh character/item/effect evidence:
   potion overlap without repeat consumption, ready independent buffs, either-form
   coverage, expiry/refresh and target cleanup. Only qualified native effect
   observations prove application; retain unresolved outcomes honestly.

## Reviewed actor observation and ownership checkpoint

The shared actor/context protocol now has native/host golden fixtures and a real
Windows cross-process fence consumer. Actor authority is independent of optional
target context authority. Child cleanup requires an exact positive closure receipt
and keeps the aggregate parent cleanup obligation registered; its next cleanup
operation receives a fresh budget only after that proof.

The native resolver reports qualified effect coverage, learned rank and readiness
from retained native objects. Owned inventory lookup retains exact item/template
references and revalidates them before use. Numeric selector manifests distinguish
explicit item templates from configured effect-source powers. Semantic group
hashes survive ordering, display-name and Grant changes. The native application
journal preserves possible application across target and parent transitions;
only later complete native presence resolves pending application. Local native
settlement remains independent, so a locally finished potion can permit another
buff while its remote application is pending.

Validation: five focused native CTest targets passed; 65 host checks passed,
including the Windows x86 native fence consumer and scoped cleanup negatives.
Resolver qualification passed 57 unit checks and 17 checks on each exact original
and prepared official client image. Inventory qualification passed 105 unit checks
and both original/prepared native probes. Independent reviews found no remaining
actionable issues in these frozen slices. These are source checkpoints: canonical
publication, shared runtime/coordinator integration and complete package validation
remain in progress. No new runtime version is installed.

## Integrated production path

One actor owner now spans buff preparation and optional NPC/manual-player target
contexts. The command channel exposes actor protocol v3; old v2 mutation is not
advertised or dispatched in the production DLL. Old protocol unit fixtures remain
as regression evidence. Actor/context v4 fences bind the actual process, producer,
Grant and immutable selector manifest. Manual attack-list schema 6 migrates saved
content while revoking target authority before changes; actor-only ownership is
preserved independently.

Every preparation observation requests a fresh native capture before reading the
publication. Failed capture invalidates old authority, while unavailable buffs do
not prevent ordinary combat. Immutable pending commands retain their original
publication through owner-open latency. Exact application history is projected
back into receipts without settling unrelated local actions. Target continuation
checks retained identity, party/protection and native combat state each update,
including after a locally settled ATTACK. Unconfirmed child cleanup blocks all new
native entry, including actor-only buffs; reads, history and cleanup remain usable.

Host fixtures cover delayed potion application followed by another buff and NPC
or listed combat under the same parent. Positive child cleanup preserves pending
potion history and actor-only local obligations. Foreign/adopted actions cannot be
discharged merely by an unproven LOCAL_RELEASED receipt. No timers, system-message
text, UI selection or configurable hotkeys serve as buff/combat authority.

The package and hosted gates now require the production runtime fixture, native
actor adapters, effects/inventory/resolver probes, shared wire fixtures and real
Windows cross-process parent/child and publication tests. Original and prepared
client images are probed for both DLL profiles. These source and fixture checks
do not claim live buff success. The installed runtime remains .62/.42.

Integration validation: the complete host suite passed 4,789 tests and 788
subtests, with 39 environment-dependent skips. The full native build passed
219 tests with three client-image checks deferred to exact-source packaging.
The production runtime fixture exercises 189 assertions, including the unresolved
child cleanup gate, positive closure and immutable replay. Host source/package
lint passed. Independent host, native adapter, runtime and CI reviews are complete.
The candidate versions are host 0.3.63 and native 1.8.43.

## Exact-source package qualification

Package `artifacts/b43/c34beb8b` is an acceptance candidate built from committed
source `e8aec9942e84ef367593461b698fee9eb143e3aa`, host 0.3.63 / native 1.8.43.
All 15 hosted checks passed on that source head. The packaging environment was the
existing repository Python 3.12.14 / pytest 8.4.2 environment; its host run passed
4,788 tests with 37 environment skips. Both native profiles passed 219 tests, with
three image-dependent CTests covered by explicit original/prepared client probes.
Each profile additionally passed 73 movement, 86 combat and 106 actor IPC checks,
with no skips in those IPC suites. All 16 new item/effect/inventory/buff probes
passed across both images and profiles. Installed-wheel checks passed.

The package completed 82 stages. Read-only inspection verified all 110 indexed
file sizes/hashes, exact Git source archive contents, required IPC/probe receipts
and the DLL version resource 1.8.43.0. The existing two transparency diagnostics
per profile reproduce their documented rendering limitations and remain recorded
in the receipt; they are not new bot failures.

| Artifact | SHA-256 |
| --- | --- |
| Acceptance ZIP | `a273661516d7ccde20ed98cf326fd4d8dc48a41324d9f8792df2535955528b26` |
| Receipt | `48c2522bfd67d3ce9ee5db2595b2f72c05384a1be5c921a2b09f7c7ed5a5dab8` |
| Full DLL | `0807494a529c2c59dd15031a5eb6701926cc40a4e454167efa5c0aa87709e098` |
| Host wheel | `fc2cbdcbf13d38699e4fc5ac1f98868394ffb1a71c38a94f1a98591d43f938f4` |

Failed attempt `45545fb4` caught a stale exported API patch version; `e8aec99`
fixed it. Attempt `d0178057` passed native/profile gates but stopped at wheel build
because the invoked Python 3.11 lacked packaging tools. Final `c34beb8b` reran the
complete committed workflow in the verified existing build environment. Failed
attempt records are diagnostic evidence, not deployment fallbacks.

The read-only deployment audit found required migrations: readiness must require
actor capability 0x80, payload verification must check actor-v3 and native buff
publication gates, and controlled live helpers must distinguish actor owner,
target context, local settlement and remote application. Old v2 acceptance helpers
cannot be used with version-only edits. Source-only helper preparation was initially blocked by automatic review. The
user explicitly approved that preparation and reported the game closed, so helper
migration can proceed. Package generation and read-only receipt inspection
completed independently. No VM files or live settings have been changed.

A private Umbra intent JSON is schema/CLI/manifest validated under
`artifacts/bot-buffs/20261001/umbra-buff-intent.json`, SHA-256
`db8810268cf75acf6d55fb95eac9d9655868b019dde3ddcf02aa6fc7252946ea`.
It enables five groups/six actions and preserves existing Shot to the Leg settings
when applied through the buff-only settings option. It has not been saved to the
live character. Installed .62/.42 remains in place; automatic retaliation remains
disabled. Merge, installation and live buff acceptance are still outstanding.

## Installed .63/.43 and restarted-client boundary

The user explicitly approved PR #59 merge/install after hosted checks. All 15
checks passed at `1ceead0`; merge `1517a61` retains package source `e8aec99`.
The separately reviewed deployment helpers verified the actual .62/.42 baseline,
then installed 463 host modules while preserving 9,572 files. Exactly one client
inventory record changed, for the new DLL. Manager 6480 activated healthy; all five
shortcuts and startup preflight passed. The old .62 host and .42 payload/staging
binaries were removed after exact ownership/hash checks; no rollback was retained.

Initial PID 5328 loaded the qualified DLL at 23:11:43.8987094 UTC. The user then
restarted the client through the updated desktop shortcut. Fresh launch receipt:
PID 8616 / creation FILETIME 134353700194624995 / HWND 2687708, source `e8aec99`,
DLL SHA `0807494a529c2c59dd15031a5eb6701926cc40a4e454167efa5c0aa87709e098`.
Both Vendor Test and Modded Client shortcuts point to `launch-reviewed.ps1`;
dashboard shortcuts point to `host-0.3.63/Scripts/pythonw.exe`. The user reported
Umbra in world near NPCs; read-only readiness found actor capability 0x80, alive
actor, owner NONE, fresh scene 1 and no cleanup pending. Revalidate before each
live operation. This record does not claim a buff application or NPC action.

Compact installation evidence under private `artifacts/bot-deploy/20261001-b43`
includes twelve exported receipts and seven independently checked installed-file
hashes. Initial exported launch/readiness receipts retain PID 5328 deliberately;
they must not authorize the restarted PID 8616. The active bounded test will record
its own exact identity and distinguish entry, local settlement, pending remote
application, native effect presence, child closure and final parent closure.
