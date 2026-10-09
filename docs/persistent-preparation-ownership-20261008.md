# Persistent preparation ownership

This source checkpoint adds the native and coordinator ownership boundary for
background self-preparation. It is not an installed release. The worker and saved
intent integration remains on PR #115; potion interruption reconciliation remains
separate unfinished work. The shared integration destination is `main`.

## Authority and lifecycle

An actor parent has an immutable purpose: `COMBAT` or `PREPARATION`. A preparation
parent has no movement Grant and cannot attach a target, submit an attack, or be
upgraded into combat. Capability `0x200` identifies the new native support. An
unresolved preparation parent owns the same sole actor arbiter and prevents a
competing automated movement acquisition. Conversely, preparation cannot open over
an existing automation Grant, even before that operation opens its actor parent.
It never takes manual movement ownership.

Preparation entry checks exact actor/process/scene identity, native UI and local
movement readiness, and meaningful input for this client. Keyboard/controller input
in another foreground client is not this actor's manual takeover. Controller input
uses configured deadzones. Native paths and queued movement for the local actor
defer new entries; unrelated actors' tree branches are not scanned or required to
remain stable. The passive lookup uses the qualified native unsigned key comparator
(second word, then first), bounded to 64 visited nodes with local path rereads.

Manual activity vetoes new work without making immutable status queries unavailable.
The worker's explicit intent callback is checked again immediately before a new
parent open or action submit. Explicit Pause/Stop behavior belongs to the worker
service; this native boundary does not turn ordinary manual input into a latched
user Resume requirement.

## Passive local settlement

A self-power's local initiation token is armed before the owned followup and
published only for a coherent empty-to-one protocol-vector transition. The token
includes actor key, thread, state pointer, vector storage and generation. Same-actor
ordinary Use, unowned append, duplicate IDs, changed storage, reentrant mutation or
an incoherent read invalidate unresolved proof. The real native first-match remover
must return successfully and change the retained exact single-ID vector to empty.
Generic idle, elapsed time and an old initiation epoch are insufficient.

Mutation invalidators and token publication share synchronization; native originals
and memory captures execute outside that lock. A positively observed removal remains
terminal if later manual work starts. Preparation polling additionally requires the
exact actor lifetime; a later manual cast does not prolong the retired responsibility.
Passive parent stop never
dispatches combat-off or cancels an unrelated user action. It can remain pending
after the host's original cleanup deadline.

`NativeMovementSession.preparation_lease(scene)` claims only the existing producer
transport; `maintain_preparation(lease)` renews that exact lease without reacquiring
movement. `NativeActorCoordinator` exposes:

- `preparation_step(allow_new=False)` for observation and an existing proposal's
  status, without allocating or submitting a new proposal.
- `local_pending` for retained immutable local responsibility.
- `close_unopened()` for failed setup before any native owner/action attempt.
- `finish(reason)` for the original bounded passive cleanup attempt.
- `inspect_owner_closure()` for exact `OWNER_STATUS` correlation with that original
  stop after its deadline, without another stop or a renewed deadline.
- `close_retired_process()` for disposal only after the Windows process inspector
  proves the original PID/creation lifetime is gone. Inspection failure is not proof.

Neither worker thread completion nor transaction settlement proves remote effects.
Application history remains in the native actor journal across parent replacement.

## Potion evidence and remaining work

The provisional all-entry item/PRESENT barrier was removed. The user's subsequent
manual test showed attacks did not cancel that potion activation. Movement did
cancel a later attempt, but the passive packet capture ended without its terminal
power row. Missing packets do not establish failure, permit replay, or settle local
ownership. Quantity decrement and an item response alone also do not prove activation
completion.

The next independent qualification examines ordinary movement call `0x631a3` into
the native actor state setter: it dispatches a CharacterActivityEvent before the
state change. Existing initiation remover hooks do not cover this path. A future
semantic cancellation observation must prove exact actor/power lifecycle and ordering,
handle duplicate or replaced activation as unknown, and distinguish local interruption
from a server response. This checkpoint adds no cancellation-based item retry and no
blanket attack/buff wait for potion coverage.

## Validation and release boundary

Focused host tests cover explicit purpose, no movement/target authority, immutable
cleanup queries, worker admission revocation and exact process retirement. Native
tests cover input gates, local path races, token interleavings, passive parent stop
and preserved remote application behavior. The isolated exact-image initiation probe
passes 27 cases on both original and prepared client 1.3.38.15; those cases execute
qualified append/removal paths, not a live potion interruption.

Full combined qualification, worker integration and installation remain pending.
Any eventual native release must preserve and qualify the user's current cosmetic
overlay separately; this source checkpoint does not replace the running DLL.
