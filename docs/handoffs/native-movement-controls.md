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

The native ownership/input policy, steering, stop, camera, terrain-pick, lifetime,
UI ownership, Windows/XInput capture and native-update consumer are implemented.
The consumer is registered after successful shared extension startup. Initial
preferences are disabled; explicitly saved preferences apply on later starts. Settings UI/persistence and both entry points are implemented; automation
transport is still being connected. No action-channel movement capability is advertised, no installed
package has changed, and no connected acceptance is claimed. This checkpoint is
not the complete requested feature or an acceptance package.

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

- [x] Implement and test the shared input interpretation and ownership policy.
- [x] Bind native stop, steering, camera and picking with native lifetime guards.
- [x] Bind native UI/text/modal ownership and shared pointer-coordinate conversion.
- [x] Compose Windows/XInput input capture and the native-update consumer.
- [x] Wire real settings, remapping, controller configuration and feature controls.
- [ ] Active: wire travel/PvE dispatch and immutable ownership grants with the hardening owner.
- [ ] Validate production native adapters, both profiles, lifecycle and delayed dispatch.
- [ ] Build/install the complete combined package through the existing integration owner.
- [ ] Run focused connected acceptance for all input methods, camera, obstacles,
  real release/stop, chat/UI safety, multi-client isolation and navigation takeover.

Next item is immutable automation command transport and the typed producer session. Connected engine behavior still
requires the complete combined package and coordinated acceptance. Historical
checkpoint notes below describe the progression, not additional active todos.

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


Native update hook consolidation is implemented in the existing boundary module.
Controls and optional trace now share one verified slot, immutable original call-
through and serialized lifecycle. Either consumer may start first. Retiring trace
cannot remove active controls, and retiring controls cannot remove active trace.
The final consumer restores only its own slot. Admitted callbacks and their pinned
state/original survive retirement; replacement slot owners are preserved. Runtime
must request its own retirement only after its owning-thread native stop completes.
A consumer cannot replace its callback or restart a retired generation.

Both complete DLL profiles build and all ten focused movement/backend/hook tests
pass per profile with zero skips. New lifecycle cases cover both startup orders,
held controls callbacks, controls partial-install failure and intervening slot
replacement; existing trace rollback/concurrent-stop cases continue passing.
This checkpoint supplies the shared callback boundary, not an activated input
consumer. Active work remains steering, picking and input runtime composition,
then settings/grant transport and complete-candidate package/connected acceptance.
On activation, native camera changes must feed the existing fresh camera
observation before sky/world rendering, as requested by the integration owner;
no separate camera authority or cached matrix approximation is introduced here.


Native directional steering now binds the actual target constructor and Move
wrapper in the shared backend. It preserves native collision/restriction/deferred
admission, uses the native look-ahead, coalesces unchanged input during pending
native work, and publishes native messages on start/time-based refresh. Release
uses the shared cancellation/state-message path. A reproduced scene-transition
cleanup bug is fixed: failed-move stop cannot capture a replacement actor under
its obsolete grant. Both complete DLL profiles and focused policy/backend tests
pass, including several update rates and pending/deferred work.

The backend takes parent-local direction; native ray conversion evidence is now
recorded explicitly in the investigation. Active work remains camera-basis,
terrain-pick and Windows/XInput/UI composition into the shared native-update
consumer, followed by settings, automation grant transport and complete installed
candidate verification. Directional binding tests use native-call doubles; native
solver, connected steering cadence and all-three-input acceptance remain open.
This checkpoint does not advertise or install partial controls.


Terrain picking now binds native screen unprojection, ray construction, world
collision and the native parent-local hit conversion. The full 3D ray is retained;
there is no flat-plane fallback. Native actor/parent hit references live only for
the admitted update and are released on replacement pick or owning-thread
EndUpdate. Native misses return no point. Scene invalidation prevents further hit
conversion while old retained references can still be released. Foreign threads
cannot pick or end the owning phase. Both DLL profiles and policy/backend tests
pass; a zero-height hidden test window was corrected to explicit client bounds.
The tests use controlled native-call doubles, not real terrain collision evidence.

Active work remains completing drag destination actuation and camera basis/input/UI
composition into the native-update consumer, then settings, automation grant
transport and complete package/connected acceptance. The pick is not activated or
advertised independently of the complete controls feature.


Drag destination actuation now consumes only the current update's validated native
pick. It applies the native hit to the destination marker, retains the marker and
native parent in the ground target, and calls the native movement wrapper with
collision/restriction handling. It does not relocate the player or simulate a
click. Unchanged active movement and pending native solve/deferred work are
coalesced; the latest pointer pick is applied after native work completes. Release
uses the same cancellation/idle-message path as directional movement. All actor,
marker, ground-target and ray reference lifetimes are explicit.

A new regression reproduced a parent-frame change on the same actor during marker
application. Every captured native transaction now checks that frame as well as
actor/world/window/scene. Runtime Input.scene MUST change on native parent-frame
transitions; otherwise stale local coordinates cannot be re-armed. Tests also
cover expired picks, marker-induced scene replacement, held drag/release, pending
path cancellation and obsolete-stop retirement after a new frame identity. Both
complete DLL profiles and focused policy/backend tests pass with zero skips.
Native-call doubles do not certify the native terrain solver or server result.

Active work now moves to camera basis and Windows/XInput/UI consumer composition,
with real settings and manager grant transport next, then complete-candidate
package and connected acceptance. No controls capability is advertised yet.


Camera-relative movement basis now uses the native current view's center/right
unprojection rays and the same locked native inverse-parent conversion used for
picking. It projects/normalizes those results in the actor's native X/Z frame and
preserves the native screen-right sign. This avoids guessing camera yaw conventions,
orbit offsets or cached matrices. Temporary conversion-ray references are released
immediately; invalidation during their release also rejects the axes. Degenerate
views return unavailable axes rather than a world-axis fallback. The current view
means the view already presented to the user; controller camera mutation is still
followed by the game's original update before subsequent rendering observations.

Both DLL profiles and focused policy/backend tests pass for transformed/translated
parent-frame composition, degenerate views and frame changes during conversion and
reference cleanup. These native-call-double tests do not certify rendered native
camera output. Active next work is Windows/XInput/UI input consumer wiring and
settings/manager grant transport, then complete candidate/package acceptance.


Native lifetime tracking now observes the sealed reference-finalizer ABI for actor
and parent and the exact reviewed world deallocation import. It invalidates the
current epoch before original destruction and checks captured watch generation.
Same-address reuse gets a fresh epoch; same allocation cannot rearm while its
original destructor is held. Callback completion never invalidates a replacement
watch. Unknown reference interfaces, foreign slot replacements and partial install
fail closed, preserving original call-through and foreign ownership. The observer
has terminal retirement only; ordinary settings toggles keep it registered.

Production native Bind now requires BeginUpdate(receiver, observed_scene), with
Input.scene equal to observed_scene.epoch. The previous unobserved overload is not
an activation path after production Bind. Every actuator scene check also verifies
the lifetime epoch, so a destruction callback invalidates a captured stop before
the next input tick. Runtime must StartNativeMovementLifetime on the owning client
thread, Observe each admitted native update, finish its owning-thread stop before
terminal retirement, and retain callback state for process lifetime. Do not use
renderer frame/context counters for this identity.

Both DLL profiles and 11 policy/backend/lifetime tests pass with zero skips. New
lifetime tests cover actor/parent/world ABA, watched and ordinary free, held actor
and world callbacks, watch replacement, partial-install rollback with dispatched
callback, foreign finalizer/free slots, unsupported image/interface and production
actuator rejection of old stops before another input tick. A test-only symbol
collision was corrected before rebuilding and rerunning the final test binaries.
New production source: movement_lifetime.cpp in both profiles; native_stop tests
also link it and import_hook.cpp. Integration owner reconciles the package builder.

Active next: complete Windows/XInput/native UI consumer composition; then real
settings and automation grant transport, complete candidate/package checks and
coordinated connected acceptance. No partial controls capability is advertised or
installed. Source destination remains codex/native-lifecycle-hardening, then its
reviewed combined integration; PR31 is the earlier merged checkpoint only.


The integration review identified a mid-update hook replacement gap. Lifetime
Current now validates the watched actor/parent interface slots and world free
slot at each actuator boundary, immediately latching rejection and advancing the
epoch on mismatch. Restoring a slot cannot revive that epoch. Cleanup remains on
the owning Observe/Retire path and never overwrites a foreign slot. Immutable
slot-record publication is atomic for callbacks consulting Current concurrently.
Both full DLL profiles and 13 focused tests pass with zero skips, including
replacement after BeginUpdate and before Execute for both finalizer and free.

The separate first/replacement-watch arming interval remains under investigation:
existing held-watched callbacks alone do not prove that destruction between the
initial capture and watch publication is observed. This is an explicit remaining
activation gate, not a claim that rendering or input-thread ownership proves
native destruction confinement. Active next is closing that specific interval,
then the Windows/XInput/UI consumer, settings/transport and combined acceptance.


The watch arming correction now prebinds the bounded exact 34 ArcObj-family
finalizer slots before any scene observation. The complete binding list was
validated against the reviewed executable's RTTI/reference tables. New watch
capture uses an interference fence and in-flight callback accounting; no reference
slot is installed lazily from the captured object. It rejects destruction already
in flight or overlapping capture/publication. Entry after the final publication
check invalidates a newly published matching watch before original destruction.
Existing exact notices still permit disjoint replacement during a held original;
late completion does not alter the replacement's epoch. Ordinary unrelated frees
are not scene authority. Multi-slot rollback preserves foreign slots and dispatched
originals, with no lock across original call-through.

Both full DLL profiles and 34 focused policy/backend/lifetime tests pass, zero
skips. The new header movement_lifetime_bindings.h accompanies the already-wired
production source; no additional cpp membership is required. This closes the
implemented arming interval subject to integration review. Runtime activation
remains pending the complete feature. Active next is the Windows/XInput/native UI
consumer, then real settings and automation grant transport, full package checks
and coordinated connected acceptance. No installed package was replaced here.


Native UI gating now binds the game's text predicate, focused control and top-level
HUD hit-test. It respects focused text kinds, modal update ownership, native input
inhibit bits and inventory drag payload. Pointer hits are native UI/map hits;
keyboard gating is separate, and the existing native camera gesture is reported
without acquiring movement ownership. Queries run only on the exact window's
owning thread, reject reentry and recheck scene/gates after native callbacks.
Foreign text bindings and malformed geometry are unavailable; native exceptions
latch failure. This is not yet an active input interception feature.

The native rectangle getter and mouse-event scaling were verified. UI hit testing,
production terrain picking and camera-basis unprojection now share that coordinate
conversion, including resized/logical UI extents. No cursor movement or plane
picking is used. Native key event submission drains synchronously before returning
to the keyboard callback, so the existing pre-update consumer can inspect current
text/UI state; no shared update phase change or blanket pause on unrelated keys
is needed.

Both complete DLL profiles and 35 focused tests each pass with zero skips. New
production source movement_native_ui.cpp must be present in both actual builder
profiles; native backend/lifetime tests also link it. UI tests exercise native-call
doubles for text/modal/inventory/map ownership, camera separation, coordinates,
foreign thread/reentry/scene changes, foreign text slots and native faults. Active
next remains Windows/XInput consumer composition, then settings/grant transport
and complete package/connected acceptance through the integration owner.

## Stop-only window-thread admission checkpoint

Added an explicit exact-HWND, observed-lifetime emergency phase to the native
executor. It admits native cancellation and rejects picking, movement and camera
mutation. The ownership policy accepts only the captured current grant, retires
it immediately, and disarms held inputs; duplicate or delayed old stops cannot
cancel a new owner. Destruction invalidates this phase without recapturing a
replacement actor. Tests exercise actual production cancellation under the
stop-only flag, including pending path retirement and native stopped-state send.

Full-profile policy/backend/lifetime tests: 34 passed, zero skips. This is phase
and policy coverage; the Windows event consumer and its nested callback handling
are still the active todo. It does not yet certify connected focus-loss behavior.

## Windows input capture checkpoint

`movement_windows_input.cpp` now provides the native keyboard callback and Win32
subclass/capture adapter plus explicit-slot XInput sampling. It binds the HWND
stored by the native input manager's window object, checks PID/thread/exact
foreground, retains original key down/repeat/up ownership across UI changes and
remapping, and retains original callback records after retirement. Right mouse is
reserved for the native camera gesture and is rejected as a drag binding.
Eligible mouse downs are held until click/drag classification; ordinary clicks
forward their original pair once, qualified drags never become click actuation.
Actual press coordinates survive a delayed first update. The runtime must verify
the press terrain pick before setting the policy's `press_origin.ground_valid`.
Camera-gesture blocking preserves actual stick neutral state.

The adapter reports safety synchronously from focus/capture/device/window events;
it does not itself actuate movement. Six production capture tests use real Windows
subclass/capture/teardown, with controlled native UI/controller/key sources. They
cover pairing, UI/native camera preservation, loss, explicit slot/analog endpoints,
registration rollback and foreign hook/subclass ownership. Both complete profiles
compile; diagnostics runs all 41 focused tests successfully (zero skips), full
runs the same prior 35 plus all six capture tests successfully. The first test
compile needed the SDK's XInput noexcept signature; only rebuilt binaries count.

Integration-owner producer repair `d26ddab` is consumed at `bea6b0d`; seven real
Windows producer tests pass. Its handoff conflict preserves the full incoming
integration history. The owner retains shared manager composition and package
membership reconciliation. Add `movement_windows_input.cpp` exactly once to each
profile's package membership checks and link `comctl32` (CMake is already wired).

Active next todo: native-update consumer composition, including nested safety
interruption before another native move. Then settings, immutable automation
grants, combined package validation and coordinated connected acceptance. Capture
is not yet registered by extension startup and this is not a completed feature.


## Owning native consumer checkpoint

`movement_runtime.cpp` composes the native lifetime observer, capture adapter,
policy and executor before the original native update. It validates camera basis
before press/current terrain picks, preserving the final native pick for drag
actuation. A bounded immutable safety queue captures HWND, scene and grant.
Nested safety vetoes remaining work before publishing a new owner or issuing a
later move; already submitted movement is stopped before the consumer returns.
Normal focus loss uses stop-only window admission without requiring another
native update. Destroyed/retired scenes lose authority without recapturing actors.
Settings application has an exact process/window/grant/revision ticket; stale
configuration cannot stop a newly accepted owner. Ordinary disable retains the
registered consumer. Unsupported startup publishes unavailable and retires it.

The consumer now registers after successful shared extension startup. Controls
remain disabled until explicit settings; the panel/persistence and automation
wire integration are next. This source does not change the installed client.
The integration owner must add `movement_runtime.cpp` once in each actual package
profile and reconcile the additive extension startup call with shared rollback.

Thirteen consumer tests reuse production native backend call composition and real
HWND capture, with controlled native callees/lifetime/input sources. All three
inputs take over an actual native move held by an automation grant, then reject
its delayed commands/stops. Coverage includes release, no automatic route resume,
chat/held-key rearm, focus loss without updates, stale scene/settings tickets,
destruction and nested stop/camera/move callbacks. These are developer-controlled
composition tests, not live engine/server acceptance. Together with seven capture
cases and the prior 35 policy/backend/UI/lifetime cases, the affected suites pass
55 cases in each complete native profile, zero skips.

The repeated-Bind/XInput review finding is addressed by one-shot admission before
image verification/loading. Wrong/redundant/reentrant calls do not load modules;
one process-pinned XInput handle is retained. Unsupported and already-bound
regression cases verify rejection before repeated image/load admission. This is
source API/consumer coverage; complete settings, command transport, shared review,
exact-source installed package and coordinated gameplay acceptance remain todos.


## Native settings and Graphics Lab entry checkpoint

`movement_settings.cpp` implements a native per-client panel, real remapping and
controller/drag controls, and versioned validated user preferences. The panel is
reachable through paired Ctrl+Alt+F10 (text/modal gated) and Graphics Lab's selected
client button. The latter sends only a settings-open notification; the native
receiver checks the exact HWND chain and full process creation time. It cannot be
used to apply settings or submit movement. Native configuration still runs under
an immutable process/window/grant/revision ticket and stop-only phase. Controller
API availability is explicit. See [user behavior and acceptance procedure](../native-movement-controls.md).

Preferences are atomically stored as one versioned registry value and loaded at
native runtime startup. The restart regression writes an isolated test key, starts
a new hidden test process to read it through the production decoder, then removes
that exact key. The panel test uses real Win32 controls and checks layout bounds,
validation, stale-ticket rejection and close/reopen behavior; visibility/focus and
its ordinary save callback are isolated from the user's desktop/preferences.
Eight capture/settings-entry cases and thirteen consumer cases plus the panel test
pass on both profiles. The prior 35 native policy/backend/UI/lifetime tests remain
applicable. Python selected-client routing and existing Graphics Lab control tests
pass 37 cases, zero skips; Ruff passes. Initial compile-only fixture/string fixes
were corrected before the passing rebuilt tests.

Buffered gestures are now suspended on scene/UI/focus transitions so an old click
cannot leak into a replacement scene. Fresh native key downs repair pairing when
the prior release arrived outside the game window. The integration owner should
add `movement_settings.cpp` once to each package profile and retain the added
advapi32/gdi32 system links. No installed package or connected acceptance changed.
Next active todo is schema2 immutable acquire/move/stop transport and typed session,
then shared manager composition, complete-candidate review and installed validation.

## Schema 2 wire checkpoint

The command extension is 576 bytes (768 with the existing action prefix), receipt
384 bytes (512 total), and consistently published status 512 bytes. The expected
grant/token and requested automation token are distinct, with full 95-byte ASCII
identities, exact HWND, host PID/creation/lease generation and canonical UUID.
Receipts retain their originating host lease and request UUID. Shared synthetic
hex fixtures verify native/Python bytes in both directions; native settings now
reuse this codec, preserving the existing 52-byte preferences format.

Both complete DLL profiles and native wire/settings tests pass; 10 Python wire
and settings tests pass (15 malformed-input subtests), Ruff passes. This is a
codec checkpoint: active action-channel schema remains 1 until its consumer and
producer switch together. No new dispatch capability or installed-package claim.
Active todo remains schema-2 queue/status/session integration, then combined
source/package review and coordinated connected acceptance.

## Schema 2 owning-thread transport checkpoint

Active action schema now 2, command768/result512/status512, with legacy verbs and
payload1 preserved and mixed geometry rejected. Python lease claim/renew/close
methods remain unchanged. The worker captures PID/creation/lease generation and a
retained process handle; the owning update rechecks lifetime/deadline/window/scene
and full grant after manual Tick. Acquisition UUID journal returns the original
receipt, never a new generation after an ambiguous timeout. Native callbacks check
current lease admission; old lease loss cancels only its captured grant. Result
publication is single-worker and retains original sequence/ID/UUID/lease; full
result-ring backpressure keeps the pending receipt. Status uses odd/even sequence
publication and a read-only Python mapping with no lease mutation.

Channel stop now retains worker/events/storage after timeout. Confirmed worker exit
closes its handles, while admitted command/automation leases retain mapped backing
until they return. Backing acceptance is retired immediately. Named mapping collision
prevents replacement while old references remain. Production-path held-worker tests
exercise timeout, repeat start/stop rejection, release and final cleanup.

`NativeMovementSession(identity, window).snapshot()` is read-only;
`acquire(snapshot, worker_id, operation_id, canonical_uuid)` returns immutable
`NativeMovementGrant`; `move(grant, XYZ, uuid)`, `stop(grant, uuid)` and
`configure(snapshot, settings, uuid)` retain correlation. Configure requires an
already-owned producer lease. Ambiguous acquisition/stop retries must retain their
original UUID and immutable request; pending cancellation excludes further move.
Closed sessions never silently reopen. Manager operation composition remains with
the hardening owner.

Both DLL profiles +16 event-channel/runtime/held-channel cases pass0skips. Real
Python-to-native IPC through the production runtime fixture proves acquire/retry/
stop completion while Python holds its producer mutex. Read-only status tests prove
mixed schema/geometry and odd publication reject without changing lease fields.
21 Python codec/producer/IPC tests plus15 malformed subtests passed in diagnostics,
then the added second status test passed; Ruff passes.

This is a transport checkpoint, not complete feature acceptance: arbitrary native
world-destination submission is explicitly unavailable pending its verified adapter
and accepted navigation coordinate wiring. Manual controls remain operational.
Active next todo is that adapter plus typed manager composition, then combined
source/package review, installed package and coordinated connected acceptance.

## Complete native destination and operation adapter checkpoint

Native world destinations now use the verified terrain-height/downward-world-ray
path and normal native collision/movement submission. The previous explicit
unavailable destination branch is removed. `movement_dispatcher.NativeMovementTravelDispatcher`
implements the existing TravelDecisionDispatcher with the exact operation grant;
accepted bounded destinations and LT/X,LG/-Z mapping are preserved. It exposes
latched `interruption_reason` and read-only `is_set()` for the integration owner's
PvE/operation stop-signal composition; no failed route automatically reacquires.

PAUSE verb7/session.pause cancels native movement while retaining the immutable
operation grant for the next PvE approach. STOP remains terminal release. Session
renew(grant) uses a synchronized transport renewal, verifies the observed grant,
and rejects expired heartbeat or closed transport rather than claiming/reviving.
The integration owner supplies operation maintenance every250ms independently of
its slower dashboard heartbeat and owns both CLI dispatcher injection points.

Manual enabled no longer gates automation readiness. Disabled manual inputs stay
unconsumed; native automation still observes focus/UI/lifetime/lease rules. Enabling
manual input preserves active automation and requires neutral rearm before takeover.
Shutdown has a distinct terminal latch. Settings revisions retain stale protection.
Acquisition receipts are bounded at128 entries. Eviction advances a monotonic
expected-generation floor; an evicted request returns stale without native mutation.
Recent ambiguous retries return the original receipt. In the conservative edge
case of many rejected requests at one generation, a fresh observed generation is
required before another acquisition can succeed; no silent reacquisition is allowed.

Both DLL profiles and18 affected native tests pass0skips. Production runtime IPC
now exercises acquire/retry/move/pause/renew/move/terminalstop with manual controls
disabled. Native tests cover terrain miss, changed target during a pending solve,
world stop, pause/resume, manual enable/rearm/takeover, shutdown and150 successive
acquisitions with bounded receipts/latest retry.25 focused Python tests plus15
malformed subtests pass0skips; Ruff passes.

Next active todo: integrate the owner's CLI/operation composition with this adapter,
review complete combined source and package, then installed exact-package validation
and coordinated connected acceptance. No installed package/connected claim yet.
