# Native object-target actions

The shared native object-combat implementation and cleanup-pending correction
are merged through [PR #49](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/49)
at `18e65bba0229771895bcf159eea96977a43ecc99`. Installed host **0.3.57** /
native **1.8.37** use exact qualified source
`1d107a25c1356d20a0b633cc411d6b5efdc47a9b` with client **1.3.38.13**.
The bounded live manual-player attack, list removal, native cancellation and
strictly later PvE SEEKING gate passed. This does not establish a server-accepted
hit or NPC/cast acceptance. See the [deployment and live receipt](client-update-20260930-late.md).
Host and native ship together; legacy verbs 34-36 are rejected and there is no
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

The controller ranks loaded native objects and proposes BIND, ATTACK or CAST
against an exact key and token. CAST carries a numeric power identity. The runtime
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
are complemented by the qualified whole-package and bounded live gate below.

At the historical PR #46 checkpoint, the integrated host suite passed 4,041 tests with 33 explicit skips and 801
subtests; repository Ruff passed. Both native profiles, required original/prepared-image
package gates and all 15 hosted checks passed at the approved source head. PR #46
is merged; PR #48 subsequently qualified and installed client 1.3.38.13.
PR #49 subsequently corrected same-owner cleanup readiness and installed .57/.37.
The manual-player cancellation/recovery gate now passes; NPC/cast acceptance
remains open. Exact package and live evidence are recorded in the late-update receipt. Automatic retaliation remains
blocked on the separate authoritative server-character-session contract. Private
client binaries and diagnostic captures remain outside source delivery; no
retained deployment rollback artifacts are created.
