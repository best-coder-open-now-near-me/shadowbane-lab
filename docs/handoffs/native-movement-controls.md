# Unified native movement controls

Feature branch: `codex/native-movement-controls`.
Worktree: `.worktrees/native-movement-controls`.
Assigned starting source: `0c807ee774859cc3f17f9ebc04d3f0a900bd0428`.
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
