# Unified native movement controls

Feature branch: `codex/native-movement-controls`.
Worktree: `.worktrees/native-movement-controls`.
Assigned starting source: `0c807ee774859cc3f17f9ebc04d3f0a900bd0428`.
Initial checkpoint PR: https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/31
PR #31 was merged at `8536b20576fc11bc2ee33e49761f104753165b75`; it is not
an open review of subsequent commits.
Initial PR/integration destination: `codex/native-lifecycle-hardening`.
The existing hardening owner owns shared reconciliation and combined packaging.
The normal shared checkout remains on `main`. Terrain-repair branches are excluded.

## Status: unfinished, not a connected candidate

The native per-client interpretation and ownership policy is implemented in
`movement_controls.h/.cpp` and exercised by its Win32 CTest target. It is not yet
called by the extension. No controls capability is advertised, no installed package
has changed, and no native binding is enabled. This checkpoint must not be treated
as the complete requested feature or as an acceptance package.

The production policy requires a synchronous owning-client-thread actuator. A
movement ownership grant contains a generation, scene lifetime, owner and lossless
bounded worker/operation tokens. Automation acquisition requires the expected
current generation, produces a new grant, and stops the previous writer before
accepting its replacement. Manual direction or qualified drag revokes automation
immediately. Release stops movement without resuming the route. Old movement,
acquisition and stop requests are rejected before reaching the actuator. A failed
stop retains stop responsibility and excludes a replacement writer. Retiring a
scene discards old-scene work rather than stopping a replacement character.

The interpretation policy uses camera forward/right vectors projected onto the
native ground axes. Opposing keys cancel, diagonals and analog movement direction
are normalized; no analog movement speed is invented. Right-stick camera movement
uses elapsed time and does not acquire movement ownership. Focus/UI loss, controller
loss and capture loss require neutral/re-arm. Controller selection is an explicit
XInput slot. The default drag binding is XBUTTON1, with a six-pixel threshold;
invalid ground picks never fall back to a plane. These settings are internal typed
configuration so far, not an installed settings UI.

## Investigation performed in this assignment

The assigned source's travel implementation dispatches through `ClientInputAdapter`
and the minimap compiler. `InputCompiler.compile_movement_stop` explicitly rejects
immediate-stop requests. `client_action_dispatch.h` advertises transport only and
rejects actuation. Existing navigation, obstacle and rune-hunt behavior is retained.

Private, read-only inspection of the locally available reviewed client located the
movement atom, ground-pick/move-request chain, camera rotation routines, client update
candidate, native destination reset/movement-state routine and separate pending-action
queue. A native log containing "Come to Stop" was traced to another forward
destination, not accepted as proof of immediate cancellation. The native stop
candidate's local destination/state changes do not by themselves prove cancellation
of queued path work or correct server notification. Calling conventions, receiver
lifetimes, UI ownership and owning-thread invocation still require verification.

Scratch disassembly, executable references and local tools remain private under
`artifacts/native-movement/`; no client binary or private capture is source material.
No live observation requested: investigation is still making progress locally.

## Coordination

Coordination uses the already established hardening task communication channel.
The integration owner confirmed immutable captured generation and no refresh after
revocation. Requested manager seam: existing operation admission obtains an exact
native ownership grant, persists it with worker/operation identity, and carries that
same grant into travel/PvE movement and stop. Native rejection interrupts the
operation; renewal must not reacquire ownership. The owner is implementing operation
claim/latching repairs; this feature owns native actuation and adapters. No second
control plane or new baseline-approval milestone is introduced.

## Validation of this checkpoint

MSVC Win32 Release `/W4 /WX` builds the controls policy test. CTest
`wonderbane_extension_movement_controls` passes. It exercises the actual policy
implementation using an actuator test double, not the client engine. Coverage:
opposing keys, normalized diagonals, camera basis, analog direction, explicit device
selection, disconnect/reconnect neutrality, camera-only route preservation, deliberate
manual takeover, delayed movement/acquisition/stop rejection, failed-stop exclusion,
scene changes, focus/chat inhibition, remapping, invalid settings, drag threshold,
invalid pick and lost capture, client isolation and camera integration at
20/30/60/144/240 Hz. This is not evidence for collision/server/native-stop behavior.

## Todos

- [ ] Active: wire the native stop executor and remaining steering/camera/picking
  bindings into the verified native-update dispatch and real input adapters.
- [x] Implement and test the shared input interpretation and ownership policy.
- [ ] Wire all three input methods, native adapter, real settings and feature controls.
- [ ] Wire travel/PvE dispatch and immutable ownership grants with the hardening owner.
- [ ] Validate production native adapters, both profiles, lifecycle and delayed dispatch.
- [ ] Build/install the complete combined package through the existing integration owner.
- [ ] Run focused connected acceptance for all input methods, camera, obstacles,
  real release/stop, chat/UI safety, multi-client isolation and navigation takeover.

Next item remains native actuation investigation. No feature-complete PR or
connected-acceptance claim is justified by this checkpoint.

## Passive trace checkpoint

The branch also contains an opt-in passive native-update observer and read-only
collector, with additive shared startup/rollback and both-profile build wiring.
See [the bounded investigation procedure](../investigations/native-movement-boundary.md).
The exact update digest and original slot matched the existing client's read-only
memory snapshot. No hook was installed in that client and no live actuation occurred.
Held-callback shutdown/startup-failure tests pass, as do exact-identity/coherent-reader
tests. The integration owner has accepted this source-level diagnostic workflow;
installation/early connected observation remains with the existing shared workflow.
This does not complete native bindings or any of the three requested controls.
Next todo remains native binding investigation and verification.

Review correction: trace start/stop/test admission now share one lifecycle mutex;
actual current-process creation time is verified at admission, and retained trace
generations cannot be restarted. Both DLL profiles build and all 22 native tests
pass in each profile. Shared optional-telemetry changes remain the integration
owner's reconciliation responsibility; this additive trace wiring does not alter them.
Native investigation also located a separate asynchronous path request that can
repopulate path work after local destination/state reset. That cancellation race
remains unresolved; no stop binding is enabled on the strength of an idle snapshot.


## Native input investigation checkpoint

The native text-entry predicate and registered keyboard/text callback slots have
been located through their registration and message-dispatch callers. An exact-client
read-only snapshot matched all three registrations. Keyboard arguments are virtual
key, modifiers, down/up and repeat; the native message pump also gates character
translation using the text-entry predicate. The passive schema-1 `ui_candidate`
field is now identified as item-drag state and must not be used as a chat gate.
See the investigation document for the verified scope and remaining UI requirements.

The integration owner reports the camera-policy correction included in combined
source `5f0cf3b`, with both combined profile policy tests passing. The owner also
reconciled trace initialization failure as nonfatal with immediate trace cleanup.
There is still no full-controls native generation transport, installed controls
package or connected acceptance. Full controls remain excluded from runtime sources.

Next active todo remains complete native stop and steering verification, especially
asynchronous path cancellation, scheduled-action exclusion and outgoing state order.

The developer-only actual-code tree probe now passes 64,256 native removals in each
profile. This verifies the generic primitive needed for actor-scoped scheduled-entry
removal, with payload preservation and tree invariants checked after each operation.
It does not yet establish complete native stop or enable controls. Next is native
key/allocator cleanup and the complete ordered stop composition.


The conformance probe now also executes native exact-identity lookup, two-word copy
and destruction, including unsigned boundary values and missing-key checks before
and after removal. Both profiles pass 64,256 complete sequences. Native allocator
cleanup and full stop composition remain unverified; no controls are enabled.

## Untracked native intent and continuation checkpoint

Takeover now calls the actuator stop even when this controls instance has not
recorded movement. Native click or combat-follow intent may already exist in that
case. All three manual methods are tested for stop-before-submission, failed-stop
exclusion, release without resumption and stale-owner rejection. Camera-only input
and ordinary clicks preserve the existing owner. These are policy-contract checks;
they do not yet prove the native combat-follow flags are retired by an adapter.

The actual-code probe executes the native empty-path continuation helper in 144
cases, including all 16 tested state values, null and allocated empty paths,
nonempty paths, multiple continuation values and repeated calls. Complete actor
and state byte snapshots remain unchanged except the documented continuation byte
when the path is empty. Both profiles pass this probe and the takeover policy test.

Static inspection identified persistent combat-close and temporary combat-follow
intent as another world-update movement writer. The integration owner requested
its retirement in the same complete native stop implementation, with later-update
regressions after takeover and release. The native UI toggle alone does not clear
both forms. That binding/composition remains unfinished, as do native pool cleanup,
ordered server notification and full controls/package wiring. Next active todo is
still the complete native stop and steering binding; no installed client changed.

Native allocator verification now also passes in both profiles: all 64,256 scheduled
node sequences execute native key destruction and 40-byte pool return, checking
size-class isolation, payload preservation and lock release. A forced-contention
case uses the allocator's verified Win32 imports against private globals. The
probe remains excluded from normal builds and packages. Next active todo remains
complete native stop composition and its native follow-update regression; source
verification alone does not enable or certify the connected feature.

## Current source inclusion audit

After fetching origin, feature source `d4f7207f7e5b923280478d750f95f1b8a96ef779`
is an ancestor of combined source
`3d74beb1aa7fbdf602ed2bce2468bc87e34ec9a4` on
`origin/codex/native-lifecycle-hardening`. The owner integrated later checkpoints
separately after PR #31 merged. That PR's historical head is `8536b2`, not the
current feature tip. No new runtime controls or package is implied by inclusion.

The feature worktree stays on `codex/native-movement-controls`; the normal shared
checkout remains clean on `main`. Source and tests are committed; only ignored
private investigation/build artifacts are retained under `artifacts/native-movement`.
The next implementation/review still targets the same hardening integration owner.
The active todo remains complete native stop composition, followed by all-input
runtime/settings/automation wiring and combined package/connected acceptance.

## Shared acceptance plan and path lifetime checkpoint

This feature follows the integration owner's [shared acceptance plan](https://github.com/best-coder-open-now-near-me/shadowbane-lab/blob/758e6f8242cc25e0e749bde0d679f2fc03dd9cad/docs/combined-testing-acceptance.md).
Complete production controls and interaction/transition checks precede the single
coordinated gameplay pass. Independent integration review follows completion.
The owner retains combined packaging, known-good runtime restoration and candidate
identity records. No unfinished-feature demo, new architecture task, additional
navigation research or paid compute is part of this lane.

The developer-only actual-code probe now also executes native whole-path erase,
waypoint-reference destruction, actor retain/release and reference counting. Both
profiles pass null/empty paths and populated paths through 1,024 elements, including
shared references, native null/sentinel cases, repeated clear and an actor retained
across path destruction. Native reference-count imports use real Win32 atomics;
probe-owned virtual objects record finalization. This verifies the lifetime ABI
and primitive effects, not real game-object destructors or a connected stop.

Executed: both profile probe builds and complete updated conformance runs.
Not performed: full native stop/follow-update integration, actual input adapters,
installed controls package, combined gameplay acceptance and independent completed
integration review. These are outstanding implementation/validation, not passing
checks or environmental skips. Next active todo remains complete ordered native
stop composition and subsequent native steering/runtime wiring.

## Production native stop composition checkpoint

`movement_native_stop.h/.cpp` now implements the real native stop executor.
`movement_native_image.h/.cpp` authenticates the reviewed executable and compares
its entire loaded code section after normalizing authenticated PE relocations.
The executor binds the native routines, requires the exact client window thread and
an admitted native-update phase, retains the captured actor, and rechecks the single
controls authority plus actor/world/window identity at callback boundaries.

Stop retires both native follow intents, clears the actor's native action queue,
removes its exact scheduled entry with native destruction/pool return, cancels the
pending path request, destroys path elements, clears continuation, and invokes the
native destination reset. Only native moving state transitions to idle; other
states remain unchanged. The state message is built during that transition and
its owned reference is either consumed once by native send or released without
sending after invalidation. Missing messages and uncertain native exceptions fail
closed; an uncertain send is never retried. Native cancellation fields are written
only for the verified follow and pending-request intent, never coordinates, speed,
restrictions or simulated input.

The policy now rejects reentrant command admission during native callbacks and
honors deferred shutdown before a new movement submission. The same policy remains
the sole ownership authority, including retained failed-stop grants. No second
movement writer or command control plane was added.

Both DLL profiles build with these sources. All 23 native tests passed in each
profile; targeted stop/policy tests were rerun after callback-race corrections.
The new tests execute the production composition with controlled native-call doubles
and process-local actor/queue data. They cover all three policy input methods,
later follow/world-update attempts after takeover/release, restricted states,
wrong-thread/outside-update rejection, stale owners, missing outgoing messages,
native exceptions, callback reentry, shutdown and scene changes during state/send.
These are composition tests, not execution of the unmodified native world update or
proof of connected server behavior. Existing actual-code probes provide separate
ABI/container/lifetime evidence.

The stop executor is compiled but not called by an installed runtime adapter yet.
No movement capability is advertised or client package changed. The active todo
has therefore moved from constructing stop composition to real native-update,
movement/camera/picking and input adapter wiring; complete native behavior and
combined connected acceptance remain outstanding under the shared plan.

Integration review corrections now reject missing-connection completion for an
outgoing stop message and pin the current-player pending request once per stop
transaction. Callback-created replacement requests are left untouched; actor/world
changes abort remaining cleanup and packet submission. The investigation document
records the native producer/consumer guards and distinguishes gameplay callback
boundaries from sealed container/pool operations. Both profiles build and pass the
focused production-composition regressions, including absent requests and repeated
manual stops with different request objects. Runtime adapters and activation remain
the active todo; no connected acceptance or package change is claimed.

The remaining post-call guard gap is closed: stop now uses the captured-request
check consistently before subsequent destination, waypoint and state mutations.
New production-composition regressions first reproduced all three gaps, then passed
in both profiles after correction. They assert exact mutation counts, unchanged
replacement requests, balanced old references and no new movement/send. Retain and
position boundary fault injection is defensive coverage, not a claim that their
sealed native implementations call gameplay callbacks. Both DLL profiles build;
runtime adapters and activation remain the next active work.


The shared native backend now includes the verified native camera orientation
setter. Controller radians pass through the production policy and this executor
under the same client-thread/update-phase checks; the current route grant is
preserved. Native pitch limits and camera distance are preserved, and controller
input does not accumulate mouse-event inertia. Camera failures remain isolated
from the movement stop path. Both DLL profiles and focused policy/native backend
tests pass, including several input update rates. Native-call doubles certify the
composition, not the real native camera update or connected result.

Active todo remains complete native-update, steering, terrain-picking and input
runtime wiring. Settings/automation transport, combined package verification and
connected acceptance remain afterward. This camera checkpoint adds no runtime
activation, installed package, independent deployment or feature-complete claim.
