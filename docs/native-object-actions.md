# Native object-target actions

Installed host **0.3.58** / native **1.8.38** use exact qualified source
`05c888a4ff1e1443163ef3cb2ea6e2432672c372` with official client **1.3.38.13**.
[PR #51](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/51)
merged at `214bcdede95b8ef4f51cb1b13bdd64a31378dcb1` on October 1,
04:14:59 UTC after all 15 hosted checks passed. Qualification, installation,
manager activation and loaded-DLL identity passed. The bounded .58 basic NPC
attack/cleanup gate passed after login. The skill-opener attempt did not pass:
SELF_POWER remained UNCERTAIN without queue evidence or a followup attack, while
terminal native cleanup was confirmed. The earlier .57 manual-player recovery
pass and unconfirmed NPC cleanup attempts remain separate historical evidence.
See the [deployment record](queued-skills-20261001.md) for evidence and limits.

Host and native ship together. Legacy verbs 34-36 are rejected; there is no
keyboard/hotbar fallback.

## Ownership and composition

The native character session binds the actual client process lifetime, login
identity and local object key independently of saved character CFG files. Hotbar
layout, hotkeys and config-file hashes do not authorize combat. Canonical native
population observations provide target keys, opaque pointer tokens, health,
position and structural eligibility. UI selection is optional diagnostic state;
HUD and combat-log messages do not drive target acquisition, actions or kill credit.
AF8 is an observed combat pointer, not a universal spell-target field.

One `NativeCombatCoordinator` owns the session's exact movement Grant, engagement
fence, action correlation and cleanup obligation. Ordinary NPC policy and the
`ListedCombatCoordinator` saved-player policy use that same owner. Manual players
require current saved intent and transactional list revocation; NPCs require
native NPC identity and eligibility. Neither policy fabricates authority records
for the other. The [v2 command/v3 fence contract](native-combat-v2-contract.md)
defines their distinct immutable evidence.

The controller ranks loaded native objects and proposes BIND, ATTACK, CAST or SELF_POWER
against an exact key and token. CAST and SELF_POWER carry numeric learned-power identities. The runtime
passes that immutable proposal to the shared coordinator, then returns a typed
acknowledgement to the controller. BOUND acknowledges retained engagement;
QUEUED requires positively observed native outbound admission. Cooldowns, opener
progress, interrupt counts and retry accounting advance on the applicable
acknowledgement, never on proposal emission or a truthy transport response.

An uncertain submission remains the same pending action and is queried by its
original bytes. It blocks conflicting proposals until resolved or stopped.
DEFERRED proves no action entry and permits a new proposal on a fresh eligible
frame; a deferred opener stays scheduled. Historical queued evidence accompanying
a closed or retired engagement cannot reopen it or count as current authority.
Trace records retain full correlated native evidence separately from legacy
read-only intent descriptors.

`NativeMovementSession` owns monotonic engagement and request ordinal allocation
across coordinator instances. Requests continue increasing across engagements;
old-owner cleanup can still allocate its control correlation after a newer
engagement has been allocated. No unbounded UUID or per-engagement allocator
registry is needed.

## Native service

`combat_v2_runtime` executes on the existing native owner-update callback, under
the producer lease, exact Grant and scene lifetime watch. Transport workers only
queue immutable commands. The service retains actor and target references across
multiple actions. ArcWorld's qualified exact-key registry lookup resolves both key
words to an owned object reference on that owner thread; fresh address hints are
checked against the resolved objects and never confer authority by themselves.

The character and target checks, current party membership, protected-role/owner
policy and engagement fence are refreshed before action admission. Repeated
actions can use an entered fence only for the same retained engagement. Revocation
blocks later admissions; it cannot recall an action that already reached the
native queue. Append checks remain bounded scalar/atomic predicates under the
native queue lock.

Object-action capability `0x10` is advertised only when the complete v2 native
service and its submission observers are ready. Legacy combat verbs 34-36 are
rejected; capability `0x08` cannot authorize this path. Status, cancellation and
stop remain reachable after action readiness drops, subject to their exact old
owner and command correlation. There is no selected-input or keyboard fallback.

## Explicit melee and power entry

The melee adapter takes the retained target object directly and preserves the
reviewed ordinary native attack guards and call order. It does not read or write
UI selection. Its submission scope binds the actual factory output, owned request
and transferred queue reference; sender and followup observation are correlated
to that invocation. It does not synthesize packets or invoke a raw factory as a
substitute for the complete legality path.

The power adapter takes a numeric power ID and retained target object. It resolves
the current learned rank and manager-owned definition inside the owner callback,
checks supported object-target category/delivery semantics, and invokes the
ordinary native power entry. No host-supplied power pointer, rank, hotbar slot or
key mapping substitutes for those checks. Shadow Touch uses numeric ID 428918601;
its object-target definition was separately inspected read-only in the current
official client data. Definitions are not cached as retained ArcObjects.

SELF_POWER is the actor-directed variant: the NPC remains the bound engagement
target, while native entry derives the actor recipient. New submissions require
capability `0x20`, a supported learned definition and native admission. Generic
saved opening-skill settings are scoped to native server/character identity; the
manager/listener default to basic combat instead of assuming an assassin. A
positive skill enqueue advances to the same engagement's attack without a fixed
250 ms delay, subject to actual native busy/deferred state. Neither a native
power-tracking vector nor queue acknowledgement proves server consumption or
skill application. Existing CAST semantics remain unchanged.

The .58 skill attempt exposed a combat-mode prerequisite gap: ordinary attack
entry establishes combat mode, while the installed power route does not. A native
correction is qualified in .59/.39 on draft PR #52, outside main and the
installed package. Passive exact-session inspection
confirmed Shot's native stance requirement 1 while the actor was in mode 1.
Mode preparation must remain inside the same owned native action, preserving
entry/correlation evidence and rechecking the Grant/fence after callbacks. Host
policy must not emulate it with a hotkey, an extra configuration flag or a delay.
The failed skill receipt alone does not establish the cause; a later owner
revocation was also recorded and its trigger is unknown. Existing owner guards
and no-automatic-restart handling remain unchanged. The [live evidence record](queued-skills-20261001.md) distinguishes
this uncertainty from the passed basic NPC queue/cleanup gate.

Power send and followup interception uses reviewed instruction sites and an
explicit invocation bridge. Native frame provenance prevents a nested unrelated
invocation, even one with matching power and target, from borrowing an outer
scope. A shared append router prevents competing melee/power hooks from chaining
ownership accidentally. Exact produced-message identity, class and payload are
verified before attributing queue admission. Unrelated native calls retain their
ordinary behavior.

Native entry may change local state before queueing. Missing positive queue
evidence is not success. Persistent receipt sinks preserve known entry and queued
history across later C++ or SEH faults; explicit boundary restoration unlinks scope
state before returning from a fault. Faulted owned references are quarantined,
and the service becomes unavailable rather than retrying uncertain native effects.

## Scheduling and cleanup

An already active eligible AF8 NPC can be adopted with BIND and no new attack or
startup pause. An unknown busy cast remains observed without guessing its target
from selection. Native action-state 1 with no pending action is a local scheduling
observation; it does not prove damage, server acceptance or projectile arrival.
Fresh eligible casts and attacks reuse the engagement without an idle toggle or
reacquiring ownership. Native busy state arising after entry does not retroactively
invalidate that action. AF8 becoming null during a cast does not prove cleanup.

Intentional retarget, target invalidation, owner stop and task termination retain
the old target and cleanup obligation until the exact native stop is confirmed or
the scene actually retires. Local stop confirmation requires mode 1, action 1,
no pending action and no combat target. Lost UI selection alone does not interrupt
an engagement. After confirmed abandonment, ordinary policy takes a fresh frame
through resource and camp recovery before proposing another target.

Combat settlement uses an absolute three-second deadline shared by
STOP_ENGAGEMENT polling, PAUSE and fence revocation/closure. Parent cancellation
blocks new actions but retains only the exact pending owner's guarded lease until
closure, safety failure or expiry. Expiry keeps the last correlated evidence and
unresolved obligation; it never becomes a successful cleanup result. Subsequent
terminal movement-owner STOP is separately bounded by the session transport
timeout and may retry once with the same request identity.

Native action and engagement ledgers retain bounded history and monotonic floors.
Records stay pinned through synchronous Bind, Submit and Stop callbacks, including
reentrant cancellation/retirement and cache pressure. UNKNOWN cannot erase an
already owned cleanup obligation; it becomes BLOCKED. Closure can coexist with
historical queued evidence, and neither history eviction nor a new control ID
allows an old engagement to reopen.

## Qualification and remaining delivery

The registry probe exercises actual reviewed-image key lookup and reference
ownership. The explicit melee probe compares ordinary native control flow across
2,048 guard combinations. The power probe checks the actual callsite/frame ABI,
queue correlation and owned-code normalization. Original and prepared client
1.3.38.12 forms have focused probe evidence; their instrumented helper boundaries
do not establish live server acceptance or gameplay effects.

Focused native fixtures cover replay, revocation, busy casts, selection
independence, faults, reentrant stop/retirement and bounded history. Host tests
cover typed acknowledgement accounting, exact pending-action polling, shared
listed/NPC ownership, public-runner cleanup and fresh-frame recovery. These checks
do not replace final whole-candidate validation.

The original PR #46/48 validation is historical. Current .58/.38 qualification
passed 4,203 host tests and 801 subtests; both native profiles passed 202 generic
native cases, all 85 combat IPC and 72 movement IPC cases, plus explicit image
gates. All 15 hosted checks passed before approved PR #51 merge. Installation and
loaded-DLL checks passed. The bounded .58 basic NPC queue/cleanup gate passed;
skill/attack acceptance did not pass and awaits qualification of the native
prerequisite correction and a bounded repeat. The [deployment record](queued-skills-20261001.md) preserves the
earlier .57 manual pass and unconfirmed NPC cleanup attempts separately. Automatic retaliation
remains blocked on the authoritative server-character-session contract. Private
client binaries and captures remain outside source delivery; no rollback copies
are retained.
