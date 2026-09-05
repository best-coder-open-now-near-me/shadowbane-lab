# Unified native movement controls

Feature branch: `codex/native-movement-controls`.
Worktree: `.worktrees/native-movement-controls`.
Assigned starting source: `0c807ee774859cc3f17f9ebc04d3f0a900bd0428`.
Draft PR: https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/31
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

- [ ] Active: finish native steering, queue cancellation, server notification,
  camera, picking, UI ownership and owning-thread binding investigation/verification.
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
