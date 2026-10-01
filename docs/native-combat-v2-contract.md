# Native combat command v2 and engagement fence v3

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

## Same-owner cleanup status

Installed 0.3.57 / 1.8.37 distinguishes movement request readiness from
owner lifetime during native cancellation. Movement status `CLEANUP_PENDING`
(`0x40`) describes only cleanup still owned by the exact current automation
Grant, under valid native bindings, scene and input/safety conditions. READY
stays clear. The host may retain that owner, renew its lease and poll or finish
cleanup; it must not acquire a replacement or submit new movement/combat work.
When native cleanup completes, the same owner can return to READY and ordinary
PvE seeking. Pending cleanup does not count as completed cleanup or server proof.
Changed Grant/scene, terminal/fault or focus/UI invalidation remain permanent
stops. Missing READY without this explicit valid pending state is still rejected.
The host and native changes were qualified and installed together.

## Ownership and identities

One existing producer lease and exact movement Grant own one active engagement
per client. An engagement is an immutable actor/target/authority binding with an
independent, positive 128-bit EngagementId. An action has a separate positive
128-bit RequestId, scoped to that engagement. Both encode as exactly 16 big-endian
bytes and increase monotonically within their exact producer Host and Grant
namespace. They are ordinals, not random UUIDs. The host's session-owned allocator
is stricter: request IDs increase across engagements and coordinator instances,
including later cleanup controls for an older allocated engagement. It retains
only counters, not an unbounded registry. Repeated actions reuse the engagement,
fence and retained native target reference; they do not pause, cancel or reacquire
the owner.

An existing valid AF8 NPC may be adopted through BIND without stance change,
attack or cast. AF8 is the observed combat pointer, not a universal spell target.
An unknown busy cast remains unbound and observed until qualified native action
state permits another action. Animation impact and projectile arrival are not
completion gates.

The existing opaque observation token remains the 96-bit BLAKE2s digest of the
profile image identity, PID and pointer. It must never be truncated or decoded
into the new uint32 address hints. A canonical population resolver validates the
retained opaque token plus native object key and returns fresh process-local
actor/target address hints. The native receiver independently resolves and owns
objects by exact native key, then compares the resulting pointers to the hints.
It never dereferences, retains or grants authority from a host address hint.

The engagement identity includes exact client and producer lifetimes, lease
and movement generations, scene, Grant operation digest, actor and target keys,
address hints, authority and its identity evidence. One engagement ID cannot be
reused with different binding bytes, even after stop or scene retirement.

## Command: 576 bytes

All existing fields and offsets through byte 535 remain. The request field at
240 is the action request ID for action verbs, or a control correlation ID for
engagement verbs. The binding digest at 256 hashes the canonical v3 engagement
fence with its state normalized to REGISTERING; it does not hash the action ID.

The previous 40 reserved bytes at 536 become:

| Offset | Type | Field |
| --- | --- | --- |
| 536 | uint32 | version, exactly 2 |
| 540 | uint32 | authority: MANUAL_PLAYER=1, NPC=2 |
| 544 | uint32 | action: NONE=0, ATTACK=1, CAST=2 |
| 548 | uint32 | power_id; nonzero only for CAST |
| 552 | uint32 | actor_address_hint |
| 556 | uint32 | target_address_hint |
| 560 | byte[16] | engagement_id |

Hints must be nonzero, aligned, bounded 32-bit user addresses, distinct from one
another. Both keys are non-null; the actor discriminator is 53. The command must
agree byte-for-byte with its reconstructed fence binding and exact Grant.

MANUAL_PLAYER requires target discriminator 53, a current complete saved manual
entry, nonzero store/owner/entry/name digests and positive revision. Native name,
server, player type, party and protected-target checks remain mandatory.

NPC requires target discriminator 37, zero store/entry/target-name digests and
revision 0. The owner/local-name/server evidence remains nonzero and is validated
against the native actor. Native NPC eligibility, protected-role/owner and party
checks remain mandatory; absence of a player name is not NPC authority. NPC
fences use the same kernel ticket implementation but are not inserted into an
AttackListStore or supplied with fabricated durable list entries.

CAST binds the verified numeric learned-power ID, not ASS-013, a hotbar slot or
an ArcPower address supplied by the host. Native resolves the verified learned
rank and manager-owned power definition during the owner callback and validates
the supported target/delivery semantics. It does not cache or ArcObject-retain
the definition or temporary learned-rank lookup.

## Verbs and replay

| Verb | Value | Action field | Effect |
| --- | --- | --- | --- |
| BIND_ENGAGEMENT | 37 | NONE | Admit and retain the exact engagement without combat input |
| SUBMIT | 38 | ATTACK or CAST | Attempt this immutable action; atomically bind if absent |
| ACTION_STATUS | 39 | ATTACK or CAST | Return this exact action history plus current engagement state |
| CANCEL_ACTION | 40 | ATTACK or CAST | Tombstone a never-entered action; entered action requests engagement stop |
| ENGAGEMENT_STATUS | 41 | NONE | Observe engagement state without creating or acquiring it |
| STOP_ENGAGEMENT | 42 | NONE | Tombstone the engagement before stopping any owned activity |

ACTION_STATUS and CANCEL_ACTION carry the exact original action command bytes.
SUBMIT replay with the same (engagement ID, action ID) and bytes returns its
prior result; changed power, target, authority, Grant or any other command byte
within that identity is invalid. Action ID 1 may occur in another engagement;
its complete identity differs. IDs are not regenerated after transport timeouts. A second legitimate
action receives a new ID after a fresh policy decision.

Engagement controls correlate their response with their control ID and echoed
verb, but their idempotence is keyed by engagement ID and full engagement binding.
A different control ID cannot reopen a stopped engagement. Unknown status never
creates a record. Unknown STOP installs a durable engagement tombstone before
acknowledgement, preventing every delayed BIND/SUBMIT for that binding. It does
not stop another engagement and does not claim native actor idleness.

A never-entered CANCEL_ACTION installs an immutable action tombstone before
acknowledgement. It does not revoke or release an existing engagement. If native
entry occurred, cancellation stops the engagement because the qualified native
stop primitive is not scoped to an individual spell/attack. Historical native
entry and outbound admission survive that stop; local cancellation does not
recall an already submitted server action or projectile.

## Fence: 320 bytes, schema 3

Use magic WBCFNC3 followed by NUL, schema 3 and a v3 mapping/mutex namespace.
The mapping name is Local\WonderBane.CombatFence.v3. followed by the lowercase
SHA-256 hex digest of the complete binding normalized to REGISTERING; append
.lock for its mutex. Registry keys use this full identity. Ordinal-only names
would collide across clients and Grants and are forbidden. The
16-byte request field at offset 80 now means engagement ID. Existing field offsets
remain. Padding at 272 becomes authority uint32, actor_address_hint uint32,
target_address_hint uint32 and 36 zero reserved bytes. Action ID, action kind and
power ID are deliberately absent: this fence authorizes the exact engagement.

States remain REGISTERING=0, PENDING=1, ENTERED=2, REVOKED=3 and
ENTERED_REVOKED=4. The consumer performs a nonblocking, mutex-protected authority
check before every BIND or new SUBMIT. First admission changes PENDING to ENTERED.
Subsequent actions may use ENTERED only for the same retained native engagement
and complete binding. No transition returns to PENDING. Revoked states, dead
producer, abandoned mutex, unavailable mapping and changed bytes never admit a
new action. Native lease, Grant, object, party and power checks are fresh per
action even when the fence is already ENTERED.

Revocation linearizes against each admission, not merely the first action.
An action already admitted may need native cleanup; a subsequent action cannot
reuse the entered state to bypass revocation. STATUS/CANCEL/STOP remain callable
for the immutable old owner after capability/readiness or current-Grant loss.
They can only report or clean that old engagement and cannot acquire a new one.

Attack-list edits revoke v3 engagement tickets under the existing list record
lock before publishing the new list revision. Incompatible live v2 tickets must
be retired by the coordinated process restart; old sidecar data must not be
silently interpreted as v3 bindings.

## Receipt: 384 bytes

Keep existing offsets through binding_digest at 308. The old 44-byte tail at 340
becomes:

| Offset | Type | Field |
| --- | --- | --- |
| 340 | uint32 | version, exactly 2 |
| 344 | uint32 | authority |
| 348 | uint32 | action |
| 352 | uint32 | power_id |
| 356 | byte[16] | engagement_id |
| 372 | uint32 | entry_state: UNKNOWN=0, NEVER_ENTERED=1, ENTERED=2 |
| 376 | uint32 | echoed verb |
| 380 | uint32 | closure proof |

Every structured receipt echoes the request/control ID, exact Host/window/Grant,
keys, revision, engagement binding digest and new semantic fields. The host checks
all of them plus the transport result before exposing even diagnostic text.

The phase field is explicitly engagement state:

| State | Value | Meaning |
| --- | --- | --- |
| UNKNOWN | 0 | No established engagement state; not proof of idleness |
| BOUND | 1 | Exact engagement and cleanup ownership retained |
| STOPPING | 2 | New actions prohibited; native cleanup remains pending |
| CLOSED | 3 | Engagement permanently closed with the stated closure proof |
| RETIRED | 4 | Exact native scene actually retired |
| BLOCKED | 5 | Ownership/cleanup uncertain; retained and unavailable for new action |

Closure proof is NONE=0, NEVER_BOUND=1, NATIVE_STOPPED=2, SCENE_RETIRED=3
or HISTORY_EXPIRED=4.
CLOSED must carry NEVER_BOUND or NATIVE_STOPPED; RETIRED must carry SCENE_RETIRED.
Other states carry NONE, except the conservative expired-history response
(UNKNOWN state, UNKNOWN entry, HISTORY_EXPIRED proof, no flags). The host
cleanup-confirmed predicate is only
CLOSED+NATIVE_STOPPED or RETIRED+SCENE_RETIRED, never UNKNOWN or NEVER_BOUND.

NEVER_BOUND proves that this engagement never acquired native ownership and its
future admission is tombstoned. It can release a genuinely unentered submission
transaction. It cannot clear a host obligation adopted from an already running
native action. In particular, an unacknowledged BIND followed by unknown STOP
must retain the existing same-Grant native owner-stop obligation until that
separate native cleanup is acknowledged.

Preserve existing request outcome ordinals 0-9, rename LOCAL_CANCELLED(8) to
ENGAGEMENT_CLOSED, and add BOUND=10, ACTION_CANCELLED=11, DEFERRED=12, HISTORY_EXPIRED=13. The outcome
is the result of the requested operation. ACTION_STATUS returns the stored action
outcome and its original action evidence; engagement controls report control
outcomes. Closing/retiring the engagement does not rewrite stored action outcomes.
DEFERRED is a terminal no-entry decision, allowing a fresh policy decision later;
it is not an instruction to retry the same immutable action as new work. For
SUBMIT it carries NEVER_ENTERED; for BIND it carries UNKNOWN entry (no action),
CLOSED state and NEVER_BOUND proof. A fresh BIND decision allocates a newer
engagement ordinal rather than reopening the deferred binding.

Flags retain CLEANUP_REQUIRED=1, OUTBOUND_QUEUED=2 and replace the former local
cancelled bit with UNCERTAIN_HISTORY=4. Native entry and historical flags latch
per action. OUTBOUND_QUEUED implies entry_state ENTERED. ACTION_CANCELLED requires
NEVER_ENTERED and no outbound history. Control requests with action NONE use
UNKNOWN entry and do not invent per-action entry/outbound history. Host accessors
preserve tri-state entry (unknown is not false). CLEANUP_REQUIRED describes current
engagement ownership, not whether this particular action entered. It is cleared
only by a closure proof; never by selected-target absence or null AF8 alone.

A previously queued action may therefore report historical outbound admission
with CLOSED or RETIRED engagement state. The old queued-implies-currently-engaged
receipt invariant must be removed. Diagnostic detail remains bounded opaque
ASCII and is never an admission, entry or cleanup authority.

## Native records and bounded failure

Use separate records: EngagementRecord (immutable binding, retained owner/target,
fence, state, closure proof) and ActionRecord (complete immutable command,
per-action outcome, entered/queued/uncertain history and diagnostic). Native
callbacks update their exact records, not a process-global last action. A
reentrant stop/retirement wins engagement-state publication; a later correlated
return may only add historical action evidence and cannot reopen ownership.

Maintain an engagement high-water ordinal per exact client/producer/Grant
namespace and an action high-water ordinal per retained engagement. Advance the
appropriate high-water value before side effects, only for canonical, fully
validated BIND/SUBMIT/CANCEL/STOP. STATUS and malformed requests never advance it.
An exact active/in-flight or cached record is checked before the floor. An unknown
older/equal ordinal without its record returns HISTORY_EXPIRED and never executes.
That means this handling performs no entry; it is not evidence that the original
action never entered. Entry is UNKNOWN and no outbound claim is fabricated.

Keep bounded recent histories: 256 action receipts belonging to the active
engagement and 256 other action receipts, plus 256 engagement records with
reserved active/latest-closure slots. Records currently used by Execute are
pinned through Bind, Submit and Stop callbacks and cannot be pruned by reentrant
calls. This transient pinning may exceed cache limits during a callback; later
pruning restores the bound. An UNKNOWN state update for an already owned or
ever-bound engagement becomes BLOCKED and retains cleanup responsibility. Floors
are never evicted inside a live namespace. Unknown STOP raises the absent
engagement floor and tombstones the requested engagement, but does not stop a
different active engagement. That exact active engagement remains usable even if
its ordinal is below a later unknown STOP. Unknown CANCEL similarly raises the
action floor without abandoning an exact active/in-flight action; if that exact
action already entered, CANCEL requests whole-engagement stop. Unknown CANCEL
may retain an immutable, unbound engagement record for a later fresh action,
but that prospective record cannot newly bind after a newer engagement has
actually started. Track the latest actual-start ordinal separately from unknown
STOP floors. Older cached prospective records then provide history only; a
delayed old SUBMIT cannot resurrect them after a later engagement completed.

Keep the most recent closed engagement acknowledgement until a newer engagement
actually starts, allowing the host to obtain required cleanup proof before
progressing. Once a receipt is outside retained history, return HISTORY_EXPIRED
instead of manufacturing NEVER_ENTERED or NEVER_BOUND. ENGAGEMENT_STATUS can
separately return a still-cached exact closure proof when an action receipt has
expired. Bounded tombstone/history eviction cannot make an older ordinal eligible
again. Producer/Grant retirement permits namespace reclamation only after old
ownership is cleaned; native current-owner checks forbid reauthorizing that old
namespace. Actual scene retirement remains distinct from losing receipt history.

Stop/cleanup remains available under action-history pressure. No 4096-request
lifetime limit or unbounded global UUID set is introduced for continuous runs.

## Host implementation

- `combat_fence_v3.py` and the Windows ticket backend supply v3 engagement tickets.
  Registration and revocation remain one authority boundary. NPC registration
  uses that shared boundary; it does not use a pretend AttackListStore.
- `combat_wire_v2.py` supplies the strict action/engagement receipt model;
  `combat_channel.py` uses verbs 37-42. Receipt correlation
  includes verb, engagement, action and numeric power before returning detail.
- NativeMovementSession retains the same producer lease and Grant. Admission
  readiness applies only to BIND/SUBMIT; old-owner status/cancel/stop remain routed
  after readiness loss. No timeout retry creates a new UUID or Grant.
- `NativeCombatCoordinator` owns the fence and cleanup obligation for both
  ordinary NPC and manually listed player combat. Listed candidate ranking and
  durable list intent remain policy inputs, not a separate native owner.
- Startup AF8 adoption uses BIND without a redundant attack. New target acquisition
  ranks canonical loaded objects and binds their exact keys; selection cycling is
  removed. Policy emits typed Attack(actor,target) / Cast(actor,power,target).
- Controller proposals are immutable BIND/ATTACK/CAST values with target token/key,
  proposal ID and numeric power ID. Typed BOUND/QUEUED acknowledgements account
  for retained ownership and positively observed outbound admission separately.
  Controller cooldown/action-start accounting follows those acknowledgements,
  not merely emitted intent. Uncertain action submission blocks new conflicting
  actions until exact status/cancellation resolves ownership.
- Intentional retarget, invalidation and explicit stop revoke the engagement,
  confirm exact cleanup, and only then acquire another target from a fresh frame.
  Same-engagement attack/cast actions do not repeat that cleanup sequence.
- The native character session binds process lifetime, login identity and local
  object key independently of saved CFG files. GUI selection, hotbar/F-key
  validation and config-file hashes are absent from native action authorization.
  Legacy intent adapters are not a production fallback. Native power ownership,
  scene and the movement operation remain mandatory; config parsing may serve
  separate diagnostics.
- Capability `0x10` requires the complete v2 owner service and melee/power
  observers. Legacy verbs 34-36 are rejected, and `0x08` cannot authorize object
  actions. Readiness loss blocks BIND/SUBMIT while preserving exact-owner cleanup.
- Full trace records retain the correlated native update and tri-state entry,
  including polling frames without a new policy intent. Historical QUEUED with
  CLOSED/RETIRED maps to rejection of current action authority, while preserving
  the historical evidence. DEFERRED openers remain scheduled for a fresh idle frame.

## Required negative and lifecycle coverage

Golden command/fence/receipt geometry and strict version/verb/zero-field matrices;
same action ID with changed bytes; same engagement with changed actor/target/hint;
key resolution returning a different pointer; manually listed players versus NPC
policy; missing/dead/replaced object; protected/pet/party target; fence revocation
between two actions; queued SUBMIT after STOP-before-BIND; unknown action cancel
inside a live engagement; BIND timeout followed by NEVER_BOUND without false
adoption cleanup; no-input AF8 adoption; repeated cast/attack without PAUSE;
unknown busy cast withholding; action timeout with exact replay/status; reentrant
stop and retirement preserving entry/outbound history; full action ledger still
allowing stop; no fallback to GUI selection/hotkeys.
