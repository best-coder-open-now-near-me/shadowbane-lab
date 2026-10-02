# Automatic buff preparation - October 1, 2026

## Scope and source status

The user authorized automatic application and refresh of missing Greater Concoction
Potion, Precision, Beorc Rune, Transform and Defensive Stance effects. The native
and host slice, observation/admission repairs, pending-action settlement repair
and heterogeneous inventory census are installed as **.66/.46** from qualified
source `9e1a77ae9e763a65bfc7f39587c30b3f46c39c4b`. PR #62 merged into main at
`a983384b2e95a6ab6cc3f46a750265b82ec0bae2`. Shared actor ownership, canonical
observations, preparation, saved intent and NPC/manual-player runners are integrated.

Live qualification remains incomplete. The historical .65 run confirmed Precision
and Beorc effects, but no potion or NPC attack; Rat's queued action remained locally
pending in the captured trace. The fixes and final .66 package/deployment receipts
are recorded below without changing that failed result. The active next item is
Umbra login and fresh native readiness, followed by the bounded one-NPC/buff gate.
The delivery-record branch is `codex/buff-deployment-20261002`; installed source and
chronological evidence remain distinct from this documentation branch. See the
[branch map](git-branch-map.md).

The earlier .62/.42 [bounded combat recovery gate](native-owner-liveness-20261001.md)
passed native reuse-blocked opener fallback. That historical combat result does
not qualify buff application, overlap, expiry or refresh.

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
5. Complete: PR #59 delivered the buff slice; PR #60 delivered the startup repair.
   The user approved both merge/install steps; .64/.44 is now installed.
6. **Active:** correct and independently review the private camp filter, then complete
   bounded acceptance against fresh character/item/effect evidence:
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
remain in progress. At that source checkpoint, no new runtime version was installed.

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
do not claim live buff success. At that integration checkpoint, .62/.42 remained installed.

Integration validation: the complete host suite passed 4,789 tests and 788
subtests, with 39 environment-dependent skips. The full native build passed
219 tests with three client-image checks deferred to exact-source packaging.
The production runtime fixture exercises 189 assertions, including the unresolved
child cleanup gate, positive closure and immutable replay. Host source/package
lint passed. Independent host, native adapter, runtime and CI reviews are complete.
That integration candidate used host 0.3.63 and native 1.8.43.

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
completed independently. At that qualification checkpoint, no VM files or live
settings had been changed. The subsequent installation is recorded below.

A private Umbra intent JSON is schema/CLI/manifest validated under
`artifacts/bot-buffs/20261001/umbra-buff-intent.json`, SHA-256
`db8810268cf75acf6d55fb95eac9d9655868b019dde3ddcf02aa6fc7252946ea`.
It enables five groups/six actions and preserves existing Shot to the Leg settings
when applied through the buff-only settings option. It has not been saved to the
live character. At that checkpoint .62/.42 remained installed; subsequent merge
and installation are recorded below. Live buff acceptance remains outstanding,
and automatic retaliation remains disabled.

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

## First bounded .63/.43 acceptance: effect observation unavailable

The approved run `actor-preparation-ce616a3df0e044c4859d64f888b6f8b4` revalidated
Umbra in PID 8616 with the installed exact DLL and fresh idle scene. It did not
pass: four REGISTER_SELECTORS reads reused request 2 and manifest digest
`10862bd07353869c4178648d02da1e0108959d9d929f4d68b217fa5299fd45f2`; each returned
UNAVAILABLE. There was no OPEN_OWNER, ATTACH_CONTEXT or SUBMIT. STOP_OWNER request
3 confirmed owner CLOSED / NEVER_BOUND. The watchdog and unexpected-operation-stop
flags were false; subsequent passive readiness confirmed owner NONE and no
cleanup pending. No potion use, buff entry or NPC attack is claimed.

A passive read of the existing native publication, without a new registration or
producer, found revision 1, sequence 8, UNKNOWN=2 (effect capture), complete=false
and zero factual/action/application counts. Its sampled tick 316601125 belongs to
the failed requests; its age is not current buff authority. This separates the
failure from selector mapping/open failure. The underlying effect-capture branch
still needs diagnosis before another gameplay test. User-reported potion expiry
is recorded as context, not as native coverage evidence.

Private evidence remains under
`artifacts/bot-deploy/20261001-b43/failed-registration-evidence`:

| File | SHA-256 |
| --- | --- |
| acceptance.json | `b9aa5cd44014f3d4875d6cc27ea5e1d79df9ca8e28aa1738b65fcd542c671624` |
| events.jsonl | `0f072495b1da0f09449242da2304717e1e7e9167681f2cef0aefcf9fbf92a918` |

The private acceptance helper was corrected so a failed NPC runner cannot enter
its later preparation-only phase. The original failure made one extra read-only
registration in that phase; it sent no gameplay action. The revised helper and
readiness tests passed 69 cases. Existing staged helper hashes were left intact;
a revised live helper must be reviewed and pinned separately before use.

## .64/.44 cold-start repair

The source audit identified a deterministic initialization dependency failure.
`actor_effects::StartAtBootstrap` requires `GraphicsExecutableSha256Matches`, but
Initialize called it before `StartGraphicsStatusPublication` populated the hash.
The observer therefore rejected cold startup. Later graphics initialization could
not establish effect history retroactively. Passive inspection of PID 8616
confirmed all nine mutation CALL sites and all three effect virtual slots still
contained their original client values; the prepared entrypoint matched and all
20 observed effect records passed the diagnostic layout predicates. This matches
the startup defect; it is not native absence authority.

The installed repair starts graphics publication before the observer, while the same
synchronous prepared entrypoint still holds the original initializer return
address. The diagnostics worker does not run native actor/effect code. Graphics
failure skips observer installation, and late initialization retains its existing
unavailable behavior. No hash, original-caller or native observation gate is
weakened. The exported-initializer regression models an initially empty identity
cache, verifies dependency order, duplicate initialization and failed-start retry.
The separate synthetic effect fixture exercises the real public bootstrap entry:
cold identity, late caller, failed image verification and mismatched verified base
leave all hook sites pristine; initialized identity installs before entry. It does
not substitute for private exact-image qualification. Focused startup/effect
checks and 481 package-contract tests passed before the source checkpoint.
Host 0.3.64 / native 1.8.44 completed the exact-source qualification below.
The user subsequently approved merge/install; deployment is recorded below.

## Qualified .64/.44 package

Package `artifacts/b44/9282f541` was built from committed source
`1bbd536c791136e3d485cb935b7bc4482d0b1f5c`. The full host suite passed 4,787 tests
with 38 skips. Both native profiles passed 219 tests, with three private-image
CTest placeholders covered by the explicit original/prepared image probes.
Per-profile IPC passed 73 movement, 86 combat and 106 actor tests, with no IPC
skips. Installed-wheel checks passed. All 82 package stages and 110 indexed
artifact hashes were independently verified, including source archive identity,
both version resources and the startup/public-bootstrap regressions. The two
existing transparency diagnostics per profile retained their previously documented
limitations; no new required gate failed.

| Artifact | SHA-256 |
| --- | --- |
| Acceptance ZIP | `5d4d9b8ebdaf8795ee73135d0b0f614daf72caed1286a2df6bd0ce3bb2c1746f` |
| Receipt | `ac09bcba3f9c20ce1ebcfb561ae937cf6f47ef27194df7d8b3b8fb9826238e7d` |
| Full DLL | `94af80cd77835a8ea7efbeb892a880ee171f53e86c91d423064a942cec53b936` |
| Host wheel | `de9e17d99bd04616f4bcb563f446c3f32c509239553ec02e86692becccf3866b` |

Private deployment/acceptance helpers under `artifacts/bot-deploy/20261001-b44`
were migrated from the installed .63/.43 baseline. Qualified pins and dependency
hashes are fixed; 102 offline tests, 26 PowerShell parse checks and mocked exact-path
retirement checks passed. At that source-only checkpoint no payload had been applied
or staged to the VM. Fresh read-only inspection at 23:53:27 UTC found game PID 8616, healthy idle manager 6480/parent500,
and the exact .63/.43 installed identity. That running baseline is diagnostic;
the later installation used a fresh closed-client baseline and new approval. Settings,
jobs and original client assets remain in place; no rollback artifacts were made.

## Installed .64/.44 and first live acceptance - October 2

The user approved PR #60 merge/install. Approved head `23f1674` passed all 15
hosted checks; merge `5c94808` at 00:17:59 UTC retains exact package source
`1bbd536`. Installation verified 463 modules, 9,574 preserved files and one client
DLL inventory change. Manager 7096 was healthy, and all five shortcuts and startup
preflight passed. User settings, saved jobs and historical evidence remain in
place; no rollback copies were made.

After verified activation, the inspected obsolete .63 host (2,116 files) and two
.43 guest payload binaries were removed, totaling 50,804,512 bytes. Four obsolete
host/share binaries totaling 5,617,612 bytes were also removed by exact identity.
Twelve compact receipts and seven installed-file hashes are retained privately
under `artifacts/bot-deploy/20261001-b44/receipts`.

Launch at 00:23:54.8667615 UTC verified DLL
`94af80cd77835a8ea7efbeb892a880ee171f53e86c91d423064a942cec53b936` in PID 7932,
creation FILETIME `134353742281930705`, HWND `3015386`. Passive readiness observed
an alive actor, owner NONE, fresh scene 1 and capabilities 129. Each subsequent
operation still requires fresh exact identity/readiness validation.

The first bounded run remains **not passed**. REGISTER_SELECTORS and OBSERVE_ACTOR
returned OBSERVED. One USE_ITEM entered, received a positive outbound QUEUED
receipt, settled locally and retained application PENDING. No ATTACH_CONTEXT or
NPC attack occurred. The private helper's target picker chose an NPC about 108
units away despite its configured 80-unit camp limit; its strict observation
boundary rejected the frame. The helper ended through exact parent LOCAL_RELEASED
cleanup, and later passive readiness found owner NONE. Local release does not
recall a queued remote potion application.

Preserved evidence is `artifacts/bot-deploy/20261001-b44/first-live-evidence`:
acceptance SHA-256 `69df95e18c6adf6d17d32e51e85ae8c746b7408e92adffede1093d93a396840a`;
events SHA-256 `1423c4b36bd6ccbe2f5bbfca9fe524d4aed80d161fc2a403a2d92e6324ad7e97`.
This run proves registration and local item submission/settlement, not buff
application, potion overlap, duration, expiry, NPC death or server kill credit.
The next acceptance step must use the corrected reviewed camp filter and fresh
canonical coverage/application history, preserving duplicate-potion suppression.

## .64/.44 second live acceptance

The preserved `artifacts/bot-deploy/20261001-b44/live-v2-evidence` result is
**not passed**. Fresh canonical publications reported all nine Greater Concoction
Potion descriptors and Precision PRESENT. No additional USE_ITEM was submitted
in this run. Precision and the saved Shot to the Leg opener queued, followed by
one ATTACK against the pinned NPC `[23883,37]`. Exact STOP_CONTEXT returned
NATIVE_STOPPED at trace sequence 28, retaining the shared parent owner.

After child cleanup, 29 Beorc Rune proposals returned
DEFERRED/NEVER_ENTERED/SETTLED. Along with the three queued actions, they reached
the helper's 32-submission bound (`RuntimeError: Submission bound`). They did not
enter 29 native casts. Final STOP_OWNER returned LOCAL_RELEASED at sequence 211;
no manual-list entries remained and the watchdog did not fire. The receipt still
reported mode 1, action state 2 and a combat target. Parent ownership release is
therefore established, but native idle is not. The result also records
`parent_operation_cancelled` and `unexpected_operation_stop`; these are retained
as reported rather than relabeled a successful run.

Source/trace review found that no-entry Beorc journal updates advance publication
revision even while readiness and coverage facts remain unchanged. The policy's
fresh-revision check can consequently admit another refused proposal. Native
actor-only admission after child closure is also under investigation: publication
reported Beorc READY while SUBMIT deferred, but the recorder did not retain the
per-attempt native detail needed to establish the precise blocker. No cause is
inferred from action state or final target presence alone.

A subsequent read-only census (`post-v2-action-observation.txt`) matched the actor's
AF8 to the same registered NPC key/token. Its health was 201.6433/400 at roughly
two units; its action target was Umbra. The actor reported mode 1, action state 2,
initiation state 5 and an empty protocol vector. These are passive observations,
not damage attribution, an uninterrupted-action history or permission to resume.
They support retaining the native foreign-target guard. The next private
acceptance design will cover a full encounter rather than stopping immediately
after queueing, subject to review; no new gameplay run has been issued.

The subsequent .65/.45 repair below reconciles native admission facts and host
retry progress; its installation remains the next prerequisite for gameplay.
This evidence proves the stated
client coverage and queue/cleanup boundaries, not full buff preparation,
expiry/refresh, potion overlap timing, NPC death, server kill credit or skill
consumption. The first live failure and this partial result remain unchanged.

Compact evidence SHA-256:

- `acceptance.json`: `77a4cfa1a43e2b6cc79b8c90edc9a384898eba469580017136309e99692bf1ca`
- `events.jsonl`: `eb5be76f5cbb8315497ba508e94b50e32797a89f4e59a15bfebba4299b6d4fe1`

## .65/.45 admission repair candidate

The reviewed repair separates native entry eligibility from application-journal
history. Publication schema v2 carries a monotonic admission revision and typed
local blockers: initiation, an in-flight native invocation, retained local work,
a foreign action target, or child cleanup. A shared native evaluator serves both
publication and final entry. An owned encounter target remains eligible under
its existing context; the foreign-target guard is unchanged. Locally settled
potion application may remain remotely pending while other buffs proceed.

The host suppresses a definitively refused action at the same admission revision.
Journal-only updates cannot renew permission. A freshly observed eligibility
transition permits reconsideration; uncertain entered requests remain tied to
their original status/cleanup operation. New capability 0x100 and the v2 mapping
are required for new admission. Existing lifecycle queries and cleanup remain
routable. Typed blocker traces are informational and do not consume a combat
scheduling iteration or impose an all-buffs barrier.

Focused native suites and the production DLL build passed; independent native
and combined source reviews found no outstanding issue. The full host suite
passed 4,836 tests with 36 skips; focused host checks also exercised the real v2
publication mapping and the production runner's no-barrier behavior. Exact-source
package qualification is complete as recorded below. At that qualification checkpoint the candidate was not yet merged or installed;
the later installation and live result are recorded below.

The next private acceptance helper uses one immutable NPC, native health-zero
proof, correlated child cleanup and the same parent owner for remaining buffs.
It retains bounded duration and action counts, optional Shot-to-the-Leg semantics,
and no replay of uncertain attacks. Its 98 offline tests and independent review
passed. Qualified source/artifact pins and nine acceptance dependencies are
frozen against the verified package below. No gameplay success is claimed from
offline tests.

## Qualified .65/.45 package

Package `artifacts/b45/38619e76` was built from committed source
`fc8b316781bba53605729a2bee3578a1ace3b10e`. The packaged host suite passed
4,835 tests with 37 skips. Both native profiles passed 219 tests and all 121
mandatory native gates. Per profile, real IPC passed 73 movement, 86 combat and
130 actor tests with zero IPC skips or errors. The three native private-image
placeholders were covered by explicit original/prepared image probes. The two
previously documented transparency diagnostics per profile remain separate
limitations; no new required gate failed.

Independent verification covered all 82 required stages, all 110 indexed artifact
hashes and sizes, archive entries, exact source identity, wheel RECORD and both
DLL version resources. Installed-wheel checks passed. All 15 hosted checks passed
at the exact packaged source; subsequent qualification documentation must also
pass hosted checks before an approved merge.

| Artifact | SHA-256 |
| --- | --- |
| Acceptance ZIP | `339210b78b68f928cc5317fa074fecff87a269db67a62fe8239056a86d6d1ecc` |
| Receipt | `29444cd060a13f929233b59485fb673517e9990e0ff3265e76137321dc09a2b2` |
| Full DLL | `bc76ae8bac5f464cf81fb3ae75de7e2e836ce3b3d039822bb324ec5ae9bdb777` |
| Host wheel | `681466e70642f28417e5a3d009ed65dbeae3790ff765cebbe63f1f361d434f0e` |

Fresh read-only VM inspection at 12:21:54 UTC on October 2 found the game closed,
the exact .64/.44 installed baseline, healthy idle manager 7096 and all five
shortcuts still pointing to the installed runtime. These are recorded facts,
not permanent process identity or permission to install. Settings, jobs and
historical evidence remain in place. At that pre-installation checkpoint, no .65/.45 runtime had been deployed and
no rollback copies were created. Deployment helper tests passed 17 cases, with
16 verifier tests, 11 distribution ownership fixtures, PowerShell parsing and
exact-path retirement checks also passing. The acceptance helper passed 98
offline tests after qualified pin closure. Final independent review verified
all 36 deployment and nine acceptance source dependencies and reran 131
deployment/verifier/acceptance/readiness tests successfully. Its review covered
the fresh-launch wrappers, qualified artifact identity and current-write disk
requirement without any rollback allowance. The next step at that checkpoint was merge/install approval, followed by a fresh
baseline and bounded one-NPC/buff acceptance after login. The following section
records that completed installation and the failed live gate.


## Installed .65/.45 and first bounded run - October 2

PR #61 merged at `1e7c26f` at 13:17:17 UTC after all 15 checks passed at
`86d76b9`. The user has given standing approval for routine bot merges and
qualified installation; required reviews/checks and preservation rules still
apply. Installation verified 463 modules, 9,575 retained files and one DLL
inventory change. Manager 9932 activated healthy, all five shortcuts passed, and
startup preflight passed. Exact obsolete .64 environment retirement removed
2,116 files plus two .44 guest payloads (50,803,605 bytes); four obsolete staging
binaries totaled 5,617,156 bytes. No rollback copies were retained. Twelve compact
receipts and seven current installed-file hashes are preserved privately.

Launch at 13:23:19.4677569 UTC verified the qualified DLL in PID 7336, creation
FILETIME `134354209911431065`, HWND `3474162`. Following user login, passive
preflight confirmed Umbra/Wonderbane and actor/admission capabilities 0x181.
The bounded run `actor-full-encounter-9046c452a4d648dcb2bef68eb831fd69` is
**not passed**. Three self-power requests queued: Precision at 484 ms, Beorc at
2,234 ms, and Rat Shape at 7,562 ms. Canonical effects subsequently confirmed
Precision and Beorc. Rat remained locally pending through the last captured
publication; its eventual application is not established by this trace.

No potion command was submitted. Across 24 complete publications, all nine
potion descriptors were missing and the item selector reported ITEM_UNAVAILABLE
with zero item/template operands and quantity. This does not establish an empty
inventory: native inventory census failure and no eligible item must be
separated. No potion reuse refusal or pending application history was present.
The user observed the other buffs triggering, which is retained as user feedback
rather than substituted for missing native effect evidence.

No NPC context or ATTACK occurred. Initial nearest-NPC distance was about 80.10
units against the 80-unit test camp. Rat's last queued/pending STATUS was at
12,250 ms; parent STOP_OWNER request 30 appeared at 12,875 ms, before the runner
reported emergency_stop/native_movement_owner_revoked at 14,953 ms. This order
matches the production host's five-second preparation-resolution timeout and
requires fixing pending handling. A later passive telemetry capture retained
last_owner_loss reason `stalled`: interval 281 ms, generation 3 to 4, owner
AUTOMATION to NONE, key bits zero, tick 327954968. This is a native loss record
as well as a preceding host stop request; their timing must be correlated before
assigning a single cause. Final parent NATIVE_STOPPED cleanup completed; fresh passive readiness showed
an alive actor, owner NONE and no pending cleanup. No watchdog fired.

That run led to native potion lookup diagnosis and the repair of legitimate long
pending-buff handling, with shared-owner cancellation and duplicate suppression
preserved. These repairs are integrated in .66/.46 below. Full buff coverage, expiry/refresh, potion overlap and
NPC encounter acceptance remain unproved. Evidence remains in
`artifacts/bot-deploy/20261002-b45/live-evidence`.

Compact evidence SHA-256:

- `acceptance.json`: `adbedd889a105693d57753731104ba0ebfde983010f5c97ad51cb08eb2816e2f`
- `events.jsonl`: `3b58ddcafdf86e78a99585e93335b412d5d1d97ffff58a59d828b501710e7c27`


The subsequent passive inventory census identified a concrete structural failure:
an inventory object at address 314019760 had vtable RVA `0x1143278`, while the
current scanner required the base item RVA `0x1142748` for every node. The census
was rejected before any absence conclusion; its `capture_rejected` record is
`artifacts/bot-deploy/20261002-b45/inventory-observation.json`. This is not an
empty-inventory claim or permission to dispatch through the unqualified class.
The native correction must qualify heterogeneous inventory traversal separately
from strict actionable-potion eligibility. No gameplay action was issued by this
diagnostic. The host pending-action correction independently passed 37 focused
tests and review; native inventory work was still in progress at that point.
Both repairs are now integrated in PR #62, as recorded below.


A second independently reviewed passive census, qualified for the five exact
primary ArcItem classes in the official image, completed across both current
actor containers (11 objects, split 9 and 2). It found two plain ArcItem stacks
for the already-reviewed potion template `[980066,0]`, with quantities 4 and 5
and the required type 8 / flags 0x0a. The report is
`artifacts/bot-deploy/20261002-b45/heterogeneous-inventory-observation.json`.
This confirms the potions are represented in the observed inventory and the
class restriction caused the earlier census failure. Passive rereads do not
prove native locked lookup/retain or dispatch; no item was used by the census.


## Qualified and installed .66/.46 - October 2

PR #62 merged exact source `9e1a77ae9e763a65bfc7f39587c30b3f46c39c4b` into
main at `a983384b2e95a6ab6cc3f46a750265b82ec0bae2`, 14:11:08 UTC. The release
changes the pending-action watchdog to measure unavailable correlated native
status, rather than elapsed action age. A valid live-parent response preserves
an immutable pending/uncertain command without resubmission. Explicit safety
cancellation remains available; remote application pending after positive local
settlement still permits other actions.

The native inventory census qualifies five exact primary classes before reading
common identity fields: ArcContainerObject, ArcDeed, ArcItem, ArcRune and ArcKey.
Only a plain ArcItem with the exact configured potion template `[980066,0]`, type
8, flags 0x0a and positive quantity becomes an actionable operand. Native retained
lookup, complete recapture and current-owner checks remain required. A complete,
stable census with no eligible match is distinct from UNKNOWN after an unreadable,
changed or malformed census. UNKNOWN zeros all item operands and does not block
independently ready powers or fabricate missing-effect evidence.

Package `artifacts/b46/948aa06b` passed 4,857 host tests with 37 skips. Both native
profiles passed 219 tests and all 121 required gates. Real IPC per profile passed
73 movement, 86 combat and 143 actor cases, with no IPC skips/errors. The three
native private-image placeholders were covered by explicit image probes. Each
original/prepared inventory probe passed 10 cases, reusing 48 native primitives
and qualifying all five primary classes. The two previously documented native
transparency diagnostics per profile remain separate limitations; no required
gate failed. Independent verification checked 82 stages, all 110 indexed artifact
hashes/sizes, source identity, wheel RECORD and both DLL version resources.

| Artifact | SHA-256 |
| --- | --- |
| Acceptance ZIP | `33c951be988e3252b5a6b026c86229e226c65b475746c0d100d8a3afe2c07671` |
| Receipt | `36955219c29144a193ab373871a83664782505147ebd13fad97b4d6010b6ced6` |
| Full DLL | `b1393468817344be3722ff923bafe025c3b320e680a88e4a8e3751197e1ba674` |
| Host wheel | `4e811e4b99afdd0e91dca7cd65af1cd4f1580da737bb695dc95889db1a2f68ac` |

Qualified helper review verified 36 deployment dependencies, nine acceptance
sources and the seven-file stage plan; 131 focused helper tests passed. Both
acceptance wrappers now use the same radius 120 for production selection and
validation. One immutable NPC, at most four positively settled attack queues,
one optional Shot opener, one potentially entered action per buff group, and
30-second NPC / 45-second whole-run bounds remain. Uncertain actions only poll
the original command. Buff coverage is not a prerequisite for starting combat.

Installation verified 463 modules, 9,576 retained files and one DLL inventory
change. Manager 9900 activated healthy; five shortcuts and startup preflight
passed. The obsolete .65 host (2,116 files) and two .45 guest payloads totaled
50,825,499 bytes removed after exact ownership checks. Four obsolete host/share
staging binaries totaled another 5,630,514 bytes. Settings, jobs and diagnostic
evidence remain in place; no rollback copies were retained. Twelve compact
receipts and seven installed-file hashes are preserved privately under
`artifacts/bot-deploy/20261002-b46/receipts`.

The verified launch at 17:53:00.5627234 UTC loaded the qualified DLL into PID 7588,
creation FILETIME `134354371726530142`, HWND `5702362`. Passive inspection was
**not ready** at login/loading; no .66 gameplay action was issued. The seven
acceptance dependencies are staged separately in
`bot-actor-full-encounter-20261002-b46`. The next gate requires Umbra login and a
fresh exact-session preflight. Full buff coverage, potion application/overlap,
expiry/refresh and the new full-encounter gate remain unproved; the historical
.65 failure is unchanged.
