# Passive movement boundary investigation

This is an **unfinished-feature diagnostic**, disabled by default. It provides no
movement or camera actuation and does not make WASD/controller/drag available.
The integration owner reconciles startup/rollback and the combined package. Do not
install this branch's DLL independently or replace the shared client/VM.

## Question answered by this trace

For the reviewed client's native world-update virtual dispatch, which thread and
receiver execute it, and what native path-count/movement-state values are visible
there? Static inspection identifies the update and its native movement call. A
read-only guest memory check matched the entire normalized update digest and original
virtual slot, but cannot establish execution/thread identity. Existing diagnostic
artifacts contain no armed trace of this boundary.

The trace does **not** establish immediate stop, server acknowledgement, action-queue
cancellation, text-entry classification or complete collision-preserving steering.
Idle state alone cannot prove those behaviors. They remain movement-assignment work.

## Source and lifecycle

`movement_boundary_trace.cpp` validates the current reviewed executable fingerprint,
all 2350 bytes of the update method normalized over its 63 PE relocations, and the
original thunk before the existing atomic slot helper installs one passive callback.
Only the reviewed executable variant checked in this assignment is supported.
There is no search or fallback. Every call forwards the original receiver and double
argument and preserves its integer return. No engine functions other than that
original update are called; no actor, destination, camera or UI values are written.

Initialization follows process pinning and graphics executable verification, before
the shared renderer starts. This feature branch originally made opted-in trace
failure participate in initialization rollback. The integration owner reconciled
that wiring as optional: failure immediately stops the trace and allows ordinary
client initialization to continue. With the opt-in unset, no mapping or slot change
occurs. Use the combined initializer for package validation.
One lifecycle mutex serializes production/test admission and stop, and admission
compares the supplied creation FILETIME to GetProcessTimes for the current process.
A retained generation is never reset or restarted. Stop disables publication, drains the bounded publication section, and restores only
our own slot. The original function pointer, code and 18,480-byte mapping remain
process-pinned, including startup failure and late callback cases. There is no worker,
input sampler, command receiver or competing movement authority in this diagnostic.

The mapping name includes PID and creation FILETIME. Its header has magic `WBMVTR1`,
schema 1, record size 72, capacity 256 and exact identity. Each record commits its
sequence after its payload; the read-only collector accepts only identical committed
slots across two independent reads. Overwritten/missing sequence counts are retained
in output. Read failures are explicit. The schema-1 `ui_candidate` field has now been
identified as the native item-drag payload; it is **not a text-entry predicate**.
The field name is retained for ABI compatibility. `modal_candidate` also remains
unverified as a complete UI gate. Neither field may enable or suppress controls. Captures include process-local addresses and stay private under `artifacts/`.

## Reviewable procedure through the existing package workflow

1. The integration owner reconciles this source and runs both native profiles and
   their boundary/policy CTests, plus the Python collector tests. Package with the
   existing builder and record the combined SHA/package hash. This checkpoint does
   not authorize an early shared VM/client replacement.
2. If a narrowly scoped connected observation is authorized in that workflow, set
   `WONDERBANE_MOVEMENT_TRACE=1` **only in the intended client launch environment**.
   Do not set it globally. Unset it for all ordinary launches. Use the existing
   client lifecycle; do not attach a second DLL or inject a separate tracer.
3. After successful initialization, obtain that client's PID and process creation
   FILETIME from the existing verified identity. Run the installed Python module:

   ```powershell
   python -m shadowbane_lab.client_extension.movement_boundary `
     --process-id <verified-pid> --creation-filetime <verified-filetime> `
     --seconds 10 --output artifacts/movement-boundary-private.jsonl
   ```

   The output must not already exist. Run the collector in the same Windows session
   as the client. It opens the mapping read-only and performs no client input.
4. First capture idle world updates only. Check stable receiver, `read_valid=1`,
   monotonically increasing sequences and native delta, and compare observed thread
   to the exact foreground client's window thread. Retain disagreements as evidence;
   never enable actuation just because a method is named Update.
5. Request any further connected observation only for its remaining specific fact.
   A later queued-path/cancellation test needs an independently verified native stop
   implementation and appropriate bounded test; this trace is not that proof.

## Developer validation

Both Win32 DLL profiles build and all 22 CTests pass in each profile. Production tracing code is compiled into tests with
an isolated test-only installation seam and test original callback. Tests cover
opt-in absence, unsupported executable rejection, exact lifetime header, duplicate
start, committed publication, invalid receiver reads, unchanged call-through,
held original callback across shutdown, callback after shutdown, startup failure
after slot visibility, retained mapping/code responsibility and replacement-slot
protection, stale creation-time rejection and concurrent stop blocked behind a held
installation. The test seam is absent from production builds. These are lifecycle
regressions, not a substitute for observing the real client thread.

Python tests verify ABI sizes, exact-client rejection, two-read coherence, ring
wrap/overwrites, sequence regression, malformed size and nonfinite delta rejection.

## Native input findings

Static inspection followed registration, the Windows message dispatcher, native GUI
key delivery and focused-control handling in the reviewed executable. A read-only
snapshot of the existing exact client matched the registered text predicate,
keyboard callback and text callback pointers. No callback was installed or called
by that probe. These are binding evidence, not connected controls acceptance.

| Native boundary | Verified behavior | Remaining requirement |
| --- | --- | --- |
| Text-entry predicate | Checks an active HUD and the front HUD's focused control; accepts the three native editable-control kinds also handled by the text editor. | Invoke only through a fingerprint-verified binding on the owning thread; combine with modal, scene, focus and inventory ownership. |
| Keyboard callback | Four caller-cleaned arguments: virtual key, modifiers, down/up, repeat. The dispatcher derives down/up and repeat from the Windows message flags. Extended Enter is translated to a distinct native key code. | Intercept only enabled movement bindings with paired press/release handling; preserve all other callbacks. |
| Character translation | The message pump consults the same text predicate before translating ordinary keydown messages into text. Text/IME events use a separate registered callback. | Preserve text/IME handling while chat owns input; never swallow movement-letter text in an editor. |
| Focused control | The native getter obtains the front HUD through native dynamic casting, then reads its focused control. The keyboard handler first offers input to that control before game-action bindings. | Do not replace dynamic casting with an assumed raw base-pointer layout. |
| Item dragging | The previously collected UI candidate is set by the native item-drag/cursor path. | Treat it as inventory-drag evidence, not evidence that chat is or is not focused. |

The callback registrations avoid a need to synthesize input. Their presence alone
does not establish an installed interception lifecycle or complete UI classification.
Raw disassembly, addresses and process snapshots remain in private local artifacts.

## Cancellation findings and rejected shortcuts

The native movement request checks restrictions and rejects a destination too close
to the player **before** reaching its pending-path cancellation block. Therefore a
request to the actor's current position is not a complete stop operation.

The local stop method resets the native destination and movement state but does not
erase the queued path or cancel the separate asynchronous path request. The world
update can finish that request and repopulate the path. The native path-vector erase
routine and action-queue erase routine are separate boundaries; the latter does not
by itself remove the separate scheduled-action entry.

The movement-state setter can build a native outgoing message while applying a state
transition. Its update path then clears the state-change flag. Calling local stop
first and asking for the same state afterward can therefore return no message.
Normal movement selects the moving state, and the local stop selects idle; the
animation dispatcher corroborates those meanings. Those states must not be forced
over death, incapacitation or other movement restrictions.

Complete stop still needs a verified ordered operation covering current destination,
queued path, asynchronous request, active and scheduled actions, and native server
notification. A scheduled null action is not an acceptable synchronous stop if it
can later cancel a replacement owner's command. Neither an idle snapshot nor the
policy tests prove that ordered operation. No stop binding is enabled yet.

## Actual native tree-removal conformance probe

`wonderbane_extension_movement_tree_probe` is an explicit developer-only target,
excluded from normal builds and not linked into or installed with the extension.
It accepts a locally supplied reviewed executable, verifies the entire file SHA256
and exact native helper digests, and copies only those reviewed helpers into its
own process. The container and continuation helpers are import-free and relocation-free.
The native pool-return helper has an exact reviewed relocation list, private allocator
globals, and only its two verified Win32 imports: InterlockedExchange and Sleep.
No game API is stubbed. Relative calls between the lookup,
its comparator thunk and comparator retain their original spacing; unused gaps trap. Code memory changes from writable to
executable/read-only before execution; private allocator data is never executable. It never opens or modifies another process,
loads the game, supplies input, connects to a server, or distributes client bytes.

Build and run it explicitly from the configured Win32 build directory:

```powershell
cmake --build <build-directory> --config Release --target wonderbane_extension_movement_tree_probe
& <build-directory>/Release/wonderbane_extension_movement_tree_probe.exe <local-reviewed-client-executable>
```

Both profiles passed 64,256 actual native lookup/copy/removal/destruction sequences
across 1,024 generated trees
with ascending, descending and deterministic shuffled deletion orders. After every
removal the probe checks parent links, ordering, node identity, extrema, color and
black-height invariants, and every payload word including detached nodes. Native
lookup must find the exact two-word identity before removal and return the sentinel
afterward. Cases include zero, unsigned high-bit values, all-one words, identities
sharing one word, and a missing key adjacent to the maximum identity. Native copy
returns the destination identity unchanged, and its native destructor is a no-op. A supplied
unsupported executable is rejected before executable memory is allocated.

This verifies native lookup, value copy/destruction and generic detachment/rebalancing,
not a replacement container implementation. The later pool-return extension below
verifies native allocator cleanup. It does not verify action-queue reentrancy,
path cancellation or server behavior. Those remain
part of the complete stop binding. The purpose is precise removal of the retiring
actor's scheduled entry without retaining a delayed cancellation or clearing unrelated
actors' entries. A different native map's erase wrapper cannot be reused blindly:
its payload destructor and allocation size differ from the scheduled-action map.


Further static checks established that scheduled-entry keys are plain two-word
identities. Their destructor is a no-op; scheduled nodes still require the native
40-byte pool return after detachment and a map-count decrement. Active-action nodes
use a different size and payload destructor. The native continuous movement caller
uses a ten-unit look-ahead destination and its own message throttling. Its differing
final wrapper argument affects deferred action construction, not pathfinding; it is
not a safe shortcut for bypassing collision or asynchronous path handling.

## Follow intent and restricted-state continuation

The native world update can initiate combat-target following from either persistent
combat-close preference or temporary follow intent. Native configuration and UI
messages corroborate that behavior. A manual owner must retire both forms before
movement submission; release must not restore them. The existing UI toggle changes
only the persistent form, so it is not by itself a complete cancellation operation.
Camera-only input must preserve both follow and automation ownership.

A separate native helper clears path continuation only when the native path vector
is empty. Unlike the broader local-stop method, it does not select the idle state.
The actual-code conformance probe now invokes this exact reviewed helper in 144
cases and checks entire actor/state snapshots before and after two consecutive
calls. This verifies empty-path preconditions, nonempty-path preservation and
idempotence while preserving all tested movement-state values. It does not verify
path element destruction, follow retirement or complete stop/network ordering.

## Native scheduled-node allocator conformance

Both profiles now execute the native scheduled-node key destructor and 40-byte pool
return after each of the 64,256 removals. The probe checks the returned node, previous
free-list head, preserved payload, untouched other size classes and released lock.
A separate forced-contention case waits for the native allocator's failed exchange
before another thread releases the private lock. The allocator completes through
its real Win32 synchronization dependencies. No client allocator globals or live
process memory are accessed. Full-file and per-helper seals precede execution.

This completes isolated verification of scheduled-node lookup, detachment, key
cleanup and native pool return. It does not complete actor/action lifetime handling,
selective retirement of queued movement, follow intent or state-message ordering.

## Native path destruction and retiring-actor lifetime

Native path elements contain coordinates and an owning reference. Whole-path erase
calls the element destructor, which releases through the object's native interface
adjustment and reference lifetime. Clearing vector bounds directly would leak that
ownership; dropping the actor before native cleanup callbacks finish could invalidate
later stop steps.

The actual-code probe now executes native whole-path erase and its element destructor,
native actor retention/release, and native reference increment/decrement helpers.
Both profiles pass null and allocated-empty paths and sizes 1, 2, 7, 31, 127 and
1,024. Cases include shared references, null and native sentinel references, repeated
clear and an explicit retiring-actor lease across destruction. It verifies unchanged
coordinates/capacity, cleared references, exactly one finalization per probe-owned
object and actor survival until its explicit release. Finalizers record events on
probe-owned virtual objects; actual game-object destructor behavior is not exercised.

The two additional verified imports are KERNEL32 InterlockedIncrement and
InterlockedDecrement. Their sealed native callers use private reference objects;
no connected client or actor is touched. The previously verified continuation,
scheduled-container and allocator tests still pass in both profiles. Complete stop
must compose these lifetimes with exact owner/scene checks, pending-request and
follow retirement, action queues, destination cancellation and native state-message
ordering before runtime capability or connected acceptance is justified.

## Ordered stop implementation and verification boundary

The production executor is now `movement_native_stop.cpp`, with the reviewed-image
binding seal in `movement_native_image.cpp`. It consumes the existing policy's
captured grant and uses native lifetime, action, scheduled-tree, pool, path,
continuation, destination and state-message operations. The only direct engine
writes reproduce the reviewed cancellation intent fields for follow and the pending
path request; actor coordinates, movement speed and restriction state are untouched.

Execution requires an explicitly admitted native-update phase on the exact window
thread, before the original update runs. The future runtime hook must establish
and close that phase; polling/render/teardown callbacks may not call it directly.
The executor revalidates authority and actor/scene identity after native callbacks,
rejects callback-created residual work, and prevents an old state message or stop
from reaching a replacement actor. A native exception latches unavailable and
retains ambiguous resources rather than guessing reference ownership or retrying
an uncertain send.

The new CTest exercises this production composition with controlled native-call
boundaries. Its follow/world-update driver checks retired movement sources but is
not the unmodified game update. Full native execution, positive loaded-code binding
in the running client, movement/camera/picking adapters and server-effect acceptance
remain to be validated as part of the complete candidate. No owner gameplay pass
or runtime capability is justified by these unit tests alone.

## Pending-request ownership and missing-connection correction

The reviewed native move routine first compares its receiver to the current-player
global. Its pending-slot allocation/replacement branch checks that comparison again.
Both initial processing and the world-update continuation pass the current-player
global into the path processor; successful results are installed on that same
current-player global. This is the client's current-player pending slot, not a
per-arbitrary-actor request queue. No independent request actor/world identity tag
is assumed or claimed verified.

The stop executor now seals the exact pending pointer once per execution, together
with the captured player identity, world, window, scene and policy grant. A later
stop in the same manual grant obtains a new transaction snapshot. Every actual
native callback boundary rechecks the captured scope and request pointer before
further cancellation. A callback replacement is not adopted as the latest request:
cleanup aborts and the replacement object remains untouched. Tests cover replacement
from action destruction, path destruction, and actor/world changes during state
notification, as well as absent requests and successive stops in one grant.

Callback boundaries include action/object/path destruction, state/animation
notification, message send and reference release. The sealed scheduled lookup,
detachment, identity destruction and pool-return group does not invoke gameplay
callbacks: lookup/detachment/value destruction are native container primitives;
the pool's only external calls are verified Win32 InterlockedExchange and Sleep.
The executor nevertheless checks current scope again before the map-count write.

If moving-to-idle produces a message but the native connection is missing, stop now
returns failure/unavailable after local cleanup and owned-reference release. It no
longer reports completion without sending. The regression verifies no manual move,
no send, balanced references and latched unavailability. Both profile DLL builds
and focused production-composition tests pass. These checks still do not constitute
unmodified-engine or server-effect acceptance.


## Native controller camera adapter

The reviewed native orientation setter (RVA `0x51c210`, thiscall, four stack
arguments: pitch, yaw, distance, relative-target flag) provides a camera path that
avoids the mouse gesture accumulator. With the relative-target flag false its
sealed branch writes the native orientation/distance and dirty flag and does not
access the camera target or change the parent-relative yaw offset. The adapter
preserves distance and existing mouse inertia, adds the production policy's elapsed-
time radians, and applies the same native pitch limits: -45 to +85.5 degrees.
Native camera matrix and collision processing remain with the original update.

This is deliberately distinct from the gesture delta functions: when smoothing
is enabled those accumulate previous inertia per invocation. Calling them once per
render frame would not establish frame-independent controller sensitivity. The
orientation adapter uses the existing verified image seal and admitted client
update phase, preserves the current movement grant, and does not call stop/send.
A camera fault is isolated by the controls policy from movement availability.

Production-composition tests use controlled native-call doubles. They check equal
one-second yaw at 5, 10, 20, 40 and 100 ms intervals, preserved automation ownership,
native pitch limits/distance/inertia, neutral input, invalid input, wrong thread,
outside-update rejection and camera-failure isolation. They do not certify the
real native camera update, rendered result or connected package.

The native continuous movement routine updates the collision-aware destination
locally and separately gates message publication. Its reviewed time constants are
0.2 seconds for orientation publication and 0.4 seconds for changed-heading move
publication. The complete steering adapter still needs to preserve the native
start/change/continuation semantics; these findings do not license a destination-
spam approximation or establish a completed input feature.


## Native steering composition and coordinate correction

The native ray result helper is a parent-local result, despite its earlier working
name suggesting a world-space result. The helper calls the actor parent's native
conversion; that conversion copies the native transformation, invokes the imported
`math::Transformation::Inverse`, then `Transform`. Ground picking therefore must
retain native parent semantics. It must not pass arbitrary world coordinates to
movement or replace terrain picking with a plane. The directional backend accepts
normalized X/Z in that native parent-local frame; runtime camera basis/pick wiring
must supply this frame explicitly.

The backend now binds the reviewed continuous-target constructor and native Move
wrapper. It uses the native continuous routine's look-ahead constant, passes native
collision/path admission and continuous/deferred flags, and leaves speed, state,
animation restrictions and actual path resolution to the native movement code.
It does not write actor coordinates or native input flags. Unchanged direction
waits for an in-flight native path solve or deferred actor action instead of
restarting it each input poll. Changed direction reaches native replacement.

Outgoing native messages are built/submitted on start and at a 400 ms refresh
cadence while steering; local native updates are independent of that publication
cadence. The refresh is intentional even for unchanged heading because the move
packet contains a finite native destination. This is not proof of connected
responsiveness or server acceptance at every native movement speed. Those remain
combined connected acceptance requirements, along with obstacle/path interaction.
Null native output preserves normal rejection/deferred semantics; it is not an
excuse to disable collision/restrictions. Native send consumes its owned reference
once, and scene invalidation releases unsent output.

Production-composition tests exercise policy through this steering backend with
native-call doubles at 5/10/20/40/100 ms intervals, analog direction, solve/deferred
coalescing, direction changes, real shared release/stop, stale ownership and a scene
change during movement. That last test initially found cleanup capturing the new
actor under the old policy scene. Stop now reuses the movement transaction's actor
identity and refuses to act on the replacement; the test passes in both profiles.
These tests do not execute the native collision solver/world update or server.


## Native object lifetime boundary

The sealed generic reference Release at RVA `1311b0` decrements its reference
count and, at zero, calls interface vtable slot +4 with ECX equal to the reference
interface and one flags argument of 1. The reviewed release thunk is RVA `26f49`.
Actor and parent native reference wrappers obtain that interface using object+8's
virtual-base table and its +4 offset. The observer accepts only that exact release
thunk, readable/aligned reviewed-data tables and a finalizer in authenticated native
text. This verifies the invoked interface ABI for the tracked type; other release
implementations are unavailable. It does not assume an arbitrary actor vtable is
a reference interface or infer a parent's allocation base.

For the reviewed ArcCharacter reference interface, finalizer thunk RVA `6a46`
reaches the adjustment wrapper at `970d0`, then scalar destruction at `48810`.
The adjustment recovers the character allocation and the deletion flag frees it.
The observer executes before that finalizer, with immutable per-slot original
call-through. It observes parent finalization through the same verified reference
ABI, including when the parent and actor have different allocation layouts.

World construction at RVA `1f6cd0` is reached through its thunk only at the two
reviewed allocation sites (`1f524b` and `370b44`), both following allocation of
0x210 bytes. The world destructor thunk's three reviewed callers (`3734e6`,
`51ff68`, `79fad0`) deallocate the original allocation through the common native
free wrapper. That wrapper reaches the reviewed MSVCRT free import slot at RVA
`16b0504`. The observer verifies import identity and its actual CRT export before
replacement. Only the exact currently watched world allocation and captured watch
generation can invalidate a scene; unrelated and null frees merely call through.
A world is not assumed to have a vtable at offset zero.

`movement_lifetime` assigns an epoch to the verified native actor/ID, parent,
world and game-window tuple. Finalization/deallocation invalidates it before the
original call, never actuating gameplay. In-flight destruction prevents rearming
the same allocation. A different tuple can be watched while an old original is
held; that old callback's completion only removes its in-flight notice and cannot
invalidate the replacement. Same-address reuse after destruction obtains a new
epoch. Non-playable/invalid capture intervals also retire the prior epoch.

No lock spans original call-through. Watch state, slot records and originals are
process-pinned; terminal failure/retirement restores only owned slots and preserves
already-dispatched callbacks. Partial install failure cannot restart. NativeStop
requires the exact observed epoch in production BeginUpdate and checks it again
at every existing scene/current boundary, including stops. These tests use
controlled native originals and are not connected native-engine certification.


### Watch arming correction

The first implementation installed a reference slot after capturing its object,
leaving a publication interval not covered by already-watched lifetime tests.
Registration now prebinds the exact 34 reference-finalizer slot/original pairs in
`movement_lifetime_bindings.h`, derived from the reviewed image's RTTI hierarchies
containing ArcObj. The complete list was compared against that image (the SHA above)
and matched all 34 entries. Runtime also checks each exact original and generic
release thunk. This is a bounded actor-family list, not hooks for unrelated native
reference types. Observe cannot lazily register a newly discovered type.

A short arming fence begins before the authoritative capture of a new watch.
Callbacks announce entry before their pointer fast path. Unrecorded originals
already in flight prevent arming; callbacks overlapping capture mark the snapshot
uncertain. Publication checks that fence while holding the metadata lock. A callback
entering immediately after that check waits on the lock and invalidates the newly
published matching watch before running its original. Arming is sampled before
watch generation so a callback cannot pair an old generation with the post-publish
unarmed flag. Original calls never run under this lock.

Already watched held originals have exact in-flight object notices, permitting a
disjoint replacement while still prohibiting the same allocation. Their completion
cannot invalidate that replacement. Ordinary free traffic outside arming only
checks exact watched identity; its entry/exit accounting is not scene authority.
Interference with an unpublished snapshot rejects that observation and does not
assign an epoch or invalidate an unrelated established watch. The established-watch
fast path does not open a new arming interval on every update.

Production barriers test first and replacement capture, destruction already in
flight, completion before publication, held originals and entry after the final
admission check. Same-address post-destruction capture must obtain a fresh epoch.
Batch prebinding rollback preserves foreign replacement and both previously and
briefly dispatched originals. Both complete DLL profiles and 34 focused
policy/backend/lifetime tests pass with zero skips. Controlled native originals
exercise lifecycle composition; connected input acceptance remains separate.


## Native UI and input event ordering

The reviewed keyboard callback at RVA `453cc0` accepts four cdecl arguments
(virtual key, modifiers, down, repeat). Its event submission thunk reaches RVA
`7c7d10`, which both inserts and immediately drains the native event queue,
dispatching through active UI/game-window handlers before returning. The native
update driver later invokes the game-window update slot. Thus the existing
pre-update controls consumer can inspect UI effects of earlier native key events;
there is no evidence requiring a second input phase or delayed UI guess.

The native text predicate is RVA `453c40`; focused-control getter `77f8b0` resolves
the current HUD focus. Text kinds 5, 6 and 14 own input. The native modal global
is checked at the beginning of native update; native input-inhibit bits are in its
manager's +28 field. Window +28 is the existing item-drag payload. The native
camera-gesture predicate reads its existing pointer-state +18 byte, separate from
movement ownership. Top-level hit-test RVA `7834f0` walks visible native HUDs and
uses their rectangle/transparent-child rules, preserving inventory/world-map UI.

Native mouse dispatch scales physical client coordinates by native resolution
versus native window rectangle extent. The reviewed rectangle getter thunk RVA
`25167` copies the rectangle at native-window +8. `NativeClientPoint` verifies
that getter and validates extents before converting. UI hit testing and production
terrain/basis unprojection share this conversion. A read-only connected snapshot
confirmed the getter binding and coherent physical/native extents; no input was
sent and no game call was invoked by that inspection. Private inspection helper
remains under artifacts/native-movement/inspect-input-live.ps1.

### Native input HWND and keyboard consumer

The reviewed image's input-manager root leads through its window object to the
HWND returned by native CreateWindow. Creation stores that return value in the
window object's HWND field; teardown calls DestroyWindow on it before clearing
it. Native IME context acquisition uses the same field. Production input now
checks this chain rather than choosing a similarly titled/foreground window.
The keyboard dispatcher calls its callback cdecl with key/modifiers/down/repeat
and explicitly ignores the return value; the hook forwards those four arguments
unchanged for original-owned events. Private disassembly remains in the task's
ignored evidence directory. This static verification does not certify live input
or server movement acceptance.
