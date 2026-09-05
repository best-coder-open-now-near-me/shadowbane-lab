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
and exact native helper digests, and copies only those reviewed import-free,
relocation-free helpers into its own process. Relative calls between the lookup,
its comparator thunk and comparator retain their original spacing; unused gaps trap. Memory changes from writable to
executable/read-only before execution. It never opens or modifies another process,
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
not a replacement container implementation. It does not verify native allocator
cleanup, action-queue reentrancy, path cancellation or server behavior. Those remain
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
